# LM20 errata audit

Reviewed September 6, 2026 against Nordic's **nRF54LM20A Engineering B Errata
v1.1** and **nRF54LM20A Revision 1 Errata v1.0**, both dated May 12, 2026.
Their SHA-256 identities are respectively
`9b8be128283177004790986362c9bb9df193ce766231574ad0e2df76a60f6bfb` and
`6f04289f56be9dcaa306bdde17722ce2a28dc0a3a28b2e14727d8e237424920e`.
Local document locations and silicon applicability belong in `.local/AVAILABLE_INPUTS.md`.
The matching product documentation takes precedence over software libraries.

This is a scope/ownership audit, not a claim that every anomaly has been reproduced
or validated over temperature and voltage. The two documents list the same 20
inherited anomalies for these revisions. Driver paths below refer to the immutable
nrfx input locked in `sources.lock`.

| ID | Current treatment and remaining constraint |
|---|---|
| 7 | `drivers/src/nrfx_uarte.c` uses the FLUSHRX READY-event workaround. Raw HAL clients must also distinguish an empty FIFO from a valid AMOUNT. |
| 8, 69 | `drivers/src/nrfx_spim.c` contains the dynamic workarounds for MOSI timing and STOPPED after suspend. Do not bypass them with raw transactions. |
| 20 | RADIO TX/RX requires constant latency. MPSL calls the platform low-latency callbacks; direct-radio callers retain their explicit clock/power responsibility. |
| 26 | Mixed-security PPIB/DPPIC routing must use matching channel indices. The current secure-only platform does not establish general mixed-security support. |
| 30 | The errata identifies MPSL/NCS workaround coverage. Locked MPSL is used for combined targets; low-temperature correctness of standalone HFINT/GRTC is not established by room-temperature tests. |
| 37 | Selected `mdk/nrf54l/system_nrf54l.c` applies the documented register workaround in SystemInit. Applications must preserve the delay before System OFF. |
| 39 | `drivers/src/nrfx_clock_xo.c` applies PLL-before-XO ordering. Combined targets use MPSL's clock arbiter rather than loading another CLOCK ISR. |
| 44 | Match-filter DMA AMOUNT is not a valid match offset. Current validation transport does not enable this feature. |
| 47 | Emulated System OFF debug behavior is a documented limitation; an ordinary debug retry is distinct from recover/erase. |
| 49 | Check S1LEN/S1INCL and constant latency for any new radio packet format. Current radio tests do not establish arbitrary packet-format correctness. |
| 50 | RRAM writes do not infer DMA capability from SPU00 PERIPH[11]. No DMA writer is introduced. |
| 54 | SPIS board configuration must give idle SDO a defined electrical state. This is a board/pin constraint, not a universal driver default. |
| 59 | EGU and DPPI channel 0 must have consistent security attribution. Mixed-security operation remains outside this platform's validation. |
| 63 | `runtime/cortex-m/reset.c` enters CONSTLAT before SYSRESETREQ; SDC fatal reset and SDK examples use it. Device CLI defaults to pin reset. Fault handlers must avoid secondary faults/lockup; the diagnostic capture handler is not a proof against arbitrary stack corruption. |
| 102 | CCM MAC length zero is unsupported; do not infer support from the register field. Current BLE controller owns CCM configuration. |
| 104 | Analog-capable pins can short during power-on reset. Board electrical design must tolerate this; software startup cannot prevent it. |
| 105 | Do not disable TWIM mid-transaction while clock stretching. Recovery requires device reset; generic nrfx availability is not proof of safe asynchronous teardown. |
| 111 | SAADC single-ended noise shaping requires the documented restricted input range or differential-mode alternative. Not covered by basic SAADC compile tests. |
| 114 | Wake-on-pin designs must avoid the short DETECT transition sequence or use latched detection. Electrical power validation remains separate. |

## Storage and reset evidence

The RRAM controller's 128-bit write/commit semantics come from the matching
nRF54LM20A product datasheet. The scheduled write budget and retry model are
cross-checked against NCS v3.4.0 `zephyr/drivers/flash/soc_flash_nrf_rram.c` and
`nrf/drivers/mpsl/flash_sync/flash_sync_mpsl.c`; these references are not configure
or build dependencies. See [the resource contract](sdc-mpsl-resource-contract.md).

Anomaly 63 is not resolved by renaming a reset helper: it requires CONSTLAT before
the reset request, keeping interrupt callbacks from releasing it, and pin reset for
the debug control path. The implementation is centralized so application and
platform fatal resets cannot drift into different workarounds.
