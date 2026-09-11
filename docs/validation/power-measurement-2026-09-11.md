# LM20 power measurement evidence — 2026-09-11

The LM20B DK completed cold-started System ON idle and direct-RADIO transmitter
captures through the guarded OpenOCD and PPK2 workflows. These are **uncalibrated
fixture estimates**, not SoC specification values or M7 power acceptance.

## Method and results

PPK2 source output was configured to 3.0 V and read back before enabling it. The
DK SoC supply jumper was removed; DK USB remained connected and CMSIS-DAP provided
SWD, reference, ground and nRESET without supplying the target. Programming and
verification preceded a PPK2 power cycle. No debug session ran during acquisition;
post-capture GDB inspected retained RAM while PPK2 kept the target powered.

Samples used the nominal 100 ksample/s timebase. The first second was excluded
from each mean below; the remaining windows include all workload activity and
sleep. No idle subtraction or range-switch smoothing was applied.

| Workload | Averaging window | Mean current estimate | Mean power at configured 3.0 V |
| --- | --- | ---: | ---: |
| System ON WFE | 1–5 s | 314.71 µA | 0.944 mW |
| Direct TX, 1 Mbit/s | 1–10 s | 890.93 µA | 2.673 mW |
| Direct TX, 2 Mbit/s | 1–10 s | 713.22 µA | 2.140 mW |
| Direct TX, 4 Mbit/s BT=0.6 | 1–10 s | 616.25 µA | 1.849 mW |

Each transmitter schedules 16-byte packets every 10 ms at 0 dBm and 2416 MHz.
CPU polling during HFXO startup and TX is included; the CPU sleeps and HFXO stops
between packets. Post-capture state was stage 1 with packet counters consistent
with continued 100 Hz execution and no valid fault-record magic. This supports
transmitter execution, not reception or an independently measured RF data rate.
At the scheduled 100 Hz rate, total fixture energy per interval is approximately
26.73, 21.40 and 18.49 µJ respectively, including baseline and clock startup.

The instrument reported missing calibration coefficients, so the decoder used
recorded defaults. The `calibrated=0` field alone is not a reliable factory-
calibration verdict. The approximately 315 µA idle reading is not
an established SoC baseline. Board/debug connections and supply arrangement are
part of the measured fixture. Voltage is a configured value, not a measured rail.
Raw range-switch peaks are retained and must not be treated as calibrated peaks.
Sample counter continuity passed; its modulo-64 limitation still applies.

## Unfinished gates

Two 10-second System OFF runs did not show the expected 5-second GRTC wake
transition. Post-capture debug attachment observed reset reason `DIF` (0x400),
not a proven GRTC wake. Both compare-IRQ variants behaved this way. The public
probe retains the locked official compare-IRQ configuration; no causal fix or
successful real System OFF wake is claimed.

OpenOCD programming/readback, double-read backup, restoration and post-cold-start
GDB attach/read passed. The wired pin-reset request did not restart the CPU in
this fixture. Reset-dependent main/step/watchpoint validation remains open.

The seven-workload M7 gate still needs calibrated measurements, retry traffic,
BLE idle/active coexistence and matching peer evidence. These direct-TX captures
do not replace those workloads. USB remote wake also remains a separate gate.

## Artifact identity and restoration

| Target | Captured ELF SHA-256 |
| --- | --- |
| `power_idle` | `925b5c7344109a0bfbf367166445e4adb0195a899e73cbe6a592ee388e5f445d` |
| `power_radio_1m` | `23151cb31a0ae205a100e70c5d412ea2beb1977cff0ce1a272435917e10565ea` |
| `power_radio_2m` | `1f68d7ca1b8479070beec7f4f984bca2ac28f83d94aab50209fc48ff64e0e47d` |
| `power_radio_4m` | `8d0d2c896ddb33116c93601ab723859afa4bdb507e5d43a38c29fce72407178e` |

Ignored local receipts bind captures to immutable programming snapshots, target
identity, raw samples, calibration metadata, CSV hashes and post-capture reads.
The pre-test firmware and ordinary RRAM settings were restored from double-read
backups with byte verification. No configuration/one-time regions or persistent
probe settings were changed. The bounded PPK2 supply session turns output off at
completion.

## CoreMark and startup audit

A separate bare-metal port of official EEMBC CoreMark commit
`1f483d5b8316753a742cbf5590caf5bd0a4e4777` ran unchanged algorithm sources with
10,000 iterations, performance seeds and a 2,000-byte workload. LLVM Release
`-O3`, 128 MHz, RRAM execution, GRTC timing and RAM-only reporting were used;
USB, UART and wireless were not initialized. The workload ran for approximately
20.9 seconds, then stopped HFXO and slept. Means below use only seconds 1–10.

| Configuration | CoreMark iterations/s | Mean current estimate |
| --- | ---: | ---: |
| Cache enabled, DC/DC disabled | 478.56 | 9.394 mA |
| Cache enabled, DC/DC enabled manually | 478.48 | 2.858 mA |
| SDK platform defaults, no application enable calls | 478.17 | 2.852 mA |

All three runs passed CoreMark validation with final CRC `0x988c`. This is a
local compiler/port comparison, not an EEMBC-certified score or a reproduction
of Nordic's compiler and RAM configuration. Post-run GDB for the SDK-default
image confirmed cache=1, DCDCEN=1, CPU=128 MHz and RRAM idle mode=PowerOff.
HFXO/LFXO capacitor codes were 41/22, matching the observed factory trims.
INDUCTORDET read zero even with DCDCEN=1 and the large current reduction; this
unresolved observation is not presented as positive converter-status proof.

The earlier idle/RADIO table predates this initialization correction and is not
a measurement of the new defaults. See the [startup audit](../provenance/lm20-power-startup.md)
for authority, the missing defaults, oscillator arithmetic and remaining power
responsibilities. The SDK-default CoreMark ELF SHA-256 is
`9e3561460d185bd4cec5f2f3601a7a47f25e2c9c0d1bfb6a44f1b4e109584406`.

The corrected defaults and finite transmitter profiles were subsequently measured
with [packet counts, burst timing and electrical windows](wireless-power-2026-09-11.md).
