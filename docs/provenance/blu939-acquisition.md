# BLU939 acquisition contract

The maintainer-only `tools/nrfkit blu939` workflow is an independent PySerial
implementation. It does not compile, link, import, execute, or redistribute the
manufacturer's C++ SDK. That SDK was used only as a read-only description of the
CDC serial operations listed below.

| Reference file | SHA-256 | Serial fact checked |
| --- | --- | --- |
| `SerialPort.cpp` | `27c07e91d23c8afd30c4b52a1f660c942320bd418e4bff6e41a2ec1a0a16bb76` | 115200-baud raw CDC transport |
| `SerialPort.h` | `1d8456b33a7bec65c0eeb71ca4720ad096f4d6561c5d29d7411f3882f2e28ece` | No parity, eight data bits, one stop bit and no flow control |
| `blu_api.cpp` | `fa0c8b19eb87510b66b0f56599c62e07b38720ea32801ac7989005631e03592a` | Metadata, acquisition, output and regulator command byte sequences; four-byte little-endian sample delivery |
| `blu_api.h` | `0880131fdfb142cab2840a1618bbea0b4b3664c9718e19f387a2a98e106ab74f` | Command identifiers and sample bit fields |
| `port_enum.cpp` | `1939f33ea53e7ee7b98fd3c5abaa0a686a26d163349a8517677095427889b948` | USB VID/PID discovery filter |

Linux discovery filters the CDC port by USB VID/PID and requires a nonempty serial
identity. An explicit `--instrument-serial` disambiguates multiple devices. The
process holds a per-instrument lock and opens the TTY exclusively; it never selects
the first unrelated `/dev/ttyACM*` node.

`info` sends only the metadata request. It requires the instrument's `END` record,
also applies a bounded quiet interval and size limit, requires ASCII key/value
records, and checks all six resistance and offset calibration pairs. It does not
change output power or saved configuration. Local port and serial identities stay
in the ignored run report.

The regulator accepts 500–5000 mV, encoded as a big-endian 16-bit argument. Power-on
requires an explicit voltage and first requests output off, then changes the voltage,
checks the metadata readback and requests output on. The protocol has no physical
output-state readback, so reports distinguish a command from a verified voltage.
Every bounded power session and powered capture requests output off in cleanup,
including after errors. The operator must establish the actual DUT wiring, isolation
and allowed voltage before using either operation.

Acquisition sends the start byte, stores the raw four-byte records without formatting
on the receive path, stops at a bounded byte count and always sends the stop byte.
Offline decoding uses the instrument's six calibration pairs and the nominal
100 ksample/s clock to emit `time_s,current_a` CSV accepted by `m7-power-audit`.
Samples are unfiltered; range transitions, reserved range encodings and signed
near-zero readings are reported rather than hidden. The instrument's `Calibrated`
field is retained verbatim but is not converted into a project pass/fail result: the
manufacturer's conversion path does not read that field and instead applies the six
returned resistance/offset pairs. Its value therefore cannot by itself prove or
disprove calibration. Unlike PPK2 records, this sample format exposes no sequence
counter. Complete four-byte framing therefore does not prove sample continuity. That
limitation must remain visible in measurement conclusions.

Raw data, metadata, normalized CSV, hashes and optional firmware identity remain in
the gitignored run directory. One capture does not complete M7: the final reducer
still requires all seven workloads, independently established supply voltage and an
instrument identity.
