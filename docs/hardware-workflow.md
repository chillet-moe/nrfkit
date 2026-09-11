# Hardware workflow and Codex permissions

Real-board operations are performed through `tools/nrfkit`. Read-only source inspection and host tests run in the normal sandbox. USB devices, serial ports, debug probes, vendor programmers, GDB servers, and similar hardware interfaces require Codex tool escalation before they can be used reliably.

Escalation only grants the process access to the host interface. It does not expand hardware authorization. The safety rules in `AGENTS.md` and [`docs/development/PLAN.md`](development/PLAN.md) still apply: unattended work may use ordinary application RRAM and RAM through the image guard, reset, halt, and debug operations, but may not mass erase, recover, provision, change protection, update board-controller firmware, or write configuration and one-time regions.

Persistent probe and interface-controller settings form a separate authorization boundary. Changing VCOM routing, HWFC connectivity, MSD exposure, J-Link configuration, or a similar persistent setting requires a new explicit user authorization in addition to tool escalation. Every change must first save the complete original state below `.work/`, restrict the write to the authorized delta, and read back the result after the controller re-enumerates. A temporary experiment must restore in cleanup on both success and failure and read back the complete original state again. An intentionally persistent change is allowed only when the user explicitly names the desired final state; record that state in the ignored local inventory and require a new authorization to reverse it. An escalation dialog is not a substitute for this authorization.

Use this sequence:

1. Run source, tool, manifest, ELF, and HEX checks without hardware access.
2. Invoke the applicable public CLI command. If USB, serial, probe IPC, or local-port access is denied by the sandbox, rerun that same command with Codex escalation instead of bypassing the CLI.
3. Keep the safety guard, immutable image snapshot, unique-probe selection, per-probe lock, timeout, process cleanup, and `.work/runs/` report active in the escalated run.
4. Treat an escalation or transport failure as infrastructure evidence. Repair the workflow and rerun it; do not respond with direct vendor erase, recover, or provisioning commands.

For a VCOM token failure, preserve the raw local transcript and classify its byte pattern before retrying. Ordered ASCII with missing groups indicates transport loss rather than a baud-rate mismatch. Check exclusive TTY ownership and the probe's enumerated USB functions. Some J-Link OB configurations expose MSD and VCOM concurrently and are subject to [documented packet-size limitations](https://kb.segger.com/J-Link_OB). For a confirmed affected probe that does not need drag-and-drop programming, SEGGER's supported workaround is to keep MSD disabled; J-Link debug and VCOM remain available. Do not weaken the exact-token contract or alter a persistent setting without the separate authorization procedure above.

`tools/nrfkit probe-msd disable` is the repository-owned persistent workaround. It is fixed to backup, `MSDDisable`, reboot, and verification of MSD absence plus J-Link and dual VCOM presence. It refuses to write without `--authorize-persistent-change`. `probe-msd enable` is the symmetric recovery operation and requires a new authorization. Neither command exposes arbitrary J-Link configuration.

For the P0 oracle matrix, `tools/nrfkit p0-gate` treats an already-disabled MSD interface as the preferred no-mutation state and verifies the required J-Link and dual-VCOM contract through every child operation. If MSD remains enabled, the gate gives an actionable persistent-workaround message. Its optional temporary compatibility path remains fixed to disable, reboot, verify, run the public child gates, enable, reboot, and verify; its final report must show `probe_msd_restored: true` before that temporary experiment is considered safely complete.

For the standalone SDK, `sdk manifest` accepts the versioned default LM20 application layout or a validated consumer-owned layout emitted by the target. It derives the programming allowlist only from ordinary application RRAM and excludes declared settings and scratch reservations. The resulting guarded manifest is consumed by `inspect`, `flash`, `run`, and `gdb-smoke`. `m2-gate` is the aggregate acceptance entry point used by the opt-in CTest `hardware` test. It performs 20 exact build-ID program/reset/token cycles, the Reset Handler/main/single-step/RAM/observable-variable GDB contract, and deliberate HardFault capture. Its `finally` path always runs the guarded normal-image workflow; the gate is successful only when that recovery emits the expected normal boot token. CTest supplies a per-board `RESOURCE_LOCK` and an outer timeout, while every child retains its own probe lock, timeout, immutable snapshot, and structured run report.

Local reports may contain probe identities and device paths. They remain below gitignored `.work/` and must not be copied into tracked documentation, commits, issues, or public artifacts.

The M5 direct-radio work left a reusable two-device executor. M7 must resolve the
LM20 and laboratory peer independently, validate each chip and image range, acquire
a separate lock for each probe, start the receiver before the transmitter, apply a
hard timeout to both processes, and terminate both process groups on every exit.
Reports use only neutral roles; any private peer name, local source path, probe
identity, or raw transcript stays in ignored local storage. The first new PHY gate
is 4 Mbit/s in both directions for three rounds. The existing 2 and 1 Mbit/s profiles
are compatibility and diagnostic baselines, not substitutes for that gate.

Before any SDC/MPSL hardware operation, its locked nrfxlib
README, API documentation, integration notes, release notes, component manifests,
license, attribution, and documented resource requirements must be read and reduced
to a source-located resource/ABI contract. The host gate must check archive/header
identity, target, security domain, float ABI, ELF attributes, unresolved symbols,
alignment, final memory map, and every documented peripheral/IRQ/priority/clock/
lifecycle constraint. Do not use repeated flashes to discover a documented rule.

The completed M6 SDC oracle and consumer lifecycle reuse the same public manifest, inspect,
safe-flash, serial/HCI, GDB, timeout, lock, process cleanup, and structured-report
machinery. Multirole is tested first; Peripheral-only and Central-only then repeat
their valid HCI subsets. A minimal MPSL substrate is necessarily active before SDC,
but direct RADIO access is forbidden outside an MPSL-granted Timeslot whenever MPSL
owns the documented resources. The gate additionally records lifecycle re-entry,
actual Controller memory, final map/ELF RAM budget, Controller-buffer canaries, stack
watermark, persisted fault state, both connection roles, disconnection, and both raw
ACL directions. M7 exercises Timeslot grant, blocked, cancel, extend, deadline, and
teardown behavior with SDC-disabled lifecycle, advertising, and a connection.
`tools/nrfkit m7-radio-dual` runs the direct or Timeslot two-endpoint profiles;
`tools/nrfkit m7-coexistence` starts the sequence-gated peer first and then composes
the SDC oracle. Its PASS requires both raw ACL and a peer-received private packet
from the connected-stage burst. Both commands reject a shared probe and clean up the
receiver process group on failure. Electrical power is a separate instrumented gate;
firmware duty counters are not accepted as current or energy measurements. Export
instrument captures to normalized `time_s,current_a` CSV and run
`tools/nrfkit m7-power-audit` with all seven required profiles, the measured supply
voltage, and the instrument identity. Raw captures and their local paths remain
outside Git; the ignored report retains only their hashes and integrated results.

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

For a consumer image that does not implement the M4 oracle protocol,
`tools/nrfkit consumer-usb-smoke` retains the guarded manifest/program/reset path
but restricts host interaction to standard configuration, interface, and endpoint
descriptor inspection plus ordinary USB reset/re-enumeration. VID, PID, expected
speed, interface count, and reconnect cycles are explicit command inputs. It does
not claim interfaces, send HID reports, or issue vendor requests; selecting standard
configuration 1 is allowed when the host has not already configured the device. This
smoke does not count as remote-wake or electrical-power evidence.

The official S115 reference oracle retains `tools/nrfkit m6-ble-gate`.
Bond-settings operations accept only that official oracle; retired SDK adapter
manifests require the [archived tools](architecture/s115-archive.md).
The gate uses the BlueZ D-Bus API
directly and never starts an interactive `bluetoothctl` session. Every D-Bus
operation has a finite timeout, failed pairing is cancelled, the exact test
device is disconnected and removed, and an optional `btmon` process is wrapped
in an outer hard timeout and process-group cleanup. `--hci-trace` is diagnostic
only: lack of permission is recorded and never blocks a phase that firmware
events and functional results can prove. The gate has no sudo mode and never
runs `timeout`, `btmon`, or `btmgmt` as root.

BlueZ `Pairable=false` and privileged controller-bondable helpers are retired.
They remain historical infrastructure evidence only and must not be retried or
treated as a completion gate. These Host-oriented tools are not the raw-HCI SDC M6
gate and must not be reused as if they were.

`tools/nrfkit m6-ble-scan` is the bounded advertising-only host gate. It uses
the BlueZ system D-Bus API, requires exactly one powered adapter, and accepts a
result only after observing both the requested device name and RSSI. On every
exit it stops discovery if it started discovery, removes the matching unpaired
device object, or accepts BlueZ's `DoesNotExist` race only when a final object
manager read independently confirms absence. It is a host validation tool, not
a project-owned BLE stack.

The retained P2 and P3 evidence used the L15 laboratory central in
`tests/hardware/m6-s145-central`. It is built only by the explicit official
reference workflow against the locked nRF-BM release and L15-specific S145; it
does not enter the consumer build. Its profiles explicitly select legacy/LESC,
bonding, I/O capability, and both key-distribution directions. A profile passes
only when the actual SoftDevice `AUTH_STATUS` line matches the expected bond,
LESC, encryption, and negotiated-key fields. The reconnect profile additionally
uses Peer Manager's live connection-security status to distinguish a stored-key
procedure from fresh pairing.

For any explicitly requested historical replay in a multi-probe setup, resolve the local LM20/L15 aliases from the ignored
inventory, then pass both probe identities explicitly. Never rely on enumeration
order. Each child operation must still validate PCA10184 versus PCA10156, audit
the SoC-specific image ranges, and acquire its own probe lock. This retained S115
route is stopped and must not run as part of the current goal.

The optional [OpenOCD backend](architecture/openocd-backend.md) supports an external
CMSIS-DAP probe without the board's J-Link/VCOM. Use its guarded backup before
replacing an image that must be restored. [PPK2 acquisition](provenance/ppk2-acquisition.md)
is exposed through `tools/nrfkit ppk2 info`, `power`, and `capture`. Instrument
settings require a known DUT supply topology and voltage; entering source mode is
not a substitute for checking the physical power connection. Cold-start measurement
must occur after the debug server exits, with no new debug attachment during capture.
