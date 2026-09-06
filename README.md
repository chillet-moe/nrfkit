# nrfkit

`nrfkit` is a community bare-metal CMake SDK currently scoped only to nRF54LM20A. An nRF54L15 DK may be used as a laboratory peer, but it is not a consumer SDK target. Consumer builds are intended to work offline with ordinary CMake, Ninja, and a host Arm cross-toolchain, without west, sysbuild, Devicetree, Kconfig, Zephyr, or an installed nRF Connect SDK.

This project is not affiliated with or endorsed by Nordic Semiconductor. Nordic Semiconductor, nRF, and related marks belong to their respective owners.

Version `0.1.0-rc.2` is the current experimental consumer release candidate. P0 through M3 and M6 provide locked official reference builds, a guarded hardware workflow, an nRF54LM20A freestanding runtime, target-scoped nrfx drivers, and a pure-CMake SoftDevice Controller/MPSL integration validated with all three controller archives. M4 USBHS device support is partially validated. M7 has bidirectional 4 Mbit/s direct and Timeslot air evidence, bounded retry/soak measurements, and three-round active-BLE coexistence evidence; USB remote wake and external electrical power measurement remain deferred. See [`docs/development/PLAN.md`](docs/development/PLAN.md) and [`CHANGELOG.md`](CHANGELOG.md) for the normative scope and release limitations.

The first M8 public integration gate now links C++23, USB HID, Multirole SDC/MPSL,
Timeslot, and scheduled ordinary RRAM support in one offline source-tree
or installed-package consumer. A combined real-board image also passes USB control,
bulk, HID, and reconnect testing while MPSL remains initialized. An independently
clean downstream checkout also completes its offline Release build, manifest audit,
ordinary-settings persistence gate, and long-running fault-state check without an
SDK fork.

The review-image Timeslot retry regression is resolved by idempotently replaying an ACK for the previous valid sequence. The current gate forces that recovery path and passes a 20-round soak; see [`docs/provenance/m7-radio-evidence.md`](docs/provenance/m7-radio-evidence.md).

Clone with submodules initialized (`git clone --recurse-submodules`) before building. The complete nrfx, CherryUSB, and Nordic sdk-nrfxlib trees remain immutable, version-locked upstream submodules instead of ordinary project-owned source. NrfKit compiles or links only requested components and prepares nrfx project patches in an ignored consumer cache; configure never downloads or edits an upstream tree. All shipped dependencies live under `external/`: nrfx startup/MDK and drivers share one upstream checkout, while `external/cmsis` contains the unchanged, hash-locked CMSIS Core snapshot. The nrfx prepared cache and installation use the same selected-file manifest. An explicit `NRFKIT_NRFXLIB_ROOT` override may point at the exact same locked checkout after full identity/hash validation; normal builds never discover an installed NCS workspace.

Installed packages contain the supported nrfx driver/header closure, the CherryUSB
core plus HID/DWC2 closure, and the locked SDC/MPSL selection. They exclude unrelated
upstream demos, host tools, bundled third-party examples, and Zephyr/Kconfig glue.

The M0 source decision, current target status, and contribution contract are documented in [`docs/provenance/source-audit.md`](docs/provenance/source-audit.md), [`docs/support-matrix.md`](docs/support-matrix.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md). Exact upstream identities remain machine-independent in `sources.lock`; local source paths and hardware identities never belong in tracked files.

## Experimental firmware build

The M1 examples build without consulting NCS or west. Point CMake at the source-tree package and the host LLVM installation:

```sh
cmake -S examples -B build/lm20 -G Ninja \
  -DNrfKit_DIR="$PWD/cmake" \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchains/arm-clang.cmake" \
  -DNRF_LLVM_ROOT=/path/to/llvm
cmake --build build/lm20
```

For a C++23 consumer that uses standard library headers, keep Clang as the
compiler and additionally point `NRF_GNU_ARM_CXX_ROOT` at a GNU Arm Embedded
installation prefix. NrfKit uses its target sysroot and C++ headers without
switching the compiler away from Clang. The runtime remains freestanding: this
enables header-only standard-library facilities, not hosted I/O, a heap, or an
implicitly linked C++ runtime:

```sh
  -DNRF_GNU_ARM_CXX_ROOT=/path/to/arm-gnu-toolchain
```

This builds `empty`, `blinky`, `fault`, and the C++ constructor example. Each target produces `.elf`, `.hex`, `.bin`, `.map`, and `.image-layout.json`. The standalone layout uses RRAM at `0x00000000..0x001fd000`, RAM0 only at `0x20000000..0x20040000`, a 16 KiB stack, and no heap. RAM1 remains deliberately unavailable until its reserved top tail is modeled.

The public target API uses ordinary CMake links. Capabilities may also be grouped
in a consumer-owned INTERFACE library. See the [CMake API](docs/architecture/cmake-api.md)
for available targets and configuration rules:

```cmake
add_executable(firmware main.cpp)
nrfkit_configure_target(firmware
  SOC nrf54lm20a
  CORE cpuapp
  BOARD nrf54lm20dk
  RUNTIME freestanding
)
target_link_libraries(firmware PRIVATE NrfKit::nrfx_gpio)
nrfkit_finalize_target(firmware)
```

Applications that reserve product-owned ordinary RRAM, such as settings, may
provide a reviewed linker script and its matching guarded image-layout contract:

```cmake
nrfkit_configure_target(firmware
  SOC nrf54lm20a CORE cpuapp RUNTIME freestanding
  LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/image/application.ld"
  IMAGE_LAYOUT "${CMAKE_CURRENT_SOURCE_DIR}/image/application-layout.json"
)
```

The two files are inseparable: configuration rejects either one alone, a layout
for another target/SoC/core, or any layout that permits configuration-region writes.
The consumer linker script remains responsible for asserting that code, data,
settings, stack, and other product reservations cannot overlap. NrfKit adds a
separate assertion-only linker input that checks vector size/alignment, startup
copy/zero symbols, declared load/RAM bounds, and stack overlap; complete consumer
linker scripts do not need to be split into SDK-specific fragments.
`tools/nrfkit sdk manifest` validates that layout again and derives the guarded
application-RRAM allowlist from it; settings and scratch reservations are never
included in the programming allowlist.

Component declarations between configure and finalize may be ordered freely:
Timeslot and RRAM may be declared before SDC, but finalization requires SDC to be
present. Runtime initialization order is a separate constraint. The
[CMake composition notes](docs/architecture/cmake-composition.md) explain native
driver targets, per-firmware configuration, and why the explicit finalize step
remains.

The experimental LM20 USBHS device integration is also target-scoped:

```cmake
nrfkit_configure_usb(firmware CLASSES hid
  IN_ENDPOINT_MAX_PACKET_SIZES 8 64 32 32)
target_link_libraries(firmware PRIVATE NrfKit::usb_device)
```

It uses the pinned CherryUSB tree by default. `SOURCE_DIR` may select an explicitly
managed compatible CherryUSB checkout. The optional packet-size list describes IN
endpoints 1 upward; NrfKit derives a minimum-sized TX FIFO for each endpoint and
rejects allocations beyond the LM20 hardware capacity. If omitted, it preserves the
validated M4 oracle allocation for endpoints 1 and 2. The port's evidence hierarchy and the exact
CherryUSB documentation and newer DWC2 glue examples used during its design are
recorded in [`docs/provenance/usbhs-port.md`](docs/provenance/usbhs-port.md).
When the same target also enables SDC, enable the Controller at runtime before USB
initialization and tear USB down before the final Controller disable; NrfKit then
routes HFCLK24M through MPSL automatically.

Applications that already own CherryUSB core and class selection can use
`NrfKit::usb_port` instead of `NrfKit::usb_device`, with parameters supplied
through `nrfkit_configure_usb()`. It supplies only the
LM20 DCD, clock/power glue and configuration. Link exactly one compatible
CherryUSB core. Standard `usbd_initialize()` performs the platform attachment;
shared USB application code needs no LM20 connect call.

For settings writes while SDC/MPSL is active, link `NrfKit::rram`
and submit a snapshot with `nrfkit_rram_submit()` from `nrfkit/rram.h`. Pass the
consumer's writable settings region, then pump `nrfkit_rram_process()` alongside
`nrfkit_sdc_process()` in serialized main context. Keep dirty state until
`nrfkit_rram_result()` reports success; changes made after submission must remain
dirty. Writes are 16-byte aligned, at most 256 bytes, and scheduled one data unit
per MPSL grant without restarting SDC. Completion includes readback and session
closure. This is a transport for writes, not an atomic record format: interrupted
multi-unit writes may be partial. The consumer owns journaling and recovery.

Use `nrfkit_system_reset()` for application soft resets. It implements LM20
anomaly 63; device tools default to pin reset. See the versioned
[errata audit](docs/provenance/lm20-errata.md) for applicability and limitations.

The experimental proprietary RADIO adapter is enabled independently:

```cmake
target_link_libraries(firmware PRIVATE NrfKit::radio_direct)
```

It provides cooperative RADIO ownership and explicit Nordic 1, 2, and 4 Mbit packet
configurations. Direct RADIO remains an exclusive diagnostic baseline. Multiprotocol
applications must link an SDC variant and `NrfKit::radio_timeslot`; RADIO is
then accessible only inside a granted Timeslot. The public dual-board gates cover both
4 Mbit modes, CRC/whitening rejection, bounded retry, 20-round soak, 4/2/1 rate
comparison, and active-BLE coexistence. See
[`docs/provenance/radio.md`](docs/provenance/radio.md) and
[`docs/provenance/m7-radio-evidence.md`](docs/provenance/m7-radio-evidence.md).
The latter also defines `m7-power-audit`, the normalized capture reducer required to
close the remaining external-instrument power gate.

The experimental SoftDevice Controller integration is also target-scoped and selects
exactly one locked archive variant:

```cmake
target_link_libraries(firmware PRIVATE NrfKit::sdc_multirole) # or sdc_peripheral / sdc_central
```

It supplies Controller lifecycle and raw HCI only—there is no BLE Host, ATT/GATT,
profile stack, or S115 compatibility layer. The generated guarded manifest records
the selected archives, resource configuration, final map hash, and ELF memory budget.
See [`docs/provenance/sdc-mpsl-resource-contract.md`](docs/provenance/sdc-mpsl-resource-contract.md).

The package-discovery skeleton is also usable for ordinary host consumers:

```sh
cmake -S tests/consumer/minimal -B build/minimal -G Ninja \
  -DNrfKit_DIR="$PWD/cmake"
cmake --build build/minimal
```

The root project can also be installed to a prefix; the installed package includes the same firmware API and `NrfKit::core` interface target. Host tests exercise both forms with deliberately invalid NCS/Zephyr environment paths to ensure configuration remains independent of those workspaces.

## Maintainer reference workflow

Official SDK workspaces are explicit, read-only inputs. They are never discovered or invoked by a normal consumer configure. A maintainer first validates an exact workspace and toolchain into a gitignored receipt, then builds below `.work/`:

```sh
tools/nrfkit reference prepare ncs-hello-world \
  --root /path/to/ncs/v3.4.0 \
  --toolchain /path/to/official/toolchain
tools/nrfkit reference build ncs-hello-world
tools/nrfkit inspect \
  --manifest .work/reference/build/ncs-hello-world/image-manifest.json
```

After the one-time `reference prepare`, the complete daily oracle path is one command. It reruns the tool doctor, pristine official build, manifest/ELF/HEX audit, guarded programming, serial-ready/reset sequence, and exact-token check:

```sh
tools/nrfkit run --oracle ncs-hello-world \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

`run --manifest` remains available when the firmware was produced separately; that form starts at manifest audit and does not claim to have rebuilt an official oracle.

The M6 SDC workflow carries binary H4 rather than an ASCII console token. The same
guarded bidirectional Controller gate accepts either the locked official oracle
manifest or a generated standalone SDK manifest. Run it and the independent GDB
check explicitly:

```sh
tools/nrfkit m6-sdc-oracle \
  --manifest .work/reference/build/ncs-hci-uart-sdc/image-manifest.json
tools/nrfkit gdb-smoke \
  --manifest .work/reference/build/ncs-hci-uart-sdc/image-manifest.json \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

For the standalone example, use `m6_sdc_validation.device-manifest.json`; the
Peripheral-only and Central-only examples generate correspondingly named manifests
and automatically run only their applicable HCI role subset.

The complete P0 acceptance gate is also a single public command. It performs three consecutive hello-world runs, the Bare Metal plus S115 run, and GDB smoke with exact-token verification:

```sh
tools/nrfkit p0-gate \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

Some J-Link OB probes lose VCOM data while their mass-storage interface is enabled. For a probe on which this limitation has been confirmed and drag-and-drop programming is not needed, the preferred local setup is an explicitly authorized one-time persistent disable:

```sh
tools/nrfkit probe-msd disable --authorize-persistent-change
```

The command saves the complete enumerated state in the ignored run report, emits only `MSDDisable` plus a controller reboot, and verifies that J-Link and both VCOM ports remain after re-enumeration. The tradeoff is loss of MSD drag-and-drop programming. A later `probe-msd enable --authorize-persistent-change` can restore it, but that reversal needs a new explicit authorization.

When MSD is already disabled, `p0-gate` treats that as the normal preferred state and makes no persistent change. Its `--authorize-temporary-msd-disable` option remains as a compatibility path: it disables MSD, runs the gates, and restores MSD in cleanup. Any persistent or temporary configuration change requires separate user authorization in addition to Codex tool escalation; this policy is local and is not imposed on downstream probes.

Hardware commands use the generated manifest and the same public entry point. USB, serial, probes, programming, and GDB require Codex tool escalation; see [`docs/hardware-workflow.md`](docs/hardware-workflow.md). Programming remains fail-closed and uses `ERASE_NONE`, read-back verification, immutable snapshots, and address allowlists.

The opt-in M2 SDK gate is registered as a CTest `hardware` test. It builds an exact build-ID token into the validation image, generates guarded SDK manifests, runs 20 program/reset/token cycles, checks the standalone runtime through GDB, injects a deliberate fault, and restores and verifies the normal image in cleanup:

```sh
cmake -S examples -B .work/m2 -G Ninja \
  -DNrfKit_DIR="$PWD/cmake" \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchains/arm-clang.cmake" \
  -DNRFKIT_BUILD_ID=m2-local \
  -DNRFKIT_ENABLE_HARDWARE_TESTS=ON \
  -DNRFKIT_GDB=/path/to/locked/arm-none-eabi-gdb
cmake --build .work/m2 --target hardware_validation fault
ctest --test-dir .work/m2 -L hardware --output-on-failure
```

Run the final `ctest` command with Codex tool escalation. Enabling the CTest only registers the operation; it does not access hardware during configure.

Maintainers can check required host tools without selecting or recording a probe:

```sh
tools/nrfkit doctor \
  --official-toolchain /path/to/official/toolchain \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

The ignored report records tool versions and the locked GDB hash, but no probe serial number. This preflight is for reference/hardware maintenance and is never invoked by consumer configure.

## Host tests

```sh
PYTHONPATH=tools python3 -m unittest discover -s tests/host -v
tools/check-public
```

Project-owned code is licensed under BSD-3-Clause. Official reference sources and generated firmware remain external inputs under their own licenses; see [`docs/provenance/sources.lock`](docs/provenance/sources.lock).
