# SPDX-License-Identifier: BSD-3-Clause
"""Generate a portable offline power report without third-party web assets."""

from __future__ import annotations

import csv
import html
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


class PowerReportError(RuntimeError):
    pass


def _envelope(path: Path, sample_count: int, bucket_limit: int) -> list[list[float]]:
    if sample_count < 2 or bucket_limit < 2:
        raise PowerReportError("capture and bucket limits must contain at least two samples")
    bucket_size = max(1, math.ceil(sample_count / bucket_limit))
    buckets: list[list[float]] = []
    count = 0
    start = end = total = low = high = 0.0
    try:
        stream = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise PowerReportError(f"cannot open capture CSV: {error}") from error
    with stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["time_s", "current_a"]:
            raise PowerReportError("capture CSV has an unexpected schema")
        for row_number, row in enumerate(reader, 2):
            try:
                current_time = float(row["time_s"])
                current_a = float(row["current_a"]) * 1_000_000.0
            except (KeyError, TypeError, ValueError) as error:
                raise PowerReportError(f"capture row {row_number} is invalid") from error
            if not math.isfinite(current_time) or not math.isfinite(current_a):
                raise PowerReportError(f"capture row {row_number} is nonfinite")
            if count == 0:
                start = current_time
                low = high = current_a
            end = current_time
            low = min(low, current_a)
            high = max(high, current_a)
            total += current_a
            count += 1
            if count == bucket_size:
                buckets.append([
                    round((start + end) / 2.0, 6),
                    round(low, 3), round(high, 3), round(total / count, 3),
                ])
                count = 0
                total = 0.0
        if count:
            buckets.append([
                round((start + end) / 2.0, 6),
                round(low, 3), round(high, 3), round(total / count, 3),
            ])
    if len(buckets) < 2:
        raise PowerReportError("capture produced fewer than two visualization buckets")
    return buckets


def _relative_link(target: Path, output: Path) -> str:
    return Path(os.path.relpath(target.resolve(), output.parent.resolve())).as_posix()


def _payload(report: dict[str, Any], report_path: Path, output: Path) -> dict[str, Any]:
    if report.get("operation") != "blu939-suite" or report.get("status") != "ok":
        raise PowerReportError("a successful blu939-suite report is required")
    profiles = report.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise PowerReportError("power suite report has no profiles")
    values = []
    for profile in profiles:
        try:
            name = profile["name"]
            measurement = profile["measurement"]
            csv_path = Path(profile["csv"])
            raw_path = Path(profile["raw"])
            sample_count = int(measurement["sample_count"])
        except (KeyError, TypeError, ValueError) as error:
            raise PowerReportError("power suite profile is malformed") from error
        if not isinstance(name, str) or not name:
            raise PowerReportError("power suite profile name is invalid")
        if not csv_path.is_file() or not raw_path.is_file():
            raise PowerReportError(f"profile {name} has missing capture files")
        values.append({
            "name": name,
            "duration_s": measurement["duration_s"],
            "average_ua": measurement["average_current_a"] * 1_000_000.0,
            "peak_ma": measurement["peak_current_a"] * 1_000.0,
            "energy_mj": measurement["energy_j"] * 1_000.0,
            "negative_samples": measurement["negative_samples"],
            "sample_count": sample_count,
            "csv": _relative_link(csv_path, output),
            "raw": _relative_link(raw_path, output),
            "csv_sha256": profile.get("csv_sha256", ""),
            "raw_sha256": profile.get("raw_sha256", ""),
            "observations": profile.get("observations", {}),
            "envelope": _envelope(csv_path, sample_count, 1400),
        })
    metadata = report.get("instrument_metadata", {})
    cleanup = report.get("cleanup", {})
    return {
        "started_at": report.get("started_at", ""),
        "instrument": report.get("instrument", "BLU939"),
        "supply_voltage_v": report.get("supply_voltage_v"),
        "calibrated": metadata.get("calibrated"),
        "cleanup": cleanup,
        "report": _relative_link(report_path, output),
        "profiles": values,
    }


def _document(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    title = html.escape(f"{payload['instrument']} power report")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:light dark;font-family:system-ui,sans-serif;--bg:#f5f7f8;--fg:#18272d;--muted:#5f727a;--surface:#fff;--line:#d5dfe3;--series:#087f8c;--band:rgba(8,127,140,.18);--accent:#075f69}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101719;--fg:#e4edef;--muted:#9dafb5;--surface:#172124;--line:#344448;--series:#5fc4cf;--band:rgba(95,196,207,.2);--accent:#8ad9e1}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg)}}main{{max-width:1180px;margin:auto;padding:24px 18px 48px}}h1{{font-size:1.65rem;margin:0}}.meta{{color:var(--muted);margin:.35rem 0 1.25rem}}.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}}.metric{{background:var(--surface);padding:14px}}.metric span{{display:block;color:var(--muted);font-size:.78rem}}.metric strong{{display:block;font-size:1.25rem;font-weight:500;margin-top:4px;font-variant-numeric:tabular-nums}}.controls{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:22px 0 10px}}select{{font:inherit;color:var(--fg);background:var(--surface);border:1px solid var(--line);padding:8px 10px}}.chart-wrap{{position:relative;background:var(--surface);border:1px solid var(--line);padding:12px}}canvas{{display:block;width:100%;height:430px}}.tooltip{{position:absolute;display:none;pointer-events:none;background:var(--fg);color:var(--bg);padding:6px 8px;font-size:.78rem;white-space:nowrap}}.caption{{color:var(--muted);font-size:.8rem;margin:.55rem 0 0}}.links{{display:flex;gap:16px;flex-wrap:wrap}}a{{color:var(--accent)}}table{{width:100%;border-collapse:collapse;margin-top:24px}}th,td{{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums}}th:first-child,td:first-child{{text-align:left}}th{{font-weight:500;color:var(--muted)}}footer{{color:var(--muted);font-size:.78rem;margin-top:22px}}@media(max-width:600px){{canvas{{height:320px}}th:nth-child(4),td:nth-child(4){{display:none}}}}
</style></head><body><main>
<h1>{title}</h1><p class="meta" id="meta"></p>
<section class="summary" aria-label="Selected profile summary">
<div class="metric"><span>Average current</span><strong id="average"></strong></div>
<div class="metric"><span>Peak sample</span><strong id="peak"></strong></div>
<div class="metric"><span>Energy</span><strong id="energy"></strong></div>
<div class="metric"><span>Samples</span><strong id="samples"></strong></div>
</section>
<div class="controls"><label for="profile">Profile</label><select id="profile"></select><div class="links"><a id="csv">Full CSV</a><a id="raw">Raw samples</a><a id="report">Run report</a></div></div>
<div class="chart-wrap"><canvas id="chart" role="img" aria-label="Current over time, showing mean and min/max envelope"></canvas><div class="tooltip" id="tooltip"></div></div>
<p class="caption">Mean line with per-bucket minimum/maximum envelope. The visualization is downsampled; linked CSV and binary files are original.</p>
<table><thead><tr><th>Profile</th><th>Average</th><th>Power</th><th>Peak sample</th><th>Energy</th><th>Duration</th></tr></thead><tbody id="rows"></tbody></table>
<footer id="footer"></footer>
</main><script>const DATA={encoded};
const $=id=>document.getElementById(id),select=$('profile'),canvas=$('chart'),tip=$('tooltip');let active=0,points=[];
const ua=v=>`${{v.toFixed(3)}} µA`, ma=v=>`${{v.toFixed(3)}} mA`, mj=v=>`${{v.toFixed(3)}} mJ`;
DATA.profiles.forEach((p,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=p.name;select.append(o)}});
$('meta').textContent=`${{DATA.supply_voltage_v.toFixed(3)}} V · ${{DATA.started_at}} · calibration metadata flag ${{DATA.calibrated}}`;
$('report').href=DATA.report;
$('rows').innerHTML=DATA.profiles.map(p=>`<tr><td>${{p.name}}</td><td>${{ua(p.average_ua)}}</td><td>${{(p.average_ua*DATA.supply_voltage_v/1000).toFixed(3)}} mW</td><td>${{ma(p.peak_ma)}}</td><td>${{mj(p.energy_mj)}}</td><td>${{p.duration_s.toFixed(3)}} s</td></tr>`).join('');
$('footer').textContent=`Output off requested: ${{DATA.cleanup.output_requested}} · LM20 restore verified: ${{DATA.cleanup.restore_verified}} · peer restore verified: ${{DATA.cleanup.peer_restore_verified}}`;
function draw(){{const p=DATA.profiles[active],rect=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));const c=canvas.getContext('2d');c.scale(dpr,dpr);const w=rect.width,h=rect.height,m={{l:62,r:18,t:16,b:42}},pw=w-m.l-m.r,ph=h-m.t-m.b,all=p.envelope.flatMap(d=>[d[1],d[2]]),xmin=p.envelope[0][0],xmax=p.envelope.at(-1)[0],ymin=Math.min(...all),ymax=Math.max(...all),pad=(ymax-ymin||1)*.06,lo=ymin-pad,hi=ymax+pad,x=v=>m.l+(v-xmin)/(xmax-xmin||1)*pw,y=v=>m.t+(hi-v)/(hi-lo)*ph,css=getComputedStyle(document.documentElement);c.clearRect(0,0,w,h);c.strokeStyle=css.getPropertyValue('--line');c.fillStyle=css.getPropertyValue('--muted');c.font='12px system-ui';c.textAlign='right';c.textBaseline='middle';for(let i=0;i<=4;i++){{const v=lo+(hi-lo)*i/4,py=y(v);c.beginPath();c.moveTo(m.l,py);c.lineTo(w-m.r,py);c.stroke();c.fillText(v.toFixed(0),m.l-8,py)}}c.textAlign='center';c.textBaseline='top';for(let i=0;i<=4;i++){{const v=xmin+(xmax-xmin)*i/4,px=x(v);c.fillText(v.toFixed(2),px,h-m.b+8)}}c.save();c.translate(15,m.t+ph/2);c.rotate(-Math.PI/2);c.fillText('Current (µA)',0,0);c.restore();c.fillText('Time (s)',m.l+pw/2,h-16);c.fillStyle=css.getPropertyValue('--band');c.beginPath();p.envelope.forEach((d,i)=>{{const px=x(d[0]),py=y(d[2]);i?c.lineTo(px,py):c.moveTo(px,py)}});[...p.envelope].reverse().forEach(d=>c.lineTo(x(d[0]),y(d[1])));c.closePath();c.fill();c.strokeStyle=css.getPropertyValue('--series');c.lineWidth=1.5;c.beginPath();p.envelope.forEach((d,i)=>{{const px=x(d[0]),py=y(d[3]);i?c.lineTo(px,py):c.moveTo(px,py)}});c.stroke();points=p.envelope.map(d=>({{x:x(d[0]),t:d[0],low:d[1],high:d[2],mean:d[3]}}));}}
function update(){{const p=DATA.profiles[active];$('average').textContent=ua(p.average_ua);$('peak').textContent=ma(p.peak_ma);$('energy').textContent=mj(p.energy_mj);$('samples').textContent=p.sample_count.toLocaleString();$('csv').href=p.csv;$('raw').href=p.raw;draw()}}
select.addEventListener('change',()=>{{active=Number(select.value);tip.style.display='none';update()}});canvas.addEventListener('pointermove',e=>{{if(!points.length)return;const r=canvas.getBoundingClientRect(),px=e.clientX-r.left;let best=points[0];for(const p of points)if(Math.abs(p.x-px)<Math.abs(best.x-px))best=p;tip.textContent=`${{best.t.toFixed(4)}} s · mean ${{best.mean.toFixed(3)}} µA · ${{best.low.toFixed(3)}}…${{best.high.toFixed(3)}} µA`;tip.style.display='block';tip.style.left=Math.min(r.width-tip.offsetWidth-8,Math.max(8,px+12))+'px';tip.style.top='10px'}});canvas.addEventListener('pointerleave',()=>tip.style.display='none');new ResizeObserver(draw).observe(canvas);update();
</script></body></html>'''


def generate_report(report_path: Path, output: Path | None = None) -> Path:
    report_path = report_path.resolve()
    if report_path.is_dir():
        report_path = report_path / "run.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PowerReportError(f"cannot read run report: {error}") from error
    destination = (output or report_path.with_name("index.html")).resolve()
    document = _document(_payload(report, report_path, destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=destination.parent,
        prefix=f".{destination.name}.", delete=False,
    ) as stream:
        stream.write(document)
        temporary = Path(stream.name)
    os.replace(temporary, destination)
    destination.chmod(0o644)
    return destination
