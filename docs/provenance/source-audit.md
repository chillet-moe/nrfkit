# Source and license audit

The startup/MDK audit was performed on 2026-09-04 and the first-class nrfxlib
selection was added on 2026-09-05. Exact commits and file hashes are in
`sources.lock`. M1 imports the audited CMSIS Core and nrfx/MDK subset; sdk-nrfxlib is
an immutable upstream submodule, while external oracles and legacy S115 remain
outside the consumer package.

## Release baseline

- [nRF Connect SDK v3.4.0](https://github.com/nrfconnect/sdk-nrf/releases/tag/v3.4.0) remains the production reference-oracle release selected for nRF54LM20 revision 1. Its already validated commits are unchanged.
- nRF Connect SDK Bare Metal v2.0.1 remains the source of the validated S115 10.0.1 binary, headers, license, and release notes.
- [nrfx v4.5.0](https://github.com/NordicSemiconductor/nrfx/releases/tag/v4.5.0) is newer than the nrfx 4.2.1-derived HAL snapshots in those workspaces. Its audited LM20A MDK/startup subset is the M1 consumer source, not a silent replacement for either P0 oracle.
- [CMSIS 6.3.0](https://github.com/ARM-software/CMSIS_6/releases/tag/v6.3.0), commit `45dab712`, supplies the Cortex-M33 compiler/core headers used by both Clang and GNU Arm builds.
- [sdk-nrfxlib v3.4.0](https://github.com/nrfconnect/sdk-nrfxlib/tree/v3.4.0),
  commit `d4ce5fe1`, is the first-class wireless input. Its nRF54LM SDC and MPSL
  manifests share binary revision `c8da3098`; the initial atomic selection is
  secure hard-float MPSL plus Multirole, Peripheral-only, and Central-only SDC.

## SDC/MPSL input and compatibility boundary

The selected archives, principal public headers, component manifests, README and
CHANGELOG files, and license/attribution texts are hash-locked. Multirole is the
first functional target, but all three SDC archives and MPSL must remain from the
same release, target, security domain, float ABI, and binary revision. The current
non-secure nRF54L SDC is documented as experimental, so it is not the first gate.

The package documentation is executable design input. Before implementation, M6
must extract every stated peripheral, IRQ, priority, clock, memory/alignment, link,
initialization, callback-context, and teardown requirement into a source-located
resource/ABI contract and automated checks. No hardware trial should guess a fact
already documented by the locked package.

sdk-nrfxlib v3.4.0 was tested by Nordic with the nrfx revision paired with its NCS
release, while this project uses nrfx v4.5.0. Compatibility is therefore an open
gate, not an assumption: compare API types and macros, ELF attributes and hard-float
ABI, archive undefined symbols and link closure, startup/vector bindings, resource
definitions, final map/RAM usage, and real-board behavior. A mismatch must be
explained or the route stops; it must not be hidden behind unexplained shims.

SDC depends on MPSL, so the minimal documented MPSL substrate precedes `sdc_init()`.
The separate MPSL Timeslot/proprietary-radio milestone follows SDC bring-up. Direct
RADIO access is retained only as an exclusive diagnostic/performance baseline; once
SDC is active, access to managed RADIO/timer/DPPI resources is restricted to granted
MPSL Timeslots.

The completed first-pass audit is recorded in
`docs/provenance/sdc-mpsl-resource-contract.md` and its machine-readable
companion. It covers every locked component RST document, limitation,
changelog, public header, license, and attribution file by reproducible tree
digest. The contract records the nRF54LM resource masks, callback contexts,
clock/lifecycle ordering, 8-byte Controller memory alignment, public archive
link closure, and the hard-float ELF attributes of all four selected archives.
The locked NCS v3.4.0 `hci_uart` reference now builds through the repository
workflow with machine-checked configuration and final-map evidence for hard-float
Multirole SDC plus MPSL. The generated ISR table also closes the TIMER20/ECB00
question: both remain unregistered/spurious vectors while TIMER10, GRTC_3, and
RADIO_0 carry the public MPSL handlers. Guarded raw HCI then passed Reset,
version/features, advertising and scanning in both over-the-air directions, and
the independent GDB gate reached and stepped `main`. Standalone implementation
remains the next M6 gate.

## Startup and linker search

| Source searched | Scope | nRF54LM20A / nRF54L15 result |
|---|---|---|
| nrfx v4.5.0 tag `1b7bedb5` | Entire release tree; GNU, Clang, Arm/ArmClang, and IAR filename patterns | Official GNU application and FLPR startup assembly and per-device GNU linker scripts exist for both SoCs. No device-specific Arm/ArmClang scatter file or IAR startup/linker file was found. |
| nRF Device Family Pack 8.44.1 | Complete public CMSIS pack archive | The pack predates both target SoCs and contains neither target. It is evidence only and is not an import source. |
| NCS v3.4.0 | Nordic HAL/nrfx, Zephyr SoC/board data, and TF-M module | The bundled nrfx tree has MDK headers, SVDs, memory headers, and `system_nrf54l.c`, but no target-specific standalone startup/linker pair. TF-M contains Apache-2.0 C vector tables for LM20/L15-family targets derived from CMSIS 5.9.0. |
| NCS Bare Metal v2.0.1 | Manifest repository, Nordic HAL module, board and SoftDevice trees | No independent target startup/linker pair beyond its older nrfx/Zephyr inputs. It supplies the production S115 10.0.1 package and integration evidence. |

The earlier fallback assumption is therefore superseded: M1 should start from the official nrfx v4.5.0 GNU startup, not synthesize a large assembly file from TF-M. The TF-M C implementation remains independent comparison evidence for vector order and reset behavior.

## Planned source and license disposition

| Material | License | Disposition |
|---|---|---|
| CMSIS 6.3.0 Core headers | Apache-2.0 | Imported unmodified for M1. |
| nrfx/MDK device headers, vectors, SVDs, and memory headers | BSD-3-Clause | The LM20A subset is imported unmodified with notices and exact upstream paths. |
| nrfx GNU startup and `system_nrf54l.c/.h` | Apache-2.0 | Imported unmodified; SDK integration is kept in project-owned CMake/runtime/linker files. |
| nrfx device linker scripts | BSD-3-Clause at repository scope | Permitted reference/import candidate. |
| nrfx `nrf_common.ld` | Permissive CodeSourcery notice embedded in the file | Permitted candidate under `LicenseRef-CodeSourcery-Linker-Script`; preserve the notice verbatim. |
| TF-M Nordic startup comparison files | Apache-2.0 | Audit evidence; not currently planned for import. |
| sdk-nrfxlib v3.4.0 MPSL and SDC | LicenseRef-Nordic-5-Clause | First-class, immutable version-locked submodule; build targets expose only the selected nRF54LM secure hard-float components. Preserve license/attribution. Binary archives must not be modified, disassembled, decompiled, or reverse engineered. |
| S115 binary and API package | LicenseRef-Nordic-5-Clause | Optional Nordic-only component. Distribution and use must retain the supplied license and attribution and obey the Nordic-device and no-reverse-engineering conditions. |
| Project-owned build/runtime/tool code | BSD-3-Clause | Public repository license. |

## Memory cross-check

Nordic document `4539_001 v1.0`, Figure 3 on PDF page 15, shows RRAM from `0x00000000`, configuration areas at `0x00FFC000` through `0x00FFF000`, and RAM from `0x20000000` with a reserved top tail for VPR saved context and ProtectedRAM. The nrfx v4.5.0 LM20 memory header describes two physical 256 KiB RAM banks, while NCS v3.4.0 exposes a smaller CPU application SRAM range. These facts describe different abstraction levels; the full physical bank size is not by itself permission to allocate the reserved tail.

M1 therefore exposes only RAM0 (`0x20000000..0x20040000`) for the initial standalone layout. RAM1 stays unavailable until a later layout explicitly accounts for the VPR saved-context and ProtectedRAM tail. The SDK does not copy a generated Zephyr linker script or allocate the entire second bank merely because the generic nrfx memory header names it. The same cross-check applies to RRAM, S115 placement, configuration areas, and every linker assertion.

## Reproducibility

The release archive/tag, source URL, commit, per-file SHA-256, SPDX identifier, import date, and patch state are machine-independent entries in `sources.lock` and its hashed `vendor-imports.lock`. Host tests require that the latter covers every tracked `third_party` file and that every digest still matches. Local workspaces and downloaded audit archives are discovery inputs only.
