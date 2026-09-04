# Hardware workflow and Codex permissions

Real-board operations are performed through `tools/nrf-cmake-sdk`. Read-only source inspection and host tests run in the normal sandbox. USB devices, serial ports, debug probes, vendor programmers, GDB servers, and similar hardware interfaces require Codex tool escalation before they can be used reliably.

Escalation only grants the process access to the host interface. It does not expand hardware authorization. The safety rules in `AGENTS.md` and `PLAN.md` still apply: unattended work may use ordinary application RRAM and RAM through the image guard, reset, halt, and debug operations, but may not mass erase, recover, provision, change protection, update board-controller firmware, or write configuration and one-time regions.

Persistent probe and interface-controller settings form a separate authorization boundary. Changing VCOM routing, HWFC connectivity, MSD exposure, J-Link configuration, or a similar persistent setting requires a new explicit user authorization in addition to tool escalation. A temporary experiment must first save the complete original state below `.work/`, restrict the write to the authorized delta, read back the result, restore in cleanup on both success and failure, and read back the complete original state again. An escalation dialog is not a substitute for this authorization.

Use this sequence:

1. Run source, tool, manifest, ELF, and HEX checks without hardware access.
2. Invoke the applicable public CLI command. If USB, serial, probe IPC, or local-port access is denied by the sandbox, rerun that same command with Codex escalation instead of bypassing the CLI.
3. Keep the safety guard, immutable image snapshot, unique-probe selection, per-probe lock, timeout, process cleanup, and `.work/runs/` report active in the escalated run.
4. Treat an escalation or transport failure as infrastructure evidence. Repair the workflow and rerun it; do not respond with direct vendor erase, recover, or provisioning commands.

For a VCOM token failure, preserve the raw local transcript and classify its byte pattern before retrying. Ordered ASCII with missing groups indicates transport loss rather than a baud-rate mismatch. Check exclusive TTY ownership and the probe's enumerated USB functions. Some J-Link OB configurations expose MSD and VCOM concurrently and are subject to documented packet-size limitations; follow the probe vendor's supported diagnostic path, but do not weaken the exact-token contract or alter persistent probe settings without the separate authorization and restoration procedure above.

Local reports may contain probe identities and device paths. They remain below gitignored `.work/` and must not be copied into tracked documentation, commits, issues, or public artifacts.
