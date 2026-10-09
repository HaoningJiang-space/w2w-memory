"""Configuration writer extracted from the pinned RapidChiplet and wafer runtime.

Keeps the original configuration semantics; no geometry or scheduling imports.
"""
import copy
import math
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def working_directory(directory):
    previous = Path.cwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(previous)


def export_booksim_config(inputs, run_identifier, load):
    # Extract inputs
    booksim_config = inputs["booksim_config"]
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    routing_table_type = inputs["routing_table"]["type"]
    # Prepare the BookSim configuration file for export
    bsc = copy.deepcopy(booksim_config)
    # Remove parameters that are used by RapidChiplet and not by BookSim
    del bsc["time_limit"]
    del bsc["precision"]
    del bsc["saturation_factor"]
    # Determine router latency used in BookSim. This can be set manually in the BookSim configuration file
    # If not specified, the average latency of chiplet-internal-routers and interposer-routers is used
    if "router_latency" in bsc:
        router_latency = bsc["router_latency"]
        del bsc["router_latency"]
    else:
        router_latencies = [chiplets[x["name"]]["router_latency"] for x in placement["chiplets"]]
        router_latency = int(math.ceil(sum(router_latencies) / len(router_latencies)))
        if len(set(router_latencies)) > 1:    
            print("WARNING: In BookSim simulations, all routers (on-chip or on-interposer) have the same latency. " + \
              "In your configuration, these latencies are not identical. RapidChiplet will use the average " + \
              "latency which is %d cycles. To manually set the router-latency, " % router_latency + \
              "specify the parameter \"router_latency\" in the booksim-config input file.")
    # 1) Simulation parameters
    bsc["topology"] = "anynet" 
    bsc["network_file"] = "rapidchiplet/booksim2/src/rc_topologies/%s.anynet" % run_identifier          # NOTE: path relative to parent directory
    bsc["injection_rate"] = 1.0 if bsc["mode"] == "trace" else load
    # 3) Parameters related to the timing/latencies:
    bsc["credit_delay "] = 0
    bsc["routing_delay "] = 0
    bsc["vc_alloc_delay "] = 1
    bsc["sw_alloc_delay "] = 1
    bsc["st_final_delay "] = max(1, router_latency - 2)
    bsc["input_speedup "] = 1
    bsc["output_speedup "] = 1
    bsc["internal_speedup "] = (1.0 if router_latency >= 3 else (3.0 / router_latency))
    # 4) More simulation parameters
    bsc["use_read_write "] = 0
    bsc["routing_function "] = "modular_routing"
    bsc["path_for_stats"] = "rapidchiplet/booksim2/src/rc_stats/%s_%f.csv" % (run_identifier, load)     # NOTE: path relative to parent directory
    bsc["path_for_xy_info"] = "rapidchiplet/booksim2/src/rc_xy_info/%s.csv" % (run_identifier)          # NOTE: path relative to parent directory
    # Convert configuration file to correct format
    config_lines = [(key + " = " + str(bsc[key]) + ";") for key in bsc]
    # Store the file
    save_path = "rapidchiplet/booksim2/src/rc_configs/%s.conf" % run_identifier                         #NOTE: path relative to parent directory
    with open(save_path, "w") as file:
        for line in config_lines:
            file.write(line + "\n")

def prepare_config(inputs, directory, trace_path, seed, timeout=120, skip_idle=True):
    directory = Path(directory).resolve()
    config = inputs["booksim_config"].copy()
    config.pop("repetitions", None)  # author Python orchestration metadata
    config.update(seed=seed, trace_file=str(Path(trace_path).resolve()),
                  trace_report=str(directory / "trace_report.json"),
                  trace_skip_idle=int(skip_idle), mode="trace", ignore_cycles=0,
                  warmup_periods=0, sim_count=1, sample_period=1000000000,
                  trace_time_out=timeout, time_limit=timeout)
    modified = dict(inputs, booksim_config=config)
    with working_directory(directory):
        export_booksim_config(modified, "network", 1.0)
    return directory / "rapidchiplet/booksim2/src/rc_configs/network.conf"

