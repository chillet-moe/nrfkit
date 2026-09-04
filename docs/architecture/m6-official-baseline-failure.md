# M6 strict official-application equivalence checkpoint: stopped failure

This note records the bounded nRF Bare Metal v2.0.1 `ble_hids_mouse` portability
experiment requested for LM20 and S115 10.0.1. It contains no probe identity,
host path, raw host log, private key, DHKey, or other pairing intermediate. The
structured, sanitized result is
`docs/provenance/m6-s115-equivalence-checkpoint.json`.

The result does **not** show that S115 cannot run outside the official build
system. The pure CMake image stopped in a repository compatibility shim before
the first S115 API call, so the version-locked ABI question remains unresolved.

## Locked official truth

The oracle was rebuilt from nRF Connect SDK Bare Metal v2.0.1 with its official
west/Zephyr/sysbuild flow, then run on the same LM20 and BlueZ adapter used for
the consumer test. The repository gate observed the official initialization
token and passed fresh pairing, bonding, an encrypted HID Report Map read,
disconnect, and bonded reconnect.

`docs/provenance/nrf-bm-hids-s115-equivalence.json` is generated from the
official build's `compile_commands.json` and generated `autoconf.h`. It records
all 276 compile entries, 273 unique compiled sources and their hashes, the 43
nRF-BM source paths, normalized compile-command hashes, and all 681 generated
`CONFIG_` definitions. The static consumer config is a byte-for-byte copy whose
SHA-256 is
`516b4d9280e4b45435ad428defc7071e3ae8a2d2032c6e274dceceb535b96fa5`.
`tools/nrfkit reference equivalence-audit` fails if the official source set,
source content, normalized commands, or static config differs from the receipt.

## Pure CMake source boundary

The consumer directly compiles the official application `main.c` and 39 other
nRF-BM application/library units from the receipt: board init, `irq_forward`,
all `nrf_sdh` units, advertising, connection parameters, QWR, the complete Peer
Manager and LESC set, BM buttons/GPIOTE/timer, ZMS and SoftDevice storage, BAS,
DIS, and HIDS. The only three compiled nRF-BM units not selected are the Zephyr
console backend, Zephyr logging backend, and boot banner; their presentation
role is supplied by the small repository log shim. Upstream files remain
immutable inputs. A hash-keyed, ignored prepared view contains only the selected
files and headers; no nRF-BM source tree is imported into version control.

Consumer configure and build do not execute or link west, sysbuild, Kconfig,
Devicetree, Zephyr, or an installed NCS tree. They use the repository's locked
LM20 startup/linker/runtime, nrfx drivers, S115 binary/API, and Oberon archive.

The prepared view applies only these audited source transformations:

- replace selected Zephyr, BM scheduler, and BM IRQ includes with
  `nrfkit/bm_port.h`, and route the PSA include to `nrfkit/bm_crypto.h`;
- express nRF-BM observer priorities through the equivalent static priority
  macro used by the freestanding port;
- make the assembly `.balign` value explicit for Clang's assembler;
- export the official IRQ setup function instead of registering it through
  Zephyr `SYS_INIT`;
- bind the official SoftDevice event dispatcher to the static MDK vector with
  the Cortex-M interrupt calling convention instead of Zephyr's dynamic ISR
  table; and
- change the official button callback's second parameter from `uint8_t` to its
  declared `enum bm_buttons_evt_type`. GCC accepted the incompatible callback
  type with a warning; Clang rejects it. The function body and registration are
  unchanged.

Repository shims provide the platform boundary that the official build receives
from Zephyr: static CLOCK/POWER, GPIOTE and GRTC vector bindings; board and GRTC
startup; the one timer used by BM buttons; freestanding atomics/ring buffers and
CRC helpers; the Cracen entropy entry point and existing Oberon-backed LESC
adapter; and literal UART logging. These are the non-upstream units that cannot
be removed while retaining the official application on the repository runtime.

## Reproduction and first divergence

Configure the examples with explicit locked `NRF_SOFTDEVICE_ROOT`,
`NRF_OBERON_ROOT`, and `NRF_BM_ROOT`, build `m6_ble_official_baseline`, and
generate its guarded device manifest. Then use only the repository workflow and
an ignored local alias:

```sh
tools/nrfkit reference equivalence-audit \
  --root OFFICIAL_SOURCE_ROOT --build-dir OFFICIAL_BUILD_DIR

tools/nrfkit run \
  --manifest BUILD/m6_ble_official_baseline.device-manifest.json \
  --probe-serial LM20 --timeout 120 --token-timeout 15

tools/nrfkit m6-ble-gate \
  --device-name nRF_BM_HIDS_MOUSE --phase oracle \
  --fresh-pairing --timeout 120
```

The consumer builds and links, passes the image range audit, and is programmed
with `ERASE_NONE`, read-back verification, explicit device selection, and a
per-probe lock. Its application ELF SHA-256 is
`89659e4fdf1f24dfe08b0e5c58ff779042ec10d255502569674f046173d6a3e6`;
its application HEX SHA-256 is
`4c5cce5bbb200e879544a732f7de3bd36646dca9ee63b4a7d6c1391b85662521`.

After reset it emits exactly the first byte, `B`, of the first official
`LOG_INF("BLE HIDS Mouse sample started.")` call and then produces no further
serial output. The initialization token is not reached. The same bounded BlueZ
gate subsequently finds no `nRF_BM_HIDS_MOUSE` advertisement before its
120-second deadline and completes cleanup.

This locates the first behavioral divergence in the repository UART/log shim:
the official application reaches `main`, but the first log call does not return.
Button initialization and `nrf_sdh_enable_request()` occur later, so this run
does not exercise S115 and cannot support a conclusion about its ABI, IRQ,
LESC, Peer Manager, HIDS, or persistence behavior.

## Stop decision

No GDB comparison, local object substitution, repeated flash, or simultaneous
BLE-layer change was performed after this failure. The S115 adaptation branch
stops at this reproducible checkpoint. Resume it only with new non-sensitive
evidence and a single-variable replacement or elimination of the blocking
log/platform shim. Until then, follow the LM20-only staged lower-layer route in
`PLAN.md`; do not mark M6 complete.
