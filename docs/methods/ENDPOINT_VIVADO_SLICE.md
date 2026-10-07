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

Implement four out-of-context blocks: duplicated TX, configurable TX, Home RX,
Shared RX. The same Home RX plus two copies of the same Shared RX are charged to
both architectures. This prevents whole-star optimization from deleting or
changing one candidate's receivers. Count TX and RX resources separately; combined
counts are sums of separately implemented local blocks. Do not sum device static
power across blocks. Timing is per block with matched interface constraints; it
does not certify the HB path or an entire reticle clock.

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
