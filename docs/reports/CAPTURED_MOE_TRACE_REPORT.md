# Complete captured MoE routing and long-request execution

## Complete capture restoration

The current imported evidence is **256 real Qwen3-235B-A22B-FP8 requests** from
the previously authorized Patterns Behind Chaos corpus. It is not generated
expert routing and is not the old two-layer route-reuse proxy. The source
dataset records each request's selected expert IDs by layer/token, including
prefill followed by decode. It does not supply hardware timestamps or model
activations. [Author dataset card](https://huggingface.co/datasets/core12345/MoE_expert_selection_trace).

| Coverage | Imported and independently compared to raw capture |
|---|---:|
| Independent requests | 256 |
| Original layers per request | 94 |
| Request-layer histories | 24,064 |
| Prefill tokens across requests | 10,460 |
| Decode tokens across requests | 32,768 |
| Ranked expert assignments across all phases/layers | 32,507,456 |
| Dropped layers / prefill tokens / decode tokens | 0 / 0 / 0 |

Every source-manifest request is processed, not just a favorable expert set.
Prefill keeps its full token-selection matrix; decode keeps all 128 captured
steps. The dataset's capture horizon is not evidence of generation after its
last step. Layer keys, expert rank order, request identities and all token
boundaries remain intact. There is no repeated request, cross-layer substitution
or route padding. The 256 requests cover the eight subjects in the original
manifest; this is complete coverage of that archived corpus, not the entire
199 GB public dataset or all MoE models.

`workloads/moe_trace.py` hashes each original file before import. A separate
readback compares **every original selection** to the normalized record, rather
than validating only counts/digests produced by the importer. The directed
negative replaces layer-1 selections with layer-0 and updates normalized
hashes; the raw comparison still rejects it. Source hashes, pinned model
config, complete normalized-file identities and coverage audit are archived in
`artifacts/provenance/captured_moe`; raw and normalized captures stay outside Git.

The dataset revision is `27febb7b2d24169560a9f6f83d38eb53f94916cf`. The model
config is separately pinned at `39eb2b067ea6b8e3e1dd97d3cd0c7ffeaf3e1a35`:
hidden 4096, expert intermediate 1536, 128 experts, top-8, 94 layers and
128×128 FP8 quantization groups. No smaller synthetic dimensions are substituted.
[Pinned official model config](https://huggingface.co/Qwen/Qwen3-235B-A22B-FP8/blob/39eb2b067ea6b8e3e1dd97d3cd0c7ffeaf3e1a35/config.json).
The capture does not record the generating checkpoint's Git revision; this
separate configuration pin establishes the declared shape, not equality to an
unrecorded checkpoint revision.

## What is available, and what remains unavailable

The capture contains ranked expert IDs. It does **not** contain router logits,
routing probabilities, token text, activation values, arrival timestamps or
hardware events. Those absent values are never synthesized as captured data.
This interface enables real expert-membership replay; it cannot validate
numerical end-to-end inference or measure the original router/attention runtime.

`captured_moe.py` adds explicit token-to-expert dispatch to the existing gated
expert operations and weighted combine. A shared expert receives its actual
captured token membership for prefill GEMM. Each dispatch/input/result is a real
DataEdge; no free multicast or implicit remote activation alias is introduced.
Gate/Up retain full hidden reductions, SiLU waits for both, and block/partition
sums retain the existing arithmetic order. Combine coefficient transfer uses
an explicit **4 B coefficient-format assumption**, not recorded probabilities
or a numerical uniform-weight substitute. This is **post-router MoE timing**.

The historical `build_moe()` and route-reuse experiments are unchanged. Their
published timing remains a mechanism reference and is not relabeled as the
new real independent-layer study. Whole Transformer attention, KV, norm,
residual, embeddings and mathematical router execution remain absent.

## Registered long-request study

The new runner uses the first request in the existing manifest order:
`Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra/59.json`. Selection precedes
performance measurement. Its real layer `0` and `1` histories are independently
read; all **46 prefill tokens and 128 decode tokens** are retained.

Two cases compare fixed Phase-Split weights with Reference compute and Up-local
compute. Mathematical operations, full 128-expert catalogs, addresses, native
tools, physical topology and budgets are fixed. Dispatch/combine and both
layers' real selections are common. SRAM cache starts empty; no warm preload
or unmeasured migration is introduced. Each case has 258 layer invocations.

Native Ramulator refresh/command/ACK, actual BookSim, finite receiver writes,
two shared-service compute contexts, two coupled fetch slots, round-robin
descriptor issue, 32 outstanding descriptors/cluster and contiguous operands
remain active. This is a long formal workload, not a few-token smoke result.
The background controller runs cases serially to bound host memory, retains
failures without automatic retries, and invokes a separate saved-result reader.
That reader checks all task completions, actual dispatch membership, each
independently captured layer/phase, arithmetic work, cache/resource conservation,
native bytes, pressure and complete drain. It accepts observed cache/traffic
differences and negative performance outcomes.

The formal run is **pending**, with no new makespan or speedup published here.
Execution source, registration, launch identity and latest verified status are
stored in the provenance directory. Code publication does not imply completion.
The saved status at **2026-10-11 13:06:42 UTC** verifies the Reference worker and
its actual BookSim child are running; no case completion existed. The second
case and independent readback follow serially. Each case registers **139,449
tasks**; neither discards the original prefill or decode phases.

## Why this is not a 94-layer Native application result

Two original expert catalogs occupy 4,833,017,856 B and fit the declared 8 GiB
DRAM. All 94 occupy 227,151,839,232 B, **211.552 GiB**, before attention and other
parameters. That cannot fit this physical machine. The lowering checks actual
bank-group address capacity; it does not shrink expert matrices, invent DRAM
capacity or reuse one layer's weights as another's.

Consequently the complete 94-layer routing *capture* and the selected-two-layer
complete-request *execution* are separate deliverables. The latter omits 92
execution layers and no captured request tokens. It must not be presented as
complete Qwen3 inference. A full-model physical experiment requires a declared
adequate storage/streaming organization and the missing non-MoE execution
semantics; that is a separate architectural extension, not a longer smoke test.

## Reproduction on hn072

The isolated root is
`/Projects/haoning/w2w-full-system-vertical-delivery-20261011`.
Source `3233bb3` imported and read back the complete corpus; source `a708d50`
freezes the serial formal controller, saved-result reader and corrected full
registration. The initial `2b01f4c` preparation rejected a serialized task-field
name before Native execution; its log and partial input are retained. Eight relevant
directed source tests pass, including full catalog/dispatch/layer namespace
checks. They establish interface correctness; they do not replace the pending
long Native execution.

```sh
python -m w2w.workloads.moe_trace --manifest /path/to/authorized/manifest.json \
  --config /path/to/pinned/config.json --config-source /path/to/config-source.json \
  --output /outside/git/complete-corpus
python -m w2w.workloads.moe_trace --verify --manifest /path/to/authorized/manifest.json \
  --output /outside/git/complete-corpus
python -m w2w.experiments.run_captured_moe --prepare \
  --corpus /outside/git/complete-corpus --index 0 --layers 0 1 \
  --output /outside/git/full-request
python -m tools.run_captured_moe_study --root /outside/git/full-request \
  --booksim-binary /path/to/frozen/booksim
```

Use the recorded Native environment, not local builds. Full capture coverage,
formal execution completeness and independent physical audit are three distinct
acceptance gates. Do not collapse them into a claim based on a short fixture.
