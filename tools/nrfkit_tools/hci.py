# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
import os
import select
import struct
import time


class HciContractError(RuntimeError):
    pass


H4_COMMAND = 0x01
H4_EVENT = 0x04
EVENT_COMMAND_COMPLETE = 0x0E
EVENT_LE_META = 0x3E
LE_ADVERTISING_REPORT = 0x02


@dataclass(frozen=True)
class HciEvent:
    event_code: int
    parameters: bytes


class H4EventParser:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[HciEvent]:
        self._buffer.extend(data)
        events: list[HciEvent] = []
        while self._buffer:
            if self._buffer[0] != H4_EVENT:
                raise HciContractError(
                    f"unexpected H4 packet type 0x{self._buffer[0]:02x}"
                )
            if len(self._buffer) < 3:
                break
            size = self._buffer[2]
            if len(self._buffer) < size + 3:
                break
            events.append(HciEvent(self._buffer[1], bytes(self._buffer[3:size + 3])))
            del self._buffer[:size + 3]
        return events


def command_packet(opcode: int, parameters: bytes = b"") -> bytes:
    if not 0 <= opcode <= 0xFFFF:
        raise HciContractError("HCI opcode is outside the 16-bit field")
    if len(parameters) > 0xFF:
        raise HciContractError("HCI command parameters exceed the 8-bit length field")
    return bytes((H4_COMMAND,)) + struct.pack("<HB", opcode, len(parameters)) + parameters


def command_complete(event: HciEvent, opcode: int) -> bytes | None:
    if event.event_code != EVENT_COMMAND_COMPLETE:
        return None
    if len(event.parameters) < 4:
        raise HciContractError("truncated HCI Command Complete event")
    completed_opcode = int.from_bytes(event.parameters[1:3], "little")
    if completed_opcode != opcode:
        return None
    return_parameters = event.parameters[3:]
    if not return_parameters:
        raise HciContractError("HCI Command Complete has no status parameter")
    if return_parameters[0] != 0:
        raise HciContractError(
            f"HCI command 0x{opcode:04x} failed with status 0x{return_parameters[0]:02x}"
        )
    return return_parameters[1:]


def advertising_reports(event: HciEvent) -> list[dict[str, object]]:
    if event.event_code != EVENT_LE_META or len(event.parameters) < 2:
        return []
    if event.parameters[0] != LE_ADVERTISING_REPORT:
        return []
    count = event.parameters[1]
    offset = 2
    reports: list[dict[str, object]] = []
    for _ in range(count):
        if offset + 9 > len(event.parameters):
            raise HciContractError("truncated LE Advertising Report")
        event_type = event.parameters[offset]
        address_type = event.parameters[offset + 1]
        address = bytes(reversed(event.parameters[offset + 2:offset + 8])).hex(":")
        data_size = event.parameters[offset + 8]
        offset += 9
        if offset + data_size + 1 > len(event.parameters):
            raise HciContractError("truncated LE Advertising Report data")
        data = bytes(event.parameters[offset:offset + data_size])
        rssi = int.from_bytes(event.parameters[offset + data_size:offset + data_size + 1],
                              "little", signed=True)
        offset += data_size + 1
        reports.append({
            "event_type": event_type,
            "address_type": address_type,
            "address": address,
            "data": data,
            "rssi": rssi,
        })
    if offset != len(event.parameters):
        raise HciContractError("LE Advertising Report has trailing bytes")
    return reports


def advertising_name(data: bytes) -> str | None:
    offset = 0
    while offset < len(data):
        size = data[offset]
        if size == 0:
            break
        end = offset + size + 1
        if end > len(data) or size < 1:
            raise HciContractError("malformed advertising data")
        ad_type = data[offset + 1]
        if ad_type in (0x08, 0x09):
            return data[offset + 2:end].decode("utf-8", errors="strict")
        offset = end
    return None


class H4Session:
    def __init__(self, descriptor: int):
        self.descriptor = descriptor
        self.parser = H4EventParser()
        self.pending: list[HciEvent] = []
        self.transcript = bytearray()

    def _write(self, data: bytes, deadline: float) -> None:
        offset = 0
        while offset < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HciContractError("timed out writing an HCI command")
            _, writable, _ = select.select([], [self.descriptor], [], remaining)
            if not writable:
                raise HciContractError("timed out writing an HCI command")
            offset += os.write(self.descriptor, data[offset:])

    def next_event(self, deadline: float) -> HciEvent:
        if self.pending:
            return self.pending.pop(0)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HciContractError("timed out waiting for an HCI event")
            readable, _, _ = select.select([self.descriptor], [], [], remaining)
            if not readable:
                raise HciContractError("timed out waiting for an HCI event")
            data = os.read(self.descriptor, 65536)
            if not data:
                raise HciContractError("HCI transport returned end of file")
            self.transcript.extend(data)
            self.pending.extend(self.parser.feed(data))
            if self.pending:
                return self.pending.pop(0)

    def command(self, opcode: int, parameters: bytes = b"", timeout: float = 5.0) -> bytes:
        deadline = time.monotonic() + timeout
        self._write(command_packet(opcode, parameters), deadline)
        while True:
            result = command_complete(self.next_event(deadline), opcode)
            if result is not None:
                return result
