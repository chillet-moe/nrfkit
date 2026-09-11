# Timed transmitter power captures — 2026-09-11

Four finite LM20B DK transmitter workloads completed with DC/DC and NVM cache
enabled by the SDK platform initialization. Every run reached stage 2, with the
expected packet/batch counts and no valid fault-record magic. Ordinary RRAM was
restored from a double-read backup and verified after the tests.

These are **uncalibrated fixture estimates**. PPK2 calibration coefficients are
missing; the recorded decoder defaults and range-switch transients affect both
averages and peaks. They do not complete the M7 electrical acceptance gate.

## Workload and time

All packets carry 16 application payload bytes at 0 dBm, 2416 MHz. Four Mbit/s
uses BT=0.6. A one-byte length field, access address, preamble and CRC are extra
framing, not counted as application data. A two-second firmware delay precedes
traffic; clock/startup time causes this to appear later on the PPK2 time axis.

| Profile | Schedule | Confirmed packets / payload | First active start to last active end | Mean active time per batch |
| --- | --- | ---: | ---: | ---: |
| 1 Mbit/s | One packet every 10 ms, 1000 batches | 1000 / 16,000 B | 9.990532 s | 548.886 µs |
| 2 Mbit/s | One packet every 10 ms, 1000 batches | 1000 / 16,000 B | 9.990435 s | 451.321 µs |
| 4 Mbit/s | One packet every 10 ms, 1000 batches | 1000 / 16,000 B | 9.990380 s | 398.096 µs |
| 4 Mbit/s burst | 64 consecutive packets every 100 ms, 100 batches | 6400 / 102,400 B | 9.906515 s | 6533.210 µs |

Thus a 4 Mbit/s burst sends **1024 payload bytes in about 6.533 ms**, including
clock and software overhead. This is not a 4 Mbit/s application goodput claim.
The complete periodic workloads each send 16,000 bytes over approximately ten
seconds; the burst workload sends 102,400 bytes over approximately ten seconds.

GRTC times bracket constant-latency entry, HFXO startup, payload preparation,
RADIO ramp/TX/disable and clock release. Active min/max were 545/552 µs,
447/455 µs, 395/402 µs and 6528/6540 µs respectively. CPU polling is included;
it sleeps between batches. Constant latency during TX implements the requirement
of LM20 anomaly 20, which the earlier power-only probe omitted. No receiver,
ACK, retry or BLE coexistence is part of this measurement.

## Electrical windows

PPK2 used 3.0 V source mode, 100 ksample/s nominal timing and an 18-second
cold-start capture. The P14 jumper was removed, DK USB remained powered and
CMSIS-DAP wiring remained connected. There was no active debug session during
capture; GDB checked results afterwards while PPK2 held power.

The traffic window starts at the detected first activity and extends one complete
scheduled interval after the last batch start, approximately ten seconds. It
includes sleep. The 18-second acquisition additionally includes startup and the
quiet intervals before and after traffic; it must not be substituted for the
traffic-window average.

| Profile | Traffic-window mean current / power | Traffic-window energy | Approximate burst-window mean current | Approximate energy per burst window |
| --- | ---: | ---: | ---: | ---: |
| 1 Mbit/s periodic | 0.472 mA / 1.415 mW | 14.147 mJ | 4.626 mA | 7.910 µJ |
| 2 Mbit/s periodic | 0.401 mA / 1.202 mW | 12.018 mJ | 4.000 mA | 5.761 µJ |
| 4 Mbit/s periodic | 0.350 mA / 1.050 mW | 10.499 mJ | 3.228 mA | 4.067 µJ |
| 4 Mbit/s burst | 0.450 mA / 1.351 mW | 13.509 mJ | 6.603 mA | 129.940 µJ |

Burst boundaries are an estimate: PPK2 and GRTC have no shared electrical trigger.
A five-sample median is used **only to locate** current transitions above the
pre-traffic median plus 0.6 mA. Groups shorter than 100 µs are rejected, adjacent
threshold samples separated by at most 100 µs are joined, and the next batch is
searched near the expected period. One missing threshold edge in the 4 Mbit/s
periodic trace is interpolated; the other runs locate every batch. A 21-batch
median of edge residuals follows slow sample-clock drift and suppresses distorted
threshold crossings. The aperture uses measured mean GRTC active time, rounded
outward with two extra 10 µs samples. All current and energy integrations use the
**unfiltered samples**, with no background subtraction. This is not a measurement
of the RF-only TX interval.

Late threshold crossings are visibly affected by range changes; 95% of edge
residuals are within 30 µs for periodic profiles and 170 µs for the 64-packet burst.
This is a locator consistency statistic, not an absolute synchronization accuracy.
The raw maximum samples in burst windows were roughly 46–51 mA. These include
range-switch artifacts and must not be advertised as calibrated radio peaks.
Post-traffic idle means were approximately 228 µA for the three periodic runs
and 17 µA for the burst run. The difference is unresolved; no common idle value
is subtracted and no PHY-specific explanation is inferred from it.

## Preserved data and viewer

Each local report retains `samples.bin`, the complete `current.csv`, calibration
metadata, immutable firmware identity and post-capture counters. The offline viewer
preserves the original sample count, lets the reader choose a workload, zoom into
a burst or view the complete capture, and recomputes selected-window statistics.
Only the displayed line is reduced to peak/valley pairs for wide views; zooming
reveals all 10 µs samples. Original CSV and binary downloads are provided beside
the chart. Machine paths, probe identities and raw debug logs remain ignored.

| Profile | Captured ELF SHA-256 |
| --- | --- |
| 1 Mbit/s | `8770cc67589fb4a86f0efadfe6725fa8fe8ff6d0853418c3dc168b4ec1f15ef2` |
| 2 Mbit/s | `24b097cb1285a67cb3446b59c07ac51ab090da7ee0695dfc9c747477d8a6f898` |
| 4 Mbit/s | `29843c9b1d63f9f16d729ad69b6fe96371275991b3cba946f960c408693e3352` |
| 4 Mbit/s burst | `d79651226ffbecab6cada6a3d3990fabb2861f9b5483ceb55afad4e946d1486a` |

See the [probe contract](../../examples/power-measurement/README.md),
[startup audit](../provenance/lm20-power-startup.md) and
[earlier captures](power-measurement-2026-09-11.md) for scope and provenance.
