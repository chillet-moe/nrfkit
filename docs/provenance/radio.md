# nRF54LM20 proprietary RADIO evidence

The RADIO implementation uses the following authority order:

1. the versioned nRF54LM20A/nRF54LM20B datasheet and revision-compatible errata;
2. reproducible behavior of the connected silicon;
3. the locked MDK register descriptions and nrfx HAL interfaces;
4. the versioned NCS `radio_test` sample as comparison evidence only.

The nrfx tree is therefore not treated as the hardware specification. It remains an
immutable submodule; project corrections are stored in `patches/nrfx/` and applied to
an ignored target build cache.

## Packet contract

`nrfkit_radio_configure_1mbit()` configures Nordic proprietary 1 Mbit mode with an
eight-bit RAM length field, a four-byte base plus one-byte prefix address, data
whitening, and a three-byte CRC. Because whitening is enabled, CRC starts after the
address as required by the datasheet. The public `channel` is the datasheet
`FREQUENCY` offset, so the carrier is `2400 MHz + channel`. The nrfx setter instead
accepts an absolute frequency on this device; the adapter performs that conversion
explicitly.

The packet pointer must refer to RAM. The first validation packet is aligned to four
bytes, contains a 32-byte deterministic payload, and transmits once at -40 dBm on
2480 MHz. The low power and single packet bound minimize unintended spectrum use.

The validation engine uses TIMER10 and DPPIC10 because both TIMER10 and RADIO belong
to the radio-local DPPI domain. TIMER10 compare publishes to RADIO TXEN; RADIO uses
READY-to-START and PHYEND-to-DISABLE shortcuts. The CPU waits for the DISABLED IRQ,
which proves that a hardware-scheduled packet traversed the transmit state machine.

## Clock and errata

The accurate HF clock is a caller-owned prerequisite. The locked nrfx XO start path
applies its revision check for erratum 39 and starts the PLL when required. The NCS
v3.4.0 sample independently starts this PLL for LM20A. The project patch
`0002-clock-xo-allow-null-source-output.patch` fixes a library API defect: the XO
implementation dereferenced the documented optional source-output pointer passed to
`nrfx_clock_is_running()`.

The current packet format has `S1LEN=0` and does not include S1 in RAM, so the
published condition for RADIO anomaly 49 is false. Optional CCM is deferred: the
applicable LM20 errata must be selected from the actual silicon revision first, and
an authenticated configuration must be used because published anomaly 102 affects
zero-length MAC operation on listed revisions.

## Ownership and evidence boundary

The public cooperative lease distinguishes proprietary and BLE owners. Acquisition
fails while either owner holds the RADIO; release fails unless the same owner calls
it while hardware state is DISABLED. Each stack remains responsible for stopping
and removing its own interrupts and DPPI bindings before release. This is deliberate:
the adapter must not guess how a future SoftDevice revision tears down its resources.

The single-board test checks ownership transitions, configuration register readback,
TIMER/DPPI scheduling, RADIO READY/END/PHYEND/DISABLED progression, interrupt wake,
and one real transmission. Register readback is not evidence that another receiver
accepted whitening or CRC. End-to-end CRC, whitening, address filtering, loss, soak,
and receiver wake remain pending. A second laboratory board and a local external
reference peer are now available, so bidirectional interoperability is the current
M5 task rather than a hardware-pending item.

The public validation sequence is deliberately incremental:

1. lock source/image receipts and host packet vectors;
2. exchange one fixed known payload in each direction;
3. repeat the bidirectional gate three times;
4. prove CRC and whitening mismatch rejection;
5. add sequence/loss accounting and bounded retry;
6. run a bounded soak; and
7. prove receive after sleep wakeup;
8. select the highest PHY supported by both endpoints, then reduce the scheduled
   interval while measuring sustained payload goodput, latency, loss, retry cost,
   queue bounds, and counter conservation.

The performance target is the highest repeatable error-free useful rate, not a
register setting or raw packet-opportunity count. The initial 1 Mbit configuration
is only a correctness baseline; 2 Mbit/s is evaluated before any final speed claim
when both endpoints support it.

Each stage records sanitized roles, exact image and source hashes, tool versions,
bounded commands, result counters, and cleanup status in `.work/`. The external
reference implementation remains a local test oracle: its private name, path,
source, business protocol, probe identity, and raw logs never enter tracked files.
Only packet behavior independently supported by public documentation or reproducible
air evidence may shape the SDK's public implementation.

When two boards are connected, build `m5_radio_tx` and `m5_radio_rx` with hardware
tests enabled, then run the guarded paired workflow:

```sh
tools/nrfkit m5-radio-dual \
  --tx-manifest build/m5_radio_tx.device-manifest.json \
  --rx-manifest build/m5_radio_rx.device-manifest.json \
  --tx-probe <transmitter-probe> --rx-probe <receiver-probe> --rounds 3
```

The command rejects identical probe identities, starts the receiver first, runs both
children through the normal manifest/address/program/serial guard, repeats the direction
three times by default, records every child report, and terminates the receiver process
group on failure. Run the same gate again with endpoint roles reversed before treating
the known-payload stage as bidirectional. Before claiming M5,
the harness must also support the fixed staged sequence above and accept an external
reference-peer adapter without exposing private details in its public arguments or
reports.

Official documentation used for this audit:

- [nRF54LM20A/nRF54LM20B datasheet](https://docs.nordicsemi.com/r/bundle/ps_nrf54lm20a/)
- RADIO packet, whitening, CRC, state-machine, and EasyDMA chapters within that
  versioned datasheet
- [CLOCK registers](https://docs.nordicsemi.com/r/bundle/ps_nrf54lm20a/page/clock.html-topic)
- [LM20 documentation and revision matrix](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54lm20a/page/comp/nrf54lm20a/nrf54lm20a_doc_ref_design_files_overview.html)
