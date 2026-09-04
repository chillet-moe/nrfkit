# SDC/MPSL resource and ABI contract

This audit applies only to the secure `nrf54lm` hard-float libraries from
sdk-nrfxlib v3.4.0. The exact repository commit, binary-manifest revision,
selected files, archives, and licenses are locked in `sources.lock`. The
machine-readable companion is `m6-sdc-mpsl-contract.json`; host tests reject
source drift, resource-mask drift, ABI drift, or a changed public archive link
closure.

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
synchronous. MPSL is uninitialized only after SDC is disabled and every
Timeslot session is closed.

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

## Remaining M6 evidence

This contract is the input to implementation, not board-completion evidence.
The next gate is guarded oracle flash plus raw HCI and GDB observation, followed
by mapping every requirement ID to standalone CMake ownership checks, platform
code, link/map checks, and bounded runtime observations. No repeated board trial
is an acceptable substitute for a documented source-level mapping.
