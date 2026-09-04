# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .process import atomic_json


class EquivalenceContractError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_path(path: Path, source_root: Path, build_root: Path) -> str:
    path = path.resolve()
    if path.is_relative_to(source_root):
        return path.relative_to(source_root).as_posix()
    if path.is_relative_to(build_root):
        return "@build/" + path.relative_to(build_root).as_posix()
    raise EquivalenceContractError(f"compiled source is outside locked roots: {path.name}")


def _normalized_command(entry: dict[str, Any], source_root: Path, build_root: Path) -> str:
    value = entry.get("command")
    if value is None:
        arguments = entry.get("arguments")
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise EquivalenceContractError("compile database entry has no valid command")
        value = "\0".join(arguments)
    if not isinstance(value, str):
        raise EquivalenceContractError("compile database command is not text")
    replacements = sorted(
        ((str(source_root), "@source"), (str(build_root), "@build")),
        key=lambda item: len(item[0]), reverse=True,
    )
    for original, replacement in replacements:
        value = value.replace(original, replacement)
    return value


def build_equivalence_receipt(
    source_root: Path, build_root: Path, compile_commands: Path, autoconf: Path,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    build_root = build_root.resolve()
    try:
        entries = json.loads(compile_commands.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EquivalenceContractError(f"cannot read compile database: {error}") from error
    if not isinstance(entries, list) or not entries:
        raise EquivalenceContractError("compile database is empty or invalid")

    sources: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise EquivalenceContractError("compile database entry has no source file")
        source = Path(entry["file"]).resolve()
        if not source.is_file():
            raise EquivalenceContractError(f"compiled source is missing: {source.name}")
        canonical = _canonical_path(source, source_root, build_root)
        command = _normalized_command(entry, source_root, build_root)
        command_hash = hashlib.sha256(command.encode()).hexdigest()
        source_hash = _sha256(source)
        record = sources.setdefault(canonical, {"sha256": source_hash, "commands": []})
        if record["sha256"] != source_hash:
            raise EquivalenceContractError(f"compiled source changed during audit: {canonical}")
        if command_hash not in record["commands"]:
            record["commands"].append(command_hash)

    for record in sources.values():
        record["commands"].sort()
    sources = dict(sorted(sources.items()))
    nrf_bm_sources = [path for path in sources if path.startswith("nrf-bm/")]
    try:
        config_text = autoconf.read_text(encoding="utf-8")
    except OSError as error:
        raise EquivalenceContractError(f"cannot read generated autoconf: {error}") from error
    macros = [line for line in config_text.splitlines() if line.startswith("#define CONFIG_")]
    if not macros:
        raise EquivalenceContractError("generated autoconf contains no CONFIG_ definitions")

    return {
        "schema": "nrfkit-nrf-bm-equivalence/v1",
        "release": "nRF Connect SDK Bare Metal v2.0.1",
        "oracle": "nrf-bm-ble-hids-mouse-s115",
        "autoconf": {"sha256": _sha256(autoconf), "macro_count": len(macros)},
        "compile_entry_count": len(entries),
        "compiled_source_count": len(sources),
        "nrf_bm_sources": nrf_bm_sources,
        "sources": sources,
    }


def audit_equivalence(
    source_root: Path, build_root: Path, compile_commands: Path, autoconf: Path,
    receipt_path: Path, config_path: Path, *, update: bool = False,
) -> dict[str, Any]:
    receipt = build_equivalence_receipt(source_root, build_root, compile_commands, autoconf)
    if update:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(autoconf.read_bytes())
        atomic_json(receipt_path, receipt)
        return receipt
    try:
        expected = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EquivalenceContractError(f"cannot read tracked equivalence receipt: {error}") from error
    if expected != receipt:
        raise EquivalenceContractError("official source list, source hashes, or compile settings drifted")
    if not config_path.is_file() or _sha256(config_path) != receipt["autoconf"]["sha256"]:
        raise EquivalenceContractError("tracked static compatibility config drifted from autoconf")
    return receipt
