# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import unittest
from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nrfkit_tools.hci import (
    H4EventParser,
    HciContractError,
    advertising_name,
    advertising_reports,
    command_complete,
    command_packet,
)
from nrfkit_tools.cli import command_m6_sdc_oracle
from nrfkit_tools.process import ProcessResult


class HciTests(unittest.TestCase):
    def test_command_packet_and_fragmented_command_complete(self) -> None:
        self.assertEqual(command_packet(0x0C03), bytes.fromhex("01030c00"))
        parser = H4EventParser()
        self.assertEqual(parser.feed(bytes.fromhex("040e")), [])
        events = parser.feed(bytes.fromhex("0401030c00"))
        self.assertEqual(command_complete(events[0], 0x0C03), b"")

    def test_command_complete_rejects_controller_error(self) -> None:
        event = H4EventParser().feed(bytes.fromhex("040e0401030c0c"))[0]
        with self.assertRaisesRegex(HciContractError, "status 0x0c"):
            command_complete(event, 0x0C03)

    def test_legacy_advertising_report_extracts_name(self) -> None:
        data = bytes.fromhex("0201060a096e72666b69742d7331")
        parameters = (
            bytes((0x02, 0x01, 0x00, 0x01))
            + bytes((0x66, 0x55, 0x44, 0x33, 0x22, 0x11))
            + bytes((len(data),)) + data + bytes((0xD6,))
        )
        event = H4EventParser().feed(
            bytes((0x04, 0x3E, len(parameters))) + parameters
        )[0]
        reports = advertising_reports(event)
        self.assertEqual(reports[0]["address"], ":".join(("11", "22", "33", "44", "55", "66")))
        self.assertEqual(reports[0]["rssi"], -42)
        self.assertEqual(advertising_name(reports[0]["data"]), "nrfkit-s1")

    def test_parser_rejects_non_event_h4_packets(self) -> None:
        with self.assertRaisesRegex(HciContractError, "packet type"):
            H4EventParser().feed(bytes((0x02, 0x00, 0x00, 0x00, 0x00)))

    def test_oracle_gate_disables_advertising_and_scanning(self) -> None:
        class Session:
            transcript = bytearray(b"h4 evidence")

            def __init__(self, descriptor: int):
                self.commands: list[tuple[int, bytes]] = []

            def command(self, opcode: int, parameters: bytes = b"", timeout: float = 5.0) -> bytes:
                self.commands.append((opcode, parameters))
                return {
                    0x1001: bytes((0x0D, 0x34, 0x12, 0x0D, 0x59, 0x00, 0x34, 0x12)),
                    0x1003: bytes(8),
                    0x2003: bytes(8),
                }.get(opcode, b"")

            def next_event(self, deadline: float):
                data = bytes.fromhex("020106")
                parameters = (
                    bytes((0x02, 0x01, 0x00, 0x01))
                    + bytes((0x66, 0x55, 0x44, 0x33, 0x22, 0x11))
                    + bytes((len(data),)) + data + bytes((0xD6,))
                )
                return H4EventParser().feed(
                    bytes((0x04, 0x3E, len(parameters))) + parameters
                )[0]

        manifest = {
            "oracle": "ncs-hci-uart-sdc", "board_version": "PCA10184",
            "vcom": 1, "device_family": "NRF54L", "core": "Application",
            "hci_transport": {
                "type": "H4", "baud": 1000000, "hardware_flow_control": True,
            },
            "build_evidence": {"status": "ok"},
        }
        args = Namespace(
            manifest=Path("manifest.json"), nrfutil="nrfutil", timeout=5.0,
            probe_serial="LM20", reset_kind="RESET_DEFAULT", hci_timeout=1.0,
            advertising_timeout=1.0, scan_timeout=1.0, scan_reports=1,
            serial_ready_delay=0.0, device_name="nrfkit-sdc-oracle",
        )
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            created: list[Session] = []

            def session_factory(descriptor: int) -> Session:
                session = Session(descriptor)
                created.append(session)
                return session

            with (
                patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                patch("nrfkit_tools.cli.load_manifest", return_value=manifest),
                patch(
                    "nrfkit_tools.cli._initialize_device_report",
                    side_effect=lambda *unused: report.update({"stages": []}),
                ),
                patch("nrfkit_tools.cli._select", return_value={"serialNumber": "probe"}),
                patch("nrfkit_tools.cli._probe_lock", return_value=nullcontext()),
                patch("nrfkit_tools.cli._snapshot_hexes", return_value=[Path("image.hex")]),
                patch("nrfkit_tools.cli._program"),
                patch("nrfkit_tools.cli.sha256", return_value="a" * 64),
                patch("nrfkit_tools.cli._serial_port", return_value=Path("test-vcom")),
                patch("nrfkit_tools.cli._serial_open", return_value=17),
                patch("nrfkit_tools.cli.termios.tcflush"),
                patch("nrfkit_tools.cli.time.sleep"),
                patch("nrfkit_tools.cli.H4Session", side_effect=session_factory),
                patch(
                    "nrfkit_tools.cli.run_logged",
                    return_value=ProcessResult(0, False, 0.01, ""),
                ),
                patch(
                    "nrfkit_tools.cli.scan_ble_advertisement",
                    return_value={
                        "rssi_observed": True,
                        "cleanup": {"verified": True},
                    },
                ),
                patch(
                    "nrfkit_tools.cli._serial_cleanup",
                    return_value=({"serial_closed": True}, None),
                ),
            ):
                self.assertEqual(command_m6_sdc_oracle(args), 0)
            opcodes = [opcode for opcode, unused in created[0].commands]
            self.assertIn((0x200A, b"\x00"), created[0].commands)
            self.assertIn((0x200C, b"\x00\x01"), created[0].commands)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(opcodes[:4], [0x0C03, 0x1001, 0x1003, 0x2003])


if __name__ == "__main__":
    unittest.main()
