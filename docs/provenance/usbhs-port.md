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
it, and `nrfkit_enable_usb_device(... SOURCE_DIR ...)` permits an explicitly supplied
compatible tree. NrfKit owns only the LM20 glue and target configuration; upstream
CherryUSB is not copied into ordinary project-owned source.

## LM20 wrapper and core facts

The port uses the execution-domain `NRF_USBHS` and `NRF_USBHSCORE` mappings from the
locked device headers. It starts VREGUSB and derives VBUS state from the documented
`VBUSDETECTED`/`VBUSREMOVED` events. The 24 MHz clock, USBHS wrapper, PHY override,
45 us PHY interval, wrapper start task, and 1 ms settling interval were compared with
the versioned NCS v3.4.0 USBHS wrapper. No NCS or Zephyr source participates in the
consumer build.

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

## Validation boundary

The repository gate covers control transfers, high-speed bulk OUT/IN loopback, HID
interrupt OUT/IN, 100 controlled USB resets/reconnects, and a 60-second transfer
stress run while an nrfx TIMER instance remains active for remote wake. Linux
runtime-PM suspend/resume and remote wake require root write access to the device's
sysfs power attributes. A run using `--skip-power` is useful transfer evidence but is
not the M4 low-power exit result.

TinyUSB remains a viable alternative stack because it also has a portable DCD
boundary, but it was not selected for this first port. Maintaining two USB stacks
before one LM20 implementation has complete device and low-power evidence would add
parallel integration surface without strengthening the hardware facts.
