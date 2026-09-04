# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Clang/LLD primary and GNU Arm smoke PASS; target-scoped nrfx drivers | SDK M2 gate plus M3 core/peripheral/System ON sleep and retention PASS | M3 complete |
| nRF54LM20A + sdk-nrfxlib v3.4.0 SDC/MPSL | Initial source/hash/license selection complete; detailed resource/ABI contract pending | Not implemented | Official oracle and LM20 lifecycle/HCI gates pending | Current M6; Multirole first |
| nRF54LM20A + S115 10.0.1 | Complete historical checkpoint | Reproducible pure-CMake baseline stopped at documented platform boundary | Official HIDS oracle PASS; pure baseline stops before advertising | Historical route stopped |
| nRF54L15 laboratory fixture | Official sources plus local reference-peer input | Not a consumer target | Legacy BLE central checkpoint PASS; SDC peer and 4 Mbit/s radio work pending | Test fixture only |
| Source-tree and installed `find_package` | N/A | Host PASS, offline; firmware and nrfx API included | N/A | Experimental M3 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | Official oracles and standalone SDK PASS | M2 complete |
| nRF54LM20A direct proprietary RADIO 1/2 Mbit | Complete for current packet/clock inputs | Target-scoped adapter, ownership API, LM20/L15 validation images, and two-board runner build | 1 Mbit single-board scheduled TX PASS; bidirectional air evidence not yet run | M5 diagnostic baseline |
| nRF54LM20A/L15 proprietary RADIO 4 Mbit | MDK register capability confirmed; mode/errata audit pending | Not implemented | Bidirectional, performance, power, and Timeslot evidence pending | Primary M7 PHY target |
| MPSL Timeslot private radio with active SDC | Initial package source lock complete | Not implemented | Disabled/advertising/connected coexistence gates pending | Planned M7 |

The firmware API remains experimental and supports only the LM20A application core
standalone layout. M3 validates the listed nrfx drivers, IRQ/DMA paths, bounded RRAM
scratch write, System ON GRTC wake, and reset retention. True System OFF wake remains
unclaimed because an attached debug session forces the datasheet-defined emulated
mode. The current BLE scope ends at SoftDevice Controller lifecycle and raw HCI;
Host, ATT/GATT, HID profile, and product pairing policy are outside the plan. Legacy
S115 assets remain a reproducible historical checkpoint rather than the active route.
Direct RADIO is not a coexistence claim: with SDC active, proprietary access must be
inside a granted MPSL Timeslot.
