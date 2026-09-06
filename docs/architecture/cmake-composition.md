# CMake composition

The SDK provides platform and capability targets. The consumer assembles the
firmware and owns image policy. See the [consumer API](cmake-api.md).

## Responsibilities

- `NrfKitPlatform.cmake`: SoC, official startup, optional freestanding runtime and
  DK targets. It does not mutate a consumer executable or choose its layout.
- `NrfKitDependencies.cmake`: immutable file selections for caches and installation.
- `NrfKitNrfx.cmake`: patched nrfx input, driver source targets and resource claims.
- `NrfKitWireless.cmake`: source/Controller/MPSL dependency composition and conflicts.
- `NrfKitNrfxlib.cmake`: locked binary/header/license identity validation.
- `NrfKitUsb.cmake`: optional built-in port; consumer owns core/classes and config.

`NrfKitFirmware.cmake` and `NrfKitImage.cmake` were removed. There is no custom
configure/finalize state machine, manually traversed dependency graph, or hidden
DEFER pass. CMake propagates sources, includes, definitions and archive dependencies.
Driver configuration is evaluated by the preprocessor in each compilation context.
Resource ownership, CLOCK ownership, RADIO mode and Controller variant use native
`COMPATIBLE_INTERFACE_STRING` checks at generation time. Timeslot/RRAM require an
explicit Controller target; a compile-time contract rejects its absence without
choosing a variant implicitly.

The consumer chooses a complete linker script and attaches it with standard
`target_link_options` and `LINK_DEPENDS`. The optional runtime carries a static
startup-ABI assertion script, independent of product layout JSON. This retains
physical bounds and copy/zero/stack checks while leaving narrower reservations to
the consumer's own linker. Artifact conversion is consumer policy.

The SDK's validation examples opt into their own common firmware helper. Their
reviewed JSON allowlists serve the hardware guard only; they are not required to
build a normal consumer. The guard still validates all actual ELF/HEX load ranges
against declared writable bounds and hard-coded forbidden regions.

## Configuration scope

SDK and nrfx INTERFACE sources compile in the consuming target's context. Serial
drivers carry PRS as an ordinary dependency. Controller/MPSL remain immutable
imported static archives with matching security and float ABI. Application claims are attached to executable targets. Each claim updates target
properties; compile definitions read their final accumulated masks. The default
nrfx header ORs those masks with the documented SDC reservations, preserving both
owners without a generated per-image configuration file. Runtime initialization
and clock ownership remain explicit application obligations, independent of link order.

Shared source bundles should use INTERFACE libraries. A separately compiled library
owns its own settings; a consumer cannot retroactively change them. Native conditional
links are supported, without a second partial evaluator of generator expressions.

Normal configure is offline and does not require Python, NCS or Zephyr. Immutable
input preparation and validation happen when the package defines its targets;
unused driver sources and Controller archives are not linked into an image.
