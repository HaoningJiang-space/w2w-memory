// Thin incremental adapter; all command scheduling and timing remain upstream.
#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/string.h>
#include <memory>
#include <set>
#include <stdexcept>
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"
#include "ramulator/python/binding_utils.h"

class IncrementalMemory {
  std::unique_ptr<IFrontEnd> frontend;
  std::unique_ptr<IMemorySystem> memory;
  std::set<uint64_t> pending;
  std::vector<std::pair<uint64_t, uint64_t>> completed;
  uint64_t cycle = 0;
  int channels = 0;
  int transaction_bytes = 0;
  uint64_t array_atoms = 1u << 20;
  bool closed = false;
 public:
  explicit IncrementalMemory(nb::dict config, uint64_t atom_limit = 1u << 20) : array_atoms(atom_limit) {
    if (array_atoms != (1u << 20) && array_atoms != (1u << 22))
      throw std::runtime_error("Unsupported explicitly declared RWDL array capacity");
    channels = nb::len(nb::cast<nb::list>(
        nb::cast<nb::dict>(config["memory_system"])["controllers"]));
    auto cfg = py_to_confignode(config);
    frontend.reset(Factory::create_frontend(cfg));
    memory.reset(Factory::create_memory_system(cfg));
    frontend->connect_memory_system(memory.get());
    memory->connect_frontend(frontend.get());
    transaction_bytes = memory->get_tx_bytes();
    if (transaction_bytes != 32 && transaction_bytes != 16)
      throw std::runtime_error("Bridge requires an exact 32- or 16-byte DRAM transaction");
  }
  bool send(uint64_t id, int bank, uint64_t word_address) {
    if (closed || pending.count(id)) throw std::runtime_error("Closed backend or duplicate ID");
    AddrVec_t address;
    if (transaction_bytes == 32) {
      // HBM2_2Gb: one 32-bank channel/M; 32 bursts/row.
      if (bank < 0 || bank >= channels * 32 || word_address >= (1u << 19))
        throw std::runtime_error("Address outside HBM2 reference bank");
      const int local = bank % 32;
      address = {bank / 32, local / 16, 0, (local % 16) / 4,
                 local % 4, int(word_address / 32), int((word_address % 32) * 4)};
    } else {
      // One shared physical array/controller, 64 sixteen-byte columns/row.
      if (bank < 0 || bank >= channels || word_address >= array_atoms)
        throw std::runtime_error("Address outside RWDL candidate array");
      address = {bank, 0, 0, int(word_address / 64), int(word_address % 64)};
    }
    Request req(address, Request::Type::Read);
    req.addr = (uint64_t(bank) * (transaction_bytes == 32 ? (1u << 19) : array_atoms)
                + word_address) * transaction_bytes;
    req.source_id = 0;
    req.size_bytes = transaction_bytes;
    req.callback = [this, id](Request&) {
      if (!pending.erase(id)) throw std::runtime_error("Unknown/duplicate completion");
      completed.emplace_back(id, cycle);
    };
    pending.insert(id);
    if (!memory->send(req)) { pending.erase(id); return false; }
    return true;
  }
  std::vector<std::pair<uint64_t, uint64_t>> advance(uint64_t target) {
    if (closed || target < cycle) throw std::runtime_error("Invalid DRAM clock advance");
    while (cycle < target) { ++cycle; memory->tick(); }
    return std::exchange(completed, {});
  }
  std::pair<uint64_t,std::vector<std::pair<uint64_t,uint64_t>>> advance_until_event(uint64_t target) {
    if (closed || target < cycle || !completed.empty())
      throw std::runtime_error("Invalid first-callback DRAM advance");
    while (cycle < target) {
      ++cycle; memory->tick();
      if (!completed.empty()) break;
    }
    return {cycle,std::exchange(completed,{})};
  }
  nb::dict stats() {
    memory->update_stats_recursive();
    return nb::cast<nb::dict>(confignode_to_py(memory->collect_stats()));
  }
  size_t outstanding() const { return pending.size(); }
  void close() {
    if (closed) return;
    frontend->finalize(); memory->finalize(); closed = true;
  }
  ~IncrementalMemory() { try { close(); } catch (...) {} }
};

#include "memory_island.hpp"

NB_MODULE(_w2w_ramulator, m) {
  m.attr("upstream_commit") = W2W_RAMULATOR_COMMIT;
  nb::class_<IncrementalMemory>(m, "IncrementalMemory")
    .def(nb::init<nb::dict,uint64_t>(), nb::arg("config"), nb::arg("array_atoms") = (1u << 20))
    .def("send", &IncrementalMemory::send)
    .def("advance", &IncrementalMemory::advance)
    .def("advance_until_event", &IncrementalMemory::advance_until_event)
    .def("stats", &IncrementalMemory::stats)
    .def("outstanding", &IncrementalMemory::outstanding)
    .def("close", &IncrementalMemory::close);
  nb::class_<MemoryServiceIsland>(m,"MemoryServiceIsland")
    .def(nb::init<IncrementalMemory&,nb::dict>(),nb::keep_alive<1,2>())
    .def("submit",&MemoryServiceIsland::submit)
    .def("advance",&MemoryServiceIsland::advance,nb::arg("target_ps"),nb::arg("until_observable")=false)
    .def("ledger",&MemoryServiceIsland::ledger);
}
