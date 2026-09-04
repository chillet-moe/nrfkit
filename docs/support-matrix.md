# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Clang/LLD primary and GNU Arm smoke PASS; target-scoped nrfx drivers | SDK M2 gate plus M3 core/peripheral/System ON sleep and retention PASS | M3 complete |
| nRF54LM20A + S115 10.0.1 | Complete | Not implemented | Official Bare Metal oracle and GDB PASS | M3 planned |
| nRF54L15 application core, standalone | Complete | Not implemented | No board currently validated | M5 planned |
| nRF54L15 + S115 10.0.1 | Complete | Not implemented | Not run | M5 planned |
| Source-tree and installed `find_package` | N/A | Host PASS, offline; firmware and nrfx API included | N/A | Experimental M3 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | Official oracles and standalone SDK PASS | M2 complete |

The firmware API remains experimental and supports only the LM20A application core standalone layout. M3 validates the listed nrfx drivers, IRQ/DMA paths, bounded RRAM scratch write, System ON GRTC wake, and reset retention. True System OFF wake remains unclaimed because an attached debug session forces the datasheet-defined emulated mode.
