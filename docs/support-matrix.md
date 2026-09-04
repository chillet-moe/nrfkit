# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Clang/LLD primary and GNU Arm smoke PASS; target-scoped nrfx drivers | SDK M2 gate plus M3 core/peripheral/System ON sleep and retention PASS | M3 complete |
| nRF54LM20A + S115 10.0.1 | Complete | Reproducible pure-CMake baseline stopped at documented platform boundary | Official HIDS oracle PASS; pure baseline boots but fails first BlueZ plaintext connection | M6 incomplete |
| nRF54L15 laboratory fixture | Locked S145 central input | Not a consumer target | P2/P3, bonding and reconnect peer PASS | Test fixture only |
| Source-tree and installed `find_package` | N/A | Host PASS, offline; firmware and nrfx API included | N/A | Experimental M3 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | Official oracles and standalone SDK PASS | M2 complete |
| nRF54LM20A proprietary RADIO 1 Mbit | Complete for packet/clock inputs | Target-scoped adapter and ownership API build | Single-board scheduled TX PASS; dual-board link pending | Experimental M5 |

The firmware API remains experimental and supports only the LM20A application core standalone layout. M3 validates the listed nrfx drivers, IRQ/DMA paths, bounded RRAM scratch write, System ON GRTC wake, and reset retention. True System OFF wake remains unclaimed because an attached debug session forces the datasheet-defined emulated mode.
