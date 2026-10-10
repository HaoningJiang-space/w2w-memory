# Matrix service: finite-cache confirmation and release/issue isolation

The completed cold S0/S1 study remains frozen at `869f0ac`. Its Phase-Split
result is 456.627 µs, not a measured multi-layer result. This stage first
checks persistent finite-cache behavior and separates projection release from
request issue order. It does not add gateways, native domains, HB lanes, MACs,
Down prefetch or a new matrix-fragment execution model.

## S1 finite-cache pair: completed and independently audited

Execution source is `9160207`. Reference and Phase-Split run the same archived
24-token, two-layer FFN proxy with independent layer weight identities. Both
place the full 128-expert catalog, retain Reference compute placement and have
the same initial whole-layer L0 cache contents/order, outside measurement.
The routing is reused at both layers; this is not a complete Transformer.

Each cluster retains 184 MiB finite LRU cache inside 192 MiB physical SRAM,
two compute contexts, two matrix-fetch slots with 136 B funded state, one shared
MAC/read grant, two descriptor issue opportunities/cycle and 32 outstanding
requests. Both use S1 projection dependencies and round-robin issue. Cache
hits use the existing finite lookup/compute services and release fetch ownership
without native requests; fills and consumers pin entries normally. Whole
matrices are still stored. Optional compute-epoch and interactive acceleration
remain disabled, so their separate acceptance results are not mixed into this
architecture comparison.

The BookSim binary SHA is `9d18611aa0cc74b6d8a475e302134c7888b1417648607abce3a6f8d04311e308`;
the bridge SHA is `37eb00768993fb5cfd903c690e72a21cdc69e10f4acbc421762f54dc5a33ba54`.
These are the completed cold study's same tools. The new source's default S0
multi-layer input has exactly the old normalized fingerprint:
`696e79e95d7a62cccbde8e2e3ead9fcf1d7d7fc60a9dc7b895ced9118cbcccc2`.

Eleven relevant remote tests pass, including independent layer/token barriers,
fixed mathematical work/preload and native S1 cases with initial hits, eviction,
reload and complete fetch/cache drain for both layouts. No old large matrix
was rerun for this extension.

The pair is archived on hn072 under
`/Projects/haoning/w2w-full-system-matrix-service-20261010/concurrent-hierarchy-r1`.
`hierarchy-monitor-r1.log` checks each minute, independently audits after both
completions, then reconstructs stages. Failures stop for inspection; there are
no automatic retries or performance-dependent workload changes.

Acceptance reports complete and token-12–23 elapsed times; per-invocation cache
hits, misses, compulsory/reload/native bytes; actual gateway/domain work;
fabric hop/data-lane-distance activity; operand/compute readiness and drain.
Equal initial cache does not require equal later traffic. Negative performance,
changed miss counts and zero reload are valid observations, not reasons to
discard or rerun a case. No S1 multi-layer benefit was claimed at registration.

Both registered workers now complete. Independent saved-result and stage
readbacks at `9160207` report Reference **13.300139 ms** and Phase-Split
**10.979869 ms**, a **17.45%** reduction. Token-12–23 elapsed time is
**6.419167 / 4.862114 ms**, a **24.26%** reduction. Both have 9,492 hits,
4,332 misses, 2,271,770,112 native bytes and 648,178,176 reload bytes; the late
interval has 591,541,248 reload bytes in either case. Counts are observed and
independently checked, not an acceptance requirement. Lateral data-lane
activity increases about 3.63×; no energy/PPA benefit is established.
Full raw/stage readbacks remain in the declared archive; receipts are in
`artifacts/provenance/fetch_state`. This is the original two-coupled-slot S1
pair, independent of the later split-controller intervention.

## Fixed-slot factor probe: completed and independently audited

The twelve native cases at `9fbb4db` cross:

| Factor | Values |
|---|---|
| Projection release | D0 serial Gate→Up; D1 independent Gate/Up |
| Descriptor issue | Ordered; round-robin |
| Physical placement | Reference; Hybrid; Phase-Split |

Every cell has the **same two fetch slots and 136 B state**. D0 therefore does
not reproduce original S0's unbounded matrix-fetch admission. At fixed release,
ordered-versus-round-robin isolates issue policy. At fixed issue, D0-versus-D1
isolates the allowed release edges. Their difference-in-differences reports
interaction within this fixed finite-state design.

Hidden=1024, intermediate=1536 and block width=128 retain three blocks per
partition, so Hybrid's Down movement remains meaningful. The full catalog has
128 experts; the active pair is 62/108, selected post-hoc from the old cold
input because they share compute/service groups. This is an explanatory
contention fixture, not independent routing validation or a placement search.
All cells read 9,439,488 B and have the same mathematical work, physical data
resources, compute placement and two shared-service contexts. Policy placement
still uses catalog identity only.

The probe records complete raw executions and independently replays saved
graph/input identity, byte/address/command/ACK, operand, fetch, shared issue/MAC,
capacity and drain audits. It reports stage/paired intervals, native row and
latency observations, gateway work, actual hops and data-lane byte·µm. It is
fixed before execution; if it does not reproduce Hybrid's full-size regression,
that negative finding is retained rather than expanding a fixture search.

All twelve cases complete and pass independent saved-result replay, with
9,439,488 native bytes, 124 tasks and 128 physical domains in every cell.
Execution remains `9fbb4db`; no case is replaced or retried based on its outcome.

| Placement | D0 ordered (µs) | D0 round-robin (µs) | D1 ordered (µs) | D1 round-robin (µs) |
|---|---:|---:|---:|---:|
| Reference | 98.183 | 97.624 | 97.895 | 97.526 |
| Hybrid | 88.521 | 83.206 | 87.019 | 84.300 |
| Phase-Split | 73.139 | 73.372 | 67.702 | 66.894 |

At fixed round-robin, independent release helps Phase-Split by 6.478 µs but
hurts Hybrid by 1.094 µs. At fixed ordered issue, independent release instead
helps Hybrid by 1.502 µs. Hybrid's release×issue interaction is therefore
+2.596 µs; Phase-Split's is −1.041 µs. This reproduces the direction of Hybrid's
negative concurrency effect in a fixed-state native fixture. It does not assign
the full cold study's 42-µs regression to one exclusive cause or validate new
routing workloads. Round-robin itself improves Hybrid at either release setting.

The readback retains exact gateway/native work, task milestones and actual
fabric activity. Context, fetch and service-window sums overlap; they are not
added to manufacture a system stall decomposition. Raw archive identities and
the complete independent audits are in `artifacts/provenance/matrix_service`.

Analysis-only readback at `d2b4893` adds 72 exactly matched acquire/release
ownership intervals per case and preserves every previous audit, effect and
case field. Hybrid's round-robin final `e62/b8/up` illustrates why legal release
is different from fetch admission:

| Observed milestone | D0 round-robin (µs) | D1 round-robin (µs) |
|---|---:|---:|
| Previous block accumulate completes | 60.230 | 60.872 |
| Up dependency ready | 67.373 | 60.872 |
| Up obtains a fetch slot | 67.373 | 68.002 |
| Up last descriptor issued | 72.836 | 73.744 |
| Up completes | 76.429 | 77.565 |
| Down completes | 82.507 | 83.601 |
| Layer completes | 83.206 | 84.300 |

From 60.872 to 60.953 µs, D1's two slots belong to `e108/b2/gate` and
`e108/b2/up`; from 60.953 to 68.002 µs they belong to `e108/b2/up` and
`e62/b8/gate`. Thus its entire 7.130-µs dependency-ready-to-admission interval
coincides with full finite fetch ownership. After the peer Up releases, this Up
can enter. This is direct evidence of cross-expert admission competition, not a
long gateway data queue or a mathematical Gate→Up requirement. The matched
timeline already differs before this block; the ownership interval is not
identified as an exclusive 7.130-µs contribution to the 1.094-µs final slowdown.

## State-lifetime follow-up: G1/G2 completed, fragments deferred

The [fetch-state report](FETCH_STATE_LIFETIME_REPORT.md) partitions all twelve
saved ownership timelines into issuing and return-only intervals. In Hybrid's
7.130-µs admission wait, at least one owner is return-only for 4.078 µs.
This identifies an opportunity rather than a makespan saving.

The extracted controller matches full physical records, native command logs
and endpoint traces before intervention. Nine frozen native cases compare two
coupled slots, three coupled slots and two issue contexts with three bounded
return associations. Phase-Split takes **66.894 / 65.800 / 64.935 µs**;
declared control state is **136 / 200 / 440 B/cluster**. Hybrid's motivating
admission wait disappears with split state, but its case improves by only
0.062 µs. Return tags, operands and matrix SRAM stay funded until commit.
The candidate does not demonstrate a low-cost dominant bottleneck, so G3
fragment execution remains deferred. Default behavior stays coupled.

## Down prefetch: interval bound and finite-slot constraint

For the full cold matrix M=524,416 B, Phase-Split assigns Gate/Down to A and
Up to B, each 32 B/ns. If **all three misses must be served after the selected
block release**, their payload-work bound is

\[
T\geq\max((M_G+M_D)/B_A,M_U/B_B)=32.776\ \mu s.
\]

The observed final-block span is 43.763 µs. The resulting 10.987 µs gap is an
optimistic interval reference, not a promised prefetch gain. Starting a fetch
before that release moves work outside the interval; it does not remove the
full-layer service obligation. Cache hits similarly change remaining native
work and require their own bound.

Both existing fetch slots remain held until their entire Gate/Up operands
arrive. Simply removing Down's fetch dependency cannot make three matrices
simultaneously own those two slots. A same-budget proposal must choose among
existing streams, release/reassign legal bounded state, or explicitly budget
additional associations. It must also distinguish Down's independent weight
fetch from its arithmetic dependency on H. An opportunistic whole-matrix slot
release near the projection tail can offer far less overlap than the optimistic
11-µs reference.

## Intermediate slices: specify storage and readiness before execution

An intermediate slice J supports independent complete Gate/Up dot products,
then H[J], then its contribution Wd[:,J]H[J]. A hidden reduction slice K only
produces partial Gate/Up sums; all K contributions must join before SiLU.
The two decompositions cannot share a generic byte-ready interpretation.

The present weight catalog is an opaque packed matrix with 128×128 FP8 scale
groups. `build_moe` deliberately rejects block widths below 128. A 32/16-element
fragment must retain the original scale/storage identity; it cannot use the
existing integer formula to create a zero-scale matrix or silently reread all
scales for every fragment. Gate/Up output-row slices and corresponding Down
column slices also have different contiguity under a row-major layout. A
candidate must declare column/intermediate-major Down packing or pay explicit
strided access/gather service. Byte counts alone do not specify that layout.

With contiguous, aligned slices and the existing 4-KiB descriptors, splitting
512 KiB into 128/64-KiB pieces need not increase data-descriptor count. It does
increase task/fragment association and completion state. Strided packing or
repeated scales can increase requests, and must be counted separately.
FP32 output accumulator ownership, contribution order, BF16 H conversion,
partial-sum transfers and context/metadata SRAM must also be specified; algebraic
equivalence does not promise bit-identical reordered floating-point sums.
No finer-grain performance or numerical result is reported in this protocol.

## Physical opportunity and conditional energy reference

The completed S1 lane-distance activity ratio is 8.0293× for Phase-Split versus
Reference. These are actual executed data-lane bytes including cell padding,
multiplied by modeled path length; they are not measured energy. Under the
explicit assumption that only NoC dynamic energy changes proportionally while
all other energy is fixed, EDP improves if the Reference NoC share is below
3.8616%. The allowed total-energy ratio is 1.2714×. Changed command activity,
routers, buffering, SRAM and control energy can invalidate that simplification.

Bringing two vertical service domains nearer one consumer could reduce lateral
transport. It must retain total HB/data/control/buffer budgets and account for
changed array-to-HB collection paths, landing footprints, shared injection and
the other consumers that lose a nearby port. Moving a gateway does not eliminate
its wires or copy native bandwidth. This is a subsequent physical hypothesis,
not a new topology or an accepted PPA result.
