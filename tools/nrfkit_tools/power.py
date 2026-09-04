# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


class PowerCaptureError(RuntimeError):
    pass


REQUIRED_PROFILES = (
    "idle",
    "direct-1m",
    "direct-2m",
    "direct-4m",
    "timeslot-retry-4m",
    "ble",
    "ble-timeslot-4m",
)


def summarize_capture(
    path: Path,
    *,
    supply_voltage_v: float,
    minimum_duration_s: float,
    maximum_sample_gap_s: float,
) -> dict[str, Any]:
    if not math.isfinite(supply_voltage_v) or supply_voltage_v <= 0.0:
        raise PowerCaptureError("supply voltage must be finite and positive")
    if minimum_duration_s <= 0.0 or maximum_sample_gap_s <= 0.0:
        raise PowerCaptureError("duration and sample-gap limits must be positive")
    try:
        stream = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise PowerCaptureError(f"cannot open capture: {error}") from error

    with stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["time_s", "current_a"]:
            raise PowerCaptureError(
                "capture must have exactly the time_s,current_a header"
            )
        first_time: float | None = None
        previous_time: float | None = None
        previous_current: float | None = None
        charge_c = 0.0
        peak_current_a = 0.0
        maximum_gap_s = 0.0
        sample_count = 0
        for row_number, row in enumerate(reader, 2):
            try:
                current_time = float(row["time_s"])
                current_a = float(row["current_a"])
            except (KeyError, TypeError, ValueError) as error:
                raise PowerCaptureError(
                    f"capture row {row_number} is not numeric"
                ) from error
            if (
                not math.isfinite(current_time)
                or not math.isfinite(current_a)
                or current_a < 0.0
            ):
                raise PowerCaptureError(
                    f"capture row {row_number} has an invalid value"
                )
            if first_time is None:
                first_time = current_time
            elif previous_time is not None and previous_current is not None:
                gap_s = current_time - previous_time
                if gap_s <= 0.0:
                    raise PowerCaptureError("capture timestamps must strictly increase")
                maximum_gap_s = max(maximum_gap_s, gap_s)
                charge_c += gap_s * (previous_current + current_a) / 2.0
            previous_time = current_time
            previous_current = current_a
            peak_current_a = max(peak_current_a, current_a)
            sample_count += 1

    if sample_count < 2 or first_time is None or previous_time is None:
        raise PowerCaptureError("capture must contain at least two samples")
    duration_s = previous_time - first_time
    if duration_s < minimum_duration_s:
        raise PowerCaptureError(
            f"capture duration {duration_s} is below {minimum_duration_s} seconds"
        )
    if maximum_gap_s > maximum_sample_gap_s:
        raise PowerCaptureError(
            f"capture sample gap {maximum_gap_s} exceeds {maximum_sample_gap_s} seconds"
        )
    return {
        "sample_count": sample_count,
        "duration_s": duration_s,
        "maximum_sample_gap_s": maximum_gap_s,
        "average_current_a": charge_c / duration_s,
        "peak_current_a": peak_current_a,
        "charge_c": charge_c,
        "energy_j": charge_c * supply_voltage_v,
    }
