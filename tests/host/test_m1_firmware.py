# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from nrfkit_tools.image import parse_elf, parse_ihex, require_allowed
from nrfkit_tools.cli import load_manifest
from nrfkit_tools.sdk import SdkContractError, create_device_manifest


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
STARTUP = (
    ROOT / "third_party/nrfx/mdk/nrf54l/nrf54lm20a"
    / "gcc_startup_nrf54lm20a_application.S"
)
DEVICE_HEADER = (
    ROOT / "third_party/nrfx/mdk/nrf54l/nrf54lm20a"
    / "nrf54lm20a_application.h"
)
SVD = (
    ROOT / "third_party/nrfx/mdk/nrf54l/nrf54lm20a"
    / "nrf54lm20a_application.svd"
)


def run(argv: list[str]) -> str:
    result = subprocess.run(
        argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stdout}")
    return result.stdout


class M1FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmake = shutil.which("cmake")
        cls.ninja = shutil.which("ninja") or shutil.which("ninja-build")
        configured_llvm = os.environ.get("NRF_LLVM_ROOT")
        clang = shutil.which("clang")
        if configured_llvm:
            llvm_root = Path(configured_llvm)
        elif clang:
            llvm_root = Path(clang).resolve().parent.parent
        else:
            raise unittest.SkipTest("the locked LLVM tools are required")
        cls.llvm_root = llvm_root
        cls.readelf = llvm_root / "bin/llvm-readelf"
        cls.objdump = llvm_root / "bin/llvm-objdump"
        if not all((cls.cmake, cls.ninja, cls.readelf.exists(), cls.objdump.exists())):
            raise unittest.SkipTest("CMake, Ninja, and the locked LLVM tools are required")
        cls.temporary = tempfile.TemporaryDirectory()
        base = Path(cls.temporary.name)
        cls.build_a = base / "absolute-path-a" / "build"
        cls.build_b = base / "different" / "absolute-path-b" / "build"
        for build in (cls.build_a, cls.build_b):
            run([
                cls.cmake, "-S", str(EXAMPLES), "-B", str(build), "-G", "Ninja",
                f"-DNrfKit_DIR={ROOT / 'cmake'}",
                f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                f"-DNRF_LLVM_ROOT={llvm_root}",
            ])
            run([cls.cmake, "--build", str(build)])

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_load_images_are_reproducible_across_absolute_build_paths(self) -> None:
        for name in (
            "empty", "blinky", "fault", "constructors", "hardware_validation",
            "nrfx_minimal", "nrfx_all",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    (self.build_a / f"{name}.hex").read_bytes(),
                    (self.build_b / f"{name}.hex").read_bytes(),
                )
                self.assertEqual(
                    (self.build_a / f"{name}.bin").read_bytes(),
                    (self.build_b / f"{name}.bin").read_bytes(),
                )

    def test_vector_table_matches_startup_header_and_svd(self) -> None:
        source = STARTUP.read_text(encoding="utf-8")
        table = source.split("__isr_vector:", 1)[1].split(
            ".size __isr_vector", 1
        )[0]
        entries = re.findall(r"^\s*\.long\s+([^\s/]+)", table, re.MULTILINE)
        self.assertEqual(len(entries), 306)
        self.assertEqual(entries[-1], "VREGUSB_IRQHandler")

        header = DEVICE_HEADER.read_text(encoding="utf-8")
        header_irqs = {
            name: int(value)
            for name, value in re.findall(
                r"^\s*([A-Z][A-Z0-9_]+)_IRQn\s*=\s*([0-9]+),",
                header, re.MULTILINE,
            )
        }
        svd_irqs = {}
        for interrupt in ET.parse(SVD).getroot().findall(".//interrupt"):
            name = interrupt.findtext("name")
            value = interrupt.findtext("value")
            if name is not None and value is not None:
                svd_irqs[name] = int(value)
        self.assertEqual(set(header_irqs) - set(svd_irqs), {"CM33SS"})
        self.assertEqual(
            {name: header_irqs[name] for name in svd_irqs}, svd_irqs
        )
        for name, irq in header_irqs.items():
            self.assertEqual(entries[16 + irq], f"{name}_IRQHandler")

        sections = run([str(self.readelf), "-SW", str(self.build_a / "empty.elf")])
        self.assertRegex(
            sections,
            r"\.isr_vector\s+PROGBITS\s+00000000\s+[0-9a-f]+\s+0004c8",
        )
        vector_dump = run([
            str(self.objdump), "-s", "-j", ".isr_vector",
            str(self.build_a / "empty.elf"),
        ])
        self.assertIn("00000420", vector_dump)

    def test_runtime_sections_symbols_and_constructor_contract(self) -> None:
        empty_sections = run([
            str(self.readelf), "-SW", str(self.build_a / "empty.elf")
        ])
        for name in (".data", ".bss", ".noinit"):
            self.assertIn(name, empty_sections)
        empty_symbols = run([
            str(self.readelf), "-sW", str(self.build_a / "empty.elf")
        ])
        for symbol in (
            "__StackTop", "__StackLimit", "__HeapBase", "__HeapLimit",
            "__data_load_start", "__data_start", "__data_end",
            "__bss_start__", "__bss_end__", "__noinit_start", "__noinit_end",
            "nrfkit_last_fault",
        ):
            self.assertIn(symbol, empty_symbols)
        self.assertRegex(empty_symbols, r"20040000\s+0\s+NOTYPE\s+GLOBAL.*__StackTop")

        constructors_sections = run([
            str(self.readelf), "-SW", str(self.build_a / "constructors.elf")
        ])
        self.assertRegex(
            constructors_sections,
            r"\.init_array\s+INIT_ARRAY\s+[0-9a-f]+\s+[0-9a-f]+\s+000004",
        )
        constructors_symbols = run([
            str(self.readelf), "-sW", str(self.build_a / "constructors.elf")
        ])
        self.assertIn("constructor_observation", constructors_symbols)

    def test_artifacts_and_load_ranges_exclude_configuration_regions(self) -> None:
        for name in (
            "empty", "blinky", "fault", "constructors", "hardware_validation",
            "nrfx_minimal", "nrfx_all",
        ):
            with self.subTest(name=name):
                elf = parse_elf(self.build_a / f"{name}.elf")
                ihex = parse_ihex(self.build_a / f"{name}.hex")
                require_allowed(elf.ranges, ((0, 0x001FD000),))
                require_allowed(ihex.ranges, ((0, 0x001FD000),))
                self.assertTrue((self.build_a / f"{name}.map").is_file())
                self.assertTrue((self.build_a / f"{name}.image-layout.json").is_file())

    def test_nrfx_configuration_and_sources_are_target_scoped(self) -> None:
        import json

        minimal_dir = self.build_a / "nrfkit/nrfx_minimal"
        all_dir = self.build_a / "nrfkit/nrfx_all"
        minimal_config = (minimal_dir / "nrfx_config.h").read_text(encoding="utf-8")
        all_config = (all_dir / "nrfx_config.h").read_text(encoding="utf-8")
        self.assertNotEqual(minimal_config, all_config)
        self.assertNotIn("NRFX_TIMER_ENABLED 1", minimal_config)
        self.assertIn("NRFX_TIMER_ENABLED 1", all_config)
        self.assertIn(
            "#define NRFX_GPIOTE_CONFIG_NUM_OF_EVT_HANDLERS "
            "CONFIG_NRFX_GPIOTE_NUM_OF_EVT_HANDLERS",
            all_config,
        )

        minimal = json.loads((minimal_dir / "nrfx-target.json").read_text())
        complete = json.loads((all_dir / "nrfx-target.json").read_text())
        self.assertEqual(minimal["drivers"], ["gpio", "reset"])
        self.assertEqual(minimal["sources"], [])
        self.assertIn("drivers/src/nrfx_timer.c", complete["sources"])
        self.assertNotIn("drivers/src/nrfx_timer.c", minimal["sources"])
        self.assertTrue(all("zephyr" not in source.lower() for source in complete["sources"]))

    def test_nrfx_resource_conflicts_and_bounds_fail_at_configure_time(self) -> None:
        fixture = ROOT / "tests/consumer/nrfx-contract"
        for case, expected in (
            ("conflict", "already owned by 'first'"),
            ("out-of-range", "is out of range"),
        ):
            build = Path(self.temporary.name) / f"nrfx-{case}"
            result = subprocess.run([
                self.cmake, "-S", str(fixture), "-B", str(build), "-G", "Ninja",
                f"-DNrfKit_DIR={ROOT / 'cmake'}",
                f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                f"-DNRF_LLVM_ROOT={self.llvm_root}",
                f"-DCONTRACT_CASE={case}",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected, result.stdout)

    def test_sdk_artifacts_form_a_guarded_device_manifest(self) -> None:
        path = create_device_manifest(
            ROOT, self.build_a, "hardware_validation", "NRFKIT_TEST build-id"
        )
        manifest = load_manifest(path)
        self.assertEqual(manifest["oracle"], "sdk-hardware_validation")
        self.assertEqual(manifest["expected_token"], "NRFKIT_TEST build-id")
        self.assertEqual(manifest["images"][0]["domain"], "hardware_validation")

    def test_sdk_manifest_rejects_unsafe_names_and_tokens_before_artifact_access(self) -> None:
        with self.assertRaisesRegex(SdkContractError, "basename"):
            create_device_manifest(ROOT, self.build_a, "../outside", "safe")
        with self.assertRaisesRegex(SdkContractError, "printable ASCII"):
            create_device_manifest(ROOT, self.build_a, "empty", "bad\ntoken")

    def test_linker_assertion_rejects_stack_overlap(self) -> None:
        result = subprocess.run(
            [self.cmake, "--build", str(self.build_a), "--target", "linker_overlap"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("zeroed RAM overlaps stack", result.stdout)

    def test_gnu_arm_compile_and_link_smoke(self) -> None:
        if shutil.which("arm-none-eabi-gcc") is None:
            self.skipTest("GNU Arm Embedded is not installed")
        build = Path(self.temporary.name) / "gnu-arm-smoke"
        run([
            self.cmake, "-S", str(EXAMPLES), "-B", str(build), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-gcc.cmake'}",
        ])
        run([self.cmake, "--build", str(build), "--target", "empty"])
        self.assertTrue((build / "empty.elf").is_file())

    def test_installed_package_builds_firmware_offline(self) -> None:
        base = Path(self.temporary.name) / "installed-firmware"
        sdk_build = base / "sdk-build"
        prefix = base / "prefix"
        build = base / "consumer-build"
        run([
            self.cmake, "-S", str(ROOT), "-B", str(sdk_build), "-G", "Ninja",
            f"-DCMAKE_INSTALL_PREFIX={prefix}",
        ])
        run([self.cmake, "--build", str(sdk_build), "--target", "install"])
        run([
            self.cmake, "-S", str(EXAMPLES), "-B", str(build), "-G", "Ninja",
            f"-DCMAKE_PREFIX_PATH={prefix}",
            f"-DCMAKE_TOOLCHAIN_FILE={prefix / 'share/nrfkit/cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={self.llvm_root}",
        ])
        run([self.cmake, "--build", str(build), "--target", "m3_power_validation"])
        self.assertTrue((build / "m3_power_validation.elf").is_file())

    def test_custom_layout_checks_reject_startup_abi_and_declared_range_drift(self) -> None:
        for case, expected in (("symbol", "nrfkit: data copy source"),
                               ("range", "nrfkit: vector outside layout")):
            with self.subTest(case=case):
                source = Path(self.temporary.name) / f"bad-layout-{case}"
                shutil.copytree(ROOT / "tests/consumer/custom-layout", source)
                script = (ROOT / "linker/layouts/nrf54lm20a-cpuapp-standalone.ld").read_text()
                if case == "symbol":
                    script = script.replace("__data_load_start = LOADADDR(.data);",
                                            "__data_load_start = LOADADDR(.data) + 4;")
                else:
                    layout = json.loads((source / "image-layout.json").read_text())
                    layout["rram"]["origin"] = 0x800
                    layout["rram"]["length"] -= 0x800
                    (source / "image-layout.json").write_text(json.dumps(layout))
                (source / "custom.ld").write_text(script)
                cmake_file = source / "CMakeLists.txt"
                cmake_file.write_text(cmake_file.read_text().replace(
                    "${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld",
                    "${CMAKE_CURRENT_SOURCE_DIR}/custom.ld"))
                build = source / "build"
                run([self.cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
                     f"-DNrfKit_DIR={ROOT / 'cmake'}",
                     f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                     f"-DNRF_LLVM_ROOT={self.llvm_root}"])
                result = subprocess.run([self.cmake, "--build", str(build)],
                                        text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout + result.stderr)

    def test_consumer_owned_linker_and_image_layout_are_used_together(self) -> None:
        fixture = ROOT / "tests/consumer/custom-layout"
        build = Path(self.temporary.name) / "custom-layout"
        run([
            self.cmake, "-S", str(fixture), "-B", str(build), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={self.llvm_root}",
        ])
        run([self.cmake, "--build", str(build)])
        self.assertEqual(
            (build / "custom_layout.image-layout.json").read_text(encoding="utf-8"),
            (fixture / "image-layout.json").read_text(encoding="utf-8"),
        )
        reserved_layout = {
            "schema": "nrfkit-image-layout/v1",
            "target": "custom_layout",
            "soc": "nrf54lm20a",
            "core": "cpuapp",
            "rram": {"origin": 0, "length": 0x001F4F00},
            "settings": {"origin": 0x001F4F00, "length": 0x8000, "write_unit": 16},
            "rram_scratch": {"origin": 0x001FCF00, "length": 0x100, "write_unit": 16},
            "ram": {"origin": 0x20000000, "length": 0x40000},
            "configuration_regions_allowed": False,
        }
        (build / "custom_layout.image-layout.json").write_text(
            json.dumps(reserved_layout), encoding="utf-8"
        )
        manifest_path = create_device_manifest(
            ROOT, build, "custom_layout", "CUSTOM_LAYOUT_TEST"
        )
        manifest = load_manifest(manifest_path)
        self.assertEqual(manifest["debug_allowlist"], [[0, 0x001F4F00]])
        self.assertEqual(manifest["images"][0]["allowlist"], [[0, 0x001F4F00]])
        reserved_layout["settings"]["origin"] = 0x1000
        (build / "custom_layout.image-layout.json").write_text(
            json.dumps(reserved_layout), encoding="utf-8"
        )
        with self.assertRaisesRegex(SdkContractError, "regions overlap"):
            create_device_manifest(ROOT, build, "custom_layout", "CUSTOM_LAYOUT_TEST")


if __name__ == "__main__":
    unittest.main()
