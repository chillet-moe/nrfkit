---
name: nrf-hardware-workflow
description: Safely run USB, serial, debug-probe, programming, reset, GDB, or real-board operations in nrf-cmake-sdk when Codex sandbox escalation and the repository safety guard are required.
---

# nRF hardware workflow

Before hardware access, read the repository `AGENTS.md`, the relevant `PLAN.md` hardware rules, `docs/development-inputs.md`, `.local/AVAILABLE_INPUTS.md` when present, and `docs/hardware-workflow.md`.

Run host-side source, manifest, ELF, and HEX checks first. Use `tools/nrf-cmake-sdk` for every supported device operation. USB devices, serial ports, probe IPC, GDB server ports, vendor programmers, and real-board debugging require Codex tool escalation; request escalation on the public CLI command before relying on hardware results.

Escalation is host-access permission, not broader hardware authorization. Preserve the image guard, immutable snapshot, dynamic probe selection, per-probe lock, timeout, cleanup, and ignored run report. Never use escalation to mass erase, recover, provision, change protection, update board-controller firmware, or write UICR, SICR, OTP, KMU, Root-of-Trust, BOOTCONF, or other configuration/one-time regions.

If the public workflow fails, classify and repair the infrastructure before retrying. A direct vendor command is permitted only during the explicitly allowed P0 bring-up described by `PLAN.md`; any successful ground-truth command must be encoded, tested, and rerun through the public CLI in the same task.
