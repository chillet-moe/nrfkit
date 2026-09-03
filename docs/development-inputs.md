# Development input contract

This document defines the kinds of input available to maintainers and autonomous agents. It intentionally contains no private repository names, machine-specific absolute paths, probe serial numbers, or raw logs. The exact local inventory belongs in the gitignored `.local/AVAILABLE_INPUTS.md`.

## Read order

1. `AGENTS.md` for stable safety and publication constraints.
2. `PLAN.md` for the current milestone, accepted design, and completion gates.
3. This document for input discovery and provenance rules.
4. `.local/AVAILABLE_INPUTS.md`, when present, for the current machine only.

The local inventory is useful context, not authority. Every path, source identity, tool, and connected device must still be validated before use.

## Input classes

| Input | Purpose | May affect consumer builds? | Required evidence |
|---|---|---:|---|
| Nordic nRF Connect SDK workspace | Official build/run oracle and implementation evidence | No | Release plus exact module commits |
| nRF Connect SDK Bare Metal workspace | Bare-metal, SoftDevice, startup, linker, and integration evidence | No | Release plus exact module commits |
| Nordic product documentation | Memory, reset, security, power, peripheral, and errata facts | No | Document title, revision, URL or file hash |
| Vendored public source snapshots | Inputs shipped by this SDK | Yes | Upstream path, commit, file hashes, license, patches |
| Wireless binary packages | Optional runtime components | Yes, when selected | Exact version, binary/header/spec hashes, license, ABI checks |
| Local read-only implementation references | General tooling and architecture patterns | No | Local-only identity; never publish its name or path |
| Development kits and probes | Hardware validation | No | Dynamically detected family, board type, capabilities, and local-only identity |
| Host and vendor tools | Build, inspect, program, reset, serial, and debug | No | Executable identity and version in each run receipt |

## Discovery and precedence

Tools must resolve inputs in this order:

1. Explicit command-line argument.
2. A documented project-specific environment variable.
3. An entry in the local inventory.
4. Read-only automatic discovery, followed by unambiguous validation.

There must be no baked-in home-directory path. Multiple matching SDK workspaces, probes, serial ports, or executables are an error unless the caller makes the choice explicit. A discovered directory name is not a version check; Git identities and required file hashes must match the tracked source lock.

Normal consumer configure and build paths must not consult the local inventory, discover an NCS installation, access the network, or invoke west. Official workspaces are available only to explicit maintainer/reference commands.

## Official reference inputs

The active reference versions, samples, board targets, and expected runtime observations are defined by the earliest incomplete milestone in `PLAN.md`. Reference preparation must:

- leave official workspaces unchanged;
- validate all required module commits and source hashes;
- write the resolved absolute paths only to a gitignored source receipt;
- keep builds and generated manifests below `.work/`;
- never silently switch to a newer installed release.

If an official input is absent, a maintainer workflow may download the exact public release after recording its origin and checksum. Downloads must never occur during ordinary CMake configure or build.

## Hardware inputs

Connected hardware is always runtime state. The repository must never assume that a previously seen probe is still present or that a `/dev/tty*` number is stable. Each operation must enumerate again, validate the device family and board capability, select exactly one probe, acquire a per-probe lock, and derive VCOM ports from the current enumeration.

Probe serial numbers, USB topology, local device paths, and unsanitized logs may be stored in `.local/` or `.work/`, but never in tracked files or public artifacts.

Hardware authorization is defined in `PLAN.md`; the existence of a local device does not authorize mass erase, recover, protection changes, provisioning, or writes to one-time/configuration regions.

## Local implementation references

A local inventory may name private repositories that contain useful process-control or hardware-tooling patterns. When the inventory marks them as relevant to the active milestone, review the listed areas before designing that subsystem; if an input is unavailable, record that fact instead of silently ignoring it. They are read-only evidence. Reimplement the general mechanism under this project's architecture and license; do not copy private identifiers, documentation, source text, path conventions, product assumptions, commit messages, or logs into public content.

## Keeping the inventory current

The local inventory is a human-readable handoff document. Update its observation date and facts when the machine, SDK installations, tools, board connection, authorization, or private references change. Automated commands may generate separate receipts below `.work/`; they must not overwrite human notes or promote local values into tracked files.
