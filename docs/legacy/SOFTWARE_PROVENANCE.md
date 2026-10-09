# Retained software provenance

The original repository was `https://github.com/spcl/nw-design-for-wsi`.
Its artifact, authorship and reports remain at `v2-frozen-37400e6`.
`REMOVED_SOURCE.json` inventories removed paths. Software origin does not make
that project's machine assumptions the basis of Architecture V3.

BookSim remains the fork pinned at 9470042fb2d8b5368556e46cc75ac818dbf31522.
Original bytes/licenses remain under `third_party/booksim2/`; project patches
and IPC are under `booksim_runtime/`. The manifest records upstream/intermediate
origins, hashes and namespace migration. Topology/config export was replaced;
router, arbitration and credit algorithms were retained.

Ramulator is pinned at 72427a1bba3771564c4fb0e494ba02242fd1eaa7.
Its license remains under `third_party/licenses/`; project RWDL/refresh/bridge
sources remain in Git. JSON header authorship/MIT license remain beside the
header. Historical netrace and DELVE license texts remain in the legacy license
index with their original path hashes.

RTL-owner and `wafer_simulator` working directories were not modified or removed.
