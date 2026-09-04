# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    timed_out: bool
    duration_seconds: float
    stdout: str


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def _terminate_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_logged(
    argv: Sequence[str],
    log: Path,
    timeout: float,
    *,
    environment: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> ProcessResult:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env=environment,
        cwd=cwd,
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
        result = ProcessResult(
            process.returncode, False, time.monotonic() - started, stdout
        )
    except subprocess.TimeoutExpired:
        _terminate_group(process)
        stdout, _ = process.communicate()
        stdout += f"\ncommand timed out after {timeout:g} seconds\n"
        result = ProcessResult(124, True, time.monotonic() - started, stdout)
    except BaseException:
        _terminate_group(process)
        raise
    log.write_text(result.stdout, encoding="utf-8")
    return result
