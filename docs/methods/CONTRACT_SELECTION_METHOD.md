# Contract-aware selection: first controlled experiment

## Registered question

With geometry, repeated exposure, static bytes and arbitration held fixed, does the endpoint service abstraction change the design selected under identical resource limits? This is a small diagnostic of the synthesis objective, not a new geometry or bank fabric.

## Frozen system and finite catalog

Reuse `run_endpoint_bridge`: H/plus, 36C+36M, 18 reciprocal pairs, half-home/half-peer layout, 32 banks/M, home+two opposite outputs/bank, native service 1 TB/s/M, controller 4 TB/s, and the same physical HB ports. Every used compute-bank relation retains its unique actual route. No address permission creates a physical recipient.

Enumerate 16 implementations: complete-word output widths 64/128/192/256 bits and depths 0/1/2/8. Depth zero is the blocking shared holding register; other depths have independent egress queues. Round-robin is fixed. Full-word execution is reused, not a new arbitration search. The two-dimensional budgets separately bound total exported lane bits and storage bits. The 96 exposure connections and existing wire proxy are identical across candidates. Counters are not calibrated PPA; smaller widths need not imply less area overall.

Selectors:

1. **Optimistic:** parent bank plus independent output capacities, ignoring realization even at depth zero.
2. **Fluid contract:** distinguish direct serialized occupancy from buffered independent drain, retain fractional service/ideal long-run envelope.
3. **Executed catalog:** use the verified complete-word execution service of each implementation.

All selectors use the same candidates, budgets, objective, and deterministic tie rule (smaller storage, then lanes). Results are evaluated using selector-independent measured execution. Minimum full-load service is either 0 or 1, explicitly registered. A predicted-feasible design violating its actual floor is reported as infeasible, not ranked by regret.

## Activity and objective

For uniform K-of-36 activity, conditioned on a client being active, its partner is idle with probability (36-K)/35. Let u be its measured single-client rate, v its measured rate with an active partner. Then:

E[per-active BW] = v + (u-v)(36-K)/35.

The probability no active pair occurs is choose(18,K)*2^K/choose(36,K) for K<=18, otherwise zero. Hence E[common BW] = v + (u-v) P(no active pair), assuming u>=v. This is exact activity averaging of measured implementation rates, not an exact silicon result.

Evaluate K=9,18,36 and the predeclared mixture with weights .5,.25,.25. No fitted activity statistics or train/validation split is needed: the entire specified probability model is integrated analytically. These synthetic distributions do not establish real workload opportunity. Common rate is reported independently; it is not the average-throughput objective.

## Correctness and claim boundary

- Reproduce the endpoint bridge after repository reorganization and compare every result except source/host metadata to the archived result.
- Reuse its full fixed-byte LP witnesses and physical capacities; independently verify all 160 bridge rows.
- Test population formulas by exhaustive subsets of 4/6/8 clients.
- Enumerate all feasible catalog entries, with exact catalog optimum and deterministic ties. No MILP or Gurobi is necessary for 16 candidates.
- Reference home-only 1 TB/s and the existing full-width pair expectation 1.771429. Beating a mistaken optimistic selection is not beating these strong baselines.

Only if this diagnostic exposes a useful design-choice gap should the next experiment expand exposure or placement, preserving the same real-contract evaluator and resource ledger. A lack of improvement over the strong baseline is a valid result, not a reason to relabel the objective.
