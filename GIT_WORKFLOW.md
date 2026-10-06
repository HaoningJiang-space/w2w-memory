# Git workflow

The research repository is **private**:
[HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory).
Preserve the original upstream history; do not force-push or rewrite shared
research commits.

## Workspaces and remotes

| Workspace | Location |
|---|---|
| Local | `/Users/haoning/project/w2w/nw-design-for-wsi` |
| Experiment server | `wangziheng@eex005:/home/wangziheng/Video/w2w-memory` |

Both existing workspaces retain `origin` for
`https://github.com/spcl/nw-design-for-wsi.git` and use `research-origin` for
`https://github.com/HaoningJiang-space/w2w-memory.git`.
Their default push remote is `research-origin`.

The active/default research branch is `research/bounded-bank-sharing`.
`research/memory-on-logic-gate` preserves the earlier Gate state.
The original upstream commit is `9470042fb2d8b5368556e46cc75ac818dbf31522`.

For a fresh clone, Git initially names the research remote `origin`; use these
commands to establish the same naming convention:

```sh
git clone https://github.com/HaoningJiang-space/w2w-memory.git
cd w2w-memory
git remote rename origin research-origin
git remote add origin https://github.com/spcl/nw-design-for-wsi.git
git config remote.pushDefault research-origin
```

## Publish and synchronize

Review the working tree and stage explicit files. Keep source changes and
experiment provenance in commits. Push the active research branch:

```sh
git status --short --branch
git diff --check
git push research-origin research/bounded-bank-sharing
```

On eex005, inspect the working tree first, then synchronize without discarding
uncommitted work:

```sh
git fetch research-origin
git switch research/bounded-bank-sharing
git merge --ff-only research-origin/research/bounded-bank-sharing
git rev-parse HEAD
git status --short --branch
```

Use existing GitHub CLI/keychain credentials locally. Do not copy credentials
to the server or put them in remote URLs. If the private GitHub repository is
not accessible from eex005, transport already-published commits using an
incremental Git bundle through the authorized interactive PowerIC connection.
Verify the bundle, fetch its branch, merge with `--ff-only`, and verify that
the local, GitHub and server commit IDs match. Bundle files belong in ignored
`build/`, not in tracked history.

## Experiment artifacts

Commit source, tests, methods, reports, compact results and publication figures.
Keep `.venv/`, `build/`, `memory_results/`, login files and credentials out of
Git. The full result directories remain on both existing workspaces; a fresh
clone must reproduce or separately retrieve them using the documented commands.

Each experiment records its exact code commit, working-tree status, package
versions and result hashes. Later documentation commits do not change the
recorded experiment commit. Run appropriate checks after code changes; a
documentation-only publication does not require repeating experiments.
