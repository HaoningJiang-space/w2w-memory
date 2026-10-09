# Frozen V2 evidence

`v2-frozen-37400e6` preserves the complete V2 source tree, historical commands,
Network Design artifact, licenses, selected results and native provenance.
The file-level evidence inventory is `artifacts/provenance/v2_freeze/manifest.json`.

Recover into a separate checkout with `git worktree add --detach <directory>
v2-frozen-37400e6`. Use the native identities and server archive paths in the
inventory. No historical experiment has been rerun or rewritten by this freeze.
Raw captures and native builds remain in those isolated server archives.

The 128 B cost experiment is separately frozen at `v2-cost-128-d5674f9`.
Its execution source is d5674f9; its offline analysis source is 6120344.
Its results compare V2 machines and cannot be mixed with V3 machine results.

V3 does not promise compatibility with historical CLI commands. Frozen source
is the reproduction interface. Removing an artifact from the current checkout
neither removes its Git history nor changes attribution for retained code.
