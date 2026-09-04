# M6 pre-equivalence pure CMake baseline: stopped failure

This note records the reproducible stopping point for the first LM20 S115
integration attempt. It is not a strict reconstruction of the official
`ble_hids_mouse` application and therefore is not evidence that the S115 ABI
cannot run outside the official build system.
It contains no probe identity, host path, raw log, private key, DHKey, or other
sensitive pairing intermediate.

## Compared images

The working oracle is the nRF Bare Metal v2.0.1 `ble_hids_mouse` sample built
with its official environment for nRF54LM20 DK and S115 10.0.1. On the same
BlueZ adapter it has passed pairing, encrypted HID Report Map reading,
disconnect, and bonded reconnect.

The failing image is `m6_ble_official_baseline`. Its normal consumer configure
and build do not execute or link west, sysbuild, Kconfig, Devicetree, Zephyr, or
an installed NCS tree. The external nRF-BM, S115 API/HEX, and Oberon locations
are explicit, version-locked development inputs.

The exact upstream selection is declared by `source_files` and
`official_sources` in `cmake/modules/NrfKitFirmware.cmake`. It includes:

- nRF-BM SoftDevice IRQ forwarding and all `nrf_sdh` translation units;
- BLE advertising, connection-parameter handling, and QWR;
- the complete Peer Manager module set, its S115 storage backend, and ZMS;
- HIDS; and
- all nRF-BM public and Peer Manager headers selected by the adapter.

The ignored prepared view records a SHA-256 for every selected file plus the
locked nRF-BM commit. Repository-owned code supplies only the freestanding
primitives, fixed LM20 memory/partition facts, Cracen/Oberon PSA-shaped crypto
adapter, board initialization, and the application wiring. BAS and DIS are not
linked into this stopped reproducer because the failure precedes GATT service
resolution; adding them cannot distinguish the observed link-layer failure.

## Reproduction

Configure with explicit `NRF_SOFTDEVICE_ROOT`, `NRF_OBERON_ROOT`, and
`NRF_BM_ROOT`, build `m6_ble_official_baseline`, and create its guarded device
manifest with `tools/nrfkit sdk manifest`. Then use only the repository
workflows, with the ignored local alias rather than an enumeration default:

```sh
tools/nrfkit run \
  --manifest BUILD/m6_ble_official_baseline.device-manifest.json \
  --probe-serial LM20 --timeout 90 --token-timeout 20

tools/nrfkit m6-ble-gate \
  --device-name nrfkit-m6-official --phase plaintext \
  --fresh-pairing --timeout 45
```

The guarded run reaches `NRFKIT_M6_OFFICIAL READY`. The BlueZ operation then
fails at the first plaintext connection with
`org.bluez.Error.Failed: le-connection-abort-by-local`. No SoftDevice BLE event
is delivered to the application. The gate cancels any pairing operation,
disconnects if necessary, removes the exact device object, and verifies that
cleanup completed. This occurs before SMP, LESC, Peer Manager security,
bonding, HIDS access, or persistence can participate.

## Remaining official runtime boundary

The official oracle ELF links the following platform units that the stopped
pure CMake target intentionally does not import:

- Zephyr LM20 SoC initialization, including `nordicsemi_nrf54l_init` and its
  init-level ordering;
- Zephyr system-clock/GRTC device initialization and the associated nrfx clock
  translation units; and
- Zephyr kernel/Arm interrupt initialization, software ISR table, and dynamic
  IRQ connection machinery.

The pure target already matches the official application RAM origin, S115
clock configuration, forwarding assembly, handler source, and direct-ISR
exception ABI. The evidence therefore defines the three groups above as the
remaining dependency boundary, but it does not prove that any one group alone
is the cause. Importing any of them as an unexplained runtime dependency would
violate the consumer contract. Resume this branch only when a non-sensitive,
single-variable test can distinguish those groups; do not continue with
scattered GDB probes or simultaneous BLE-layer changes.

## Bounded RADIO diagnostic

A temporary advertising-only LM20 diagnostic subsequently transmitted a
standards-shaped nonconnectable packet on all three primary advertising
channels. The same bounded BlueZ D-Bus scanner observed its name, RSSI, and
random address type, then stopped discovery and verified removal of the
temporary device object. The diagnostic initially traversed READY, END,
PHYEND, and DISABLED without being received because its whitening initializer
omitted the fixed bit 6 required by the LM20 `DATAWHITE` layout. Matching the
datasheet and official nRF54L controller write fixed reception.

This proves the board's HF clock, RADIO BLE 1 Mbit transmit path, and host scan
path independently of S115. It does not exercise SoftDevice receive events,
GRTC scheduling, or its IRQ bootstrap, so those remain inside the boundary
above. The temporary transmitter is intentionally not retained: the project
route continues with thin, versioned official-source adaptation and does not
implement its own BLE protocol stack.
