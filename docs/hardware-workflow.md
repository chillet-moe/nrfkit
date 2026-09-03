# Hardware workflow and Codex permissions

Real-board operations are performed through `tools/nrf-cmake-sdk`. Read-only source inspection and host tests run in the normal sandbox. USB devices, serial ports, debug probes, vendor programmers, GDB servers, and similar hardware interfaces require Codex tool escalation before they can be used reliably.

Escalation only grants the process access to the host interface. It does not expand hardware authorization. The safety rules in `AGENTS.md` and `PLAN.md` still apply: unattended work may use ordinary application RRAM and RAM through the image guard, reset, halt, and debug operations, but may not mass erase, recover, provision, change protection, update board-controller firmware, or write configuration and one-time regions.

Use this sequence:

1. Run source, tool, manifest, ELF, and HEX checks without hardware access.
2. Invoke the applicable public CLI command. If USB, serial, probe IPC, or local-port access is denied by the sandbox, rerun that same command with Codex escalation instead of bypassing the CLI.
3. Keep the safety guard, immutable image snapshot, unique-probe selection, per-probe lock, timeout, process cleanup, and `.work/runs/` report active in the escalated run.
4. Treat an escalation or transport failure as infrastructure evidence. Repair the workflow and rerun it; do not respond with direct vendor erase, recover, or provisioning commands.

Local reports may contain probe identities and device paths. They remain below gitignored `.work/` and must not be copied into tracked documentation, commits, issues, or public artifacts.
