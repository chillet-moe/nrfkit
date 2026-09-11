# LM20 power and oscillator startup

The freestanding runtime calls `nrfkit_platform_init()` after MDK `SystemInit`
and C data initialization, before preinit functions, C++ constructors and `main`.
It enables the main DC/DC converter and the 8 KiB NVM cache, updates
`SystemCoreClock`, then invokes the initializer supplied by the linked board.
Custom C runtimes must call this function at the equivalent point.

`NrfKit::board_nrf54lm20dk` configures the DK's internal HFXO and LFXO capacitor
loads, respectively 15 pF and 17 pF, from the chip's factory trim values. It does
not start either crystal. A requested or running crystal retains its configuration;
a bootloader must establish the same board configuration before starting clocks,
or stop them before handing off. A custom board can provide `nrfkit_board_init()`
without linking the DK target. Applications linking only the SoC have no oscillator
load configuration supplied by the SDK.

## Authority and comparison

The authority is **nRF54LM20A/nRF54LM20B Datasheet v1.0**, SHA-256
`03a834fb52be8cf6248df6f67737f055c035cfb83492d44d58bdc2f0bfa3a3af`:

- §4.2.3: the two-way cache serves instruction and data accesses to NVM. Enable is
  explicit; enabling invalidates cache contents. Writes are write-around and
  invalidate their cache line. This is not a write-back RAM/DMA cache.
- §3.5.2: this device's NVM is RRAM. Executing from RRAM and executing from NVM are
  not two distinct memory choices. An 8 KiB cache does not imply an entire program
  is resident; hot code and data compete for lines.
- §5.7.1: normal operation supports DC/DC, with the specified external components.
  Startup uses a fallback regulator until software enables `VREGMAIN.DCDCEN`.
  VREGMAIN supplies the SoC except the separately VBUS-supplied USB PHY (§5.8).
  `DCDCEN=1` is an enable request, not independent proof of inductor detection.
- §5.5.1–5.5.2: configure oscillator capacitors before starting crystals, using
  device-specific FICR trim and the documented equations.
- §11.1 and §11.2.1.4: the 2.4 mA CoreMark table entry assumes 3 V, 25 °C, DC/DC,
  cache, idle peripherals and the specified RAM configuration. The cover lists
  2.6 mA. Neither figure specifies current for an arbitrary USB/radio application
  or the entire DK.

The versioned software comparison is NCS v3.4.0's Zephyr commit
[`bf801e4e3d19e1ffa76164346480cb7734dd2800`](https://github.com/nrfconnect/sdk-zephyr/tree/bf801e4e3d19e1ffa76164346480cb7734dd2800):
`soc/nordic/nrf54l/soc.c` supplies cache, regulator and oscillator initialization;
`boards/nordic/nrf54lm20dk/nrf54lm20_a_b_cpuapp_common.dtsi` specifies the DK's
loads and DC/DC mode. These remain read-only references, never build inputs.
The locked nrfx v4.5.0 MDK `SystemInit` does not supply these three defaults.

## Capacitor arithmetic discrepancy

The locked nrfx commit `1b7bedb5c7f379a3ec3ece851796e94d7e5d0b2c` provides
`NRF_OSCILLATORS_LFXO_CAP_CALCULATE` in `hal/nrf_oscillators.h` and the HFXO
calculation in `bsp/stable/soc/nrfx_soc_defines.h`. The LFXO macro shifts the
slope term before multiplication and both macros extract signed slope as unsigned.
They must not be used for this board initialization.

A minimal numeric reproduction with FICR slope=0, offset=0 and LFXO=17 pF gives
`(392 >> 9) * 22 + (0 >> 6) = 0` from the nrfx macro, whereas the datasheet gives
`round(22 * 392 / 512) = 17`. With HFXO=15 pF, slope=-1 encoded as 511, offset=0,
the macro gives 48 whereas the documented signed calculation rounds to 29.
These are arithmetic test vectors, not claims about a manufactured chip's trim.

The board implementation uses the datasheet equations with integer arithmetic,
sign extension and rounding only after summation, as in the NCS reference. Host
tests compare against independent rational arithmetic across every nine-bit slope
encoding and representative offsets, and verify that active crystal loads remain
unchanged. No upstream file is modified.

## Other power responsibilities

| Area | Ownership and audit result |
| --- | --- |
| PLL/core frequency | MDK selects 128 MHz by default; existing official frequency override remains available. SDC requires 128 MHz. |
| FICR trim, startup errata, RRAM sleep | MDK retains these operations. Default RRAM power-off in System ON idle adds the documented wake latency. |
| Constant latency | Required during RADIO activity by anomaly 20. MPSL callbacks retain/release it and restore RRAM low-power state; it must not be forced off during wireless work. |
| Clock requests | Drivers and MPSL own their requests. Startup does not acquire permanent HFXO, LFCLK or USB clock requests. |
| RAM sections | Application/linker lifetime determines which sections may be powered down or retained. Startup cannot infer unused memory safely, including stacks, DMA, Controller and boot handoff storage. |
| Peripherals and GPIO | Application must uninitialize unused peripherals, release clock requests, and use appropriate pin electrical states. Blindly disabling peripherals at handoff breaks ownership. |
| Idle CPU | Application must use an interrupt/event-safe sleep loop; a busy main loop remains an active workload even with no radio traffic. |
| Debug/System OFF | Debug interface mode changes sleep behavior. True System OFF wake remains an open hardware gate. |

The [revision-matched errata audit](lm20-errata.md) still applies, especially
20, 30, 37, 39, 47 and 63. No new cache/DC/DC workaround appears in the two locked
errata documents. Standalone low-temperature GRTC behavior remains unverified;
room-temperature CoreMark does not establish temperature coverage.

Nordic's [Designing low-power Bluetooth LE products course](https://academy.nordicsemi.com/courses/designing-low-power-bluetooth-le-products/)
is a useful workflow guide; the versioned datasheet remains the source of register
and electrical requirements.
