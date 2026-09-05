# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Clang/LLD primary and GNU Arm smoke PASS; target-scoped nrfx drivers | SDK M2 gate plus M3 core/peripheral/System ON sleep and retention PASS | M3 complete |
| nRF54LM20A + sdk-nrfxlib v3.4.0 SDC/MPSL | Complete source/hash/license and resource/ABI contract | Pure-CMake Multirole, Peripheral-only, and Central-only targets PASS offline | Official oracle PASS; all standalone archives 3/3 PASS with lifecycle, roles, connection/disconnection, bidirectional ACL, budgets, canaries, stack watermark, fault status, and GDB | M6 complete |
| nRF54LM20A + S115 10.0.1 | Complete historical checkpoint | Reproducible pure-CMake baseline stopped at documented platform boundary | Official HIDS oracle PASS; pure baseline stops before advertising | Historical route stopped |
| nRF54L15 laboratory fixture | Official sources plus locked public reference-peer fixture | Not a consumer target | 1/2/4 Mbit direct, Timeslot, retry, and active-BLE coexistence peer PASS | Test fixture only |
| Source-tree and installed `find_package` | N/A | Host PASS, offline; firmware and nrfx API included | N/A | Experimental M3 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | Official oracles and standalone SDK PASS | M2 complete |
| nRF54LM20A direct proprietary RADIO 1/2 Mbit | Complete for current packet/clock inputs | Target-scoped adapter, ownership API, validation images, and two-board runner | Bidirectional compatibility baseline and rate comparison PASS | M5 diagnostic baseline |
| nRF54LM20A/L15 proprietary RADIO 4 Mbit | Both mode encodings, packet fields, clock, and applicable errata audited | BT=0.6 default and explicit BT=0.4; shared direct/Timeslot packet API | Current negative/rate/Timeslot directions 3/3 and idempotent-retry 20-round soak PASS | M7 functional PASS; electrical power deferred |
| MPSL Timeslot private radio with active SDC | Complete locked MPSL contract | Pure-CMake backend with bounded grant/deadline/cleanup lifecycle | Disabled lifecycle plus advertising/connected 4 Mbit air gate 3/3 PASS with raw ACL | M7 functional PASS; electrical power pending |
| Combined LM20 consumer prerequisites | Complete for current USB/SDC/Timeslot/RRAM lifecycle boundary | C++23 source-tree and installed `find_package` builds PASS offline in both CMake declaration orders | SDC/MPSL plus USB control/bulk/HID, 20 reconnects and 20-second stress PASS | M8 public prerequisite PASS; private integration pending |

The firmware API remains experimental and supports only the LM20A application core
standalone layout. M3 validates the listed nrfx drivers, IRQ/DMA paths, bounded RRAM
scratch write, System ON GRTC wake, and reset retention. True System OFF wake remains
unclaimed because an attached debug session forces the datasheet-defined emulated
mode. The completed M6 BLE scope ends at SoftDevice Controller lifecycle and raw HCI;
Host, ATT/GATT, HID profile, and product pairing policy are outside the plan. Legacy
S115 assets remain a reproducible historical checkpoint rather than the active route.
Direct RADIO is not a coexistence claim: with SDC active, proprietary access must be
inside a granted MPSL Timeslot.

The review-image retry regression is resolved. The peer now replays an ACK for the
immediately previous valid sequence without committing it twice, and every run forces
one post-commit ACK suppression to exercise that recovery. See
[`m7-radio-evidence.md`](provenance/m7-radio-evidence.md) for the failed controls and
current three-round plus 20-round evidence.
