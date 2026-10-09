// Independent array refresh; reuse Ramulator priority, precharge and timing.
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/dram/dram_spec.h"

namespace Ramulator {
class W2WRWDLRefresh : public IRefreshManager, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IRefreshManager, W2WRWDLRefresh, "W2WRWDLRefresh")
  ControllerBase* ctrl;
  int interval, command;
 public:
  void init() override {
    ctrl = cast_parent<ControllerBase>();
    const auto& spec = *ctrl->m_device.m_spec;
    if (spec.standard_name != "W2WRWDL")
      throw std::runtime_error("RWDL refresh requires W2WRWDL");
    interval = spec.get_timing_value("nREFI");
    command = spec.get_command_id("REFab");
  }
  void tick() override {
    if (ctrl->m_clk % interval) return;
    AddrVec_t address{ctrl->m_channel_id, 0, -1, -1, -1};
    Request req(address, Request::Cmd, command);
    if (!ctrl->priority_send(req))
      throw std::runtime_error("RWDL refresh priority slot overflow");
  }
};
}  // namespace Ramulator
