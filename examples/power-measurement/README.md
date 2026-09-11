# Power measurement firmware

These LM20 DK programs leave UART, USB, LEDs and DWT tracing uninitialized.
They expose state in RAM for inspection **after** the electrical capture. They
have real-board idle and direct-TX captures; automatic System OFF wake remains
unverified. See the [results](../../docs/validation/power-measurement-2026-09-11.md). None of these programs completes the M7 seven-workload power gate.

| Target | Workload | Post-capture state |
| --- | --- | --- |
| `power_idle` | System ON WFE loop after normal startup | `nrfkit_power_stage = 1` |
| `power_system_off` | Cold start, System OFF with retained marker, GRTC wake about 5 s later, System ON WFE | Stage 2 and `nrfkit_power_reset_reason` containing GRTC, without DIF |
| `power_radio_1m` | Direct RADIO 1 Mbit/s periodic TX | Stage 1, increasing `nrfkit_power_packets` |
| `power_radio_2m` | Direct RADIO 2 Mbit/s periodic TX | Same |
| `power_radio_4m` | Direct RADIO 4 Mbit/s BT=0.6 periodic TX | Same |

The radio profiles use 16 payload bytes, 0 dBm, 2416 MHz and 10 ms scheduled
packet spacing. They use the same packet/address/CRC/whitening configuration as
the existing direct-RADIO link validation. CPU polling during HFXO startup and
TX is included in the measurement; HFXO is stopped and the CPU sleeps between
packets. They measure a specified transmitter workload, not receiver delivery,
retry energy, BLE coexistence, or an optimized lower bound. A missed scheduling
deadline is a failure, not silently shifted traffic.

System OFF follows the locked nRF54LM20A/B Datasheet v1.0 sections 5.2 and 8.11.2:
clear RESETREAS, stop HFXO, program GRTC while active, then release the active
request and wait for RTCOMPARESYNC before entering OFF. WAKETIME uses its maximum
8-bit value, 255 LFCLK ticks (about 7.8 ms); TIMEOUT is 257 ticks. The program needs
no compare IRQ after reset. RAM retention protects only the section containing
the phase marker. Stages 101 and above identify failed preconditions; a hard
fault/assert record also invalidates a run. A debugger attached during sleep
can cause emulated OFF, and starting a debug session can itself wake the device.
Stage 2 alone is consequently insufficient evidence of genuine OFF.

Build with the normal example CMake configuration, selecting the targets above.
Before programming, generate each manifest explicitly:

```sh
tools/nrfkit sdk manifest --build-dir <build> --target power_radio_4m \
  --expected-token unused-power-capture
```

The manifest CLI still requires a token field, but these programs emit no serial
token and must not be passed to the UART-based `run` gate. Use the guarded
[OpenOCD workflow](../../docs/architecture/openocd-backend.md) to back up the union
of all ranges that will be overwritten, flash, verify, and later restore them.

For the normal DK configuration, follow the official
[external SoC supply with DK functionality](https://docs.nordicsemi.com/r/bundle/ug_nrf54lm20_dk/page/ug/nrf54lm20_dk/hw_desription/direct_supply.html):
remove the P14 jumper, keep J3/J4 supplying the DK before enabling P14 power, and
use the allowed external voltage. The debugger's voltage reference is not a DK
power source. The alternative stand-alone configuration requires the documented
resistor routing; it is unnecessary when using the powered-DK configuration.

For programming, keep a bounded `tools/nrfkit ppk2 power --state on --duration 120
--voltage-mv <voltage>` session open while using OpenOCD. PPK2 stops supplying power
when the serial connection closes. After flashing, disconnect the debug session
and allow the supply session to finish. Keep DK power present. Cold-start and
capture using `tools/nrfkit ppk2 capture --power-cycle --voltage-mv <voltage>
--manifest <manifest> --label <workload> --duration 10 --hold-after 30`.
The post-capture hold preserves RAM for inspection before automatic output-off
cleanup. For System OFF, inspect only after the automatic wake and capture have
finished; the capture must include both the OFF interval and wake transition.

Record firmware hash, supply setup, instrument calibration status, capture
timestamps and post-capture fault/stage/counter observations together. Confirm
radio packet counts against the actual elapsed interval and use a receiver when
claiming delivery. Preserve raw captures and the original firmware backup in the
ignored workspace. See the [PPK2 acquisition contract](../../docs/provenance/ppk2-acquisition.md)
for sample continuity and voltage/calibration limitations.
