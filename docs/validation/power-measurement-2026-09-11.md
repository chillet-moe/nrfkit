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

The instrument reported `calibrated=0` and missing calibration coefficients, so
the decoder used recorded defaults. The approximately 315 µA idle reading is not
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
