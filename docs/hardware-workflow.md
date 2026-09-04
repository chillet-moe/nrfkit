# Hardware workflow and Codex permissions

Real-board operations are performed through `tools/nrfkit`. Read-only source inspection and host tests run in the normal sandbox. USB devices, serial ports, debug probes, vendor programmers, GDB servers, and similar hardware interfaces require Codex tool escalation before they can be used reliably.

Escalation only grants the process access to the host interface. It does not expand hardware authorization. The safety rules in `AGENTS.md` and `PLAN.md` still apply: unattended work may use ordinary application RRAM and RAM through the image guard, reset, halt, and debug operations, but may not mass erase, recover, provision, change protection, update board-controller firmware, or write configuration and one-time regions.

Persistent probe and interface-controller settings form a separate authorization boundary. Changing VCOM routing, HWFC connectivity, MSD exposure, J-Link configuration, or a similar persistent setting requires a new explicit user authorization in addition to tool escalation. Every change must first save the complete original state below `.work/`, restrict the write to the authorized delta, and read back the result after the controller re-enumerates. A temporary experiment must restore in cleanup on both success and failure and read back the complete original state again. An intentionally persistent change is allowed only when the user explicitly names the desired final state; record that state in the ignored local inventory and require a new authorization to reverse it. An escalation dialog is not a substitute for this authorization.

Use this sequence:

1. Run source, tool, manifest, ELF, and HEX checks without hardware access.
2. Invoke the applicable public CLI command. If USB, serial, probe IPC, or local-port access is denied by the sandbox, rerun that same command with Codex escalation instead of bypassing the CLI.
3. Keep the safety guard, immutable image snapshot, unique-probe selection, per-probe lock, timeout, process cleanup, and `.work/runs/` report active in the escalated run.
4. Treat an escalation or transport failure as infrastructure evidence. Repair the workflow and rerun it; do not respond with direct vendor erase, recover, or provisioning commands.

For a VCOM token failure, preserve the raw local transcript and classify its byte pattern before retrying. Ordered ASCII with missing groups indicates transport loss rather than a baud-rate mismatch. Check exclusive TTY ownership and the probe's enumerated USB functions. Some J-Link OB configurations expose MSD and VCOM concurrently and are subject to [documented packet-size limitations](https://kb.segger.com/J-Link_OB). For a confirmed affected probe that does not need drag-and-drop programming, SEGGER's supported workaround is to keep MSD disabled; J-Link debug and VCOM remain available. Do not weaken the exact-token contract or alter a persistent setting without the separate authorization procedure above.

`tools/nrfkit probe-msd disable` is the repository-owned persistent workaround. It is fixed to backup, `MSDDisable`, reboot, and verification of MSD absence plus J-Link and dual VCOM presence. It refuses to write without `--authorize-persistent-change`. `probe-msd enable` is the symmetric recovery operation and requires a new authorization. Neither command exposes arbitrary J-Link configuration.

For the P0 oracle matrix, `tools/nrfkit p0-gate` treats an already-disabled MSD interface as the preferred no-mutation state and verifies the required J-Link and dual-VCOM contract through every child operation. If MSD remains enabled, the gate gives an actionable persistent-workaround message. Its optional temporary compatibility path remains fixed to disable, reboot, verify, run the public child gates, enable, reboot, and verify; its final report must show `probe_msd_restored: true` before that temporary experiment is considered safely complete.

For the standalone SDK, `sdk manifest` accepts only the versioned LM20 application layout and produces the same guarded manifest consumed by `inspect`, `flash`, `run`, and `gdb-smoke`. `m2-gate` is the aggregate acceptance entry point used by the opt-in CTest `hardware` test. It performs 20 exact build-ID program/reset/token cycles, the Reset Handler/main/single-step/RAM/observable-variable GDB contract, and deliberate HardFault capture. Its `finally` path always runs the guarded normal-image workflow; the gate is successful only when that recovery emits the expected normal boot token. CTest supplies a per-board `RESOURCE_LOCK` and an outer timeout, while every child retains its own probe lock, timeout, immutable snapshot, and structured run report.

Local reports may contain probe identities and device paths. They remain below gitignored `.work/` and must not be copied into tracked documentation, commits, issues, or public artifacts.

The M4 USB device gate is `tools/nrfkit m4-usb-gate`. Its default contract performs
100 controlled reconnects, transfer/HID stress, and Linux runtime-PM suspend plus
remote wake. USB access always requires Codex tool escalation. The runtime-PM portion
also needs operating-system root permission to modify the selected device's sysfs
power attributes; Codex escalation does not grant that permission. Run that portion
only in an explicitly approved root-capable environment. `--skip-power` is
development-only and its structured report explicitly records the skipped gate; it
cannot be used as M4 completion evidence. After the transfer gate has programmed and
verified the current image, `tools/nrfkit m4-usb-power` runs the root-required power
contract and writes its own structured report. It first proves an ordinary
host-initiated suspend/resume cycle without reset, then separately arms and checks
device-initiated remote wake. This ordering distinguishes a broken DWC2 resume path
from a remote-wake signal or USB-topology failure. The root environment must provide
PyUSB; do not copy credentials or machine-specific Python paths into repository
documentation.

The M6 host gate is `tools/nrfkit m6-ble-gate`. It uses the BlueZ D-Bus API
directly and never starts an interactive `bluetoothctl` session. Every D-Bus
operation has a finite timeout, failed pairing is cancelled, the exact test
device is disconnected and removed, and an optional `btmon` process is wrapped
in an outer hard timeout and process-group cleanup. `--hci-trace` is diagnostic
only: lack of permission is recorded and never blocks a phase that firmware
events and functional results can prove. The gate has no sudo mode and never
runs `timeout`, `btmon`, or `btmgmt` as root.

BlueZ `Pairable=false` and privileged controller-bondable helpers are retired
from the M6 route. They remain historical infrastructure evidence only and must
not be retried or treated as a completion gate.

`tools/nrfkit m6-ble-scan` is the bounded advertising-only host gate. It uses
the BlueZ system D-Bus API, requires exactly one powered adapter, and accepts a
result only after observing both the requested device name and RSSI. On every
exit it stops discovery if it started discovery, removes the matching unpaired
device object, or accepts BlueZ's `DoesNotExist` race only when a final object
manager read independently confirms absence. It is a host validation tool, not
a project-owned BLE stack.

P2 and P3 instead use the L15 laboratory central in
`tests/hardware/m6-s145-central`. It is built only by the explicit official
reference workflow against the locked nRF-BM release and L15-specific S145; it
does not enter the consumer build. Its profiles explicitly select legacy/LESC,
bonding, I/O capability, and both key-distribution directions. A profile passes
only when the actual SoftDevice `AUTH_STATUS` line matches the expected bond,
LESC, encryption, and negotiated-key fields. The reconnect profile additionally
uses Peer Manager's live connection-security status to distinguish a stored-key
procedure from fresh pairing.

In a multi-probe setup, resolve the local LM20/L15 aliases from the ignored
inventory, then pass both probe identities explicitly. Never rely on enumeration
order. Each child operation must still validate PCA10184 versus PCA10156, audit
the SoC-specific image ranges, and acquire its own probe lock. The fixed order is
plaintext, L15-driven legacy/no-bond, L15-driven LESC/no-bond, bonding, BlueZ HID,
then persistent encrypted reconnect. Normal bonding, HID and persistence remain
subject to the BlueZ interoperability gate even when the L15 security oracle
passes.
