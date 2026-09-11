# PPK2 acquisition contract

The maintainer-only `tools/nrfkit ppk2` workflow uses PySerial; no instrument
package is needed by firmware builds. Protocol facts were checked against Nordic's
[Power Profiler implementation at 881d596480f60dea045ad6f3643afdc3f9d5a0a6](https://github.com/NordicSemiconductor/pc-nrfconnect-ppk/tree/881d596480f60dea045ad6f3643afdc3f9d5a0a6).
Upstream source is an external reference, not redistributed SDK code.

| Source file | SHA-256 | Contract used |
| --- | --- | --- |
| `src/constants.ts` | `c4694fcffacba61dc792a56a8857fcafd996af64d97c8785f3b081804935f12e` | Metadata, sampling, output, regulator and mode command identifiers |
| `src/device/abstractDevice.ts` | `cea60ac61c4abeb758f4af18bd2ff0acf0478a578742401ff25cedfc0b92abff` | Big-endian millivolt regulator argument |
| `src/device/serialDevice.ts` | `37bda3ca2fb927ec67aa0d981773ec09371a2a799138397f2da6b362bd1ae926` | 10 microsecond sample clock, bit fields and current conversion coefficients |
| `worker/serialDevice.js` | `c966986e2bb290d70343b99a22f48242d9aea533a135cfc4695e4ed23713f42f` | 115200-baud CDC transport configuration |

Linux discovery requires the PPK2 product descriptor, its USB VID/PID and the
command/data CDC interface 1, rather than selecting the first serial port. A second
CDC interface is not a second instrument. An explicit serial disambiguates multiple
instruments; the process holds a device lock and an exclusive serial handle.
`info` requests metadata without stopping acquisition or changing power.

`power --state on --duration 60` holds the serial connection and source output for
a bounded interval, then requests output off before closing. Nordic confirms that
[PPK2 output depends on keeping the serial connection open](https://devzone.nordicsemi.com/f/nordic-q-a/87399/keep-power-profiler-powered-up-when-not-communcating).
A completed power-on command must not be interpreted as a persistent supply.
Mode and configured voltage are read back, with bounded polling for asynchronous
regulator updates. PPK2 metadata does not report the physical output state or independently
measure DUT voltage: reports distinguish requested output from verified mode/voltage
configuration. No calibration, firmware, persistent gain or probe configuration is
written. Choose the voltage and wiring from the actual DUT specification before
issuing a power command.

`capture` first validates optional firmware identity and instrument metadata, then
writes binary samples with bounded reads. Decoding occurs after acquisition so CSV
formatting cannot stall USB reception. Raw samples, metadata, CSV, firmware identity
and SHA-256 values remain in the ignored run directory. A manifest only binds the
intended firmware; the caller must separately establish that it is running.
`--power-cycle` explicitly cold-starts the DUT and requests output off in cleanup,
including after capture or decoding errors. `--hold-after` keeps the same connection
and output alive briefly after a successful capture for post-capture target inspection.
Without `--power-cycle`, capture sends no output command; it is suitable for an
externally supplied DUT in ampere mode or instrument diagnostics, not an assumption
that a previous closed source session still powers the DUT.

Four-byte little-endian samples contain a 14-bit ADC value, 3-bit range, 6-bit
sequence counter and digital bits. ADC codes are scaled by four. The decoder rejects
invalid ranges and counter discontinuities instead of interpolating missing data.
A six-bit counter cannot detect losses of exactly 64 samples, so continuity is a
bounded check, not proof against every transport failure. Timestamps use the nominal
100 ksample/s instrument clock. The M7 reducer defaults to a 10.1 microsecond maximum
gap, allowing the PPK2 period and decimal roundoff.

Missing/nonfinite calibration coefficients use the published Nordic defaults;
zeros remain zeros. Reports list every defaulted coefficient and the instrument's
calibration flag. Samples remain unfiltered, including range-switch transients;
range counts, transitions and signed near-zero samples are reported. Peaks can
therefore include switching artifacts. Charge uses trapezoidal integration; energy
is explicitly an estimate from configured voltage, not independently measured
voltage. Such a capture must not be presented as a calibrated absolute-power result.
The M7 final audit still requires the seven defined workloads and measured supply
voltage; a single capture does not complete M7.

For a bare LM20 DK, follow the official
[stand-alone supply configuration](https://docs.nordicsemi.com/r/bundle/ug_nrf54lm20_dk/page/ug/nrf54lm20_dk/hw_desription/stand_alone_supply.html):
P14 accepts 1.7–3.6 V, and the analog-switch resistor routing must isolate the
unpowered onboard circuitry. This differs from
[external SoC supply with powered DK functionality](https://docs.nordicsemi.com/r/bundle/ug_nrf54lm20_dk/page/ug/nrf54lm20_dk/hw_desription/direct_supply.html).
Exact wiring, voltage and local instrument observations belong in the local inventory.
