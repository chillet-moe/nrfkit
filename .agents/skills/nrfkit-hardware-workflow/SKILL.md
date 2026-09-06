---
name: nrfkit-hardware-workflow
description: Safely run USB, serial, debug-probe, programming, reset, GDB, or real-board operations in nrfkit when Codex sandbox escalation and the repository safety guard are required.
---

# nRF hardware workflow

Before hardware access, read the repository `AGENTS.md`, the relevant [`docs/development/PLAN.md`](../../../docs/development/PLAN.md) hardware rules, `docs/development-inputs.md`, `.local/AVAILABLE_INPUTS.md` when present, and `docs/hardware-workflow.md`.

Run host-side source, manifest, ELF, and HEX checks first. Use `tools/nrfkit` for every supported device operation. USB devices, serial ports, probe IPC, GDB server ports, vendor programmers, and real-board debugging require Codex tool escalation; request escalation on the public CLI command before relying on hardware results.

Escalation is host-access permission, not broader hardware authorization. Preserve the image guard, immutable snapshot, dynamic probe selection, per-probe lock, timeout, cleanup, and ignored run report. Never use escalation to mass erase, recover, provision, change protection, update board-controller firmware, or write UICR, SICR, OTP, KMU, Root-of-Trust, BOOTCONF, or other configuration/one-time regions.

Persistent probe or interface-controller settings are a separate authorization boundary. VCOM, HWFC, MSD, J-Link, and similar configuration changes require a new explicit user authorization even when the command already has Codex escalation. Before any change, record the exact original state below `.work/`, constrain the allowed delta, and read it back. Restore and verify the full original state after a temporary change. A persistent change is allowed only when the user explicitly names that final state; record it as expected local state, verify it after the controller reboots and re-enumerates, and require a new explicit authorization to reverse it. Do not treat a request to approve tool escalation as approval for the configuration change.

If the public workflow fails, classify and repair the infrastructure before retrying. A direct vendor command is permitted only during the explicitly allowed P0 bring-up described by [`docs/development/PLAN.md`](../../../docs/development/PLAN.md); any successful ground-truth command must be encoded, tested, and rerun through the public CLI in the same task.
