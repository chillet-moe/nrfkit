# Contributing

Read `AGENTS.md`, [`docs/development/PLAN.md`](docs/development/PLAN.md), and `docs/development-inputs.md` before changing the project. `docs/development/PLAN.md` is the normative execution plan; milestone exit conditions are part of the change contract.

Keep consumer configure and build paths offline and independent of west, sysbuild, Devicetree, Kconfig, Zephyr, and an installed nRF Connect SDK. Use target-scoped modern CMake and preserve public API and data compatibility unless a change explicitly permits a break.

Official and third-party inputs require a `docs/provenance/sources.lock` entry with an exact release/commit, upstream path, SHA-256, license, import date, and patch state. Retain valid design comments and license notices. Do not copy generated linker output as an undocumented source.

Run before submitting:

```sh
PYTHONPATH=tools python3 -m unittest discover -s tests/host -v
tools/check-public
git diff --check
```

Real-board work must use `tools/nrfkit` and the hardware workflow. USB, serial, debug-probe, and programmer access requires Codex tool escalation. Persistent probe/controller changes need a separate explicit user authorization. Never infer authorization for mass erase, recover, provisioning, protection changes, controller firmware updates, or configuration/one-time memory writes.

Keep local paths, probe identities, private downstream names, and raw logs in ignored `.local/` or `.work/` files. Commit messages use English Conventional Commits.
