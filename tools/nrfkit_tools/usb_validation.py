# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import os
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
STATUS_FORMAT = "<19I3i"


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


def _find_ids(*, vid: int, pid: int, timeout: float) -> Any:
    usb_core, _ = _modules()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        device = usb_core.find(idVendor=vid, idProduct=pid)
        if device is not None:
            return device
        time.sleep(0.05)
    raise UsbValidationError(
        f"USB consumer device {vid:04x}:{pid:04x} did not enumerate"
    )


def _configured_device(*, vid: int, pid: int, timeout: float) -> tuple[Any, Any]:
    _, usb_util = _modules()
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        device = _find_ids(
            vid=vid, pid=pid, timeout=max(0.05, deadline - time.monotonic())
        )
        try:
            try:
                configuration = device.get_active_configuration()
            except Exception:
                device.set_configuration(1)
                configuration = device.get_active_configuration()
            return device, configuration
        except Exception as error:
            last_error = error
            usb_util.dispose_resources(device)
            time.sleep(0.05)
    raise UsbValidationError(
        f"USB consumer device cannot select configuration 1: {last_error}"
    )


def inspect_standard_descriptors(
    *, vid: int, pid: int, expected_speed: int | None,
    expected_interfaces: int | None, timeout: float,
) -> dict[str, Any]:
    """Inspect only standard descriptors; never send a consumer protocol request."""
    device, configuration = _configured_device(vid=vid, pid=pid, timeout=timeout)
    speed = getattr(device, "speed", None)
    if expected_speed is not None and speed != expected_speed:
        raise UsbValidationError(
            f"USB consumer device speed is {speed}, expected {expected_speed}"
        )
    interfaces = []
    for interface in configuration:
        endpoints = [
            {
                "address": int(endpoint.bEndpointAddress),
                "attributes": int(endpoint.bmAttributes),
                "max_packet_size": int(endpoint.wMaxPacketSize),
                "interval": int(endpoint.bInterval),
            }
            for endpoint in interface
        ]
        interfaces.append({
            "number": int(interface.bInterfaceNumber),
            "alternate_setting": int(interface.bAlternateSetting),
            "class": int(interface.bInterfaceClass),
            "subclass": int(interface.bInterfaceSubClass),
            "protocol": int(interface.bInterfaceProtocol),
            "endpoints": endpoints,
        })
    interface_numbers = {item["number"] for item in interfaces}
    if expected_interfaces is not None and len(interface_numbers) != expected_interfaces:
        raise UsbValidationError(
            f"USB consumer device has {len(interface_numbers)} interfaces, "
            f"expected {expected_interfaces}"
        )
    return {
        "vid": int(device.idVendor),
        "pid": int(device.idProduct),
        "speed": speed,
        "configuration": int(configuration.bConfigurationValue),
        "interfaces": interfaces,
    }


def run_standard_reconnect_validation(
    *, vid: int, pid: int, cycles: int, timeout: float,
) -> dict[str, int]:
    """Exercise ordinary USB reset without claiming interfaces or sending payloads."""
    if cycles < 0:
        raise UsbValidationError("USB reconnect cycle count must not be negative")
    _, usb_util = _modules()
    completed = 0
    for _ in range(cycles):
        device = _find_ids(vid=vid, pid=pid, timeout=timeout)
        try:
            device.reset()
        finally:
            usb_util.dispose_resources(device)
        device, _ = _configured_device(vid=vid, pid=pid, timeout=timeout)
        usb_util.dispose_resources(device)
        completed += 1
    return {"requested_cycles": cycles, "completed_cycles": completed}


def _claim(device: Any, interfaces: tuple[int, ...] = (0, 1)) -> tuple[Any, list[int]]:
    _, usb_util = _modules()
    detached: list[int] = []
    for interface in interfaces:
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
    for interface in interfaces:
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
        "wake_dctl_before", "wake_dctl_after", "wake_dsts_before", "wake_dsts_after",
        "wake_pcgcctl_before", "wake_pcgcctl_after",
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


def _input_event_device(sysfs: Path) -> Path:
    usb_device = sysfs.resolve()
    for candidate in Path("/sys/class/input").glob("event*"):
        target = (candidate / "device").resolve()
        if usb_device == target or usb_device in target.parents:
            return Path("/dev/input") / candidate.name
    raise UsbValidationError("cannot find the validation device's input event node")


def _power_attributes(power: Path) -> dict[str, str]:
    return {
        name: (power / name).read_text().strip()
        for name in ("control", "autosuspend_delay_ms", "wakeup")
    }


def _restore_power_attributes(power: Path, attributes: dict[str, str]) -> None:
    for name in ("control", "autosuspend_delay_ms", "wakeup"):
        try:
            (power / name).write_text(attributes[name])
        except OSError:
            pass


def _claimed_status(device: Any) -> dict[str, int]:
    usb_util, detached = _claim(device, (0,))
    try:
        return read_status(device)
    finally:
        _release(device, usb_util, detached)


def _wait_runtime_status(power: Path, expected: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (power / "runtime_status").read_text().strip() == expected:
            return True
        time.sleep(0.001)
    return False


def _validate_host_resume(before: dict[str, int], after: dict[str, int]) -> None:
    if after["configured_count"] != before["configured_count"]:
        raise UsbValidationError(
            f"host resume reset or reconfigured the device; before={before}; after={after}"
        )
    if after["suspend_count"] <= before["suspend_count"]:
        raise UsbValidationError(
            f"firmware did not observe host-controlled USB suspend; "
            f"before={before}; after={after}"
        )
    if after["resume_count"] <= before["resume_count"]:
        raise UsbValidationError(
            f"firmware did not observe host-controlled USB resume; "
            f"before={before}; after={after}"
        )


def run_host_resume_validation(*, timeout: float) -> dict[str, Any]:
    device = _find(timeout)
    power = _sysfs_device(device) / "power"
    attributes = _power_attributes(power)
    try:
        usb_util, detached = _claim(device, (0,))
        try:
            # A previous interrupted validation may have left a one-shot wake
            # request armed. Cancel it so this control phase exercises only the
            # ordinary host-initiated resume path.
            device.ctrl_transfer(
                0x41, REQUEST_ARM_REMOTE_WAKE, 0, 0, None, timeout=2000,
            )
            before = read_status(device)
        finally:
            _release(device, usb_util, detached)
    except Exception as error:
        raise UsbValidationError(
            f"cannot initialize host-resume control phase: {error}"
        ) from error
    suspended = False
    resumed = False
    try:
        try:
            (power / "autosuspend_delay_ms").write_text("0")
            (power / "control").write_text("auto")
        except PermissionError as error:
            raise UsbValidationError(
                "M4 power validation requires root write access to USB runtime-PM sysfs"
            ) from error
        suspended = _wait_runtime_status(power, "suspended", timeout)
        if suspended:
            (power / "control").write_text("on")
            resumed = _wait_runtime_status(power, "active", timeout)
    finally:
        _restore_power_attributes(power, attributes)

    try:
        device = _find(timeout)
        after = _claimed_status(device)
    except Exception as error:
        raise UsbValidationError(
            f"cannot read status after host-initiated resume: {error}"
        ) from error
    if not suspended:
        raise UsbValidationError(
            f"host did not runtime-suspend the USB device; status={after}"
        )
    if not resumed:
        raise UsbValidationError(
            f"host did not resume the runtime-suspended USB device; status={after}"
        )
    _validate_host_resume(before, after)
    return {
        "suspended": suspended,
        "resumed": resumed,
        "before_status": before,
        "after_status": after,
    }


def run_power_validation(*, timeout: float, wake_delay_ms: int = 500) -> dict[str, Any]:
    device = _find(timeout)
    sysfs = _sysfs_device(device)
    power = sysfs / "power"
    attributes = _power_attributes(power)
    suspended = False
    resumed = False
    input_fd: int | None = None
    try:
        try:
            # Enable wakeup policy before advertising DEVICE_REMOTE_WAKEUP. Linux
            # evaluates the policy while preparing runtime suspend.
            (power / "wakeup").write_text("enabled")
            # Leave a visible active interval after remote wake.  With a zero
            # delay Linux can autosuspend the device again before userspace
            # observes the transient resume, turning a successful wake into a
            # false failure.
            (power / "autosuspend_delay_ms").write_text("1000")
        except PermissionError as error:
            raise UsbValidationError(
                "M4 power validation requires root write access to USB runtime-PM sysfs"
            ) from error

        # Keeping usbhid open makes its interface request remote wakeup from
        # the USB core. Claim only the vendor interface used for test control.
        input_fd = os.open(_input_event_device(sysfs), os.O_RDONLY | os.O_NONBLOCK)
        usb_util, detached = _claim(device, (0,))
        try:
            before = read_status(device)
            # Standard SET_FEATURE(DEVICE_REMOTE_WAKEUP), then arm the firmware.
            device.ctrl_transfer(0x00, 0x03, 0x0001, 0, None, timeout=2000)
            device.ctrl_transfer(
                0x41, REQUEST_ARM_REMOTE_WAKE, wake_delay_ms, 0, None, timeout=2000,
            )
        finally:
            _release(device, usb_util, detached)

        (power / "control").write_text("auto")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = (power / "runtime_status").read_text().strip()
            if state == "suspended":
                suspended = True
            elif suspended and state == "active":
                resumed = True
                (power / "control").write_text("on")
                break
            # Pin the device on as soon as the resume transition is observed.
            time.sleep(0.0001)
    finally:
        if input_fd is not None:
            os.close(input_fd)
        _restore_power_attributes(power, attributes)

    # A failed selective-resume can make Linux reset and re-enumerate the
    # device.  Let libusb discard the removed generation so diagnostics come
    # from the live device instead of failing while opening a stale handle.
    time.sleep(1.0)
    device = _find(timeout)
    usb_util, detached = _claim(device)
    try:
        after = read_status(device)
    finally:
        _release(device, usb_util, detached)
    if not suspended:
        raise UsbValidationError(
            f"host did not runtime-suspend the USB device; status={after}"
        )
    if not resumed:
        raise UsbValidationError(
            f"device did not remotely wake the USB link; status={after}"
        )
    if after["configured_count"] != before["configured_count"]:
        raise UsbValidationError(
            f"remote wake caused a USB reset or reconfiguration; "
            f"before={before}; after={after}"
        )
    if after["suspend_count"] <= before["suspend_count"]:
        raise UsbValidationError(
            f"firmware did not observe suspend before remote wake; "
            f"before={before}; after={after}"
        )
    if after["resume_count"] <= before["resume_count"]:
        raise UsbValidationError(
            f"firmware did not observe resume after remote wake; "
            f"before={before}; after={after}"
        )
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
