# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Package skeleton only | Official NCS oracle PASS | M1 planned |
| nRF54LM20A + S115 10.0.1 | Complete | Not implemented | Official Bare Metal oracle and GDB PASS | M3 planned |
| nRF54L15 application core, standalone | Complete | Not implemented | No board currently validated | M5 planned |
| nRF54L15 + S115 10.0.1 | Complete | Not implemented | Not run | M5 planned |
| Source-tree and installed `find_package` | N/A | Host PASS, offline | N/A | Experimental M0 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | nRF54LM20 DK PASS | P0 complete |

No row claims a released firmware API yet. Hardware support becomes complete only after the milestone's specified real-board tests pass.
