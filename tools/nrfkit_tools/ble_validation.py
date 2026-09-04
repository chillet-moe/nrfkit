# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from contextlib import contextmanager, nullcontext
import os
from pathlib import Path
import signal
import subprocess
import time
import threading
from typing import Any, Callable, Iterator


class BleValidationError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


BLUEZ = "org.bluez"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
PROPERTIES = "org.freedesktop.DBus.Properties"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
GATT_SERVICE = "org.bluez.GattService1"
GATT_CHARACTERISTIC = "org.bluez.GattCharacteristic1"

HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
REQUIRED_HID_CHARACTERISTICS = {
    "00002a4a-0000-1000-8000-00805f9b34fb",
    "00002a4b-0000-1000-8000-00805f9b34fb",
    "00002a4c-0000-1000-8000-00805f9b34fb",
    "00002a4d-0000-1000-8000-00805f9b34fb",
    "00002a4e-0000-1000-8000-00805f9b34fb",
}
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
HID_REPORT_MAP = "00002a4b-0000-1000-8000-00805f9b34fb"


def hci_monitor_argv(*, btmon: str, timeout: float) -> list[str]:
    if timeout <= 0:
        raise BleValidationError("HCI trace timeout must be positive")
    return [
        "timeout", "--foreground", "--signal=INT", "--kill-after=2",
        f"{timeout:g}", btmon,
    ]


def bluetooth_info_argv(
    *, btmgmt: str, index: int, timeout: float,
) -> list[str]:
    if timeout <= 0:
        raise BleValidationError("Bluetooth info timeout must be positive")
    if index < 0:
        raise BleValidationError("Bluetooth controller index must not be negative")
    return [
        "timeout", "--foreground", "--signal=TERM", "--kill-after=2",
        f"{timeout:g}", btmgmt, "--index", str(index), "info",
    ]


@contextmanager
def capture_hci(
    *, log: Path, btmon: str, timeout: float
) -> Iterator[dict[str, Any]]:
    argv = hci_monitor_argv(btmon=btmon, timeout=timeout)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as stream:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            process_group=0,
        )
        time.sleep(0.3)
        if process.poll() is not None:
            raise BleValidationError(
                f"HCI monitor exited during startup with status {process.returncode}"
            )
        trace = {"argv": argv, "pid": process.pid, "cleaned": False}
        try:
            yield trace
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired as error:
                        raise BleValidationError(
                            "HCI monitor did not terminate during cleanup"
                        ) from error
            trace["cleaned"] = process.poll() is not None


@contextmanager
def optional_hci_capture(
    *, log: Path, btmon: str, timeout: float
) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {
        "requested": True,
        "available": False,
        "cleaned": True,
    }
    context = capture_hci(log=log, btmon=btmon, timeout=timeout)
    try:
        trace = context.__enter__()
    except BaseException as error:
        state["error"] = f"{type(error).__name__}: {error}"
        yield state
        return

    state.update(trace)
    state["available"] = True
    try:
        yield state
    finally:
        try:
            context.__exit__(None, None, None)
        except BaseException as error:
            state["cleaned"] = False
            state["cleanup_error"] = f"{type(error).__name__}: {error}"
        else:
            state["cleaned"] = bool(trace.get("cleaned", False))


def _uuid(value: Any) -> str:
    return str(value).lower()


def audit_gatt_objects(
    objects: dict[Any, Any], device_path: str, *, require_hid: bool = True
) -> dict[str, Any]:
    service_paths: dict[str, str] = {}
    characteristics: dict[str, str] = {}
    prefix = f"{device_path}/"
    for raw_path, interfaces in objects.items():
        path = str(raw_path)
        if not path.startswith(prefix):
            continue
        if GATT_SERVICE in interfaces:
            service_paths[path] = _uuid(interfaces[GATT_SERVICE].get("UUID", ""))
        if GATT_CHARACTERISTIC in interfaces:
            characteristics[path] = _uuid(
                interfaces[GATT_CHARACTERISTIC].get("UUID", "")
            )

    service_uuids = set(service_paths.values())
    characteristic_uuids = set(characteristics.values())
    required_services = {BATTERY_SERVICE}
    required_characteristics = {BATTERY_LEVEL}
    if require_hid:
        required_services.add(HID_SERVICE)
        required_characteristics.update(REQUIRED_HID_CHARACTERISTICS)
    missing_services = required_services - service_uuids
    missing_characteristics = required_characteristics - characteristic_uuids
    if missing_services or missing_characteristics:
        raise BleValidationError(
            "GATT contract is incomplete: "
            f"missing services={sorted(missing_services)}, "
            f"missing characteristics={sorted(missing_characteristics)}"
        )
    return {
        "services": sorted(service_uuids),
        "characteristics": sorted(characteristic_uuids),
        "characteristic_paths": characteristics,
    }


def _wait_until(
    predicate: Callable[[], Any], timeout: float, description: str
) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise BleValidationError(f"timed out waiting for {description}")


def scan_ble_advertisement(*, device_name: str, timeout: float) -> dict[str, Any]:
    if timeout <= 0:
        raise BleValidationError("BLE scan timeout must be positive")
    try:
        import dbus
    except ImportError as error:
        raise BleValidationError("python3-dbus is required for BLE scanning") from error

    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object(BLUEZ, "/"), OBJECT_MANAGER)

    def managed_objects() -> dict[Any, Any]:
        return manager.GetManagedObjects(timeout=10)

    objects = managed_objects()
    adapters = [
        (str(path), interfaces[ADAPTER])
        for path, interfaces in objects.items()
        if ADAPTER in interfaces and bool(interfaces[ADAPTER].get("Powered", False))
    ]
    if len(adapters) != 1:
        raise BleValidationError(
            f"expected exactly one powered Bluetooth adapter, found {len(adapters)}"
        )
    adapter_path, adapter_properties = adapters[0]
    adapter = dbus.Interface(bus.get_object(BLUEZ, adapter_path), ADAPTER)

    def matching_device() -> tuple[str, Any] | None:
        for path, interfaces in managed_objects().items():
            properties = interfaces.get(DEVICE)
            if properties is None or str(properties.get("Adapter", "")) != adapter_path:
                continue
            names = {str(properties.get("Name", "")), str(properties.get("Alias", ""))}
            if device_name in names and "RSSI" in properties:
                return str(path), properties
        return None

    existing = matching_device()
    if existing is not None:
        if bool(existing[1].get("Paired", False)) or bool(existing[1].get("Bonded", False)):
            raise BleValidationError("advertising scan target unexpectedly has host bond state")
        adapter.RemoveDevice(dbus.ObjectPath(existing[0]), timeout=10)
        _wait_until(lambda: matching_device() is None, timeout, "old scan target removal")

    owned_discovery = not bool(adapter_properties.get("Discovering", False))
    found: tuple[str, Any] | None = None
    cleanup: dict[str, Any] = {
        "stop_discovery_attempted": owned_discovery,
        "remove_device_attempted": False,
        "errors": [],
    }
    result: dict[str, Any] | None = None
    failure: Exception | None = None
    try:
        if owned_discovery:
            adapter.StartDiscovery(timeout=10)
        found = _wait_until(matching_device, timeout, device_name)
        result = {
            "adapter": adapter_path.rsplit("/", 1)[-1],
            "device_name": device_name,
            "rssi_observed": True,
            "address_type": str(found[1].get("AddressType", "")),
            "cleanup": cleanup,
        }
    except Exception as error:
        failure = error
    finally:
        if owned_discovery:
            try:
                adapter.StopDiscovery(timeout=10)
            except dbus.DBusException as error:
                cleanup["errors"].append(f"StopDiscovery: {error}")
        try:
            current = found or matching_device()
        except dbus.DBusException as error:
            cleanup["errors"].append(f"FindForRemoval: {error}")
            current = None
        if current is not None:
            try:
                cleanup["remove_device_attempted"] = True
                adapter.RemoveDevice(dbus.ObjectPath(current[0]), timeout=10)
                _wait_until(
                    lambda: matching_device() is None,
                    min(timeout, 10.0), "scan target removal",
                )
            except dbus.DBusException as error:
                # BlueZ may discard an unpaired discovery object as soon as
                # discovery stops.  DoesNotExist is successful cleanup if the
                # subsequent object-manager read also confirms absence.
                if error.get_dbus_name() == "org.bluez.Error.DoesNotExist":
                    cleanup["remove_device_outcome"] = "already-absent"
                else:
                    cleanup["errors"].append(f"RemoveDevice: {error}")
            except BleValidationError as error:
                cleanup["errors"].append(f"RemoveDevice: {error}")
        try:
            cleanup["verified"] = matching_device() is None
        except dbus.DBusException as error:
            cleanup["errors"].append(f"VerifyRemoval: {error}")
            cleanup["verified"] = False
        if cleanup["errors"]:
            cleanup["verified"] = False

    if failure is not None:
        details: dict[str, Any] = {
            "failure_stage": "ble-advertisement",
            "cleanup": cleanup,
        }
        if isinstance(failure, dbus.DBusException):
            details["dbus_error"] = failure.get_dbus_name()
        raise BleValidationError(str(failure), details=details) from failure
    assert result is not None
    return result


def run_ble_validation(
    *, device_name: str, timeout: float, fresh_pairing: bool,
    hci_trace_log: Path | None = None, btmon: str = "btmon",
    phase: str = "oracle",
) -> dict[str, Any]:
    phases = {"plaintext", "bonding", "hid", "persistence", "oracle"}
    if phase not in phases:
        raise BleValidationError(f"unknown BLE validation phase: {phase}")
    requires_pairing = phase != "plaintext"
    requires_hid = phase in {"hid", "persistence", "oracle"}
    requires_reconnect = phase in {"persistence", "oracle"}
    try:
        import dbus
        import dbus.service
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError as error:
        raise BleValidationError(
            "python3-dbus and PyGObject are required for BLE validation"
        ) from error

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object(BLUEZ, "/"), OBJECT_MANAGER)

    def managed_objects() -> dict[Any, Any]:
        return manager.GetManagedObjects(timeout=10)

    objects = managed_objects()
    adapters = [
        (str(path), interfaces[ADAPTER])
        for path, interfaces in objects.items()
        if ADAPTER in interfaces and bool(interfaces[ADAPTER].get("Powered", False))
    ]
    if len(adapters) != 1:
        raise BleValidationError(
            f"expected exactly one powered Bluetooth adapter, found {len(adapters)}"
        )
    adapter_path, adapter_properties = adapters[0]
    adapter = dbus.Interface(bus.get_object(BLUEZ, adapter_path), ADAPTER)

    def matching_device() -> tuple[str, Any] | None:
        for path, interfaces in managed_objects().items():
            properties = interfaces.get(DEVICE)
            if properties is None or str(properties.get("Adapter", "")) != adapter_path:
                continue
            names = {str(properties.get("Name", "")), str(properties.get("Alias", ""))}
            if device_name in names:
                return str(path), properties
        return None

    existing = matching_device()
    removed_existing_bond = False
    if fresh_pairing and existing is not None:
        adapter.RemoveDevice(dbus.ObjectPath(existing[0]), timeout=10)
        removed_existing_bond = True
        _wait_until(lambda: matching_device() is None, timeout, "old BLE device removal")

    discovering = bool(adapter_properties.get("Discovering", False))
    if not discovering:
        adapter.StartDiscovery(timeout=10)
    try:
        device_path, _ = _wait_until(matching_device, timeout, device_name)
    finally:
        if not discovering:
            try:
                adapter.StopDiscovery(timeout=10)
            except dbus.DBusException:
                pass

    device = dbus.Interface(bus.get_object(BLUEZ, device_path), DEVICE)
    device_properties = dbus.Interface(bus.get_object(BLUEZ, device_path), PROPERTIES)

    def device_state() -> dict[str, bool]:
        return {
            name.lower(): bool(device_properties.Get(DEVICE, name))
            for name in ("Connected", "Paired", "Bonded", "ServicesResolved")
        }

    def cleanup_failed_pairing() -> dict[str, Any]:
        cleanup: dict[str, Any] = {
            "cancel_pairing_attempted": True,
            "disconnect_attempted": False,
            "remove_device_attempted": False,
            "errors": [],
        }
        try:
            device.CancelPairing(timeout=10)
        except dbus.DBusException as error:
            if error.get_dbus_name() not in {
                "org.bluez.Error.DoesNotExist",
                "org.bluez.Error.NotReady",
            }:
                cleanup["errors"].append(f"CancelPairing: {error}")
        try:
            if bool(device_properties.Get(DEVICE, "Connected")):
                cleanup["disconnect_attempted"] = True
                device.Disconnect(timeout=10)
                _wait_until(
                    lambda: not bool(device_properties.Get(DEVICE, "Connected")),
                    min(timeout, 10.0), "failed BLE pairing disconnect",
                )
        except (dbus.DBusException, BleValidationError) as error:
            cleanup["errors"].append(f"Disconnect: {error}")
        try:
            cleanup["remove_device_attempted"] = True
            adapter.RemoveDevice(dbus.ObjectPath(device_path), timeout=10)
            _wait_until(
                lambda: matching_device() is None,
                min(timeout, 10.0), "failed BLE pairing device removal",
            )
        except (dbus.DBusException, BleValidationError) as error:
            cleanup["errors"].append(f"RemoveDevice: {error}")
        try:
            cleanup["verified"] = matching_device() is None
        except dbus.DBusException as error:
            cleanup["errors"].append(f"VerifyRemoval: {error}")
            cleanup["verified"] = False
        return cleanup

    pairing_performed = requires_pairing and not bool(
        device_properties.Get(DEVICE, "Paired")
    )
    if fresh_pairing and requires_pairing and not pairing_performed:
        raise BleValidationError("fresh pairing target was already paired after discovery")
    if not requires_pairing and bool(device_properties.Get(DEVICE, "Paired")):
        raise BleValidationError("plaintext target unexpectedly has a host pairing")
    if pairing_performed:
        agent_path = "/org/nrfkit/BleValidationAgent"
        agent_manager = dbus.Interface(
            bus.get_object(BLUEZ, "/org/bluez"), "org.bluez.AgentManager1"
        )

        class PairingAgent(dbus.service.Object):
            def _require_target(self, path: Any) -> None:
                if str(path) != device_path:
                    raise dbus.exceptions.DBusException(
                        "org.bluez.Error.Rejected", "unexpected pairing target"
                    )

            @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
            def Release(self) -> None:
                pass

            @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
            def DisplayPasskey(self, path: Any, passkey: Any, entered: Any) -> None:
                self._require_target(path)

            @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
            def DisplayPinCode(self, path: Any, pin_code: Any) -> None:
                self._require_target(path)

            @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
            def RequestConfirmation(self, path: Any, passkey: Any) -> None:
                self._require_target(path)

            @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
            def RequestAuthorization(self, path: Any) -> None:
                self._require_target(path)

            @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
            def AuthorizeService(self, path: Any, uuid: Any) -> None:
                self._require_target(path)

            @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
            def Cancel(self) -> None:
                pass

        event_loop = GLib.MainLoop()
        event_thread = threading.Thread(target=event_loop.run, daemon=True)
        agent = PairingAgent(bus, agent_path)
        agent_manager.RegisterAgent(agent_path, "NoInputNoOutput", timeout=10)
        event_thread.start()
        trace_context = (
            optional_hci_capture(
                log=hci_trace_log, btmon=btmon,
                timeout=timeout + 10.0,
            )
            if hci_trace_log is not None else nullcontext({
                "requested": False, "available": False, "cleaned": True,
            })
        )
        hci_trace_state: dict[str, Any] = {}
        try:
            try:
                with trace_context as hci_trace_state:
                    try:
                        device.Pair(timeout=timeout)
                    except dbus.DBusException as error:
                        if error.get_dbus_name() != "org.bluez.Error.AlreadyExists":
                            try:
                                state: dict[str, Any] = device_state()
                            except dbus.DBusException as state_error:
                                state = {"error": str(state_error)}
                            cleanup = cleanup_failed_pairing()
                            raise BleValidationError(
                                f"BLE pairing failed: {error}",
                                details={
                                    "failure_stage": "ble-pairing",
                                    "phase": phase,
                                    "device_name": device_name,
                                    "dbus_error": error.get_dbus_name(),
                                    "state_before_cleanup": state,
                                    "cleanup": cleanup,
                                },
                            ) from error
            except BleValidationError as error:
                error.details.setdefault("hci_trace", dict(hci_trace_state))
                raise
        finally:
            try:
                try:
                    agent_manager.UnregisterAgent(agent_path, timeout=10)
                except dbus.DBusException:
                    pass
            finally:
                event_loop.quit()
                event_thread.join(timeout=2)
                agent.remove_from_connection()

    if requires_pairing:
        _wait_until(
            lambda: bool(device_properties.Get(DEVICE, "Paired")),
            timeout,
            "BLE pairing",
        )
        bonded = bool(device_properties.Get(DEVICE, "Bonded"))
        if not bonded:
            raise BleValidationError(
                f"BlueZ did not retain the required bond for phase {phase}"
            )
    if not bool(device_properties.Get(DEVICE, "Connected")):
        try:
            device.Connect(timeout=timeout)
        except dbus.DBusException as error:
            try:
                state: dict[str, Any] = device_state()
            except dbus.DBusException as state_error:
                state = {"error": str(state_error)}
            cleanup = cleanup_failed_pairing()
            raise BleValidationError(
                f"BLE connection failed: {error}",
                details={
                    "failure_stage": "ble-connect",
                    "phase": phase,
                    "device_name": device_name,
                    "dbus_error": error.get_dbus_name(),
                    "state_before_cleanup": state,
                    "cleanup": cleanup,
                },
            ) from error
    _wait_until(
        lambda: bool(device_properties.Get(DEVICE, "ServicesResolved")),
        timeout,
        "GATT service resolution",
    )

    gatt = audit_gatt_objects(
        managed_objects(), device_path, require_hid=requires_hid
    )
    characteristic_paths = gatt.pop("characteristic_paths")

    def read_values(selected: set[str]) -> dict[str, list[int]]:
        readable: dict[str, list[int]] = {}
        for path, uuid in characteristic_paths.items():
            if uuid not in selected:
                continue
            characteristic = dbus.Interface(
                bus.get_object(BLUEZ, path), GATT_CHARACTERISTIC
            )
            try:
                value = characteristic.ReadValue({}, timeout=10)
            except dbus.DBusException as error:
                if error.get_dbus_name() in {
                    "org.bluez.Error.NotPermitted",
                    "org.bluez.Error.NotSupported",
                }:
                    continue
                raise BleValidationError(
                    f"GATT read failed for {uuid}: {error}"
                ) from error
            readable[uuid] = [int(byte) for byte in value]
        return readable

    selected = set() if phase == "plaintext" else {BATTERY_LEVEL}
    if requires_hid:
        selected.update(REQUIRED_HID_CHARACTERISTICS)
    readable = read_values(selected)

    required_reads = set() if phase == "plaintext" else {BATTERY_LEVEL}
    if requires_hid:
        required_reads.add(HID_REPORT_MAP)
    for required in required_reads:
        if required not in readable:
            raise BleValidationError(f"required GATT value was not readable: {required}")

    device.Disconnect(timeout=10)
    _wait_until(
        lambda: not bool(device_properties.Get(DEVICE, "Connected")),
        timeout,
        "BLE disconnect",
    )
    protected_uuid = HID_REPORT_MAP if requires_hid else (
        BATTERY_LEVEL if requires_pairing else None
    )
    reconnect_read: dict[str, list[int]] = {}
    if requires_reconnect:
        device.Connect(timeout=timeout)
        _wait_until(
            lambda: bool(device_properties.Get(DEVICE, "ServicesResolved")),
            timeout,
            "bonded BLE reconnect",
        )
        reconnect_read = read_values({protected_uuid})
        if protected_uuid not in reconnect_read:
            raise BleValidationError(
                "encrypted attribute was not readable after bonded reconnect"
            )
    return {
        "adapter": adapter_path.rsplit("/", 1)[-1],
        "device_name": device_name,
        "phase": phase,
        "removed_existing_bond": removed_existing_bond,
        "pairing_performed": pairing_performed,
        "hci_trace": hci_trace_state if pairing_performed else {
            "requested": hci_trace_log is not None,
            "available": False,
            "cleaned": True,
        },
        "paired": requires_pairing,
        "bonded": requires_pairing,
        "connected": requires_reconnect,
        "services_resolved": True,
        "encryption": {
            "verified": requires_pairing,
            "evidence": "successful GATT ReadValue on an ENC_NO_MITM attribute",
            "characteristic_uuid": protected_uuid if requires_pairing else None,
            "required_security": "Bluetooth Security Mode 1 Level 2",
        },
        "bonded_reconnect": {
            "verified": requires_reconnect,
            "encrypted_attribute_read": reconnect_read.get(protected_uuid),
        },
        "gatt": gatt,
        "read_values": readable,
    }
