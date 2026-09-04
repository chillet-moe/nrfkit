# M7 proprietary radio and Timeslot evidence

This record separates protocol evidence, scheduler evidence, timing evidence, and
electrical power evidence. All run IDs name ignored local structured reports; they
contain the machine-specific image paths and probe identities that must not enter
the public repository.

## Packet and PHY decision

The common packet is a four-byte access address followed by an eight-bit payload
length, a deterministic 16-byte payload, data whitening, and a three-byte CRC. The
LM20 and L15 use the same channel, address, whitening IV/polynomial, CRC initial
value/polynomial, and sequence validation. Both hardware-defined 4 Mbit modes were
tested in both directions for three consecutive rounds:

| Mode and direction | Result | Report ID |
|---|---:|---|
| BT=0.6, LM20 TX to L15 RX | 3 x 1000 received, no loss or invalid payload | `20260905-045244-m7-radio-dual-741560` |
| BT=0.6, L15 TX to LM20 RX | 3 x 500 received, 499 sequence gaps, no CRC or invalid payload | `20260905-045312-m7-radio-dual-741973` |
| BT=0.4, LM20 TX to L15 RX | 3 x 1000 received, no loss or invalid payload | `20260905-045417-m7-radio-dual-742471` |
| BT=0.4, L15 TX to LM20 RX | 498/500/500 received; one rejected CRC packet; no invalid payload | `20260905-045930-m7-radio-dual-744650` |

The receive-side gaps come from an intentionally unpaced transmitter racing a
single-packet polling receiver; they are recorded rather than called RF loss. BT=0.6
is the default because it was clean in all six direction/round combinations, while
BT=0.4 had one correctly rejected CRC packet. BT=0.4 remains selectable.

Wrong CRC-initial and wrong whitening-IV prefixes were rejected before payload
accounting. Each negative run observed nine CRC failures and zero invalid accepted
payloads (`20260905-053146-m7-radio-dual-767944` and
`20260905-053208-m7-radio-dual-768135`).

## Timeslot lifecycle and air link

The backend uses a statically allocated MPSL session, guaranteed XTAL grants, normal
priority, a TIMER0 cleanup deadline, and a cleanup margin of at least the locked
MPSL extension margin. It owns RADIO only from START until cleanup. END, blocked,
cancelled, invalid return, overstay, extension failure, session idle, and asynchronous
close all have bounded cleanup paths. SDC may be disabled while the retained MPSL
session finishes, but MPSL is not uninitialized until the session closes.

With SDC enabled, the LM20 Timeslot endpoint sent 1000 packets in 1000 grants with no
deadline timeout in each of three rounds; the L15 received all of them. In the reverse
direction the scheduled receiver accepted 133/131/135 valid packets with no invalid
payload or CRC failure (`20260905-052611-m7-radio-dual-763276` and
`20260905-052641-m7-radio-dual-763760`).

The coexistence validation deliberately separates startup lifecycle from radio work.
The SDC-disabled phase proves close/reopen and one successful extension without
touching RADIO. Explicit advertising and connected phases each request an eight-grant
burst and transmit one 4 Mbit BT=0.6 packet per grant. Blocked and cancelled requests
are resubmitted outside callback context with a 16-attempt budget. The safe tested
envelope is therefore a finite eight-grant burst, 1000 microseconds per grant, at a
10000-microsecond normal-request distance; it is not permission for an unbounded
continuous schedule. Earlier continuous schedules at both 10 and 100 milliseconds
starved the BLE ACL test and were rejected.

The final gate starts a sequence-gated L15 receiver before the LM20 Controller. The
peer reports PASS only after sequence 15, which is emitted by the active-connection
burst. Across three rounds, every peer received sequences 0 through 15 with no loss
or invalid payload, while every LM20 report completed advertising, connection,
bidirectional raw ACL, 16 private packets, and cleanup
(`20260905-060446-m7-coexistence-806839`). This is the coexistence claim; direct
RADIO reports alone are not.

## Rate, latency, retry, sleep, and stability

All payload-rate measurements use the same 16-byte payload and a 128 MHz DWT cycle
counter. Direct LM20 transmit measurements are 1,118,492 bit/s at 4 Mbit PHY,
766,171 bit/s at 2 Mbit, and 484,043 bit/s at 1 Mbit. Corresponding single-packet
polling receive measurements are 649,610, 426,095, and 258,573 bit/s. Report IDs are
`20260905-054001-m7-radio-dual-780269`,
`20260905-054044-m5-radio-dual-780637`,
`20260905-054129-m5-radio-dual-781025`,
`20260905-054248-m7-radio-dual-781693`,
`20260905-054305-m5-radio-dual-781865`, and
`20260905-054322-m5-radio-dual-781692`.

The bounded Timeslot protocol has an eight-entry queue and three-retry ceiling. Its
peer intentionally drops the first acknowledgement for every eighth sequence. In 20
consecutive rounds it conserved 64 accepted/completed packets, eight retries, zero
drops, peak queue depth eight, 72 grants, four synchronized channel switches, and
287 foreground sleeps per round. Mean round-trip latency ranged from 5573.5625 to
5573.625 microseconds (`20260905-054701-m7-radio-dual-786083`). Receiving after
`WFE` wake is intrinsic to every grant/acknowledgement iteration rather than a
separate busy-wait-only demonstration.

For this retry test the measurable scheduling/power proxy is 216 milliseconds of
reserved grant time over 356.708--356.712 milliseconds, or 60.55% reservation duty.
The connected coexistence envelope reserves 8 milliseconds across each approximately
71-millisecond finite burst, or 11.27% within-burst reservation duty. These values
quantify scheduling cost, not electrical current or energy.

## Remaining electrical power boundary

No current probe, oscilloscope, ampere meter, power analyzer, or Power Profiler Kit
is present in the recorded development inputs or USB inventory. Nordic's LM20 DK
guide exposes measurement pins but requires an external instrument for current
profile or average-current measurement. Serial and debug connections also alter the
measurement boundary. Consequently M7 has functional, timing, stability, and duty
evidence, but it does not yet claim measured amperes, watts, or joules. Closing the
PLAN power exit condition requires an instrumented baseline/4/2/1/Timeslot run using
the same packet and timing method.

Official board measurement instructions:

- [nRF54LM20 DK current measurements](https://docs.nordicsemi.com/r/bundle/ug_nrf54lm20_dk/)
- [Nordic power-measurement hardware requirements](https://docs.nordicsemi.com/r/bundle/nwp_049/page/wp/nwp_049/setup_hw_and_tools.html)
