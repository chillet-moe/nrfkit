# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from .image import parse_elf, parse_ihex, require_allowed
from .process import atomic_json, run_logged


class ReferenceContractError(RuntimeError):
    pass


def _metadata_value(path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*(\S.*?)\s*$")
    try:
        matches = [match.group(1) for line in path.read_text(encoding="utf-8").splitlines()
                   if (match := pattern.match(line))]
    except OSError as error:
        raise ReferenceContractError(f"cannot read build metadata {path}: {error}") from error
    if len(matches) != 1:
        raise ReferenceContractError(f"build metadata must declare exactly one {key}: {path}")
    return matches[0]


def _build_domains(build_dir: Path) -> tuple[str, dict[str, Path], list[str]]:
    domains = build_dir / "domains.yaml"
    default = _metadata_value(domains, "default")
    lines = domains.read_text(encoding="utf-8").splitlines()
    domain_builds: dict[str, Path] = {}
    for index, line in enumerate(lines):
        match_name = re.fullmatch(r"\s*-\s+name:\s*(\S.*?)\s*", line)
        if match_name:
            for candidate in lines[index + 1 :]:
                if re.match(r"\s*-\s+name:", candidate):
                    break
                match = re.fullmatch(r"\s+build_dir:\s*(\S.*?)\s*", candidate)
                if match:
                    domain_builds[match_name.group(1)] = Path(match.group(1)).resolve()
                    break
    if default not in domain_builds or any(
        not path.is_relative_to(build_dir.resolve()) for path in domain_builds.values()
    ):
        raise ReferenceContractError("build domains are missing or outside the reference build")
    try:
        flash_index = lines.index("flash_order:")
    except ValueError as error:
        raise ReferenceContractError("build metadata has no flash_order") from error
    flash_order: list[str] = []
    for line in lines[flash_index + 1 :]:
        match = re.fullmatch(r"\s+-\s+(\S.*?)\s*", line)
        if not match:
            break
        flash_order.append(match.group(1))
    if not flash_order or any(name not in domain_builds for name in flash_order):
        raise ReferenceContractError("flash_order does not identify valid build domains")
    return default, domain_builds, flash_order


def _runner_artifact(domain_build: Path, key: str, root: Path) -> Path:
    value = _metadata_value(domain_build / "zephyr/runners.yaml", key)
    path = Path(value)
    if not path.is_absolute():
        if path.name != value:
            raise ReferenceContractError("relative runner artifact must be a plain file name")
        path = domain_build / "zephyr" / path
    path = path.resolve()
    if not (path.is_relative_to(domain_build.resolve()) or path.is_relative_to(root.resolve())):
        raise ReferenceContractError("runner artifact is outside the build and locked source roots")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_lock(project: Path) -> dict[str, Any]:
    path = project / "docs/provenance/sources.lock"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceContractError(f"cannot read source lock: {error}") from error
    if value.get("schema") != "nrf-cmake-sdk-sources/v1":
        raise ReferenceContractError("unsupported source lock schema")
    return value


def oracle(project: Path, oracle_id: str) -> dict[str, Any]:
    try:
        return load_lock(project)["oracles"][oracle_id]
    except KeyError as error:
        raise ReferenceContractError(f"unknown oracle: {oracle_id}") from error


def _git_head(path: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"], check=True,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ReferenceContractError(f"cannot identify Git module {path}: {error}") from error


def _toolchain_variant(toolchain: Path) -> str:
    candidates = (
        ("zephyr/gnu", toolchain / "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"),
        ("zephyr", toolchain / "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"),
    )
    matches = [variant for variant, compiler in candidates if compiler.is_file()]
    if len(matches) != 1:
        raise ReferenceContractError("official toolchain does not contain exactly one supported Arm compiler")
    return matches[0]


def prepare(project: Path, oracle_id: str, root: Path, toolchain: Path) -> Path:
    root = root.resolve()
    toolchain = toolchain.resolve()
    contract = oracle(project, oracle_id)
    sdk_config = toolchain / "opt/zephyr-sdk/cmake/Zephyr-sdkConfig.cmake"
    if not sdk_config.is_file():
        raise ReferenceContractError("official toolchain does not contain a Zephyr SDK package")
    toolchain_variant = _toolchain_variant(toolchain)
    for relative, expected in contract["modules"].items():
        module = root / relative
        actual = _git_head(module)
        if actual != expected:
            raise ReferenceContractError(
                f"module {relative} is {actual}, expected {expected}"
            )
    file_receipts: dict[str, str] = {}
    for relative, expected in contract["files"].items():
        path = root / relative
        if not path.is_file():
            raise ReferenceContractError(f"required oracle file is missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise ReferenceContractError(
                f"oracle file hash mismatch for {relative}: {actual}"
            )
        file_receipts[relative] = actual
    lock_path = project / "docs/provenance/sources.lock"
    receipt = {
        "schema": "nrf-cmake-sdk-source-receipt/v1",
        "oracle": oracle_id,
        "root": str(root),
        "toolchain": str(toolchain),
        "toolchain_variant": toolchain_variant,
        "source_lock_sha256": sha256(lock_path),
        "modules": contract["modules"],
        "files": file_receipts,
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    output = project / ".work/reference/sources" / f"{oracle_id}.json"
    atomic_json(output, receipt)
    return output


def load_receipt(project: Path, oracle_id: str) -> tuple[Path, Path, dict[str, Any]]:
    path = project / ".work/reference/sources" / f"{oracle_id}.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceContractError(
            f"source receipt is missing or invalid; run reference prepare: {error}"
        ) from error
    if receipt.get("schema") != "nrf-cmake-sdk-source-receipt/v1" or receipt.get("oracle") != oracle_id:
        raise ReferenceContractError("source receipt has an invalid identity")
    lock_hash = sha256(project / "docs/provenance/sources.lock")
    if receipt.get("source_lock_sha256") != lock_hash:
        raise ReferenceContractError("source receipt is stale for the tracked source lock")
    root = Path(receipt["root"])
    toolchain = Path(receipt["toolchain"])
    contract = oracle(project, oracle_id)
    for relative, expected in contract["modules"].items():
        if _git_head(root / relative) != expected:
            raise ReferenceContractError(f"source receipt module changed: {relative}")
    if not (toolchain / "opt/zephyr-sdk/cmake/Zephyr-sdkConfig.cmake").is_file():
        raise ReferenceContractError("source receipt official toolchain is unavailable")
    if receipt.get("toolchain_variant") != _toolchain_variant(toolchain):
        raise ReferenceContractError("source receipt official toolchain variant changed")
    return root, toolchain, receipt


def _build_manifest(
    oracle_id: str,
    root: Path,
    build_dir: Path,
    contract: dict[str, Any],
    source_receipt_sha256: str,
) -> Path:
    default_domain, domain_builds, flash_order = _build_domains(build_dir)
    elf = _runner_artifact(domain_builds[default_domain], "elf_file", root)
    if not elf.is_file():
        raise ReferenceContractError("official build did not produce its declared debug ELF")
    elf_image = parse_elf(elf)
    try:
        debug_allowlist = contract["image_allowlists"][default_domain]
    except KeyError as error:
        raise ReferenceContractError("source lock has no allowlist for the default domain") from error
    require_allowed(elf_image.ranges, tuple(tuple(item) for item in debug_allowlist))
    images: list[dict[str, Any]] = []
    for order, domain in enumerate(flash_order):
        ihex = _runner_artifact(domain_builds[domain], "hex_file", root)
        if not ihex.is_file():
            raise ReferenceContractError(f"official build did not produce the declared HEX for {domain}")
        hex_image = parse_ihex(ihex)
        try:
            image_allowlist = contract["image_allowlists"][domain]
        except KeyError as error:
            raise ReferenceContractError(f"source lock has no allowlist for {domain}") from error
        require_allowed(hex_image.ranges, tuple(tuple(item) for item in image_allowlist))
        images.append({
            "domain": domain, "order": order, "path": str(ihex),
            "sha256": sha256(ihex), "ranges": hex_image.ranges,
            "allowlist": image_allowlist,
        })
    manifest = {
        "schema": "nrf-cmake-sdk-image/v1", "oracle": oracle_id,
        "source_receipt_sha256": source_receipt_sha256,
        "soc": contract["soc"], "core": contract["core"], "board": contract["board"],
        "board_version": contract["board_version"], "device_family": contract["device_family"],
        "expected_token": contract["expected_token"], "vcom": contract["vcom"],
        "debug_allowlist": debug_allowlist,
        "debug_elf": {"path": str(elf.resolve()), "sha256": sha256(elf), "ranges": elf_image.ranges},
        "images": images,
    }
    manifest_path = build_dir / "image-manifest.json"
    atomic_json(manifest_path, manifest)
    return manifest_path


def build(project: Path, oracle_id: str, timeout: float, west: str = "west") -> Path:
    root, toolchain, receipt = load_receipt(project, oracle_id)
    contract = oracle(project, oracle_id)
    build_dir = project / ".work/reference/build" / oracle_id
    run_dir = project / ".work/runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-reference-build-{oracle_id}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    argv = [
        west, "-z", str(root / "zephyr"), "build",
        "--build-dir", str(build_dir), str(root / contract["sample"]),
        "--board", contract["board"], "--pristine=always",
    ]
    report: dict[str, Any] = {
        "schema": "nrf-cmake-sdk-run/v1", "operation": "reference-build",
        "oracle": oracle_id, "status": "running", "argv": argv,
        "source_receipt_sha256": sha256(project / ".work/reference/sources" / f"{oracle_id}.json"),
    }
    atomic_json(run_dir / "run.json", report)
    environment = os.environ.copy()
    cache_dir = project / ".work/reference/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    environment.update({
        "ZEPHYR_TOOLCHAIN_VARIANT": receipt["toolchain_variant"],
        "ZEPHYR_SDK_INSTALL_DIR": str(toolchain / "opt/zephyr-sdk"),
        "XDG_CACHE_HOME": str(cache_dir),
    })
    result = run_logged(
        argv, run_dir / "build.log", timeout, cwd=root, environment=environment
    )
    report["process"] = {
        "returncode": result.returncode, "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
    }
    if result.returncode:
        report["status"] = "failed"
        atomic_json(run_dir / "run.json", report)
        raise ReferenceContractError(f"official reference build failed; see {run_dir / 'build.log'}")
    try:
        manifest_path = _build_manifest(
            oracle_id, root, build_dir, contract, report["source_receipt_sha256"]
        )
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    report["status"] = "ok"
    report["manifest"] = str(manifest_path)
    atomic_json(run_dir / "run.json", report)
    return manifest_path
