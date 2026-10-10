# Interactive committed-prefix compute gate

This registers a candidate, not an accuracy or speedup receipt. Keep the accepted
quiescent compute epoch, G1/R3 and native application records unchanged. New
tests and fixed small runs use an isolated hn072 directory. No new backend,
multicast, task readiness or hardware policy is introduced.

The exact reference uses the existing contiguous descriptor prefix, one shared
compute context and ordinary integer-ps clock phases. A candidate may defer the
repeated arithmetic update for service funded entirely by the prefix already
committed at entry. It keeps the task tail ordinary. New data can extend the
next interval; it cannot retroactively fund the current one. A new context on
another cluster ends the rule and materializes only service already executed.

The system host loop, native DRAM clocks/refresh, BookSim advance, NI credits,
receive commits and finite gateway admission still run at their old boundaries.
This is **not global time skipping**: no available backend lookahead certifies
future native arrivals. Virtual consumption is visible to operand queries at
each executed service boundary. Explicit materialization restores ordinary
state for boundary inspection and fallback. Cache, event observers, byte-count
readiness, multiple contexts and mismatched compute/NoC clocks use the fallback.

Full emits each old compute event in place. Compact records constant-service
intervals plus run-length encoded insertion positions among equal-time external
events. Its independent decoder must restore their original order, not merely
sort timestamps. The decoder and interval auditor import no execution helpers.

Fixed cases: 64 KiB remote GEMM with reuse 4,096 MAC/weight-byte; non-divisible
8,224-byte tail with reuse 5,461; the 64 KiB case with an ordinary other-cluster
task released at 5,000,501 ps; and an 8 KiB transport-dominated case with reuse
one. Machine MAC/read budgets, DRAM addresses, graph and mapping are identical
across off/quiescent/interactive Full/interactive Compact. Stable has three shuffled repetitions; the others one:
24 workers. These synthetic inputs are not FFN or physical calibration.

Accuracy compares every physical result/event field, native command/time/address
fingerprints, endpoint mutation/progress/completion fingerprints, task clocks,
prefix consumption, resource peaks and final drain. Interactive kernel iterations must also
be identical; quiescent omitted boundaries are independently reconstructed. Independently reconstruct each interval's original committed
prefix, services and consumed-before/after; require partial-input coverage and a
later descriptor commit **during** an interval. Same-count prefix-hole histories
and the same future commit must remain distinguishable in a separate negative
fixture; it is not a calibrated DRAM service result.

Cost reports actual arithmetic updates, service visits, host iterations, stored
evidence, prediction wall/CPU/RSS and complete worker wall time. Full recording
retains linear event-output cost. Compact reduction alone is not a reduction of
native simulation work. A zero/small whole-worker gain is retained and ends this
candidate; it does not authorize replacing native timing with a guessed horizon.

Commands (set original recorded native binaries and pinned Ramulator Python
path in the isolated workspace):

```sh
python3 -m unittest discover -s tests -v
python3 tools/run_interactive_compute_gate.py OUT --binary BOOKSIM
python3 tools/run_interactive_compute_gate.py OUT --readback
```

Predictive sufficiency is scoped to declared interfaces and admissible future
inputs. Finite equality checks establish these cases, not universal bisimulation
or a minimal-state theorem. At a component cut credits are inputs; in the full
closed system they are internally generated feedback, not arbitrary exogenous
requests. Distributional conditional-information equality is an almost-sure
condition under that distribution, not equality for every allowed continuation.
