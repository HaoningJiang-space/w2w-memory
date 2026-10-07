# First-principles construction verification before performance experiments

This is an independent implementation from the user's written construction.
The referenced `W2W_FIRST_PRINCIPLES_ALGORITHMS.zip` was not present in the local
workspace/Downloads. We do not claim to have audited that external source code.

## Invariants

1. Every object uses the same frozen, nonnegative byte fractions A. Every row
   sums to one: no replication, missing bytes or scenario-dependent migration.
2. Unit full-load service and unit memory capacity require column sums one.
   With 4 GiB per compute, each memory holds 4 GiB, below its 16 GiB capacity.
3. A nonzero byte fraction requires an actual physical C–M HB path. Geometry
   uses the existing repeated H/plus templates and polygon/region validation.
4. f_cm=A_cm*r_c. Enforce memory, each overlap edge, both ports and controller.
   The independent audit reconstructs all loads from A and r, without the LP.
5. r=h+x gives Lx≤q−Lh. An inactive compute releases its own resource fractions;
   available bytes cannot be substituted from a different memory.
6. Components must partition both C and M, not only C. This makes their memory,
   controller and port resources disjoint in this model and their values additive.
7. The closed form is used only for two strictly positive fractions, unit memory
   service, floor=1 for active clients, unique C–M paths and nonshared endpoint
   ports. Shared-port or parallel-path cases are rejected, not silently modeled
   as independent free links. A future general model should use explicit flow.

The implementation remains a reticle-level pooled-memory relaxation. No bank
mask, DRAM word assembly, pad alignment, wiring closure or PPA is proved here.
Data usage may vary by reticle instance; that does not authorize nonrepeated
hardware templates. Continuous byte fractions also do not prove integer-page
implementability. These boundaries remain unchanged from the preceding work.

## Construction

Enumerate simple bipartite cycles with 2, 3 or 4 compute and equal memory count.
Canonicalize rotations/reversals. The two alternating matchings use weights λ
and 1−λ. Each column receives complementary weights; therefore row/column balance
holds without a global common λ. Each cycle is one candidate configuration.

For each cycle member, capacities a_i and b_i include the actual overlap limit.
Current capacities are <1, so full-load feasibility forces both fractions positive.
The feasible interval is [max_i(1−b_i), min_i a_i]. Reject empty intervals.

For training coefficient
π_i=E[1{i active, all distinct rivals inactive}/|S|], optimize
Σ_i π_i(min(4,a_i/λ,b_i/(1−λ))−1). Check interval endpoints and each member's
branch switchpoints a_i/(a_i+b_i), a_i/4, 1−b_i/4. Between switchpoints the
nonnegative weighted objective is convex, so its maximum is at an endpoint.
The proof is restricted to this closed-form family, not arbitrary shared channels.

The master problem is binary set partitioning, one exact coverage row per C and M.
Continuous ratios have already been locally optimized; the master is an actual
ILP. SciPy/HiGHS is used: the full catalogue has 2,614 binaries, exceeding the
previously verified 2,000-variable restricted Gurobi limit. No license changes
or claims of unrestricted Gurobi access are made.
The size limit is documented by [Gurobi](https://support.gurobi.com/hc/en-us/articles/29682074018833-What-does-Restricted-license-for-non-production-use-only-mean).

## Verification before any new performance run

`w2w/validation/verify_cycle_construction.py` performs:

- independent bounded DFS vs NetworkX cycle enumeration;
- degree-one elimination and matching deletion checks for home-pair uniqueness;
- forced inclusion feasibility for every K2,2 candidate, including non-home pairs;
- full-load resource checks at both feasible ratio endpoints and their midpoint;
- all local activity subsets of every catalogue cycle at pitches 25.6 and 25.7;
- explicit-flow throughput LP comparison for every nonempty subset, plus common
  service checks for singleton, full and alternating active sets;
- remaining-resource identity checks and independently reconstructed HB/port loads;
- 64 asymmetric capacity examples, nonuniform weights, controller switchpoints,
  comparison with 4,001-point grids, and exhaustive local LP checks;
- independent enumeration of every feasible cover on a complete 4C+4M example,
  checking the master's objective, both coverage sides and assembled full service;
- deliberate rejection of duplicated bytes, unbalanced residency, missing HB,
  overcommitted HB, shared-port misuse, wrong floor and overlapping components.

The dense grid is a numerical cross-check, not a proof of the breakpoint theorem.
The certificate records actual counts, maximum errors, versions, commit and host.
A smoke certificate cannot authorize the experiment runner.

## Conditional experiment registration

Only after a full, clean, same-commit certificate passes:

- pitches 25.6 and 25.7; same 36C+36M, 844.8 mm²/reticle, five identical ports,
  4 TB/s total HB and controller per reticle, 1 TB/s per memory;
- catalogue limits K=2,3,4; same scenarios and resources for all three;
- four existing synthetic distributions, trained separately (not one universal layout);
- new train seeds 110000–111023 (1,024), new test seeds 210000–214095 (4,096);
- select layouts only on training data; freeze arrays and verify their hashes;
- check every test state's resources independently in vectorized form;
- compare 16 preselected test states and full load per design to the global flow
  LP for both throughput and common service;
- report objective bounds/gaps, component counts, mean/P5/minimum/common service,
  paired differences and approximate 95% intervals across synthetic seeds.

These fresh-seed results independently test the written method; they are not an
exact rerun of the user's inaccessible archive and different training may choose
different tied layouts. No real-application or bank-implementation claim follows.

## Commands

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w.validation.verify_cycle_construction --output memory_results/cycle/certificate.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w.experiments.run_cycle_configuration_gate --certificate memory_results/cycle/certificate.json --output memory_results/cycle/results.json
```

All changes remain on `main`; local/GitHub/eex005 synchronize through committed Git.
