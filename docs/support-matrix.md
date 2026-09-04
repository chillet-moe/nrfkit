# Support matrix

This table distinguishes reference evidence from consumer SDK support. “Planned” does not mean compile-only or hardware support.

| Target / capability | Source audit | Consumer build | Real-board validation | Status |
|---|---:|---:|---:|---|
| nRF54LM20A application core, standalone | Complete | Clang/LLD primary and GNU Arm smoke PASS | SDK LED/VCOM/reset/fault/GDB and 20-cycle gate PASS | M2 complete |
| nRF54LM20A + S115 10.0.1 | Complete | Not implemented | Official Bare Metal oracle and GDB PASS | M3 planned |
| nRF54L15 application core, standalone | Complete | Not implemented | No board currently validated | M5 planned |
| nRF54L15 + S115 10.0.1 | Complete | Not implemented | Not run | M5 planned |
| Source-tree and installed `find_package` | N/A | Host PASS, offline; firmware API included | N/A | Experimental M1 support |
| Guarded program/reset/serial/GDB workflow | Complete | Maintainer-only | Official oracles and standalone SDK PASS | M2 complete |

The firmware API remains experimental and supports only the LM20A application core standalone layout. The M2 hardware contract is complete; nrfx drivers and low-power services remain M3 work.
