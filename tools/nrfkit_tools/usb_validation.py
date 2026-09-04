# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import time
from typing import Any


USB_VID = 0xCAFE
USB_PID = 0x4011
BULK_OUT_EP = 0x01
BULK_IN_EP = 0x81
HID_OUT_EP = 0x02
HID_IN_EP = 0x82
REQUEST_STATUS = 0x40
REQUEST_ARM_REMOTE_WAKE = 0x41
STATUS_MAGIC = 0x4D345553
STATUS_FORMAT = "<13I3i"


class UsbValidationError(RuntimeError):
    pass


def _modules() -> tuple[Any, Any]:
    try:
        import usb.core
        import usb.util
    except ImportError as error:
        raise UsbValidationError("PyUSB is required for the M4 USB gate") from error
    return usb.core, usb.util


def _find(timeout: float) -> Any:
    usb_core, _ = _modules()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device = usb_core.find(idVendor=USB_VID, idProduct=USB_PID)
        if device is not None:
            return device
        time.sleep(0.05)
    raise UsbValidationError("M4 USB validation device did not enumerate")


def _claim(device: Any) -> tuple[Any, list[int]]:
    _, usb_util = _modules()
    detached: list[int] = []
    for interface in (0, 1):
        if device.is_kernel_driver_active(interface):
            device.detach_kernel_driver(interface)
            detached.append(interface)
    try:
        active_configuration = device.get_active_configuration()
    except Exception:
        active_configuration = None
    if (active_configuration is None
            or active_configuration.bConfigurationValue != 1):
        device.set_configuration(1)
    for interface in (0, 1):
        usb_util.claim_interface(device, interface)
    return usb_util, detached


def _release(device: Any, usb_util: Any, detached: list[int]) -> None:
    for interface in (1, 0):
        try:
            usb_util.release_interface(device, interface)
        except Exception:
            pass
    for interface in detached:
        try:
            device.attach_kernel_driver(interface)
        except Exception:
            pass
    usb_util.dispose_resources(device)


def read_status(device: Any) -> dict[str, int]:
    raw = bytes(device.ctrl_transfer(0xC1, REQUEST_STATUS, 0, 0,
                                     struct.calcsize(STATUS_FORMAT), timeout=2000))
    if len(raw) != struct.calcsize(STATUS_FORMAT):
        raise UsbValidationError("USB status response has an invalid length")
    values = struct.unpack(STATUS_FORMAT, raw)
    if values[0] != STATUS_MAGIC:
        raise UsbValidationError("USB status response has an invalid magic")
    keys = (
        "magic", "configured_count", "suspend_count", "resume_count",
        "bulk_rx_bytes", "bulk_tx_bytes", "hid_rx_count", "hid_tx_count",
        "remote_wakeup_count", "ghwcfg3", "grxfsiz", "doepctl1", "doeptsiz1",
        "remote_wakeup_result", "bulk_arm_result", "hid_arm_result",
    )
    return dict(zip(keys, values, strict=True))


def run_transfer_validation(*, stress_seconds: float, timeout: float) -> dict[str, Any]:
    device = _find(timeout)
    if getattr(device, "speed", None) != 3:
        raise UsbValidationError("M4 validation device did not enumerate at high speed")
    usb_util, detached = _claim(device)
    started = time.monotonic()
    bulk_bytes = 0
    transfers = 0
    try:
        initial = read_status(device)
        hid_out = bytes([2]) + bytes(range(1, 64))
        if device.write(HID_OUT_EP, hid_out, timeout=2000) != len(hid_out):
            raise UsbValidationError("HID OUT transfer was short")
        hid_in = bytes(device.read(HID_IN_EP, len(hid_out), timeout=2000))
        if hid_in != bytes([1]) + hid_out[1:]:
            raise UsbValidationError("HID interrupt loopback data mismatch")

        counter = 0
        while time.monotonic() - started < stress_seconds:
            seed = hashlib.sha256(counter.to_bytes(8, "little")).digest()
            # CherryUSB recommends one EP MPS for unconstrained bulk OUT reads.
            payload = (seed * 16)[:512]
            if device.write(BULK_OUT_EP, payload, timeout=5000) != len(payload):
                raise UsbValidationError("bulk OUT transfer was short")
            received = bytes(device.read(BULK_IN_EP, len(payload), timeout=5000))
            if received != payload:
                raise UsbValidationError(f"bulk loopback mismatch at transfer {counter}")
            bulk_bytes += len(payload)
            transfers += 1
            counter += 1
        final = read_status(device)
    finally:
        _release(device, usb_util, detached)

    if final["bulk_rx_bytes"] - initial["bulk_rx_bytes"] != bulk_bytes:
        raise UsbValidationError("device bulk RX byte counter does not match host traffic")
    if final["bulk_tx_bytes"] - initial["bulk_tx_bytes"] != bulk_bytes:
        raise UsbValidationError("device bulk TX byte counter does not match host traffic")
    if final["hid_rx_count"] - initial["hid_rx_count"] != 1:
        raise UsbValidationError("device HID RX counter does not match host traffic")
    if final["hid_tx_count"] - initial["hid_tx_count"] != 1:
        raise UsbValidationError("device HID TX counter does not match host traffic")
    return {
        "bulk_bytes_each_direction": bulk_bytes,
        "bulk_transfers": transfers,
        "elapsed_seconds": time.monotonic() - started,
        "initial_status": initial,
        "final_status": final,
    }


def run_reconnect_validation(*, cycles: int, timeout: float) -> dict[str, int]:
    completed = 0
    for _ in range(cycles):
        device = _find(timeout)
        usb_util, detached = _claim(device)
        try:
            read_status(device)
            device.reset()
        finally:
            _release(device, usb_util, detached)
        _find(timeout)
        completed += 1
    return {"requested_cycles": cycles, "completed_cycles": completed}


def _sysfs_device(device: Any) -> Path:
    expected_bus = int(device.bus)
    expected_address = int(device.address)
    for candidate in Path("/sys/bus/usb/devices").iterdir():
        try:
            bus = int((candidate / "busnum").read_text().strip())
            address = int((candidate / "devnum").read_text().strip())
        except (FileNotFoundError, ValueError):
            continue
        if bus == expected_bus and address == expected_address:
            return candidate
    raise UsbValidationError("cannot map the validation device to Linux USB sysfs")


def run_power_validation(*, timeout: float, wake_delay_ms: int = 500) -> dict[str, Any]:
    device = _find(timeout)
    sysfs = _sysfs_device(device)
    usb_util, detached = _claim(device)
    before = read_status(device)
    try:
        # Standard SET_FEATURE(DEVICE_REMOTE_WAKEUP), then arm the test timer.
        device.ctrl_transfer(0x00, 0x03, 0x0001, 0, None, timeout=2000)
        device.ctrl_transfer(
            0x41, REQUEST_ARM_REMOTE_WAKE, wake_delay_ms, 0, None, timeout=2000,
        )
    finally:
        _release(device, usb_util, detached)

    power = sysfs / "power"
    attributes = {
        name: (power / name).read_text().strip()
        for name in ("control", "autosuspend_delay_ms", "wakeup")
    }
    suspended = False
    resumed = False
    try:
        try:
            (power / "wakeup").write_text("enabled")
            (power / "autosuspend_delay_ms").write_text("0")
            (power / "control").write_text("auto")
        except PermissionError as error:
            raise UsbValidationError(
                "M4 power validation requires root write access to USB runtime-PM sysfs"
            ) from error
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = (power / "runtime_status").read_text().strip()
            if state == "suspended":
                suspended = True
            elif suspended and state == "active":
                resumed = True
                (power / "control").write_text("on")
                break
            time.sleep(0.01)
        if not suspended:
            raise UsbValidationError("host did not runtime-suspend the USB device")
        if not resumed:
            raise UsbValidationError("device did not remotely wake the USB link")
    finally:
        for name in ("control", "autosuspend_delay_ms", "wakeup"):
            try:
                (power / name).write_text(attributes[name])
            except OSError:
                pass

    device = _find(timeout)
    usb_util, detached = _claim(device)
    try:
        after = read_status(device)
    finally:
        _release(device, usb_util, detached)
    if after["suspend_count"] <= before["suspend_count"]:
        raise UsbValidationError("firmware did not observe USB suspend")
    if after["resume_count"] <= before["resume_count"]:
        raise UsbValidationError("firmware did not observe USB resume")
    if after["remote_wakeup_count"] <= before["remote_wakeup_count"]:
        raise UsbValidationError("firmware did not complete remote wakeup")
    if after["remote_wakeup_result"] != 0:
        raise UsbValidationError("firmware remote wakeup API returned an error")
    return {
        "suspended": suspended,
        "resumed": resumed,
        "wake_delay_ms": wake_delay_ms,
        "before_status": before,
        "after_status": after,
    }
