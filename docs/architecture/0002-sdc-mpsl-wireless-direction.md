# ADR 0002: SoftDevice Controller and MPSL wireless direction

- Status: accepted
- Date: 2026-09-05

## Context

The product target needs both BLE and a high-performance proprietary 2.4 GHz link.
The completed direct-RADIO work is useful as an exclusive diagnostic and performance
baseline, but a cooperative application-side lease cannot safely schedule resources
owned by a BLE controller. A bounded attempt to reproduce the nRF Bare Metal S115
HIDS application with a thin pure-CMake compatibility layer accumulated substantial
platform lifecycle coupling and stopped at a documented, reproducible boundary.
That result does not show that S115 or BLE is defective; it shows that continuing
that particular source-equivalence route is not the best current investment.

Nordic publishes versioned SoftDevice Controller and MPSL libraries, headers,
documentation, manifests, licenses, and explicit integration/resource requirements
in `sdk-nrfxlib`. SDC supplies Controller behavior without requiring a BLE Host, and
MPSL supplies the supported radio scheduler and Timeslot API needed to coexist with
proprietary radio use. The nRF54LM20A and nRF54L15 MDK definitions expose Nordic
proprietary 4 Mbit/s modes in addition to 2 and 1 Mbit/s modes.

## Decision

1. Make `sdk-nrfxlib` a first-class, immutable, version-locked official input through
   the `external/sdk-nrfxlib` Git submodule. The initial baseline is tag v3.4.0, repository commit
   `d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b`, and nRF54LM binary manifest revision
   `c8da3098f9f034a44b6ebad30819cc0cea51da47`.
2. Select secure nRF54LM hard-float MPSL and SDC archives atomically from that
   baseline. Bring up Multirole first, then validate Peripheral-only and Central-only
   against their applicable capability subsets.
3. Implement only the documented minimum MPSL platform substrate before SDC, because
   SDC depends on MPSL. Treat SDC lifecycle and raw HCI as the first functional
   milestone. MPSL Timeslot and proprietary-radio features follow after SDC works.
4. Do not add an open BLE Host, ATT/GATT, HID profile, or product pairing policy in
   the current plan. A small deterministic raw-HCI harness is sufficient to validate
   the Controller. GZLL and further S115 compatibility work are out of scope.
5. Treat the locked SDC/MPSL documentation and manifests as integration contracts.
   Before adapting code or using hardware, extract every stated peripheral, IRQ,
   priority, clock, memory/alignment, link, initialization, callback-context, and
   teardown requirement into source-located, machine-checkable resource and ABI
   records. Do not discover documented requirements by trial-and-error flashing.
6. Do not assume sdk-nrfxlib v3.4.0 is compatible with the project's newer nrfx
   v4.5.0 merely because both support nRF54L. Gate API/header compatibility, ELF
   attributes, hard-float ABI, undefined-symbol closure, startup/IRQ binding,
   resource definitions, final memory maps, and real-board behavior first.
7. Retain the direct-RADIO implementation and two-board executor as a differential
   baseline. When SDC/MPSL is enabled, direct access to managed RADIO, timer, DPPI,
   IRQ, or clock resources is permitted only inside a granted MPSL Timeslot.
8. Make proprietary 4 Mbit/s the primary PHY target. Validate both documented 4 Mbit/s
   modes and choose the default from real LM20/L15 bidirectional, goodput, latency,
   loss, retry, stability, scheduling, and power evidence. Keep 2 and 1 Mbit/s only
   as compatibility and diagnostic baselines; they cannot substitute for the 4 Mbit/s
   gate.

## Consequences

The consumer remains ordinary CMake and does not acquire west, sysbuild, Kconfig,
Devicetree, Zephyr, or an installed NCS dependency. The complete immutable submodule
provides reproducible documentation, headers, manifests, licenses, and binaries,
while CMake exposes only selected components. An explicit alternate root is accepted
only after the same identity/hash checks. Official NCS builds remain opt-in executable
oracles and share the existing safe program, serial, GDB, timeout, lock, cleanup, and
evidence tooling.

The old S115 implementation is pinned in the [archive](s115-archive.md); its
immutable checkpoint remains useful historical evidence,
but they no longer determine milestone order. The project takes on a deliberate
binary-vendor dependency and must preserve Nordic's license and attribution, while
gaining a documented Controller boundary and the vendor-supported multiprotocol
scheduler. Explicit hardware gates now support BLE Controller behavior, both
proprietary 4 Mbit modes, direct and Timeslot air links, bounded retry/soak, rate
comparison, and active-connection coexistence. Electrical power remains separate:
measured duty is not reported as current or energy, and M7 stays open until an
external current instrument completes that gate.
