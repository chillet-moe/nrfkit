# BLU939 application power captures — 2026-09-18

An nRF54LM20B DK was cold-started from a BLU939 configured for 3.0 V and nominal
100 ksample/s acquisition. Two 30-second captures measured a validated CoreMark
workload and a representative consumer application with only USB initialization
omitted. The consumer continued to initialize its normal SDC, scanner and main
loop. These measurements characterize complete workloads, not an isolated CPU,
USB peripheral or radio current.

| Workload | Reported window | Mean current / power | Window energy |
| --- | --- | ---: | ---: |
| CoreMark | Stable execution, 1–20 s | 2.832 mA / 8.497 mW | 161.447 mJ |
| CoreMark | Post-benchmark WFE, 23–29 s | 0.208 mA / 0.624 mW | 3.742 mJ |
| Consumer without USB initialization | 1–30 s | 1.907 mA / 5.722 mW | 165.940 mJ |

CoreMark completed 10,000 iterations in 20.912117 seconds at 128 MHz. Its final
CRC was `0x988c`, cache and DC/DC were enabled, and no valid fault record was
observed. The consumer ran at 128 MHz and neither its platform nor SDC fault
record contained the valid fault magic. Its 5–30 second mean was 1.910 mA, showing
that the one-second startup exclusion did not hide a continuing ramp.

The earlier PPK2 fixture estimates were 2.852 mA for CoreMark and 1.979 mA for the
USB-disabled consumer under the same configured voltage and window definitions.
The BLU939 repetitions are approximately 0.7% and 3.6% lower respectively. This
agreement is useful as a fixture cross-check, but it is not an instrument
calibration transfer.

Each capture preserves 3,000,001 unfiltered samples, the original four-byte sample
records, normalized CSV, instrument metadata, exact firmware identity and
post-capture GDB observations in ignored local storage. The six returned
resistance/offset pairs were applied. The separate `Calibrated` field was `0` and
is retained without interpreting it as proof either for or against calibration.
Voltage is the configured value rather than an independent measurement, and the
sample format has no sequence counter.

Before programming, every overwritten ordinary-RRAM range and the consumer settings
region was read twice. The original application, settings and complete overwritten
bank 0 range were restored and verified afterwards. An initial 4 MHz SWD restore
of the application failed at its first address; the same guarded restore completed
and verified at 1 MHz. All final power sessions requested output off. The connected
laboratory peer was enumerated read-only and was not programmed or reset.
