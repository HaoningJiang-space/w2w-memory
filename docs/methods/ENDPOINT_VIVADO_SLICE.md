# Single-slice Vivado comparison

Registered 2026-10-07 before implementation. Extends the bit-perfect roundtrip
experiment at source `2745632` and result commit `78384d9`. This is FPGA local
implementation evidence, not ASIC standard-cell area or a wafer implementation.

Compare only duplicated and configurable TX: native 256-bit word, Home 256/D1,
Shared 160/D2. Keep configuration and native direction as physical input ports
during synthesis. Selection remains upstream of the first HB. Reuse the 14
archived 160-bit traces (both directions, seven patterns); validate their hashes
against the archived roundtrip artifact. No DRAM model, new placement or FIFO sweep.

Use Vivado 2024.2, `xcku040-ffva1156-2-e`, 2 ns period, 0.05 ns uncertainty,
0.2 ns max input/output delay and zero min delay. Reset and frozen configuration
inputs are excluded from operational timing paths, not tied off for synthesis.
Use two tool threads, default synthesis/opt/place/route, no candidate-specific
tuning or additional pipeline stages. Keep any timing failures in the results.

The initial KU040 launch missed the license path. After the user supplied a
readable license, an eight-register KU040 synthesis passed with an explicit
`XILINXD_LICENSE_FILE`. The main comparison therefore uses the original KU040
selection. A partial Z020 tool bring-up is not mixed into the final comparison.
Completed XSim evidence is reusable because RTL, testbench, activity window and
clock period are unchanged. Operational recipes with host/license paths live in
the user's local remote-execution skill, not in versioned license contents.

Implement four out-of-context blocks: duplicated TX, configurable TX, Home RX,
Shared RX. The same Home RX plus two copies of the same Shared RX are charged to
both architectures. This prevents whole-star optimization from deleting or
changing one candidate's receivers. Count TX and RX resources separately; combined
counts are sums of separately implemented local blocks. Do not sum device static
power across blocks. Timing is per block with matched interface constraints; it
does not certify the HB path or an entire reticle clock.
Report register-to-register timing separately from complete OOC interface timing:
an ideal external capture clock and physical internal clock insertion can dominate
an output-port slack. Preserve both rather than calling either a measured Fmax.

Run XSim with the existing paired TX/HB/RX scoreboard at a 2 ns simulated period.
Check accepted and reconstructed words, routes, held handshakes, and cycle-wise
equivalence. The simulated period does not establish achievable frequency.
For mixed and stalled traces in each direction, collect RTL SAIF for 1,040 cycles
after 1,040 warmup cycles, excluding reset. Use these same windows for power
annotation; preserve annotation coverage/warnings. The SAIF is functional RTL
activity, so internal gate glitches are not measured. No board power measurement.

Report LUT/FF/memory, setup/hold timing and unconstrained paths, routed status,
and Vivado power estimates with activity and environmental assumptions. Preserve
reports, constraints, source/input hashes, tool version and commands. No FPGA
resource-to-ASIC-area conversion. HB, wafer wires, DRAM energy and system-level
bandwidth remain outside this experiment.

Run the standalone, standard-library-only runner on the Vivado host after sourcing
its environment. Input trace directory contains the archived `home_dir0`, etc.:

```sh
python3 w2w/experiments/run_endpoint_vivado.py \
  --traces /path/to/archived/w160_d2 --output /path/to/isolated/results
```

SAIF procedure follows AMD UG900 (2024.2), [Generating SAIF Dumping](https://docs.amd.com/r/2024.2-English/ug900-vivado-logic-simulation/Generating-SAIF-Dumping);
annotation follows UG835 [read_saif](https://docs.amd.com/r/2024.2-English/ug835-vivado-tcl-commands/read_saif).

## Constraint audit and controlled RTL diagnostic

The first completed implementation (`4c1e4f8`) exposed an XDC error:
`remove_from_collection` is unsupported within the XDC reader, leaving input
delays unset. Preserve that run as diagnostic evidence, not a valid complete
interface timing comparison. Replace it with a filtered `get_ports` query and
rerun all four unchanged RTL blocks first. Save applied XDC and reject missing
input/output delays, unconstrained internal endpoints and critical warnings.

Then make a separate, matched TX-only experiment: drive beat valid/data-enable
directly from nonempty FIFO view when the elastic beat may advance, rather than
testing the calculated transmitted-unit count. On legal state, `view_count > 0`
and `0 <= offset < 8` imply a positive available-unit count. This changes neither
buffer capacity nor latency. Verify the same 14 bit-perfect traces and count
regression again; use identical corrected XDC for both architectures. Unchanged
RX blocks may be charged from the corrected baseline with explicit provenance.

Vivado 2026.1 version discovery succeeded, but its actual launch with the supplied
license failed before synthesis. No 2026.1 PPA results are claimed. These paired
diagnostics remain on verified Vivado 2024.2.
