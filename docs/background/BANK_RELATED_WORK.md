# Related work and claim boundary (2026-10-06)

This is an evidence audit, not proof that no prior work studies our exact
combination. In particular, SiloBreaker needs a full-paper comparison before
any novelty claim. Do not replace that comparison with an inferred negative.

| Work and primary source | Evidence checked | Consequence for this project |
|---|---|---|
| [SeDRAM, Electronics 2023](https://www.mdpi.com/2079-9292/12/5/1077) | Describes heterogeneous DRAM/logic wafer-level HB and independent bank/channel control; interface position matters. | HB DRAM and bank parallelism are established. Our 32-bank parameters are illustrative, not extracted from a fabricated SeDRAM instance. |
| [SiloBreaker, author publication list](https://fengbintu.github.io/publications/) and [IEEE record](https://ieeexplore.ieee.org/document/11704829) | Authors/title/TCAD 2026 verified on the author's page. IEEE full text was inaccessible through this session. | Treat resource-silo mitigation and architecture/scheduling as a direct novelty threat. Detailed router/mapping mechanisms described by the user remain pending primary full-text verification; do not assert it lacks geometric co-design. |
| [H2EAL, author preprint](https://arxiv.org/html/2508.16653v1) | Sections IV-B and IV-C discuss memory/compute co-placement, interleaved KV storage and heterogeneous mapping. | Data placement and load balancing are prior art. They must be controlled in our evaluation. |
| [H2-LLM, ISCA 2025 author PDF](https://chenzhangsjtu.github.io/files/2025-H2_LLM_ISCA25.pdf) | Abstract/introduction explicitly co-explore HB architecture and dataflow, including controller-area/computation/bandwidth tradeoffs. DOI 10.1145/3695053.3731008. | It would be inaccurate to characterize all HB prior work as software on an immutable architecture. Our proposed distinction is the repeated-reticle/whole-wafer geometric constraint, not hardware co-design in general. |
| [Exploiting Similarity Opportunities…, ISCA 2024 official slides](https://www.iscaconf.org/isca2024/slides/isca2024-Exploiting%20Similarity%20isca2024-Opportunity%20of%20Emerging%20AI%20Models%20on%203D%20Hybrid%20Bonding%20Architecture.pdf) | Page 13 visually checked: distributed vs unified controller, merging distributed I/O, crossbar area overhead. | A bank-pooling crossbar is not a new idea. Do not reuse its area percentages as costs for our unsynthesized circuit. |
| [Wafer-scale network paper](https://arxiv.org/html/2603.05266v1), [source repository](https://github.com/spcl/nw-design-for-wsi) | Placement/overlap-derived network connectivity and repeated-template assumptions; first Gate audited code and Table 1. | Reuse geometry; our extra layer is constrained bank exposure and fixed-data service, not another radix study. |
| [CPSIA, Micromachines 2024](https://www.mdpi.com/2072-666X/15/5/557) | Cross-process DRAM/HB/logic signal-integrity analysis, including driving-buffer and vertical-path models. | SI is existing work and outside this functional Gate. This simulation provides no signoff claim. |
| [Micron WoW disclosure US20240420757A1](https://patents.google.com/patent/US20240420757A1/en) | Earlier audit found fine-grained interface, sense-amplifier/LIO placement and redistribution examples. | Supports investigating granular interfaces; does not establish inexpensive or feasible reticle-wide bank sharing. Patent embodiments are not fabrication measurements. |
| [Flexible Queueing Architectures](https://arxiv.org/abs/1505.07648) | Sparse flexibility graphs and resource pooling in a queueing framework. | Theoretical inspiration for expansion/cuts. Asymptotic results do not prove our 32-bank/four-port masks are expanders or near-optimal. |

## Safe working motivation

WoW placement can expose one compute reticle to several memory reticles, but
usable access depends on which banks each overlapping interface exposes and
where required data resides. We study that composition under repeated-template
and bounded-interface constraints. Existing evidence motivates this question;
it does not establish a priority claim for the proposed synthesis problem.

Workload imbalance is a condition under which pooling might help. It is not
our discovery. The current synthetic active sets cannot establish that a real
wafer-scale workload supplies enough such imbalance.

## Manufacturing qualification

Repeated identical templates are an explicit design/manufacturing constraint
adopted here, following the upstream study. They are not a universal assertion
that every wafer-scale process forbids multiple masks, stitching, mixed
reticles or edge-specific designs. Conventional die-scale designs also have
strong physical constraints; the distinguishing feature here is the shared
template decision coupling many interfaces across the wafer.
