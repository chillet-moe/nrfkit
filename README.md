# nrf-cmake-sdk

`nrf-cmake-sdk` is a community bare-metal CMake SDK for Nordic nRF devices. The first targets are nRF54LM20A and nRF54L15. Consumer builds are intended to work offline with ordinary CMake, Ninja, and a host Arm cross-toolchain, without west, sysbuild, Devicetree, Kconfig, Zephyr, or an installed nRF Connect SDK.

This project is not affiliated with or endorsed by Nordic Semiconductor. Nordic Semiconductor, nRF, and related marks belong to their respective owners.

The project is in early bring-up. P0 provides locked official reference builds and the guarded hardware workflow. M1 provides an experimental nRF54LM20A application-core freestanding build with Clang/LLD, a GNU Arm smoke path, official startup/SystemInit, C/C++ initialization, and ELF/HEX/BIN/map/layout artifacts. Real-board validation of SDK-built images belongs to M2, so this is not yet a consumer SDK release; see [`PLAN.md`](PLAN.md) for the normative scope and completion gates.

The M0 source decision, current target status, and contribution contract are documented in [`docs/provenance/source-audit.md`](docs/provenance/source-audit.md), [`docs/support-matrix.md`](docs/support-matrix.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md). Exact upstream identities remain machine-independent in `sources.lock`; local source paths and hardware identities never belong in tracked files.

## Experimental firmware build

The M1 examples build without consulting NCS or west. Point CMake at the source-tree package and the host LLVM installation:

```sh
cmake -S examples -B build/lm20 -G Ninja \
  -DNrfCMakeSdk_DIR="$PWD/cmake" \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchains/arm-clang.cmake" \
  -DNRF_LLVM_ROOT=/path/to/llvm
cmake --build build/lm20
```

This builds `empty`, `blinky`, `fault`, and the C++ constructor example. Each target produces `.elf`, `.hex`, `.bin`, `.map`, and `.image-layout.json`. The standalone layout uses RRAM at `0x00000000..0x001fd000`, RAM0 only at `0x20000000..0x20040000`, a 16 KiB stack, and no heap. RAM1 remains deliberately unavailable until its reserved top tail is modeled.

The public target API is target-scoped:

```cmake
add_executable(firmware main.cpp)
nrf_sdk_configure_target(firmware
  SOC nrf54lm20a
  CORE cpuapp
  BOARD nrf54lm20dk
  RUNTIME freestanding
)
nrf_sdk_finalize_target(firmware)
```

The package-discovery skeleton is also usable for ordinary host consumers:

```sh
cmake -S tests/consumer/minimal -B build/minimal -G Ninja \
  -DNrfCMakeSdk_DIR="$PWD/cmake"
cmake --build build/minimal
```

The root project can also be installed to a prefix; the installed package includes the same firmware API and `NrfCMakeSdk::core` interface target. Host tests exercise both forms with deliberately invalid NCS/Zephyr environment paths to ensure configuration remains independent of those workspaces.

## Maintainer reference workflow

Official SDK workspaces are explicit, read-only inputs. They are never discovered or invoked by a normal consumer configure. A maintainer first validates an exact workspace and toolchain into a gitignored receipt, then builds below `.work/`:

```sh
tools/nrf-cmake-sdk reference prepare ncs-hello-world \
  --root /path/to/ncs/v3.4.0 \
  --toolchain /path/to/official/toolchain
tools/nrf-cmake-sdk reference build ncs-hello-world
tools/nrf-cmake-sdk inspect \
  --manifest .work/reference/build/ncs-hello-world/image-manifest.json
```

After the one-time `reference prepare`, the complete daily oracle path is one command. It reruns the tool doctor, pristine official build, manifest/ELF/HEX audit, guarded programming, serial-ready/reset sequence, and exact-token check:

```sh
tools/nrf-cmake-sdk run --oracle ncs-hello-world \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

`run --manifest` remains available when the firmware was produced separately; that form starts at manifest audit and does not claim to have rebuilt an official oracle.

The complete P0 acceptance gate is also a single public command. It performs three consecutive hello-world runs, the Bare Metal plus S115 run, and GDB smoke with exact-token verification:

```sh
tools/nrf-cmake-sdk p0-gate \
  --gdb /path/to/locked/arm-none-eabi-gdb
```

Some J-Link OB probes lose VCOM data while their mass-storage interface is enabled. For a probe on which this limitation has been confirmed and drag-and-drop programming is not needed, the preferred local setup is an explicitly authorized one-time persistent disable:

```sh
tools/nrf-cmake-sdk probe-msd disable --authorize-persistent-change
```

The command saves the complete enumerated state in the ignored run report, emits only `MSDDisable` plus a controller reboot, and verifies that J-Link and both VCOM ports remain after re-enumeration. The tradeoff is loss of MSD drag-and-drop programming. A later `probe-msd enable --authorize-persistent-change` can restore it, but that reversal needs a new explicit authorization.

When MSD is already disabled, `p0-gate` treats that as the normal preferred state and makes no persistent change. Its `--authorize-temporary-msd-disable` option remains as a compatibility path: it disables MSD, runs the gates, and restores MSD in cleanup. Any persistent or temporary configuration change requires separate user authorization in addition to Codex tool escalation; this policy is local and is not imposed on downstream probes.

Hardware commands use the generated manifest and the same public entry point. USB, serial, probes, programming, and GDB require Codex tool escalation; see [`docs/hardware-workflow.md`](docs/hardware-workflow.md). Programming remains fail-closed and uses `ERASE_NONE`, read-back verification, immutable snapshots, and address allowlists.

The opt-in M2 SDK gate is registered as a CTest `hardware` test. It builds an exact build-ID token into the validation image, generates guarded SDK manifests, runs 20 program/reset/token cycles, checks the standalone runtime through GDB, injects a deliberate fault, and restores and verifies the normal image in cleanup:

```sh
cmake -S examples -B .work/m2 -G Ninja \
  -DNrfCMakeSdk_DIR="$PWD/cmake" \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchains/arm-clang.cmake" \
  -DNRF_CMAKE_SDK_BUILD_ID=m2-local \
  -DNRF_CMAKE_SDK_ENABLE_HARDWARE_TESTS=ON \
  -DNRF_CMAKE_SDK_GDB=/path/to/locked/arm-none-eabi-gdb
cmake --build .work/m2 --target hardware_validation fault
ctest --test-dir .work/m2 -L hardware --output-on-failure
```

Run the final `ctest` command with Codex tool escalation. Enabling the CTest only registers the operation; it does not access hardware during configure.

Maintainers can check required host tools without selecting or recording a probe:

```sh
tools/nrf-cmake-sdk doctor \
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
