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

The locked LM20 and L15 MDK register definitions also expose Nordic proprietary
4 Mbit/s modes (`Nrf_4Mbit_0BT6` and `Nrf_4Mbit_0BT4`). The adapter exposes both as
explicit packet modes. Both passed three-round bidirectional known-payload gates;
BT=0.6 is the default because its tested rounds were clean, while BT=0.4 observed one
correctly rejected CRC packet. The exact results and report IDs are in
[`m7-radio-evidence.md`](m7-radio-evidence.md). The 2 and 1 Mbit/s modes remain
compatibility and rate-comparison baselines.

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

## Ownership, MPSL, and evidence boundary

The public cooperative lease distinguishes logical owners. Acquisition fails while
another owner holds the RADIO; release fails unless the same owner calls it while
hardware state is DISABLED. This is useful for exclusive direct-RADIO tests, but it
is not a valid coexistence contract with SDC/MPSL. MPSL owns documented radio-stack
resources while enabled, and application code may directly touch managed RADIO,
timer, DPPI, IRQ, or clock state only inside a granted MPSL Timeslot. Teardown and
callback-context rules come from the version-locked nrfxlib documentation and must
be encoded in the M6/M7 resource contract rather than guessed by this adapter.

The single-board test checks ownership transitions, configuration register readback,
TIMER/DPPI scheduling, RADIO READY/END/PHYEND/DISABLED progression, interrupt wake,
and one real transmission. Register readback alone is not receiver evidence. The
two-board gates now add known-payload reception, CRC and whitening rejection, sequence
accounting, bounded retry, channel switching, sleep wake, 20-round soak, and
active-BLE Timeslot coexistence. Only the paired reports support those claims.

The completed functional validation sequence was deliberately incremental:

1. audited both documented 4 Mbit/s modes and applicable errata, then locked source/image
   receipts and 4 Mbit/s host packet vectors;
2. exchanged fixed 4 Mbit/s known payloads in each direction and repeated the
   bidirectional gate three times;
3. at 4 Mbit/s, proved CRC and whitening mismatch rejection;
4. added sequence/loss accounting, bounded retry, and channel switching;
5. ran a bounded soak and proved receive after foreground sleep wakeup;
6. compared both 4 Mbit/s modes, selected the evidenced default, then reduced the
   scheduled interval while measuring sustained payload goodput, latency, loss,
   retry cost, queue bounds, counter conservation, stability, and power;
7. only after the 4 Mbit/s gate, repeated the applicable performance subset
   at 2 and 1 Mbit/s as compatibility and diagnostic comparisons; and
8. repeated the 4 Mbit/s-first sequence through the MPSL Timeslot backend with SDC
   disabled lifecycle, advertising, and an active BLE connection.

Electrical current/energy remains outside this completed functional sequence because
the available setup has no current instrument. Reservation duty is recorded as a
power proxy but is not presented as amperes, watts, or joules.

The performance target is repeatable error-free useful rate, not a register setting
or raw packet-opportunity count. The initial 1 Mbit/s and current 2 Mbit/s
configurations are correctness and comparison baselines. A final LM20/L15 result
must prioritize 4 Mbit/s and may report a lower sustainable application rate only
with measured scheduling, packet, retry, and power evidence; a 2 Mbit/s pass cannot
stand in for the 4 Mbit/s gate.

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
the known-payload stage as bidirectional. `tools/nrfkit m7-coexistence` composes the
sequence-gated peer with the raw-HCI Controller oracle and requires a packet that can
only be emitted during the active-connection burst. Neither command exposes local
probe identities in tracked files.

Official documentation used for this audit:

- [nRF54LM20A/nRF54LM20B datasheet](https://docs.nordicsemi.com/r/bundle/ps_nrf54lm20a/)
- RADIO packet, whitening, CRC, state-machine, and EasyDMA chapters within that
  versioned datasheet
- [CLOCK registers](https://docs.nordicsemi.com/r/bundle/ps_nrf54lm20a/page/clock.html-topic)
- [LM20 documentation and revision matrix](https://docs.nordicsemi.com/r/bundle/comp_matrix_nrf54lm20a/page/comp/nrf54lm20a/nrf54lm20a_doc_ref_design_files_overview.html)
