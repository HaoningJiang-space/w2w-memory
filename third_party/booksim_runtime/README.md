# Bundled optimized BookSim runtime

All project changes required by the system simulator now live in **w2w-memory**.
No checkout of `wafer_simulator` is needed to build or run the default backend.

- The unchanged author BookSim fork already lives at `rapidchiplet/booksim2`.
  Its 143-file snapshot matches `spcl/nw-design-for-wsi@9470042` byte for byte.
- The two patches and `native/` are copied unchanged from
  `HaoningJiang-space/wafer_simulator@0c56c24`. They contain the selected native
  optimizations, persistent protocol and finite supply/commit hooks.
- `w2w/network/native_booksim/` contains that revision's Python online/boundary
  interface with local imports. Only the configuration writer and small IO/type
  helpers were extracted from its dependencies; another system scheduler is not included.
- `include/nlohmann/json.hpp` is the pinned single header needed to build;
  its upstream commit and source hashes are in `manifest.json`.

BookSim's copyright/license remains in `rapidchiplet/booksim2/LICENSE.md` and
individual sources. JSON retains `JSON-LICENSE.MIT` and its header notice.
These files do not relicense upstream code. The wafer project's original files
have no separate root license in the imported revision; their provenance and
existing notices are retained.

Builds apply patches to a **new external copy**, preserving the historical base.
Use `tools/build_native.py`; the build manifest records inputs, commands,
compiler, W2W commit and binary hashes. Binaries, environments and raw traces
are not versioned. Subsequent native changes belong in this repository.
