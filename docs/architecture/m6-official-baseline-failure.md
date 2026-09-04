# Historical S115 checkpoint: strict official-application equivalence

This checkpoint is retained as diagnostic evidence. It applies only to the stopped
S115/nRF-BM compatibility route; it is not a general BLE result and does not govern
the current sdk-nrfxlib SoftDevice Controller/MPSL direction. No further S115
compatibility-layer flashing, GDB differencing, or implementation expansion is
authorized by the active route. The current decision is recorded in
`docs/architecture/0002-sdc-mpsl-wireless-direction.md`.

This note records the bounded nRF Bare Metal v2.0.1 `ble_hids_mouse` portability
experiment requested for LM20 and S115 10.0.1. It contains no probe identity,
host path, raw host log, private key, DHKey, or other pairing intermediate. The
structured, sanitized result is
`docs/provenance/m6-s115-equivalence-checkpoint.json`.

The result does **not** show that S115 cannot run outside the official build
system. The first bounded run stopped in the repository log shim before the
first S115 API call. A single-variable correction made that first log call
return, but the next bounded run still stopped before the next observable
initialization message. A subsequent offline audit found that this tested image
never invoked the official SoftDevice reset-handler forwarding setup. The
version-locked ABI question therefore remains unresolved, and a corrected
offline candidate is kept separate from the last hardware result.

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
- translate the four official APPLICATION `SYS_INIT` entries into ordered
  freestanding constructors while leaving their static functions and
  registration statements intact;
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
The log shim now follows the LM20 datasheet UARTE transaction contract: one
literal line is copied to aligned RAM, one EasyDMA transaction is issued, END
triggers STOP, and completion is bounded by TXSTOPPED/BUSERROR polling. It does
not add formatting or replace any official application handler.

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
  --probe-serial LM20 --timeout 120 --token-timeout 20

tools/nrfkit m6-ble-gate \
  --device-name nRF_BM_HIDS_MOUSE --phase oracle \
  --fresh-pairing --timeout 60
```

The consumer builds and links, passes the image range audit, and is programmed
with `ERASE_NONE`, read-back verification, explicit device selection, and a
per-probe lock. Its corrected-log application ELF SHA-256 is
`fb7250a1b022eb2594674a6af87b509198fc9b99684bda4b78989474a138a260`;
its application HEX SHA-256 is
`ccf549e5ce9e0c2e139d7719cc9d82bf489ff785616113ceaa7e20514675a4cb`.

The first image emitted exactly the first byte, `B`, of the first official
`LOG_INF("BLE HIDS Mouse sample started.")` call. Its shim started a new UARTE
DMA transaction for every byte and then used `WFE` without enabling a UARTE
interrupt. This contradicted the nRF54LM20 datasheet requirements that the DMA
reader use RAM and that transaction completion and transmitter stop be observed
through the UARTE event/state machine.

After the one-layer correction, one guarded run emitted the complete first line,
including CRLF, proving that the first log call returned. It did not emit the
next success or error message, did not reach the initialization token, and a
60-second bounded BlueZ gate did not find `nRF_BM_HIDS_MOUSE`. Discovery was
stopped on the timeout path.

The intervening unmodified official sequence is LED GPIO setup,
`bm_buttons_init()`, `bm_buttons_enable()`, the button-state read, and
`nrf_sdh_enable_request()`. This run therefore moves the first observable
divergence past logging, but cannot yet distinguish the button/GPIOTE platform
boundary from entry into the first S115 API. It must not be used as evidence
that the S115 ABI, IRQ forwarding, LESC, Peer Manager, HIDS, or persistence is
broken.

## Offline lifecycle correction after the hardware checkpoint

The official Zephyr kernel executes `board_late_init_hook()` before the
APPLICATION init level. The passed official HIDS ELF records the APPLICATION
entries in this exact order: `bm_gpiote_init`, `bm_timer_sys_init`,
`sd_irq_init`, and `irq_init`. The last hardware-tested consumer instead ran
`sd_irq_init`, `bm_gpiote_init`, `bm_timer_sys_init`, and only then its board
constructor. Worse, its prepared `irq_connect.c` exported `irq_init` and deleted
the `SYS_INIT` statement, but no caller existed; linker garbage collection
removed the routine that calls `CallSoftDeviceResetHandler`.

The current offline candidate fixes only this platform lifecycle boundary. The
board constructor uses priority 101, and the four official APPLICATION entries
use priorities 201 through 204 in the official ELF order. The preparation step
no longer changes `irq_connect.c`, and its adapter cache key was incremented so
an old transformed view cannot survive a transformation change. A post-link
audit fails unless all five map entries are present in order and
`CallSoftDeviceResetHandler` remains reachable. The candidate also maps the
official generated `CONFIG_NRFX_GPIOTE_NUM_OF_EVT_HANDLERS` value through the
same nrfx bridge used by Zephyr instead of accepting the LM20 template default.

The candidate builds, passes the post-link lifecycle audit and retains the
official source/config equivalence receipt. Its one guarded hardware run used
explicit LM20 selection, `ERASE_NONE`, read-back verification, a per-probe
lock, hard timeouts, and serial cleanup. The serial transcript was empty and a
single 60-second BlueZ gate did not discover the target. The old discovery
failure path called `StopDiscovery` in `finally` but did not record its result;
a subsequent bounded controller-info check passed, and the gate was corrected
to record and verify discovery cleanup on every timeout without repeating the
hardware experiment.

## Current decision boundary

No GDB comparison, local object substitution, or simultaneous BLE-layer change
was performed. The corrected image was programmed exactly once with explicit
LM20 selection, per-probe locking, `ERASE_NONE`, read-back verification, reset,
and hard timeouts. The official source/config equivalence audit remained green.

The previous image executed the board, GPIOTE, timer, and SoftDevice event IRQ
constructors and reached `main`; the restored official `irq_init` is the only
new executable init entry. Static audit confirms that every IRQ it registers
resolves to the matching MDK vector slot and official forwarding handler,
including SD_EVT on SWI01. The first observable divergence is therefore inside
the official `irq_init` path, before its first log becomes visible or before
`CallSoftDeviceResetHandler` returns.

Separating those cases would require another instrumented/GDB run or importing
more of the official Zephyr pre-main SoC lifecycle. That is no longer a thin
source-equivalent platform adapter. Under the experiment's stop condition, the
S115 adaptation stops at this reproducible checkpoint. The official HIDS image
remains a historical behavioral oracle. Current implementation proceeds through the
PLAN-defined, version-locked SDC-first route and then MPSL Timeslot proprietary
radio; this result must not be used to justify importing more S115 glue.
