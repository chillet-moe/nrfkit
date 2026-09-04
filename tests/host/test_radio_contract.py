# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RadioContractTests(unittest.TestCase):
    def test_public_header_exposes_explicit_owners_and_configuration(self) -> None:
        header = (ROOT / "include/nrfkit/radio.h").read_text(encoding="utf-8")
        for token in (
            "NRFKIT_RADIO_OWNER_NONE",
            "NRFKIT_RADIO_OWNER_PROPRIETARY",
            "NRFKIT_RADIO_OWNER_BLE",
            "NRFKIT_RADIO_OWNER_TIMESLOT",
            "nrfkit_radio_acquire",
            "nrfkit_radio_release",
            "nrfkit_radio_configure_packet",
            "NRFKIT_RADIO_PHY_2MBIT",
            "NRFKIT_RADIO_PHY_4MBIT",
            "NRFKIT_RADIO_4MBIT_BT_0_6",
            "NRFKIT_RADIO_4MBIT_BT_0_4",
            "nrfkit_radio_configure_1mbit",
        ):
            self.assertIn(token, header)

    def test_radio_is_target_scoped_and_owns_no_vendor_tree(self) -> None:
        module = (ROOT / "cmake/modules/NrfKitFirmware.cmake").read_text(encoding="utf-8")
        self.assertIn("function(nrfkit_enable_radio target)", module)
        self.assertIn('radio/nrf54l/radio.c', module)
        self.assertFalse((ROOT / "radio/vendor").exists())

    def test_single_board_example_uses_radio_domain_timer_and_dppi(self) -> None:
        source = (ROOT / "examples/m5-radio-validation/main.c").read_text(encoding="utf-8")
        for token in ("NRF_TIMER10", "NRF_DPPIC10", "NRF_RADIO_EVENT_END"):
            self.assertIn(token, source)
        self.assertNotIn("NRF_TIMER21", source)

    def test_dual_board_images_have_distinct_tx_and_rx_contracts(self) -> None:
        cmake = (ROOT / "examples/CMakeLists.txt").read_text(encoding="utf-8")
        source = (ROOT / "examples/m5-radio-link/main.c").read_text(encoding="utf-8")
        self.assertIn("m5_radio_${role}", cmake)
        self.assertIn("NRFKIT_M5_LINK_TX", source)
        self.assertIn("NRFKIT_M5_LINK_RX", source)
        self.assertIn("nrf_radio_crc_status_check", source)
        self.assertIn("NRFKIT_RADIO_PHY_2MBIT", source)
        self.assertIn("output[index] = data[index]", source)
        self.assertIn("(uintptr_t)output", source)
        self.assertIn("packet[0] != PACKET_LENGTH", source)
        self.assertIn("IDLE_ATTEMPT_LIMIT", source)
        self.assertIn("received >= 10U && invalid == 0U", source)
        self.assertNotIn("crc_errors == 0U", source)
        self.assertNotIn("timeout--", source)

        peer = (ROOT / "tests/hardware/m5-radio-peer/src/main.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("packet[0] != PACKET_LENGTH", peer)
        self.assertIn("IDLE_ATTEMPT_LIMIT", peer)
        self.assertNotIn("timeout--", peer)

    def test_packet_configuration_uses_a_four_byte_access_address(self) -> None:
        source = (ROOT / "radio/nrf54l/radio.c").read_text(encoding="utf-8")
        self.assertIn("packet.balen = 3U", source)
        self.assertIn("config->access_address & UINT32_C(0x00FFFFFF)", source)
        self.assertIn("config->access_address >> 24U", source)
        self.assertIn("NRF_RADIO_PREAMBLE_LENGTH_16BIT", source)
        self.assertIn("NRF_RADIO_MODE_NRF_4MBIT_BT_0_6", source)
        self.assertIn("NRF_RADIO_MODE_NRF_4MBIT_BT_0_4", source)

    def test_both_primary_4mbit_modes_have_lm20_and_peer_profiles(self) -> None:
        cmake = (ROOT / "examples/CMakeLists.txt").read_text(encoding="utf-8")
        peer = (ROOT / "tests/hardware/m5-radio-peer/src/main.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("m7_radio_${role}_4m_${mode}", cmake)
        for mode in ("bt-0-6", "bt-0-4"):
            for role in ("tx", "rx"):
                self.assertTrue((
                    ROOT / f"tests/hardware/m5-radio-peer/configs/{role}-4m-{mode}.conf"
                ).is_file())
        self.assertIn("CONFIG_NRFKIT_M7_PEER_PHY_4M", peer)
        self.assertTrue((
            ROOT / "tests/hardware/m5-radio-peer/configs/tx-timeslot-4m-bt-0-6.conf"
        ).is_file())

    def test_timeslot_backend_enforces_grant_and_deadline_contract(self) -> None:
        header = (ROOT / "include/nrfkit/timeslot.h").read_text(encoding="utf-8")
        source = (ROOT / "radio/timeslot/nrf54l/timeslot.c").read_text(
            encoding="utf-8"
        )
        module = (ROOT / "cmake/modules/NrfKitFirmware.cmake").read_text(
            encoding="utf-8"
        )
        for token in (
            "nrfkit_timeslot_open", "nrfkit_timeslot_request_earliest",
            "nrfkit_timeslot_close", "nrfkit_timeslot_deadline_pending",
            "NRFKIT_TIMESLOT_ACTION_EXTEND",
            "NRFKIT_TIMESLOT_SIGNAL_BLOCKED", "NRFKIT_TIMESLOT_SIGNAL_CANCELLED",
        ):
            self.assertIn(token, header)
        for token in (
            "MPSL_TIMESLOT_HFCLK_CFG_XTAL_GUARANTEED",
            "MPSL_TIMESLOT_EXTENSION_MARGIN_MIN_US",
            "nrf_timer_cc_set", "cleanup_grant",
            "NRFKIT_RADIO_OWNER_TIMESLOT",
        ):
            self.assertIn(token, source)
        self.assertIn("function(nrfkit_enable_mpsl_timeslot target)", module)
        self.assertIn("enable SDC on '${target}' first", module)
        link = (ROOT / "examples/m7-timeslot-radio-link/main.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("NRFKIT_RADIO_OWNER_TIMESLOT", link)
        self.assertIn("nrfkit_timeslot_deadline_pending", link)
        self.assertIn("GRANT_DISTANCE_US", link)
        retry = (ROOT / "examples/m7-timeslot-retry/main.c").read_text(
            encoding="utf-8"
        )
        for token in (
            "QUEUE_CAPACITY 8U", "MAX_RETRIES 3U", "retries == 8U",
            "channel_switches == 4U", "__WFE()",
        ):
            self.assertIn(token, retry)

    def test_dual_board_harness_rejects_a_single_probe(self) -> None:
        cli = (ROOT / "tools/nrfkit_tools/cli.py").read_text(encoding="utf-8")
        self.assertIn('subparsers.add_parser("m5-radio-dual")', cli)
        self.assertIn('subparsers.add_parser("m7-radio-dual")', cli)
        self.assertIn("requires two distinct probes", cli)
        self.assertIn('receiver_running', cli)
        self.assertIn('args.rounds', cli)
        self.assertIn('"airborne-link", round=round_number', cli)
        self.assertIn('"receiver-ready", round=round_number', cli)
        self.assertIn('"--ready-file", str(ready_file)', cli)
        self.assertNotIn('f"M5 receiver', cli)
        self.assertIn('"--require-rx-crc-rejection"', cli)
        self.assertIn('"crc-rejection", round=round_number', cli)
        self.assertIn('"--retry-contract"', cli)
        self.assertIn('"retry-queue-channel", round=round_number', cli)
        self.assertIn('"--performance-rate"', cli)
        self.assertIn('"radio-performance", round=round_number', cli)

    def test_xo_running_check_preserves_optional_output_contract(self) -> None:
        patch = (ROOT / "patches/nrfx/0002-clock-xo-allow-null-source-output.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("p_clk_src != NULL", patch)
        self.assertIn("&clk_src", patch)


if __name__ == "__main__":
    unittest.main()
