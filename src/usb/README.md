# Built-in LM20 CherryUSB port

`NrfKit::usb_port` is the SDK's optional built-in CherryUSB DWC2 port. Its
INTERFACE sources compile in each firmware's own configuration. The target
provides the LM20 DCD initialization wrapper, clock/power/VBUS glue, SDK headers,
and nrfx headers. It does not choose a USB core, classes, descriptors, FIFO layout,
or clock ownership mode.

The consumer supplies one compatible CherryUSB core/class implementation,
`usb_config.h`, and the CherryUSB `common`, `core`, and `port/dwc2` include paths.
The SDK examples demonstrate this in `examples/common/usb/reference.cmake`.

A project that needs to modify the port can copy `nrf54l/usb_dc.c`,
`nrf54l/usb_glue_dwc2.c`, and `include/nrfkit/usbhs.h` from the SDK (the header path
is relative to the repository root), then maintain a local INTERFACE target with
its own sources and include paths. Link that target **instead of**
`NrfKit::usb_port`; no path override, namespace replacement, or SDK fork is needed.
Keep the BSD-3-Clause license and SPDX notices, and record the source commit for
future manual updates. CherryUSB's DWC2 source is separate and retains its own
upstream license and attribution.

When SDC/MPSL is initialized in the image, explicitly define
`NRFKIT_USBHS_MPSL_CLOCK=1` for the firmware and link an SDC variant. The port uses
public `nrfkit/mpsl.h` requests that retain MPSL while USB holds HFCLK24M. Initialize
SDC before USB; release USB resources before final shutdown. Do not substitute
raw MPSL clock calls that bypass the SDK's client lifetime accounting. Standalone
images omit this macro and use direct clock control.

`NRFKIT_USBHS_DEVICE_TX_FIFO_WORDS` in `usb_config.h` configures EP0 through EP15
in words; omitted entries are zero-initialized. Match the configuration to the
endpoint descriptors and LM20 FIFO capacity. Modifications to a copied port and
its configuration are owned and validated by the consumer. See
`docs/provenance/usbhs-port.md` for existing hardware evidence and limitations.
