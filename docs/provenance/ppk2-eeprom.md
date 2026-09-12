# PPK2 EEPROM audit contract

The separately authorized `tools/nrfkit ppk2-eeprom` command is a recovery-first
exception to the normal no-firmware-change rule. It accepts only the
[`ppk2-eeprom` r0](https://github.com/fabiobaltieri/ppk2-eeprom/releases/tag/r0)
DFU package at source tag commit
`380720e43cc978c176b5899e2f376a569849231d` and package SHA-256
`1eafcc943caa9859529ac5cb7c6588cf70e1caf79131116bf8cccf3820181eef`.
The command also requires an explicitly hashed restore package. It records the
selected instrument's firmware identity from Nordic's DFU trigger interface and
verifies exclusive serial ownership before entering the bootloader. No firmware
version or serial device path is built into the command.

The temporary shell interface exposes only `cal_read`, a complete 256-byte raw
EEPROM read, and `reset_bl` to this workflow. `cal_write` and arbitrary shell
commands are deliberately unreachable. The raw EEPROM is read twice, both images
must be byte-identical, and every calibration field printed by `cal_read` must
match the corresponding raw bytes. Raw text, binary images, decoded IEEE-754
values and SHA-256 evidence remain in the ignored run directory. Nonfinite values
are recorded as `null` plus an explicit `nan`, `+inf`, or `-inf` classification,
so a JSON serializer cannot silently rewrite their bit patterns.

The temporary port is selected as the one newly enumerated port matching the
pinned audit firmware's USB identity; the workflow does not assume a serial device
path or USB topology location. Official firmware restoration runs in cleanup after
every point at which the temporary firmware may have been programmed, including
read or parse failures. The command does not report success until the PPK2 returns
to application mode and its DFU trigger identity exactly matches the identity
recorded before the transaction. If restoration fails, keep the instrument
connected and use the run report and DFU logs for recovery. Close Power Profiler
and every other serial client before starting; the workflow refuses to replace
firmware unless it first obtains exclusive access.
