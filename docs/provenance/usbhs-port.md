# nRF54LM20 USBHS port evidence

The nRF54LM20 USBHS device port is a project-owned CherryUSB DWC2 glue layer. Its
design authority is ordered as follows:

1. the nRF54LM20 product specification, errata, and reproducible silicon behavior;
2. the DWC2 hardware capability registers and USB protocol behavior observed on the
   target;
3. the public CherryUSB porting contract and the pinned release's current DWC2 ports;
4. Nordic's versioned NCS implementation as comparison evidence, not as the hardware
   specification.

This ordering is intentional. Vendor libraries can contain useful sequencing and
workarounds, but a disagreement about register meaning, timing, reset, or memory is
resolved against the device documentation and a minimal real-board reproduction.

## CherryUSB port contract

The implementation follows CherryUSB's [porting guide](https://cherryusb.readthedocs.io/en/latest/quick_start/transplant.html)
and [port API](https://cherryusb.readthedocs.io/en/latest/api/api_port.html):

- `usb_dc_low_level_init()` owns clocks, PHY/wrapper setup, and interrupt setup;
- the hardware interrupt dispatches `USBD_IRQHandler(busid)` with the actual bus ID;
- `usb_dc_low_level_deinit()` is the symmetric teardown path;
- `dwc2_get_user_params()` supplies a copied, target-specific DWC2 parameter record;
- DMA buffers and the generated CherryUSB configuration use the target's four-byte
  alignment contract.

Initialization does not require VBUS to be present. `nrfkit_usbhs_connect()` records
a connection request and either connects immediately or defers it until the
documented VBUS-detected interrupt, so firmware can boot before a cable is attached.

The glue structure and parameter-copy pattern were compared with the pinned v1.6.1
`usb_glue_esp.c`, `usb_glue_hc.c`, `usb_glue_kendryte.c`,
`usb_glue_nation.c`, and `usb_glue_st.c` ports. These are implementation examples,
not substitutes for LM20 facts. The application uses one endpoint maximum packet per
unframed bulk OUT arm, following CherryUSB's documented device API behavior.

CherryUSB is pinned as an immutable submodule. Consumer configure does not download
it, and the explicit example helper `nrfkit_example_usb(... SOURCE_DIR ...)` permits an explicitly supplied
compatible tree. NrfKit owns only the LM20 glue and target configuration; upstream
CherryUSB is not copied into ordinary project-owned source.

## LM20 wrapper and core facts

The port uses the execution-domain `NRF_USBHS` and `NRF_USBHSCORE` mappings from the
locked device headers. It starts VREGUSB and derives VBUS state from the documented
`VBUSDETECTED`/`VBUSREMOVED` events. The 24 MHz clock, USBHS wrapper, PHY override,
45 us PHY interval, wrapper start task, and 1 ms settling interval were compared with
the versioned NCS v3.4.0 USBHS wrapper. No NCS or Zephyr source participates in the
consumer build.

On a combined USBHS and SDC/MPSL target, MPSL owns CLOCK. Finalization therefore
selects a different clock path independent of whether the consumer enables USB or
SDC first in CMake: USB initialization retains MPSL, requests HFCLK24M through
`mpsl_clock_hfclk_src_request()`, polls the matching public running query, and
releases both the clock and retain during USB teardown. SDC must be enabled before
USB is initialized, and USB must be deinitialized before its final SDC disable.
This ordering prevents MPSL from being removed while the USB clock is live. A
USB-only target continues to use the documented CLOCK tasks directly and no longer
links the unused nrfx CLOCK ISR.

The DWC2 core identifies a 3040-word SPRAM through `GHWCFG3 = 0x0be0c0e8` on the
validation device. An initial 160-word receive FIFO satisfied CherryUSB's static
minimum but caused repeatable high-speed DMA bulk OUT timeouts. Setting the receive
FIFO to 760 words, 25 percent of the reported SPRAM and the same cap used by Nordic's
versioned implementation, made the same test pass. This value is therefore supported
by both the hardware capability register and real transfer behavior, rather than by
the Nordic implementation alone.

The final device parameters are UTMI 8-bit, device DMA enabled, descriptor DMA
disabled, RX FIFO 760 words, EP0 TX FIFO 16 words, bulk IN TX FIFO 128 words, and HID
IN TX FIFO 64 words. The validation status request exposes the key DWC2 registers and
endpoint-arm results so a failure report remains diagnosable without inventing a new
manual probe procedure.

The validation firmware starts its remote-wakeup delay only after the DWC2 suspend
event. TIMER interrupt context records that the delay expired, while the foreground
loop calls CherryUSB's remote-wakeup API so the lower-priority USBHS interrupt remains
serviceable during the resume signal. A one-shot timer-active state prevents stale
compare events from crossing validation phases, and an explicit cancel request lets
the host establish a reproducible host-resume control phase after an interrupted run.

On Linux, the host gate keeps the HID input node open while enabling runtime wakeup.
This exercises the USB core and `usbhid` remote-wakeup policy instead of assuming that
a successful standard `SET_FEATURE(DEVICE_REMOTE_WAKEUP)` transfer alone proves the
host will arm wake during selective suspend. The structured power report first checks
host-initiated resume and requires the firmware suspend/resume counters to advance
without a configuration-count change. Device-initiated remote wake is a separate
stage with the same no-reset requirement.

## Validation boundary

The repository gate covers control transfers, high-speed bulk OUT/IN loopback, HID
interrupt OUT/IN, 100 controlled USB resets/reconnects, and a 60-second transfer
stress run while an nrfx TIMER instance remains active for remote wake. Linux
runtime-PM suspend/resume and remote wake require root write access to the device's
sysfs power attributes. A run using `--skip-power` is useful transfer evidence but is
not the M4 low-power exit result. A multi-hub validation path has demonstrated clean
host-initiated suspend/resume but reset and re-enumeration after the device asserted
remote wake. That result localizes the remaining failure but is not acceptance
evidence; the final low-power gate must pass on a topology that propagates the resume
signal without resetting the device.

The combined M8 validation image initializes the Multirole Controller before USB
and retains the compiled Timeslot backend. Its guarded hardware run completed 20
USB reset/reconnect cycles and 20.05 seconds of simultaneous control, bulk, and HID
traffic while SDC/MPSL remained initialized. It transferred 57,416,192 bytes in
each bulk direction across 112,141 transfers, with both HID directions completing
and no endpoint-arm error. The local structured report is
`.work/runs/20260905-142022-m4-usb-gate-1056219/run.json`. The power stage was
intentionally skipped; this is coexistence evidence, not remote-wake acceptance.

TinyUSB remains a viable alternative stack because it also has a portable DCD
boundary, but it was not selected for this first port. Maintaining two USB stacks
before one LM20 implementation has complete device and low-power evidence would add
parallel integration surface without strengthening the hardware facts.

## Consumer ownership

The maintained built-in port lives in `src/usb/nrf54l` and is available as
`NrfKit::usb_port`. Consumers may use it or copy and maintain their own port,
linking only one implementation. Core/class selection and USB configuration are
consumer-owned; the former complete-stack target and public configuration helper
have been removed. Examples include their own helper explicitly.

Both paths use public `nrfkit/mpsl.h` for HFCLK24M ownership when explicitly built
in MPSL mode. Existing clock-client lifetime accounting is unchanged. This
ownership refactor adds no hardware evidence or new support claims.
