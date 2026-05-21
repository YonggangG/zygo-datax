"""FastAPI web application for zygo-dataX."""

from __future__ import annotations

import html
import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from zygo_datax.core import export_datx_zemax, generate_datx_wavefront_report, summarize_datx_structure

APP_ROOT = Path(__file__).resolve().parents[3]
RUN_ROOT = Path(os.environ.get("ZYGO_DATAX_RUN_ROOT", str(APP_ROOT / "runs"))).resolve()
RUN_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="zygo-dataX", version="0.1.0")


def _parse_aperture(value: str) -> tuple[float, float]:
    try:
        parts = [float(p.strip()) for p in value.split(",")]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid aperture; expected width_mm,height_mm") from exc
    if len(parts) != 2 or parts[0] <= 0 or parts[1] <= 0:
        raise HTTPException(status_code=400, detail="Invalid aperture; expected width_mm,height_mm")
    return parts[0], parts[1]


def _optional_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _save_upload(file: UploadFile, run_dir: Path) -> Path:
    suffix = Path(file.filename or "upload.datx").suffix or ".datx"
    dest = run_dir / f"input{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest


def _zip_run(run_dir: Path) -> Path:
    zip_path = run_dir / "zygo-dataX-results.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(run_dir))
    return zip_path


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return html.escape(str(value))


def _dataset_table(structure: dict[str, Any]) -> str:
    rows = []
    for item in structure["datasets"]:
        selected = []
        if item["path"] == structure.get("selected_surface_dataset"):
            selected.append("surface")
        if item["path"] == structure.get("selected_intensity_dataset"):
            selected.append("intensity")
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(item['path'])}</code></td>"
            f"<td>{html.escape(' x '.join(map(str, item['shape'])))}</td>"
            f"<td>{html.escape(str(item['dtype']))}</td>"
            f"<td>{html.escape(str(item.get('unit') or '-'))}</td>"
            f"<td>{_fmt(item.get('no_data'))}</td>"
            f"<td>{_fmt(item.get('finite_min'))}</td>"
            f"<td>{_fmt(item.get('finite_max'))}</td>"
            f"<td>{html.escape(', '.join(selected))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _link(run_id: str, *parts: str) -> str:
    return "/runs/" + html.escape(run_id) + "/" + "/".join(html.escape(p) for p in parts)


def _suggested_form_values(structure: dict[str, Any]) -> dict[str, Any]:
    width = structure.get("valid_aperture_width_mm")
    height = structure.get("valid_aperture_height_mm")
    aperture_mm = f"{width:.4f},{height:.4f}" if width and height else ""
    return {
        "aperture_mm": aperture_mm,
        "dx_px": 0,
        "dy_px": 0,
        "edge_trim_px": 0,
        "valid_aperture_width_mm": width,
        "valid_aperture_height_mm": height,
        "valid_aperture_bbox_pixels": structure.get("valid_aperture_bbox_pixels"),
        "lateral_resolution_um": structure.get("lateral_resolution_um"),
        "selected_surface_dataset": structure.get("selected_surface_dataset"),
        "note": "Aperture is initialized from the DATX valid surface mask. dx/dy/edge trim default to 0 because DATX alone does not contain the Zygo PDF report crop offset.",
    }


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#18202a; --muted:#5d6876; --line:#d8dee8; --bg:#f6f8fb; --panel:#fff; --accent:#1b6f8f; }}
    body {{ margin:0; font-family:Arial, sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ background:#132330; color:white; padding:18px 26px; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; }}
    section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin-bottom:18px; }}
    h1,h2 {{ margin:0 0 12px; }}
    label {{ display:block; font-weight:700; margin:12px 0 6px; }}
    input, select {{ width:100%; max-width:360px; padding:9px; border:1px solid var(--line); border-radius:6px; }}
    button, .button {{ display:inline-block; background:var(--accent); color:white; border:0; border-radius:6px; padding:10px 14px; text-decoration:none; cursor:pointer; margin:6px 8px 6px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ border:1px solid var(--line); padding:7px 8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef3f7; }}
    code {{ font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:12px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
    .metric {{ font-size:24px; font-weight:700; }}
    .muted {{ color:var(--muted); }}
    img {{ max-width:100%; border:1px solid var(--line); border-radius:6px; background:white; }}
  </style>
</head>
<body><header><h1>zygo-dataX</h1><div>Zygo DATX analysis and Zemax export</div></header><main>{body}</main></body></html>"""
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    body = """
<section>
  <h2>Upload DATX</h2>
  <form action=\"/analyze\" method=\"post\" enctype=\"multipart/form-data\">
    <label>DATX file</label>
    <input id=\"datx-file\" type=\"file\" name=\"file\" accept=\".datx,.datax\" required>
    <p id=\"suggest-status\" class=\"muted\">Choose a DATX file to fill suggested aperture and crop values.</p>
    <label>Aperture width,height mm</label>
    <input id=\"aperture-mm\" name=\"aperture_mm\" placeholder=\"width,height\" required>
    <div class=\"grid\">
      <div><label>dx px</label><input id=\"dx-px\" name=\"dx_px\" type=\"number\" value=\"0\"></div>
      <div><label>dy px</label><input id=\"dy-px\" name=\"dy_px\" type=\"number\" value=\"0\"></div>
      <div><label>edge trim px</label><input id=\"edge-trim-px\" name=\"edge_trim_px\" type=\"number\" value=\"0\"></div>
    </div>
    <div class=\"grid\">
      <div><label>Target P-V lambda, optional</label><input name=\"target_pv\"></div>
      <div><label>Target RMS lambda, optional</label><input name=\"target_rms\"></div>
      <div><label>Target Power lambda, optional</label><input name=\"target_power\"></div>
    </div>
    <p class=\"muted\">Zemax export writes all three maps: raw, piston + tilt removed, and irregularity.</p>
    <p><button type=\"submit\">Analyze</button></p>
  </form>
</section>
<section><h2>Conventions</h2><p>Surface lambda = native fringes * 0.5. Sag mm = native fringes * 0.5 * wavelength_nm * 1e-6. Irregularity removes piston, tilt, and power only. Fringe image uses DATX Data/Intensity.</p></section>
<script>
const fileInput = document.getElementById('datx-file');
const statusEl = document.getElementById('suggest-status');
fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  if (!file) return;
  statusEl.textContent = 'Reading DATX metadata...';
  const form = new FormData();
  form.append('file', file);
  try {
    const response = await fetch('/suggest', { method: 'POST', body: form });
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (data.aperture_mm) document.getElementById('aperture-mm').value = data.aperture_mm;
    document.getElementById('dx-px').value = data.dx_px;
    document.getElementById('dy-px').value = data.dy_px;
    document.getElementById('edge-trim-px').value = data.edge_trim_px;
    const bbox = data.valid_aperture_bbox_pixels ? ' bbox ' + JSON.stringify(data.valid_aperture_bbox_pixels) : '';
    statusEl.textContent = 'Suggested from DATX valid aperture: ' + (data.aperture_mm || 'unavailable') + ' mm;' + bbox + '.';
  } catch (error) {
    statusEl.textContent = 'Could not read DATX suggestions. Enter aperture and crop values manually.';
  }
});
</script>
"""
    return _page("zygo-dataX", body)


@app.post("/suggest")
def suggest(file: UploadFile = File(...)) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="suggest-", dir=RUN_ROOT) as tmp:
        input_path = _save_upload(file, Path(tmp))
        structure = asdict(summarize_datx_structure(input_path))
    return _suggested_form_values(structure)


@app.post("/analyze", response_class=HTMLResponse)
def analyze(
    file: UploadFile = File(...),
    aperture_mm: str = Form(...),
    dx_px: int = Form(default=0),
    dy_px: int = Form(default=0),
    edge_trim_px: int = Form(default=0),
    target_pv: str | None = Form(default=None),
    target_rms: str | None = Form(default=None),
    target_power: str | None = Form(default=None),
) -> HTMLResponse:
    aperture = _parse_aperture(aperture_mm)
    run_id = uuid.uuid4().hex
    run_dir = RUN_ROOT / run_id
    analysis_dir = run_dir / "analysis"
    zemax_dir = run_dir / "zemax"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    zemax_dir.mkdir(parents=True, exist_ok=True)
    input_path = _save_upload(file, run_dir)
    structure = asdict(summarize_datx_structure(input_path))
    report = generate_datx_wavefront_report(
        input_path,
        analysis_dir,
        report_aperture_mm=aperture,
        dx_px=dx_px,
        dy_px=dy_px,
        edge_trim_px=edge_trim_px,
        target_pv=_optional_float(target_pv),
        target_rms=_optional_float(target_rms),
        target_power=_optional_float(target_power),
    )
    zemax_results = {
        map_kind: export_datx_zemax(
            input_path,
            zemax_dir,
            report_aperture_mm=aperture,
            map_kind=map_kind,
            dx_px=dx_px,
            dy_px=dy_px,
            edge_trim_px=edge_trim_px,
        )
        for map_kind in ("raw", "tilt_removed", "irregularity")
    }
    report_data = asdict(report)
    zemax_data = {map_kind: asdict(result) for map_kind, result in zemax_results.items()}
    (run_dir / "structure_summary.json").write_text(__import__("json").dumps(structure, indent=2), encoding="utf-8")
    (run_dir / "web_result.json").write_text(__import__("json").dumps({"structure": structure, "analysis": report_data, "zemax": zemax_data}, indent=2), encoding="utf-8")
    zip_path = _zip_run(run_dir)
    values = report_data["computed_values"]
    metric_cards = "".join(
        f"<div><div class='muted'>{label}</div><div class='metric'>{_fmt(values[key], 7)} λ</div></div>"
        for label, key in [
            ("P-V", "pv_surface_lambda"),
            ("RMS", "rms_surface_lambda"),
            ("Power", "power_surface_lambda"),
            ("Irregularity", "irregularity_surface_lambda"),
        ]
    )
    highlight_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{_fmt(v)}</td></tr>" for k, v in structure["metadata_highlights"].items())
    explanation = "".join(f"<li>{html.escape(item)}</li>" for item in structure["explanation"])
    downloads = [
        ("Full ZIP", _link(run_id, zip_path.name)),
        ("Analysis JSON", _link(run_id, "analysis", "wavefront_report.json")),
        ("Analysis HTML", _link(run_id, "analysis", "wavefront_report.html")),
        ("Zernike CSV", _link(run_id, "analysis", "zernike_equivalent_terms.csv")),
    ]
    for label, result in [
        ("Raw", zemax_results["raw"]),
        ("Tilt Removed", zemax_results["tilt_removed"]),
        ("Irregularity", zemax_results["irregularity"]),
    ]:
        downloads.extend(
            [
                (f"{label} Grid Sag DAT", _link(run_id, "zemax", Path(result.grid_sag_dat).name)),
                (f"{label} Extended Polynomial TXT", _link(run_id, "zemax", Path(result.xy_polynomial_txt).name)),
                (f"{label} Extended Polynomial CSV", _link(run_id, "zemax", Path(result.xy_polynomial_csv).name)),
            ]
        )
    download_links = "".join(f"<a class='button' href='{url}'>{label}</a>" for label, url in downloads)
    body = f"""
<section><h2>DATX Structure</h2>
<div class=\"grid\">
  <div><strong>Wavelength</strong><br>{_fmt(structure.get('wavelength_nm'))} nm</div>
  <div><strong>Lateral resolution</strong><br>{_fmt(structure.get('lateral_resolution_um'))} um / px</div>
  <div><strong>Camera size</strong><br>{_fmt(structure.get('camera_width_mm'))} x {_fmt(structure.get('camera_height_mm'))} mm</div>
  <div><strong>Valid aperture bbox</strong><br>{html.escape(str(structure.get('valid_aperture_bbox_pixels') or '-'))} px</div>
  <div><strong>Valid aperture size</strong><br>{_fmt(structure.get('valid_aperture_width_mm'))} x {_fmt(structure.get('valid_aperture_height_mm'))} mm</div>
  <div><strong>Valid pixels</strong><br>{_fmt(structure.get('valid_pixels'), 8)} / {_fmt(structure.get('total_pixels'), 8)} ({_fmt(structure.get('valid_fraction'))})</div>
</div>
<h3>Readable 2D datasets</h3><table><thead><tr><th>Path</th><th>Shape</th><th>Dtype</th><th>Unit</th><th>No-data</th><th>Min</th><th>Max</th><th>Use</th></tr></thead><tbody>{_dataset_table(structure)}</tbody></table>
<h3>What can be used later</h3><ul>{explanation}</ul>
<h3>Metadata highlights</h3><table>{highlight_rows}</table></section>
<section><h2>Metrics</h2><div class=\"grid\">{metric_cards}</div></section>
<section><h2>Maps and Fringe Image</h2><div class=\"grid\">
  <div><h3>Piston + tilt removed</h3><img src=\"{_link(run_id, 'analysis', 'datx_tilt_removed_surface_lambda.png')}\"></div>
  <div><h3>Irregularity</h3><img src=\"{_link(run_id, 'analysis', 'datx_irregularity_surface_lambda.png')}\"></div>
  <div><h3>Fringe image</h3><img src=\"{_link(run_id, 'analysis', 'datx_intensity_fringe_pattern.png')}\"></div>
</div></section>
<section><h2>Summary</h2><img src=\"{_link(run_id, 'analysis', 'datx_pdf_comparison_summary.png')}\"></section>
<section><h2>Downloads</h2>{download_links}</section>
"""
    return _page("zygo-dataX result", body)


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict[str, Any]:
    path = RUN_ROOT / run_id / "web_result.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return __import__("json").loads(path.read_text(encoding="utf-8"))


@app.get("/runs/{run_id}/{filename}")
@app.get("/runs/{run_id}/{folder}/{filename}")
def run_file(run_id: str, filename: str, folder: str | None = None) -> FileResponse:
    base = RUN_ROOT / run_id
    path = base / filename if folder is None else base / folder / filename
    path = path.resolve()
    if not str(path).startswith(str(base.resolve())) or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
