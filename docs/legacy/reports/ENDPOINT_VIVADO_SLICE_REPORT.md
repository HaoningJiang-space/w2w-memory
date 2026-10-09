# Single-slice Vivado RTL and PPA diagnostic

2026-10-07. Scope: read-return source endpoint and identical destination RX blocks;
Vivado 2024.2, KU040 `xcku040-ffva1156-2-e`, 2 ns clock, 0.05 ns uncertainty.
The two source architectures keep Home 256/D1, Shared 160/D2 and the same frozen
single shared direction. All routing selection precedes the first HB.

## What prompted the diagnostic

The user questioned whether poor timing came from RTL. Inspection found two
separate issues, which are evaluated separately:

1. **Confirmed flow error.** Source `4c1e4f8` generated input delays with
   `remove_from_collection` inside XDC, which Vivado rejected with
   `Designutils 20-1307`. Its timing checks reported missing input delays
   (263/264/263/167 ports for duplicated TX/configurable TX/Home RX/Shared RX).
   The earlier complete-interface timing comparison is superseded. It is
   retained only to explain the diagnosis. A tool exit code of zero was not
   sufficient to accept that flow.
2. **RTL implementation opportunity, not an observed data bug.** The old
   configurable critical internal path was `beat_valid` to the CE of the
   160-bit output register, through four LUT levels, with 2.666 ns data delay
   (0.681 ns logic and 1.985 ns routing). In `endpoint_tx`, both valid and data
   enable tested `units != 0`, bringing the gearbox unit-count arithmetic into
   the control path. The diagnostic replaces that test with `words != 0` while
   keeping the existing elastic-beat advance condition.

For legal state, a nonempty FIFO view has `8*words - offset >= 1`, since
`words >= 1` and `0 <= offset <= 7`. With an advancing output and positive lane
width, a positive available count always produces a positive `units` count.
The simpler enable is therefore equivalent under the stated contract, without
new storage or pipeline latency. A runtime invariant checks that equivalence.
Both architectures receive exactly the same edit.

## Controlled sequence and evidence

- `4c1e4f8`: archived initial diagnostic, incomplete input constraints.
- `cff6b51`: corrected XDC, original RTL; rerun launched but stopped during the first block routing. The runner now
  rejects critical warnings and missing input/output/internal timing constraints.
- `b92deec`: only the common TX enable logic changes; its queued XSim/implementation run was stopped before execution. No corrected FPGA RX result or final corrected FPGA total is available.

The archived original XSim run passed 14 paired cases and 124,834 complete words
per architecture with source/HB/RX hold checks, exact payload/route scoreboards,
queue bounds and bit conservation. This covers the registered traces, not all
possible input sequences or post-route gate timing. No functional counterexample
was found in the source audit.

The user then prioritized the ASIC standard-cell pipeline. The unfinished
corrected FPGA runs were explicitly stopped and marked interrupted. No corrected
FPGA timing result or RTL-induced timing improvement is claimed. The simplified
RTL is instead validated through the ASIC pipeline described in
[ENDPOINT_ASIC_SLICE.md](../methods/ENDPOINT_ASIC_SLICE.md).
That pipeline has now completed; its mapped-cell area, functional results and
remaining STA violations are in the [ASIC report](ENDPOINT_ASIC_SLICE_REPORT.md).

## Tool and physical boundaries

Vivado 2026.1 reports its version, but an actual batch launch with the supplied
license exits 42 before synthesis: “Vivado Design Suite cannot be launched
because a valid license was not found.” This is independent of RTL. AMD documents
launch-time license enforcement from 2026.1 in
[UG973](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Devices-and-Features).
The working comparison remains on 2024.2. The official Ross simulation and timing
skills were read as diagnosis guidance; no Vivado MCP or 2026.1 methodology
workflow is claimed to have executed.

Resource totals are FPGA LUT/FF counts for separately implemented local blocks,
not ASIC area. Destination receivers are charged identically (one Home RX and
two Shared RX). No package pads, DRAM array/controller, HB or wafer-length wire
cost is included. OOC ports have no physical partition-pin placement, so
interface timing remains a model boundary; register-to-register timing is
reported separately and is not called measured Fmax.

Power uses four matched RTL SAIF windows (1,040 cycles, 2,080 ns each after
warmup). Partial net annotation and inferred internal-enable activity make these
estimates diagnostic only; device static power is never summed across blocks.
A timing-failing result is not evidence of operation at 500 MHz, and no hardware
power or ASIC PPA saving is claimed.
