# Registered real-routing read replays

`flow/` preserves the nine compiled windows and all 48 full-size replay artifacts.
Execution commit: `aa9d91115ceff4458789487d0ed72a2796cd5277`.
`audit.json` was produced on the server with raw-input recompilation enabled;
`replays.csv` contains every registered design/window result.

Raw licensed routing stays on the server. Manifest relative paths preserve the
original `memory_results/pbc_multiwindow` / `memory_results/pbc_corpus256` layout.
Do not interpret missing raw JSON in this Git archive as synthetic data.
Local archive checks omit `--verify-inputs`; server checks include it.

See `docs/reports/PATTERNS_REPLAY_STUDY_REPORT.md` for semantics, limits and commands.
