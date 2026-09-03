# nrf-cmake-sdk

`nrf-cmake-sdk` is a community bare-metal CMake SDK for Nordic nRF devices. The first targets are nRF54LM20A and nRF54L15. Consumer builds are intended to work offline with ordinary CMake, Ninja, and a host Arm cross-toolchain, without west, sysbuild, Devicetree, Kconfig, Zephyr, or an installed nRF Connect SDK.

This project is not affiliated with or endorsed by Nordic Semiconductor. Nordic Semiconductor, nRF, and related marks belong to their respective owners.

The project is in early bring-up. P0 currently provides locked official reference builds, ELF and Intel HEX address auditing, guarded programming, reset/run orchestration, and J-Link GDB smoke tests. This is not yet a consumer SDK release; see [`PLAN.md`](PLAN.md) for the normative scope and completion gates.

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

Hardware commands use the generated manifest and the same public entry point. USB, serial, probes, programming, and GDB require Codex tool escalation; see [`docs/hardware-workflow.md`](docs/hardware-workflow.md). Programming remains fail-closed and uses `ERASE_NONE`, read-back verification, immutable snapshots, and address allowlists.

## Host tests

```sh
PYTHONPATH=tools python3 -m unittest discover -s tests/host -v
tools/check-public
```

Project-owned code is licensed under BSD-3-Clause. Official reference sources and generated firmware remain external inputs under their own licenses; see [`docs/provenance/sources.lock`](docs/provenance/sources.lock).
