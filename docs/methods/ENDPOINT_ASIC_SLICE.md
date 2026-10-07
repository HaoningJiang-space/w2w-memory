# Single-slice standard-cell pipeline

Registered 2026-10-07. The main hardware-cost evidence is now ASIC-oriented;
Vivado remains supplemental FPGA evidence. No VCS/DC/Genus/PrimeTime executable
was discovered in the hn072 server PATH or configured environment. Their absence
from PATH is not proof that the institution has no licenses. A site environment
script and library can later replace the open tools without changing the traces.

This first pipeline uses Verilator and Icarus for the same self-checking RTL,
Yosys/ABC for Liberty mapping and OpenSTA for pre-layout timing. No P&R, DRAM
array/controller RTL, wafer network, new placement or width/depth sweep.

## Fixed comparison

- Native 256-bit read-return words; Home 256/D1, Shared 160/D2.
- Duplicated source vs configurable source; static select before the first HB.
- Map source variants separately, plus one common Home RX and common Shared RX.
  Each architecture is charged one Home RX and two Shared RX blocks.
- Preserve manufactured alternative directions. Do not tie configuration inputs
  to constants during synthesis. Configuration is frozen only in a test trace.
- Same Nangate45 typical Liberty, 2 ns target, 0.05 ns clock uncertainty,
  0.2 ns max I/O delay, zero min I/O delay, BUF_X1 input drive, 5 fF output load.
- Ideal clock and no extracted wire RC. These are local-pin assumptions, not a
  model of actual HB electrical loading or memory-process timing.
- ABC receives the same 2,000 ps target and driving/load constraints. OpenSTA
  independently checks the resulting mapped cells; a target is not achieved Fmax.

Library source: OpenROAD-flow-scripts commit
`9b26ff8ff651fc0b696f7ef20a356865ca6068bb`,
`flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib`.
SHA-256: `8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1`.
This public library provides a reproducible relative standard-cell comparison;
it is not calibrated to a DRAM process, an actual WoW stack or a foundry signoff.

## Execution and acceptance

`run_endpoint_asic.py` uses only the Python standard library. Tool environment and
library live outside Git in the remote experiment's `asic_tools` directory.

```sh
python3 w2w/experiments/run_endpoint_asic.py \
  --traces /path/to/archived/160bit/traces \
  --liberty /path/to/NangateOpenCellLibrary_typical.lib \
  --output /path/to/new/results --period 2
```

1. Check trace hashes against the archived roundtrip artifact.
2. Preserve all Verilator lint warnings and reject structural latch,
   multiple-driver, undriven or combinational-loop findings.
3. Replay 14 paired traces on Verilator and Icarus; compare exact cycle/counter
   results and historical completed-word/backpressure/occupancy counts.
4. Require both deliberately corrupted-data and changed-direction tests to fail
   through their intended checkers.
5. Map all four local blocks to the same Liberty and reject unmapped cells.
6. Run STA, preserving setup/hold paths and electrical constraint violations.
7. Generate zero-delay functional cell models from that same Liberty, check
   coverage of every mapped cell, and replay the same scoreboard using compiled
   Verilator through the mapped TX and RX netlists. This checks mapping
   semantics; it is not SDF timing simulation or formal proof.

Record source hash, tools, library hash, input hashes, source/RX area and cell
counts, and timing reports. Preserve incomplete runs separately. Do not infer
power savings, routed area, wirelength or a production Fmax from this pipeline.
Keep complete-interface and register-to-register slack separate. A completed
pipeline can still contain hold or electrical violations; report its area as
pre-repair mapped area until those constraints close. The first completed run
and these remaining violations are recorded in the
[ASIC slice report](../reports/ENDPOINT_ASIC_SLICE_REPORT.md).

## Registered hold/capacitance repair

The next comparison freezes the RTL, Liberty, 2 ns clock, all I/O delays and the
5 fF load. Optional `--repair` acts on mapped cells only: add one BUF_X1 stage
at each input with a negative hold path per iteration, and upsize a reported
overloaded driver to the next Nangate strength with the same signal ports.
Clock/reset nets and sequential cells are not edited. There are at most eight
repair iterations; unexpected internal hold, missing compatible cells, setup
failure or remaining violations stop acceptance. Initial netlists, every edit,
all STA reports, final area and mapped-trace verification remain available.

This is an explicit pre-layout netlist ECO under zero wire RC, not OpenROAD
physical repair, CTS or signoff. Do not relax min input delay to remove hold.
Do not change the direction interface in the same comparison. Equivalence of
the two architectures remains restricted to the static one-partner workload;
false-path direction controls do not certify the duplicated architecture's
general dynamic-direction timing. Sensitivity sweeps and P&R are separate work.

## Registered matched OpenROAD experiment

The subsequent user-requested physical comparison starts from the unrepaired
mapped netlists, with the same Nangate45 typical Liberty and the same shared
`slice_constraints.tcl`. It uses OpenROAD 2.0-17598-ga008522d8 (Ubuntu 22.04
prebuilt), and LEF, track, RC and extraction rules from the same pinned ORFS
revision as the library. No custom ECO buffers carry into this experiment.

Both sources and the two common receiver types use 30% initial utilization,
square aspect ratio, 5 um core margin, placement density 0.40, seed 42, two
threads, metal5/6 local I/O pins and the platform's metal2–10 signal / metal4–10
clock routing settings. CTS uses CLKBUF_X1/X2/X3. The same automatic setup/hold
repair sequence runs after CTS and with global-route parasitics; hold margin is
0.02 ns and the buffer limit is 50% for every block. Detailed routing is followed
by OpenRCX extraction and STA using propagated clocks. Record pre-repair,
post-CTS, repaired and extracted-route area/slack, added hold-buffer count/area,
route DRC count, and exact final cell counts. Replay the same mapped scoreboards.

This is local signal/clock physical validation. Power-grid routing, wafer-length
access wires, actual HB parasitics, multi-corner signoff and power are excluded.
Routing DRC means the detailed router's check, not an independent foundry deck.
A completed flow with residual violations is reported as not closed.

```sh
python3 w2w/experiments/run_endpoint_asic.py \
  --traces /path/to/inputs --liberty /path/to/NangateOpenCellLibrary_typical.lib \
  --output /path/to/new/physical_results --period 2 \
  --openroad /path/to/physical_tools/bin/openroad \
  --platform /path/to/physical_tools/nangate45
```

The prebuilt route is documented by [OpenROAD](https://openroad-flow-scripts.readthedocs.io/en/latest/user/BuildWithPrebuilt.html);
the pinned release is [2024-12-14](https://github.com/Precision-Innovations/OpenROAD/releases/tag/2024-12-14).
See the [resizer documentation](https://openroad.readthedocs.io/en/latest/main/src/rsz/README.html)
for automatic setup/hold repair. Tool/library version and raw logs take precedence
over behavior described for a newer online version.

Relevant primary tool documentation:
[Yosys ABC mapping](https://yosyshq.readthedocs.io/projects/yosys/en/v0.54/cmd/abc.html),
[OpenSTA](https://github.com/parallaxsw/OpenSTA),
[Verilator](https://verilator.org/guide/latest/).
