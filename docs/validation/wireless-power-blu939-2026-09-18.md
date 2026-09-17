# BLU939 timed transmitter power captures — 2026-09-18

Four finite nRF54LM20B DK transmitter workloads were repeated with BLU939 at a
configured 3.0 V and nominal 100 ksample/s. Each cold-start capture contains
1,800,001 samples over 18 seconds. Firmware inspection during the powered hold
confirmed stage 2, the expected packet and batch counts, and the expected timing
range for every workload. The original application RRAM was restored from a
double-read backup and verified after the tests; every supply session requested
output off during cleanup.

These results are a cross-instrument repetition of the earlier PPK2 direct-RADIO
workloads. They still do not complete the seven-workload M7 electrical gate: no
idle baseline, Timeslot retry, BLE-only, or BLE-plus-Timeslot capture was made.

## Results

All packets carry 16 application payload bytes at 0 dBm and 2416 MHz. The traffic
window uses the same current-edge locator and unfiltered integration method as the
[earlier PPK2 capture](wireless-power-2026-09-11.md). BLU939 and GRTC do not share
an electrical trigger, so burst boundaries remain estimates.

| Profile | Confirmed packets / batches | Mean active time | Traffic-window mean current / energy | Approximate active-window mean current / energy |
| --- | ---: | ---: | ---: | ---: |
| 1 Mbit/s periodic | 1000 / 1000 | 548.470 us | 0.399 mA / 11.957 mJ | 3.756 mA / 6.423 uJ |
| 2 Mbit/s periodic | 1000 / 1000 | 451.066 us | 0.339 mA / 10.158 mJ | 3.113 mA / 4.483 uJ |
| 4 Mbit/s periodic | 1000 / 1000 | 398.142 us | 0.305 mA / 9.156 mJ | 2.667 mA / 3.361 uJ |
| 4 Mbit/s burst | 6400 / 100 | 6536.180 us | 0.489 mA / 14.664 mJ | 4.500 mA / 88.561 uJ |

The complete 18-second means were 0.358, 0.326, 0.305 and 0.410 mA respectively.
The periodic edge locator matched all 1000 scheduled batches for each PHY, and the
burst locator matched all 100 batches.

## Measurement limits

The instrument returned all six resistance/offset pairs and the decoder applied
them exactly as the manufacturer conversion path does. Its separate `Calibrated`
metadata field was `0`; the manufacturer path does not consult that field, so this
record is retained but is neither promoted to a calibration claim nor treated as
proof that the returned coefficients are invalid.

The raw unfiltered traces contain small negative readings near zero: 40,962,
35,835, 27,806 and 3,154 samples respectively. The minimum was approximately
-1.23 uA. These values were preserved and integrated without clipping. Peak
samples were approximately 7.0–7.4 mA, but range transitions and the absence of an
independent voltage measurement mean they are not advertised as radio-only peaks.
BLU939 records also have no sequence counter; complete four-byte framing cannot
prove continuity.

Raw samples, normalized CSV, firmware hashes, instrument metadata, guarded flash,
GDB observations, backup and restore receipts remain in the ignored local run
directory. No device identity, local path, or raw private log is published here.
