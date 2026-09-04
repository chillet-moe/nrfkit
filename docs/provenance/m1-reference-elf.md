# M1 ELF structural comparison

The comparison uses the locked NCS v3.4.0 `hello_world` ELF built by the P0 reference workflow and the M1 Clang/LLD `empty` ELF. It compares image contracts, not implementation size: Zephyr remains an oracle and is not a consumer dependency.

| Contract | NCS v3.4.0 reference | M1 standalone ELF | Result |
|---|---:|---:|---|
| ELF class / machine | ELF32 / Arm | ELF32 / Arm | Match |
| RRAM vector origin | `0x00000000` | `0x00000000` | Match |
| Vector bytes | `0x4c8` | `0x4c8` | Match |
| Vector entries | 306 | 306 | Match |
| First code after vectors | `0x000004c8` | `0x000004c8` | Match |
| Initial stack top contract | within CPU application RAM | `0x20040000` | M1 intentionally uses RAM0 only |
| Configuration-region LOAD records | none | none | Match |

The imported startup has 290 external vector slots through IRQ 289. All 61 named IRQ numbers in `nrf54lm20a_application.h` occupy the matching vector position. The SVD independently lists 60 peripheral IRQs with the same values; `CM33SS_IRQn` is the sole device-header-only entry. Automated tests parse all three sources and inspect the linked vector section, rather than accepting the table solely by size.

The older TF-M file locked with NCS v3.4.0 also has 306 entries and the same final VREGUSB slot, but its named handlers differ at IRQs 77, 88, 90, 134, 136, 200, 208-215, 218, and 268. In particular, that snapshot predates the final PWM22/SAADC/NFCT/TEMP sequence represented consistently by nrfx v4.5.0's startup, device header, and SVD. These are recorded version differences, not values to merge. The NCS reference ELF independently confirms the `0x4c8` vector extent and first-code address; the latest internally consistent nrfx release supplies the handler identities used by M1.

The M1 ELF has separate file-backed RRAM LOAD ranges for code and initialized RAM data, and NOLOAD RAM for `.bss` and `.noinit`. The linker fixes the stack to the upper 16 KiB of RAM0, keeps the heap empty, preserves constructor arrays, and asserts that data, BSS, noinit, heap, and stack cannot overlap. Its generated Intel HEX is accepted by the same forbidden-region guard used by the hardware workflow.

This comparison does not claim runtime equivalence with Zephyr. M2 supplies the real-board reset, fault, UART, LED, repeated-programming, and GDB evidence for the project-owned runtime.
