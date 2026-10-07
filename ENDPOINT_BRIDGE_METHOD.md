# Endpoint-to-wafer integration: one frozen design

The research objective remains wafer-scale memory service. This experiment
connects endpoint contracts to the existing bank/wafer solver; it does not search
new placements or layouts and needs no train/validation split.

## Frozen system and byte semantics

Use the existing H/plus 36C+36M geometry, full-bank k3 mask (home,2,3), ports
(8000,0,8000,8000,0) bits at the existing 1 GHz port clock, and the deterministic
18-pair layout from `paired_layout`. Every object has half its unique bytes in
each paired memory and uniform striping across its 32 banks. Retain all bank,
HB edge, both-end port and controller constraints. Record one layout hash for
all experiments. Active sets: one client, its pair, random nine (seed 620100),
first nine IDs, and all 36. These are mechanism probes, not workload estimates.

The physical repeated mask has THREE bank outputs; a particular pair uses home
and one of the two opposite directions. Fixed partition therefore reserves 1/3
of native service to each physical output, including the unused direction. It
does not get a free instance-specific reallocation to the selected two ports.
Its comparison is conditional on this template, not a best private-memory design.

## LP integration

`EndpointFixedService` reuses the original `FixedService` byte equalities without
modifying legacy code. It copies the resource ledger and changes output peaks:

- Fixed partition: f[b,p] <= min(alpha,1/3)*mu[b].
- Elastic: f[b,p] <= alpha*mu[b], sum_p f[b,p] <= mu[b].
- Direct serial: additionally sum_p f[b,p]/lambda[b,p] <= eta.
- Buffered envelope: additionally sum_p f[b,p]/mu[b] <= eta.

The last condition equals the native cap when eta=1. It is an upper envelope,
not finite-FIFO execution. All addresses of the modeled bank can return through
its declared digital outputs. This does not claim arbitrary LIO/address taps
are interchangeable. A missing fixed byte source still forces the complete
request rate to zero. No data migration, copying or replacement by idle banks.

## Finite complete-word execution

`execute` implements a deliberately explicit digital model, not DRAM timing:

- A native slot admits at most one complete 256-bit word, with immutable owner
  and transaction ID. Issue occurs at slot start, followed by output drain.
- At bank mu=1/32 TB/s, a slot is 1.024 ns. This is a normalized service clock,
  not SeDRAM's published 128-bit interface or a measured physical clock.
- Each output can transmit 64/128/192/256 bits per slot. Unused lane capacity
  can serve the next already queued word, but cannot trigger mid-slot issue.
- Direct has ONE shared holding register and blocks new issue until that word
  completes. Thus noninteger word serialization can fall below the fluid bound.
- Buffered has D=1,2,8 full-word slots PER output, including the word being
  serialized. D=0 explicitly selects the direct fallback, not a zero-cost elastic
  path. The native service remains single, while outputs independently drain.
- Round-robin arbitration may skip full outputs. Ordered arbitration preserves
  destination bursts of eight words and stalls on the next full destination.
  These are two explicit policies, not a claim that DRAM requires this order.
- Queues backpressure the source. Every slot checks native admission, storage
  bounds, word conservation and bit conservation. Only complete returned words
  count as service. Warmup queues are retained, not silently flushed.

The source has no modeled activation/refresh/row-miss latency, HB propagation,
clock crossing or command pipeline. Depth effects therefore belong to this
specified digital architecture. Deeper buffering need not help regular traffic.
No one should infer real FIFO depth from these traces alone.

## Compose execution with wafer resources

All 32 banks in a memory run the same schedule; each serves at most two active
paired clients. Cache the identical per-bank traces, then scale complete-word
rates by native BANK_BW. Every used C-bank path in this design is unique.
Scenario-specific delivered-rate caps are attached to those route columns in
the existing service LP. Preserve the exact byte ratios and construct a separate
primal witness from the returned compute rates; check every original and added
resource. If an observation ends mid-period, use the lower endpoint rate for
both clients, conservatively excluding unmatched prefetch progress.

This is a composed steady-window schedule, not a general whole-wafer event
simulator. Its composition is justified here: each selected physical port has
at least 1 TB/s; even 32 synchronized bank outputs inject at most alpha TB/s
there, while a client uses two ports and its controller allows 4 TB/s. No hidden
port contention is ignored in this restricted pair design. For arbitrary
layouts/shared routes this justification does not apply; do not extrapolate the
measured caps as a universal hardware contract.

Measure 8192 slots after 1024 warmup slots; double the window for four nominated
convergence cases. Compare F/direct/buffered fluid envelopes with execution,
mean throughput, common completion and feasibility of the original 1 TB/s floor.
Do not force an infeasible floor and then silently drop the case.

## Cost scope

Keep geometry, 96 physical bank-port connections and centerline wire fixed.
Report changed output lane bits and storage separately. Direct needs a shared
256-bit register per bank; buffered needs 3*D*256 bits per bank for the repeated
three-output template (even though a pair uses only two). These replace the
endpoint-storage accounting for this comparison; do not add the old abstract
`buffer_depth` proxy again. Tags, control, pipeline/clocking and implementation
area remain unpriced. The old fabric cost dictionary is recorded as provenance,
not advertised as an updated complete PPA ledger.

## Reproduction

```sh
python -m unittest test_endpoint_execution test_endpoint_contract
python run_endpoint_bridge.py --output memory_results/endpoint_bridge/results.json
```

Commit clean source before execution. Keep the original algorithms and results
unchanged. No Gurobi is necessary: the integrated service problem is continuous
LP, and the digital model is a discrete execution simulator, not ILP.
