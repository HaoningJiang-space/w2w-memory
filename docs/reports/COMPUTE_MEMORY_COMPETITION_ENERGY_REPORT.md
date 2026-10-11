# Compute–memory competition and conditional energy/EDP

## Scope and result

The registered Up-local finite-cache pair is complete. Relative to Phase-Split
with original Up compute, completion improves **12.06%**, late-window time
**19.40%**, and NoC data-lane activity **72.15%**. Native traffic also falls
**11.17%**, entirely through fewer reload bytes. This is a cache/local-execution
result, not a same-traffic communication-only comparison. See
[the completed co-placement report](COMPUTE_MEMORY_CO_PLACEMENT_REPORT.md).

The new reader changes no execution, mapping, hardware, native backend or
arbitration. It reconstructs six existing cold/two-layer records at `0d8ab50`,
checks raw SHA against completed independent audits, and retains each source
identity. Current co-placement executions are `02dab2a`; historical Reference
records are `869f0ac` cold and `9160207` warm. Original-Up already has complete
physical-record equality to the old Phase-Split cold/warm references.

The main finding is that the final cold Gate becomes **operand-limited**, with
downstream request/service occupancy, rather than shared arithmetic/read-port
contention. Energy/EDP now has an executable activity model and exact parameter
inequalities. It remains conditional: no process-calibrated total energy or PPA
number is claimed.

## G2: observed execution boundaries

`compute_memory_competition.py` reuses sparse contiguous-prefix reconstruction
and additionally replays finite compute ownership, fetch ownership, requester
outstanding descriptors and shared MC pool ownership. Ready-context waiting
must match a real competing shared MAC/read grant; duplicated or off-clock
grants and capacity violations fail analysis. Clock opportunities are integer
ps and global-clock aligned. Fetch-full intersections use elapsed time because
allocation can occur off the compute clock.

For each Gate/Up/Down the receipt preserves dependency eligibility, allocation,
input/scale readiness, compute start, first/last issue, operand completion,
first/last service and finish. It distinguishes:

- Fetch-full time between dependency eligibility and allocation; the residual
  can include SRAM/cache/tag availability or same-tick ordering.
- Input and scale readiness after allocation, whose intervals can overlap.
- Compute-context capacity waiting after all start conditions are satisfied.
- Started-context clocks with no consumable continuous weight prefix.
- Started-context clocks with operands ready but a competing shared grant.
- Outstanding/MC-full intersections during the actual descriptor issue window.

These are observations, not independent additive stalls or predicted savings.
The latest-finishing explicit predecessor chain does not include every implicit
shared-resource edge. MC-full and outstanding-full intervals can overlap; being
full does not by itself establish the sole cause of every failed issue attempt.

### Matched final cold block: e62/b8

All times below are µs. Each column uses its own observed previous-block
completion; it is not a decomposition into independently removable delays.

| Boundary / observation | Original Up compute | Up-local |
|---|---:|---:|
| Previous-block completion / projection release | 410.271 | 380.889 |
| Gate allocation | 410.271 | 384.428 |
| Gate fetch-full admission wait | 0 | **3.539** |
| Gate input ready | 411.423 | 385.090 |
| Gate scale ready / compute start condition | 410.398 | **388.278** |
| Gate compute start | 411.423 | 388.278 |
| Gate first → last descriptor span | 18.951 | **38.737** |
| MC pool full within that span | 18.830 | **38.504** |
| Requester outstanding full within that span | 18.936 | **0** |
| Gate context: arithmetic service | 0.124 | 0.129 |
| Gate context: missing consumable operand | 20.548 | **38.773** |
| Gate context: ready but another MAC/read grant | 0 | **0** |
| Gate compute-context-full start wait | 0 | **0** |
| Gate operand wait before last descriptor issue | 17.692 | 34.824 |
| Gate operand wait after last descriptor issue | 2.856 | 3.949 |
| Gate finish | 432.095 | **427.180** |
| Up finish | 432.198 | **402.685** |
| Down finish | 454.034 | **449.083** |

Up-local releases this block 29.382 µs earlier, but Gate/Up joint completion
relative to release grows from 21.927 to 46.291 µs. Its Up finishes 24.495 µs
before Gate. The original projection pair is just Up-limited; Up-local is
Gate-limited. Gate arithmetic service differs by only 5 ns. No observed compute
context or ready-grant waiting explains the additional Gate span.

Gate's scale also arrives late: 3.850 µs after allocation, compared with input
arrival 0.662 µs after allocation. Thus the previously visible input-to-start
gap is **scale readiness**, not a full compute context. After start, 34.824 µs
of its missing-prefix clocks occur while descriptors are still being issued.
The unchanged `pool0_3` is full for 38.504 of 38.737 µs, whereas the requester
never reaches its 32-descriptor limit. This supports investigating downstream
MC/receive/request admission and time-varying service demand. It does not prove
that adding MC slots would save 38.504 µs, nor justify a new compute scheduler.

### Multi-layer competition

| Observation | Phase-Split, original Up compute | Up-local |
|---|---:|---:|
| Largest cluster arithmetic service (µs) | 73.028 | 54.554 |
| Sum of context occupancy (ms) | 129.098661 | 128.346624 |
| Sum of missing-prefix context clocks (ms) | 128.220638 | 127.516675 |
| Sum of ready/competing-grant clocks (µs) | 2.515 | 1.894 |
| Sum of compute-context-full pre-start clocks (ms) | 1.473190 | 0.712246 |

The sums span multiple tasks/contexts and overlap in wall time. Roughly 99.3%
of occupied-context clocks lack a consumable weight prefix in both cases.
Compute peak is fixed and still lightly serviced; this evidence does not make
the aggregate SRAM banking or 4096-PE internal dataflow a silicon-calibrated
model. The cache and request feedback changed with mapping, so the comparison
does not isolate a single downstream arbitration cause.

## G3: activity and energy interface

`energy_edp.py` extracts measured-in-simulation activity, in explicit units:

| Term | Activity basis | Remaining calibration / evidence |
|---|---|---|
| DRAM array | Completed 16 B read atoms / read bits | ACT/PRE/REF, state durations and RWDL currents |
| HB | Useful payload and command/ACK bits | Padding/toggles, pad drivers, CDC and clocks |
| Memory collection | Executed domain atoms × physical collection length | Per-bit/mm wires and pipeline registers |
| NoC link | Actual channel cells × length, including declared sideband | Process, toggles, repeaters/pipeline |
| Router | Actual hop cells + destination traversal per injected cell | Physical macro, ports and switching |
| Buffer | Two transfers per router traversal | Proxy, not exact buffer SRAM/toggle events |
| SRAM | Actual stream/scale reads, DMA reads, receive writes | Macro/banks; internal activation/psum accesses |
| Compute | Actual MACs and vector service cycles | FP8/FP32 circuitry and active switching |
| Control | Tag lookups, command/ACK bits, context-time | Selector/association circuitry and power gating |

`noc_data_bit_mm` remains a diagnostic. The energy link term uses
sideband-inclusive `noc_cell_bit_mm`; charging both is rejected. Command-array
energy is an alternative to per-read-bit array energy, not an additional charge.
All coefficients, common physical power and unmeasured residual energy must be
explicitly supplied. Missing/unknown coefficients and non-finite values fail.
Initial cache preload is outside both measured warm intervals.

The primary-source catalog is
[`configs/analysis/energy_sources.json`](../../configs/analysis/energy_sources.json).
[DSENT's authors](https://dspace.mit.edu/entities/publication/6fc75ecc-628b-4f2b-891e-283ab4bef330)
support parameterized technology/NoC modeling, rather than an invariant router
energy. [Eyeriss author slides, slide 20](https://eems.mit.edu/wp-content/uploads/2016/06/eyeriss_isca_2016_slides.pdf)
give normalized hierarchy costs in a commercial 65nm example: MAC/RF 1,
inter-PE 2, global buffer 6, DRAM 200. These are context for choosing separate
hierarchy terms, **not coefficients transferred to this FP8/FP32 wafer model**.
[DRAMPower's documentation](https://github.com/tukl-msd/DRAMPower) requires a
command trace and memory specification for command energy. The
[imec connectivity report](https://www.imec-int.com/en/articles/path-high-density-front-and-backside-wafer-connectivity)
motivates interconnect scaling, but bond pitch alone does not provide this
machine's pad/CDC pJ per bit.

Full application captures have native read atoms and row-class statistics, not
complete independently audited ACT/PRE/REF command logs. A row conflict is not
substituted for a precharge/activation count. Small command-closure fixtures
are not promoted to application energy. Optional command mode requires an audit
receipt bound to the raw result and trace; absent that, DRAM command/state energy
stays in the explicit unknown residual.

### Exact sensitivity boundary

Let `A` be an activity vector, `e` its coefficients, `P` common physical power,
and `R` unmeasured energy. For case `i`,

\[
E_i=\sum_k e_k A_{i,k}+P D_i+R_i.
\]

Here `D` is the drained capture horizon and `T` is output latency. Dynamic
activity covers the complete capture; common physical power is charged through
drain, rather than silently discarding the final credit/drain interval. The
final energy reader at `5807da6` retains the unchanged `0d8ab50` activity vectors
and supplies every coefficient in the exact inequality

\[
EDP_c-EDP_r=\sum_k e_k(A_{c,k}T_c-A_{r,k}T_r)
 +P(D_cT_c-D_rT_r)+R_cT_c-R_rT_r<0.
\]

This covers the entire range of nonnegative link/router coefficients, rather
than choosing a favorable nominal pJ. `edp_range` also computes exact extrema
over an explicitly declared finite coefficient/power/residual box. Such a box
is a sensitivity scenario; it is not an empirical confidence interval without
matching process/macro calibration. Unbounded residuals prevent a total-EDP
guarantee.

| Up-local compared with | Time ratio | Maximum candidate/reference total-energy ratio for EDP benefit |
|---|---:|---:|
| Cold Phase-Split | 0.989157 | **1.010961** |
| Cold historical S1 Reference | 0.777979 | **1.285382** |
| Warm Phase-Split | 0.879442 | **1.137085** |
| Warm historical S1 Reference | 0.726019 | **1.377374** |

Cold Up-local vs Phase-Split deserves particular care: NoC link activity is
0.122232×, router/buffer proxy 0.075307×, and native/HB/SRAM/MAC work is equal,
but **summed context occupancy is 1.068085×**. In a restricted normalized model
where all other activity is equal, let `f_L`, `f_R`, `f_B` and `f_C` be reference
modeled-energy shares of link, router, buffer and incremental context cost.
Then EDP improves if

\[
0.068085 f_C-0.877768 f_L-0.924693(f_R+f_B)<0.010961.
\]

These shares range over the complete nonnegative simplex. They are hypothetical
energy shares, not measured powers or a claim that occupied contexts dissipate
fixed power. The actual implementation retains independent coefficients,
common physical power and residuals instead of forcing this restricted model.

For warm Up-local vs Phase-Split, every covered activity's EDP coefficient is
nonpositive, including context-time. It therefore improves **covered-model EDP
for any shared nonnegative coefficients with positive covered energy**. Historical Reference comparisons
also have nonpositive covered EDP coefficients, even though warm Up-local has
slightly more NoC activity than Reference. This is a robust conditional result,
not proof about omitted ACT/PRE/REF, clock/control/banking or calibrated total
energy. The receipt provides the remaining allowable residual inequality.

## Evidence and research decision

Derived records, raw/audit/source SHA identities, all 16 cluster/phase summaries,
matched tail boundaries and six energy inequalities are in
`artifacts/provenance/competition_energy`. Five targeted remote checks pass:
capacity/half-open timing, real competing grants, units/EDP/residual bounds,
prefix holes and cache-hit readiness. All six application records pass the new
readback. The ordinary physical executor remains unchanged; no full application
was rerun for this analysis.

`energy_bounds.json` is the final drain-aware sensitivity receipt and binds
`analysis.json` by SHA. The latter retains the original complete competition
reconstruction and activity counts; its earlier fixed-power inequalities are
superseded by `energy_bounds.json`. Final targeted checks were repeated after
the energy horizon/invalid-input changes, not as additional unique tests.

Preserve independent vertical service and consumer-local weight execution as
the current best tested organization. Do not infer a new compute hardware
bottleneck from context occupancy alone. The next physical-model requirement is
process/macro calibration plus complete array command/state energy if an absolute
Energy/EDP claim is needed. Fetch Controller and Fragmentation remain deferred.
