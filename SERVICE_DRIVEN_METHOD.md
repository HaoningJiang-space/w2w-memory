# Service-driven static fabric optimization and an exact integer reference

This stage directly improves the fixed-data service objective. It keeps the
open research scope: service floors .9 and 1 are comparative operating points,
not a claim that every future architecture must preserve baseline service.
Previous Gate/DSE source and results are unchanged.

## Continuous joint update: LP subproblems, not an ILP

Frozen shares a[c,b] and scenario rates r[w,c] obey route_flow = a[c,b]*r[w,c].
Jointly choosing them is bilinear. `layout_step` linearizes this product at the
current exact-LP solution, with per-coordinate share radius .5/32 and rate radius
.5 TB/s. Storage, unique bytes, all bank/output/HB/controller resources and a
full-load flow certificate at the selected floor remain explicit constraints.

Four iterations at most; fractions 1, .5, .25, .125 are evaluated by the ORIGINAL
fixed-byte service LP. Accept only a measured training improvement. The linearized
objective is not a bound, and monotonic training acceptance does not imply a
global optimum or generalization. Data shares may differ between compute
reticles, but hardware masks/widths repeat. All logical objects within a compute
share its same bank fractions, under uniform within-object accesses.

For new exposure edges, use the existing service solution's unused bank capacity
and unmet compute demand to rank potential repeated bank-port connections per
wire length. Add up to four banks to one port, inherit the parent data mapping,
then optimize static bytes again. This proposal score is not a performance proof.

## Integer joint reference: actual Gurobi ILP

Restrict static data to disjoint full-bank pairs: each paired client places half
of each object in each of two memories; unmatched clients remain home-only.
All involved ports sustain 1 TB/s, so a lone paired client receives 2 TB/s;
a simultaneously active pair receives 1 each. Pair training value is exactly
the normalized frequency of exclusive activity. This analytically eliminates
fluid rates in the restricted optimization problem.

Gurobi chooses binary reciprocal pairs z[i,j], binary REPEATED bank-port edges
x[b,p], and integer 32-bit lane counts L[p]. Pair selection activates every bank
on each required memory port, with both endpoint port capacity constraints;
clients belong to at most one pair. Bank-edge count, centerline wire length and
sum(.004*L[p]) <= 4 TB/s constrain the architecture. First maximize training
served bandwidth, then minimize wire/width cost at that attained value.
Report primal objective, bound, gap and status for both solves. This reference
has only integer variables: it is a genuine **ILP**, not just an LP solved using
Gurobi. Optimality applies to the disjoint equal-half FULL-BANK pair family,
not arbitrary bank grouping, data fractions or a global wafer architecture.

Full-port activation auxiliaries factor repeated implications and keep this
reference below the restricted license limits without changing its mathematics.
Bank-resource evaluation and the continuous sequential LP still use HiGHS.
General joint exposure/layout/service would be a mixed-integer nonconvex model
unless separately discretized or decomposed; changing solvers does not linearize
continuous products. [Gurobi's constraint reference](https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/constraints.html).

## Controls and cost

Aligned/X/XY full bank exposure, contoured k=2 opposite pairs and four directions,
and full five-port exposure are initial controls. H/plus k=3 exposes every bank
to home plus one opposite port pair: compare maximum-cardinality static pairing
with the training-aware integer synthesis. k=3 has 96 edges and 1852.2 mm wire,
versus k=2's 64/943.6: any gain must be presented with this cost increase.
The 2/3 geometry can pair all 36 clients; 1/4 can pair at most 30. These are
geometric matching facts, not observations chosen from the test set.

Apply the same conservative width reduction to EVERY candidate: port service
can never exceed the summed capacities of all banks that can traverse it. Bound
both HB endpoints, overlap fractions and compute-port unions before reducing
widths. This preserves every feasible bank-limited route flow, not only training
samples. It is a baseline correction, not claimed as a new synthesis insight.
Lane quantization for this correction is 250 bits; the Gurobi reference uses
32-bit integer lanes. The primary full-bank port sizes (8000 bits) are exact in
both. Record actual widths, not just the common 4 TB/s budget.

## Registration and licensing

Training seeds 500–503; validation 1500–1503; 25/50% activity and uniform,
clustered, correlated patterns. Select designs by VALIDATION mean within budgets
(64 edges,1000 mm), (72,1400), (96,2000), (160,3600), separately for floors .9/1.
Fresh test seeds 7000–7019, four activity fractions and four patterns including
object hotspot. Identical active IDs across architectures. Selection is frozen
before test solves. Registered controls and selected designs are evaluated.
Continuous striping is a relaxation; pair seeds have a finite 64-stripe/object
representation. No replication, runtime remapping, DRAM timing or PPA claim.

The user identified eex005 Gurobi installations. Initial probes found 13.0.3 at
`/home/wangziheng/miniconda3/envs/moe-chiplet-thermal` and 12.0.1 at
`/home/wangziheng/miniconda3/envs/thermodse-moe-chiplet`. Both solved a two-variable
binary model but rejected 2101 variables (error 10010), indicating the currently
loaded size-limited license. A full academic license may exist elsewhere; its
configuration remains to be supplied. No keys or license contents are recorded.
The restricted license allows at most 2000 variables/constraints for linear
models. [Gurobi licensing explanation](https://support.gurobi.com/hc/en-us/articles/29682074018833-What-does-Restricted-license-for-non-production-use-only-mean).

Run with the repository's Python 3.13 environment and append only the existing
Gurobi 13 package location after its normal dependencies; no shared Conda changes:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python run_service_driven.py --output memory_results/service_driven --gurobi-site /home/wangziheng/miniconda3/envs/moe-chiplet-thermal/lib/python3.13/site-packages
```
