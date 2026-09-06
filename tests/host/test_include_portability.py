# SPDX-License-Identifier: BSD-3-Clause
"""Keep project-owned source includes independent of checkout layout."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROJECT_SOURCE_DIRS = (
    "boards",
    "examples",
    "include",
    "radio",
    "runtime",
    "softdevice",
    "tests",
    "usb",
)
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".S", ".s",
}
RELATIVE_INCLUDE = re.compile(r"^\s*#\s*include(?:_next)?\s*[<\"]([^>\"]+)[>\"]")


class IncludePortabilityTests(unittest.TestCase):
    def test_sdc_platform_contract_stays_out_of_the_public_include_tree(self) -> None:
        self.assertFalse(
            (ROOT / "include/nrfkit/internal/sdc_platform_internal.h").exists()
        )
        self.assertTrue(
            (
                ROOT / "softdevice/include/nrfkit/internal/sdc_platform_internal.h"
            ).is_file()
        )

    def test_project_owned_includes_do_not_walk_out_of_their_source_directory(
        self,
    ) -> None:
        violations = []
        for directory in PROJECT_SOURCE_DIRS:
            root = ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                    continue
                # The immutable vendor inputs have their own self-contained include
                # layout and are deliberately outside this project-owned check.
                if "external" in path.parts or "third_party" in path.parts:
                    continue
                for line_number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1
                ):
                    match = RELATIVE_INCLUDE.match(line)
                    if match and any(
                        part == ".." for part in Path(match.group(1)).parts
                    ):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{line_number}: {match.group(1)}"
                        )
        self.assertEqual(
            violations,
            [],
            "project-owned relative includes:\n" + "\n".join(violations),
        )
