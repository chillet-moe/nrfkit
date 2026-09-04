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
            "nrfkit_radio_acquire",
            "nrfkit_radio_release",
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

    def test_dual_board_harness_rejects_a_single_probe(self) -> None:
        cli = (ROOT / "tools/nrfkit_tools/cli.py").read_text(encoding="utf-8")
        self.assertIn('subparsers.add_parser("m5-radio-dual")', cli)
        self.assertIn("requires two distinct probes", cli)
        self.assertIn('receiver_running', cli)

    def test_xo_running_check_preserves_optional_output_contract(self) -> None:
        patch = (ROOT / "patches/nrfx/0002-clock-xo-allow-null-source-output.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("p_clk_src != NULL", patch)
        self.assertIn("&clk_src", patch)


if __name__ == "__main__":
    unittest.main()
