# ADR 0001: official startup and linker sources

- Status: accepted
- Date: 2026-09-04

## Context

The initial NCS v3.4.0 and Bare Metal v2.0.1 snapshots did not contain a standalone GNU startup/linker pair for nRF54LM20A or nRF54L15. TF-M supplied a credible CMSIS-derived C fallback. A fresh M0 audit found that Nordic's later nrfx v4.5.0 release now supplies target-specific GNU startup assembly and GNU linker scripts for both SoCs.

The generic nrfx memory files describe physical banks, while the product specification and NCS platform data reserve or omit parts of the RAM top end. The SDK also needs layouts for standalone, SoftDevice, retained storage, and future bootloader images that a single vendor example script does not express.

## Decision

1. Keep the validated NCS v3.4.0 and Bare Metal v2.0.1 builds as unchanged executable oracles.
2. Use the exact nrfx v4.5.0 GNU startup and official `system_nrf54l.c/.h` as M1's primary implementation sources. Preserve them verbatim where possible; integration changes must be separate, minimal, and recorded in `sources.lock`.
3. Use the nrfx per-device linker scripts, memory headers, device headers, SVDs, and licensed common linker script as authoritative inputs, but expose repository-owned layout wrappers/contracts with stricter memory regions and assertions. Do not copy Zephyr-generated linker output.
4. Retain TF-M startup files as independent vector/reset comparison evidence, not the primary implementation.
5. Treat Clang/LLD compatibility as a verified property, not an assumption based on GNU filenames. M1 must compile, link, inspect, and compare the resulting ELF before the source choice becomes shipped support.
6. The initial standalone LM20 layout exposes the complete RRAM application range but only RAM0. RAM1 is a separate future capability because its top end contains product-defined VPR saved-context and ProtectedRAM reservations. This conservative choice costs 256 KiB of initially usable RAM but prevents ordinary sections, heap, or stack from silently occupying an unresolved reserved tail.

## Consequences

The SDK follows a newly available official startup rather than maintaining a speculative replacement. Linker layouts remain explicit and reviewable for each image contract. More cross-check work is required before using the upper RAM bank or a wireless layout, but ambiguous memory cannot silently enter a production image.
