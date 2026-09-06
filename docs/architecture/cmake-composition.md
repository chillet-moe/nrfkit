# CMake composition

NrfKit's build layer assembles ordinary CMake targets. It is not a second
configuration language or an application lifecycle manager. Capability selection uses public `NrfKit::` targets; the previous `enable`
functions have been removed. See the [consumer API](cmake-api.md). Internal
module and target names are implementation details.

## Ownership

- `NrfKitFirmware.cmake`: firmware identity, runtime/compiler setup, and the public
  configure/finalize entry points.
- `NrfKitDependencies.cmake`: shared file-selection manifests for prepared nrfx
  inputs and dependency installation.
- `NrfKitNrfx.cmake`: immutable nrfx cache, selected driver targets, resource
  reservations, and each firmware's generated configuration.
- `NrfKitWireless.cmake` / `NrfKitNrfxlib.cmake`: wireless composition and
  version-locked binary validation, respectively.
- `NrfKitUsb.cmake`: CherryUSB port or complete device-stack selection and FIFO
  configuration.
- `NrfKitImage.cmake`: layout validation, linker assertions, and ELF/HEX/BIN/map
  metadata. Consumer linker scripts stay complete and consumer-owned.

Generated headers, JSON, and linker assertions live in `cmake/templates` as
readable files. Source and installed packages preserve the same module/template
layout. Templates are configure inputs, so editing one triggers regeneration.
Normal configuration remains offline and does not require Python or an NCS tree.

## Native targets and per-firmware configuration

nrfx and SDK capability source sets are INTERFACE targets: sources are compiled in the consuming
firmware's context, with its own nrfx configuration and compiler options. They
are not shared precompiled objects. Serial drivers link a shared PRS target;
CMake carries that dependency and deduplicates shared source files. The header
target deliberately preserves normal include-directory semantics.

SDC interface targets carry their SDK platform/HCI sources, CRACEN driver, and
imported FEM/MPSL/Controller archive dependencies. Firmware does not
need to repeat that link closure. Version, security domain, and ABI checks remain
at the binary-input boundary.

The target report records the selected sources and resource reservations. It is
an audit output, not a separate dependency graph used to decide what to compile.

## Why finalize remains

`nrfkit_configure_target()` binds an executable to LM20 and its image layout.
`target_link_libraries()` selects capabilities; Timeslot and RRAM declarations may
precede SDC. `nrfkit_finalize_target()` checks the completed composition, emits
per-firmware nrfx configuration, and attaches image artifacts. Missing SDC for
Timeslot/RRAM and a competing nrfx CLOCK owner still fail at configure time.

This explicit boundary is needed because capability links and reserved-resource
masks can accumulate over several calls. Finalization follows compile usage
requirements through consumer INTERFACE libraries and aliases; CMake itself
propagates sources, include directories, definitions, and archive dependencies. An automatic deferred pass would add
hidden execution order, and one global configuration would break builds containing
several independently configured firmware images. Neither is a simplification.
The boundary does not impose the runtime initialization order: applications still
initialize SDC/MPSL before using USB's shared clock path or submitting RRAM work.

## Validation

The contract tests cover source and installed packages, independent nrfx
configurations in one build, all supported drivers, both USB/SDC declaration
orders, SDC declared after Timeslot/RRAM, and rejection when it is absent.
The linked-target contract additionally covers direct and transitive selection and
independent firmware configurations. Existing archive hash/ABI, IRQ/resource conflict, ELF/layout, and reproducibility
checks remain in place. The historical S115 integration is available only at the
[pinned archive commit](s115-archive.md); it is absent from current packages.
