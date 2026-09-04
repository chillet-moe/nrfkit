# Agent instructions

- Read `PLAN.md` completely before changing this project. It is the normative execution plan.
- Before environment, reference-build, or hardware work, read `docs/development-inputs.md` and the local `.local/AVAILABLE_INPUTS.md` when it exists.
- Keep the public repository downstream-neutral. Never add private downstream names, product names, local paths, probe serial numbers, or raw private logs to files, commits, issues, artifacts, or release notes.
- Normal application RRAM and RAM operations are allowed only through the planned safety guard. Never write UICR, SICR, OTP, Root-of-Trust data, KMU slots, BOOTCONF, debug protection, or erase protection in unattended work.
- Never run mass erase, recover, protection-setting, provisioning, or board-controller firmware update commands without a new explicit user authorization.
- Never change persistent probe or interface-controller settings, including VCOM, HWFC, MSD, or J-Link configuration, without a new explicit user authorization. Back up the exact original state, constrain and read back every change, and restore and verify the original state after a temporary experiment.
- Startup, vector, `SystemInit`, memory maps, linker layouts, errata, and binary wireless ABI must remain traceable to versioned official sources. Do not guess missing hardware facts.
- The consumer build must not depend on west, sysbuild, Devicetree, Kconfig, Zephyr, an installed NCS tree, or network access during CMake configure.
- Official west/Zephyr/sysbuild flows are permitted only behind the explicit opt-in reference-tool commands defined by `PLAN.md`. Normal configure, build, and test commands must not prepare or mutate an official SDK tree.
- Use the repository-owned validated device workflow whenever it supports an operation. Direct vendor-tool commands are limited to bringing up a missing workflow, must be recorded as ground truth, and must then be encoded and rerun through the repository tool before repeated use.
- Treat tooling failures as infrastructure failures: repair and test the tool instead of repeatedly bypassing it with manual programming, serial, or GDB commands.
- Use target-scoped modern CMake. Do not introduce global compiler flags or a replacement configuration language.
- Hardware support is not complete until the specified real-board tests pass. A compile-only result must be labeled accordingly.
- Codex sandbox access is insufficient for USB, serial, debug probes, vendor programmers, and real-board debugging. Use the repository hardware workflow and request tool escalation before the first such operation; escalation is an execution requirement, not authorization for any operation forbidden by this file or `PLAN.md`.
- Preserve unrelated changes. Use English Conventional Commits if creating commits.
