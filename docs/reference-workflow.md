# Official reference workflow

P0 establishes two executable oracles before this project implements its own startup and linker contracts. Their exact releases, commits, source hashes, board targets, output tokens, image domains, and writable regions are recorded in `docs/provenance/sources.lock`.

`reference prepare` validates every required Git module and file hash. It writes only a local receipt below `.work/reference/sources/`; it does not copy or modify the official workspace. `reference build` is the only command allowed to invoke west. Its build and cache directories are below `.work/reference/`, and it resolves output domains and programming order from sysbuild and runner metadata.

The image manifest binds the source receipt, debug ELF, every ordered HEX image, hashes, load ranges, SoC, core, board, VCOM role, expected token, and per-image address allowlist. On nRF54LM20 DK, the CPUAPP UART20 console uses Serial Port 1 (VCOM1); this follows the official P1.16/P1.17 mapping and is not inferred from host device numbering. `inspect` reparses the ELF and every Intel HEX record. Hard-coded configuration-region exclusions take precedence over manifest claims.

`flash` and `run` dynamically enumerate a unique matching board, acquire a per-probe lock, copy each validated HEX to a read-only run snapshot, recheck its hash and ranges, then invoke nrfutil with no erase, read-back verification, and no automatic post-program reset. `run` opens the declared VCOM, asserts DTR as required by the DK interface MCU, allows a short serial-ready interval for its analog routing, and only then issues a separate reset. It requires the exact token before reporting success.

Every process has a timeout and runs in its own process group. Local paths, probe identities, raw logs, and machine details remain in atomic `.work/runs/<id>/run.json` reports and adjacent logs. They are never public artifacts.

The independent GDB client used for P0 is pinned by release, official download URL, archive checksum, executable checksum, and version in `docs/provenance/toolchains.lock`. It is a developer tool and is never downloaded or discovered by an ordinary consumer configure/build. Pass its local executable explicitly to `doctor --gdb` and `gdb-smoke --gdb`; local installation paths belong only in `.local/AVAILABLE_INPUTS.md` and ignored reports.
