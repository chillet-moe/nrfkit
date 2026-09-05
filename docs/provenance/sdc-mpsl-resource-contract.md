# SDC/MPSL resource and ABI contract

This audit applies only to the secure `nrf54lm` hard-float libraries from
sdk-nrfxlib v3.4.0. The exact repository commit, binary-manifest revision,
selected files, archives, and licenses are locked in `sources.lock`. The
machine-readable companion is `m6-sdc-mpsl-contract.json`; host tests reject
source drift, resource-mask drift, ABI drift, or a changed public archive link
closure.

Consumer CMake also validates every selected file in `sources.lock`, including
the complete exposed SDC/MPSL/FEM header set, manifests, licenses, and archives.
`NRFKIT_NRFXLIB_ROOT` explicitly selects an alternative input; otherwise the
package's `external/sdk-nrfxlib` is used. All targets in one build tree use the
same resolved root, including their generated archive records. Git checkouts
must match both the locked HEAD and release tag. Installed packages and source
archives without Git metadata establish input identity through the same file
hashes. Installation ships this selected set and its lock; consumer configure
does not require Python or network access. Changes to selected files trigger
revalidation on the next build.

## Audit scope

The review covered every RST document, changelog, limitation file, public
header, component license, and attribution file in the locked SDC and MPSL
trees. Stable tree digests and file counts make that scope reproducible without
copying the licensed upstream text into this repository. The functional scope
is deliberately smaller: raw Controller HCI and lifecycle, with Multirole
first, followed by the Peripheral-only and Central-only variants. ISO, Channel
Sounding, FEM, coexistence, radio notification, and Timeslot APIs were reviewed
for closure and future resource conflicts but are not enabled by the first M6
configuration.

## Fixed LM20 resource boundary

While MPSL is initialized, the application must treat GRTC channels 7 through
11, TIMER10, TIMER20, ECB00, RADIO, CLOCK, TEMP, DPPIC10 channel 0, DPPIC20
channel 0, PPIB11 channel 0, and PPIB21 channel 0 as owned. SDC adds CCM00,
AAR00, RRAMC, DPPIC10 channels 1 through 11, DPPIC00 channels 1 and 3, and
PPIB00/PPIB10 channels 0 through 3 while the Controller is enabled. Restricted
radio resources may only be touched during a granted Timeslot; direct-RADIO
ownership from M5 is therefore mutually exclusive with an active MPSL/SDC
configuration.

RADIO_0, TIMER10, and GRTC_3 bind the public MPSL handlers at priority 0. The
clock interrupt is forwarded below priority 0. The initial low-priority choice
is SWI00 (IRQ 28) at priority 4, matching the locked official integration, but
it remains an explicit platform resource rather than a hidden library default.
The low-priority interrupt only schedules work: `mpsl_low_priority_process()`
must execute promptly in serialized thread context and must not run directly in
the software interrupt.

## Clock, latency, and lifecycle

Before `mpsl_init()`, the platform must run GRTC with SYSCOUNTER enabled and run
the CPU at 128 MHz. The LF clock must be reported at 500 ppm or better. An RC
source requires calibration at least every eight seconds; the initial design
will use the documented 4-second check and every-second-check calibration
defaults. HFXO latency is an explicit, auditable value and may not be set below
measured worst case. The locked header offers 1400 microseconds as its
worst-case preset.

MPSL is non-reentrant. Initialization and all low-priority SDC/MPSL APIs must be
serialized. MPSL starts before SDC; feature selection and SDC resource
configuration precede enable; entropy is registered before enable. Disable is
synchronous. MPSL is uninitialized only after SDC is disabled and every retained
SDK client is released. Retained clients currently include the radio and storage Timeslot sessions and
the USBHS HFCLK24M request on a combined target. The latter uses MPSL's public clock
arbiter; linking the nrfx CLOCK driver into the same target is forbidden because
both would define and control the CLOCK interrupt.

RRAMC has a narrower lifecycle boundary. SDC owns it while the Controller is
enabled, and the MPSL low-latency callbacks access its power configuration while
MPSL is initialized. A combined binary may include the nrfx RRAMC driver for normal
application persistence, but direct application RRAMC operations must complete
before MPSL initialization or after SDC is disabled, every retained client is
released, and deferred processing has uninitialized MPSL. Configuration-region and
one-time writes remain outside this contract.

Active MPSL persistence instead uses `nrfkit_enable_rram()` and the SDK's private
storage Timeslot session. The platform configures two session contexts before
opening either client. A request copies at most 256 bytes and commits one 128-bit
unit per 600 us grant (500 us per line plus 100 us slack, matching NCS v3.4.0
`zephyr/drivers/flash/soc_flash_nrf_rram.c` and
`nrf/drivers/mpsl/flash_sync/flash_sync_mpsl.c`). Blocked requests retry at high
priority as in that reference. CONFIG, POWER.CONFIG and READYNEXTTIMEOUT are
restored; LOWPOWERCONFIG remains owned by MPSL's callbacks. A stalled controller
resets before the grant expires. A two-second scheduling deadline uses the running
GRTC counter with BUSY/overflow synchronization, without taking a compare channel; DWT is not reserved for this client.
Failure preserves the caller's dirty state; preceding units may already be written.

The public `m7_timeslot_validation` fixture and `m6-sdc-oracle --rram-check`
validate scratch writes during advertising and an active BLE connection alongside
eight-grant RADIO bursts and bidirectional raw ACL. The September 6, 2026 local
run `20260906-020419-m6-sdc-oracle-6jc6bhfz` passed both write/readback checks. This does not add power-loss atomicity or
replace the separate paired-board air gate.

The platform must implement both nRF54L low-latency callbacks. They coordinate
CPU constant-latency operation and RRAM latency as one nested/coalesced
contract: back-to-back critical work may omit an intermediate release. Both
MPSL and SDC fault callbacks can run from any context after interrupts have
been disabled. They must persist bounded diagnostics and reset; returning is
not an accepted recovery path.

## Memory, HCI, and ABI

SDC resource configuration is queried before enable. The supplied buffer must
cover the returned size, use 8-byte alignment, retain canaries for bounded
runtime verification, and appear in the final map and RAM report. The HCI and
entropy callbacks run in the same serialized context as MPSL low-priority
processing. A Controller signal drains non-blocking `sdc_hci_get()` until it
returns no packet; ACL input/output remains raw HCI rather than a hidden Host.

All four archives are ELF32 little-endian Arm EABI hard-float objects for
Armv8-M Mainline, with VFP-register argument passing and 8-byte stack alignment.
MPSL advertises FPv5/FP-D16; the three SDC variants advertise VFPv4-D16. This is
not a soft/hard-float mismatch: both use the hard-float procedure-call standard,
and Armv8-M FPv5 implements the required VFPv4 instruction subset. The
difference remains an explicit final-link audit item. The archive undefined
symbol sets are recorded without interpreting or publishing obfuscated private
symbols; all named external symbols must close against the selected MPSL and
the two platform low-latency callbacks.

## Official oracle build evidence

The locked NCS v3.4.0 `hci_uart` oracle now builds through the public reference
workflow for `nrf54lm20dk/nrf54lm20a/cpuapp`. Its configuration and final map
are checked on every build for the secure hard-float Multirole SDC archive and
the matching hard-float MPSL archive; Peripheral-only, Central-only, and Zephyr
Link Layer archives are forbidden. The generated manifest also records H4 on
VCOM1 at 1 Mbaud with hardware flow control and confines the image to ordinary
application RRAM.

The version-locked NCS MPSL integration source binds the public TIMER0, RTC0,
and RADIO entry points to LM20 TIMER10, GRTC_3, and RADIO_0 respectively. The
final map contains all three wrappers and handlers. The generated final ISR
table leaves ECB00 IRQ 75 and TIMER20 IRQ 202 on `z_irq_spurious`; neither has
an application-facing MPSL handler or a registered oracle ISR. This closes the
previous ambiguity: those two peripherals remain MPSL-owned resources, but the
standalone platform must not invent or register handlers for them.

The guarded board gate now passes on LM20. A raw Host issues HCI Reset, reads
Controller version plus classic/LE features, initializes a static random test
address, and explicitly enables the global LE Meta bit and LE Advertising
Report bit restored to defaults by Reset. The Controller's advertisement is
observed by BlueZ, then the Controller scans a process-owned temporary BlueZ
advertisement. Both directions are over-the-air observations rather than only
successful command status. The temporary host advertisement, Controller
advertising/scanning state, VCOM descriptor, and probe lock are bounded and
cleaned up. The final HCI report is
`.work/runs/20260905-034804-m6-sdc-oracle-699276/run.json`.

The independent locked Arm GDB gate also resets into the same official image,
stops at `main`, single-steps, reads CPUID, detaches, and verifies that the GDB
server exits. Its final report is
`.work/runs/20260905-034827-gdb-smoke-699428/run.json`.

## Standalone completion evidence

The pure-CMake platform maps every requirement ID to target ownership checks,
platform code, link/map checks, and bounded runtime observations. Each guarded
manifest records the exact selected archives, resource list, final map hash, ELF
RRAM bytes, initialized/static RAM, the 16 KiB reserved stack, total RAM reservation,
and remaining RAM headroom. Final total RAM reservations are 30613 bytes for
Multirole, 28509 bytes for Peripheral-only, and 28601 bytes for Central-only.

The validation firmware performs enable, disable, and re-enable before accepting
HCI traffic. Its test-only diagnostic command reports the exact configured Controller
memory requirement (3312, 1496, and 1520 bytes respectively), stack watermark,
persisted SDC fault state, UART state, ACL submission result, and both Controller
buffer canaries. The final three-run matrix observed a 1168-byte stack high-water
mark for every archive, intact canaries, and no fault. The report IDs are:

- Multirole: `20260905-044042-m6-sdc-oracle-732900`,
  `20260905-044051-m6-sdc-oracle-732993`, and
  `20260905-044105-m6-sdc-oracle-733099`;
- Peripheral-only: `20260905-044129-m6-sdc-oracle-733295`,
  `20260905-044133-m6-sdc-oracle-733368`, and
  `20260905-044140-m6-sdc-oracle-733443`;
- Central-only: `20260905-044153-m6-sdc-oracle-733549`,
  `20260905-044159-m6-sdc-oracle-733622`, and
  `20260905-044208-m6-sdc-oracle-733704`.

Multirole proves both roles, both locally initiated disconnections, Controller-to-Host
and Host-to-Controller raw ACL, and all baseline HCI commands. Each role-only archive
proves its applicable subset. The independent final GDB report ID is
`20260905-044223-gdb-smoke-733811`. No Host, ATT/GATT, profile, Zephyr component,
or S115 shim enters these images.

## M7 Timeslot closure

The project-owned Timeslot backend retains MPSL independently of SDC, uses one of the platform-owned static
session contexts, requests guaranteed-XTAL normal-priority grants, and arms the MPSL
TIMER0 cleanup compare before calling application code. RADIO ownership exists only
inside a grant. Deadline, END, extension failure, overstay, invalid return, blocked,
cancelled, idle, and asynchronous close paths all converge on bounded cleanup before
MPSL can be uninitialized.

The startup lifecycle gate closes and reopens a session while SDC is disabled, then
tests extension after SDC re-enable without mixing that lifecycle probe with RADIO
work. Explicit advertising and active-connection commands run finite eight-grant
4 Mbit BT=0.6 bursts. A blocked or cancelled request consumes a 16-attempt retry
budget and is resubmitted from serialized foreground context. Three paired-board
runs received the active-connection sequence 15 with zero loss or invalid payload
while raw bidirectional ACL remained live. Detailed rate, latency, negative, soak,
scheduling, and remaining electrical-power evidence is in
[`m7-radio-evidence.md`](m7-radio-evidence.md).

The bounded request/ACK fixture treats only the immediately previous committed
sequence as a duplicate. It replays that ACK without advancing completion or channel
state twice. Every retry run suppresses one post-commit ACK to force this path; the
current image passed the three-round gate and a 20-round soak with zero client drops.

## M8 combined-consumer checkpoint

The source-tree and installed-package fixtures now link one C++23 LM20 target with
CherryUSB HID, Multirole SDC/MPSL, the Timeslot backend, and nrfx RRAMC while all
NCS/Zephyr environment paths are deliberately invalid. Both USB-first and SDC-first
CMake declaration orders select the MPSL HFCLK24M path. The same work found and
closed two previously hidden integration defects: the freestanding `string.h`
prototype was not valid C++, and USB unnecessarily linked the nrfx CLOCK ISR beside
MPSL's handler.

A fresh local clone at the current public commit, populated with exactly the three
locked submodule commits, independently configured and linked the same combined
C++23 consumer and remained clean afterward. This closes the SDK-checkout half of
M8 reproducibility without treating the still-read-only downstream checkout as
validated.
