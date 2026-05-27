# zygo-dataX

zygo-dataX is a Python package, CLI, web service, container image, and Windows GUI launcher for analyzing Zygo DATX files. It reads Zygo HDF5/DATX surface and intensity data, generates PDF-style wavefront reports, computes metrology metrics, and exports measured surfaces for Zemax / OpticStudio.

The current implementation is calibrated for flat mirror / rectangular aperture workflows where the DATX native surface values are stored in fringes.

## Windows GUI Installation

This is the recommended first path for Windows users. The Windows GUI starts the same local web service used by the container and opens the browser automatically.

### 1. Install Prerequisites

Install these first:

- Windows 10/11
- Python 3.10 or newer from <https://www.python.org/downloads/windows/>
- Git for Windows from <https://git-scm.com/download/win>

During Python installation, enable **Add python.exe to PATH**.

Optional installer build:

- Inno Setup 6 from <https://jrsoftware.org/isinfo.php>

### 2. Clone The Repository

Open PowerShell and run:

```powershell
git clone https://github.com/YonggangG/zygo-datax.git
cd zygo-datax
```

### 3. Build The Windows GUI Launcher

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_windows_launcher.ps1
```

This creates:

```text
dist\zygo-dataX\zygo-dataX.exe
```

### 4. Run The GUI

Run:

```powershell
.\dist\zygo-dataX\zygo-dataX.exe
```

The launcher starts a local server and opens a browser, usually at:

```text
http://127.0.0.1:8017
```

If port `8017` is busy, the launcher tries ports `8020` through `8099`.

### 5. Build A Portable ZIP

After building the launcher, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_portable.ps1
```

Output:

```text
dist\release\zygo-dataX-0.1.1-portable.zip
```

Use:

1. Unzip the portable ZIP.
2. Double-click `zygo-dataX.exe`.
3. Upload a DATX file in the browser.
4. Run analysis and download the generated report/Zemax files.

### 6. Build A Windows Installer

Requires Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_installer.ps1
```

Output:

```text
dist\installer\zygo-dataX-Setup-0.1.1.exe
```

Use:

1. Run the installer.
2. Launch zygo-dataX from the Start Menu.
3. The local browser UI opens automatically.
4. Upload a DATX file and run analysis.

Cross-building a real Windows executable from Linux is not reliable with PyInstaller. Build final Windows artifacts on Windows.

## Installation From Source

Use this path for Linux/macOS development or when you want direct CLI access without building the Windows executable.

```bash
git clone https://github.com/YonggangG/zygo-datax.git
cd zygo-datax
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, the equivalent virtualenv activation is:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run a smoke check:

```bash
python -m compileall src tests
python -m pytest tests
```

## Web Interface Screenshots

Input state after choosing a DATX file. The web UI reads DATX metadata and auto-fills the suggested aperture/crop values.

![zygo-dataX web input auto-fill](docs/images/web-input-autofill.png)

Output state after analysis. The page shows DATX structure, metrics, maps, summary, and downloads for analysis and Zemax artifacts.

![zygo-dataX web analysis output](docs/images/web-output-results.png)

## Features

- Read Zygo DATX / HDF5 files.
- Discover readable 2D datasets and explain key DATX metadata.
- Extract the primary `Data/Surface` and `Data/Intensity` matrices.
- Auto-suggest aperture width/height from the DATX valid surface mask.
- Generate report maps:
  - piston + tilt removed surface map
  - irregularity map with piston + tilt + power removed
  - DATX intensity fringe image
  - summary PNG with metrics and Noll-index Zernike-equivalent terms
- Compute P-V, RMS, Power, Irregularity, and residual RMS.
- Export all three Zemax map variants by default:
  - raw
  - tilt removed
  - irregularity
- Write Zemax Grid Sag DAT files.
- Run as:
  - Windows GUI launcher executable
  - Python CLI
  - FastAPI web service
  - Docker / Portainer container

## Package Structure

```text
zygo-dataX/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── docs/
│   ├── images/
│   │   ├── web-input-autofill.png
│   │   ├── web-output-results.png
│   │   └── zemax-grid-sag-vs-extended-polynomial.jpg
│   ├── portainer-deployment.md
│   ├── windows-gui.md
│   └── windows-release.md
├── packaging/windows/
│   ├── README-WINDOWS.txt
│   └── zygo-dataX.iss
├── scripts/
│   ├── release/
│   │   ├── build_windows_installer.ps1
│   │   └── build_windows_portable.ps1
│   └── windows/
│       └── build_windows_launcher.ps1
├── src/zygo_datax/
│   ├── cli.py
│   ├── core/
│   │   ├── engine.py
│   │   └── metrics.py
│   ├── gui/
│   │   └── launcher.py
│   └── web/
│       └── app.py
└── tests/
    └── test_cli_smoke.py
```

Important modules:

- `zygo_datax.core.engine`: DATX/HDF5 loading, metadata extraction, report generation, metrics, Zemax export.
- `zygo_datax.core.metrics`: polynomial design matrix and least-squares fitting helpers.
- `zygo_datax.cli`: command-line entry point `zygo-datax`.
- `zygo_datax.web.app`: FastAPI upload/analyze/download application.
- `zygo_datax.gui.launcher`: Windows-friendly Tkinter launcher that starts the local web app.

## DATX File Structure

Zygo DATX files are HDF5 containers. A typical file contains:

- `Data/Surface/{...}`: surface phase/height matrix, usually in native fringe units.
- `Data/Intensity/{...}`: measured interferogram intensity matrix.
- `MetaData/...`: measurement and data context metadata.
- Dataset attributes such as no-data values and unit metadata.
- Metadata values such as wavelength and lateral resolution.

DATX matrices often store the full camera/sample plane, for example `1200 x 1200` pixels. The valid optical aperture is usually a smaller region inside that full matrix. zygo-dataX computes a valid mask from finite pixels and no-data attributes, then reports:

- selected surface dataset
- selected intensity dataset
- wavelength
- lateral resolution
- camera size
- valid aperture bounding box in pixels
- valid aperture width/height in mm
- valid pixel count and valid fraction

Example Side 4 values from the current validation sample:

```text
DATX shape:                 1200 x 1200
Lateral resolution:         78.090149 um / px
Valid aperture bbox px:     [192, 342, 739, 906]
Valid aperture size:        42.7153 x 44.0428 mm
```

## Algorithm And Surface Conventions

DATX native surface values are preserved as fringes.

For reflective flat mirror surface sag:

```text
surface_lambda = native_fringes * 0.5
sag_mm = native_fringes * 0.5 * wavelength_nm * 1e-6
```

Main analysis flow:

1. Open the DATX/HDF5 file with `h5py`.
2. Discover numeric 2D datasets.
3. Select the primary surface and intensity datasets.
4. Read no-data metadata and construct a valid aperture mask.
5. Read wavelength and lateral resolution metadata.
6. Convert the requested physical aperture size from mm to pixels.
7. Crop a rectangular report aperture with optional dx/dy offset and edge trim.
8. Fit and remove low-order polynomial terms:
   - piston + tilt for the main report map
   - piston + tilt + power for irregularity
9. Convert native fringes to reflection surface lambda and sag in mm.
10. Generate metrics, maps, Noll-index Zernike-equivalent terms, and Zemax exports.

Report metrics use the reflection surface convention in lambda:

- **P-V**: peak-to-valley of the piston + tilt removed report aperture.
- **RMS**: RMS of the piston + tilt removed report aperture.
- **Power**: mean coefficient of the local-aperture normalized x² and y² power terms.
- **Irregularity**: P-V after removing piston, tilt, and power only.
- **Residual RMS**: RMS of the same piston + tilt + power residual.

Astigmatism is intentionally not removed from irregularity.

The summary/report maps use a Zygo/PDF-style rainbow color scale. The fringe image uses DATX `Data/Intensity` when available, not a synthetic phase cosine image.

## Aperture And Crop Inputs

The web form and CLI aperture/crop options control which rectangular report area is extracted from the full DATX surface matrix.

- `Aperture width,height mm` / `--aperture-mm`: physical report aperture size as `width_mm,height_mm`. The program converts this size to pixels using the DATX lateral resolution metadata. For example, Side 4 auto-fills about `42.7153,44.0428`.
- `dx px` / `--dx-px`: horizontal pixel offset of the aperture center. Positive moves the aperture right; negative moves it left; `0` uses the DATX valid-mask center.
- `dy px` / `--dy-px`: vertical pixel offset of the aperture center. Positive moves the aperture down in image-array coordinates; negative moves it up; `0` uses the DATX valid-mask center.
- `edge trim px` / `--edge-trim-px`: trims this many pixels from each side of the aperture after sizing and centering. Use this to remove unstable edge pixels or to match a Zygo PDF report area that is slightly smaller than the DATX valid mask.

In short: aperture width/height controls the physical size, `dx_px` and `dy_px` control position, and `edge_trim_px` tightens the border. The web UI initializes aperture width/height from the DATX valid aperture and sets `dx_px=0`, `dy_px=0`, and `edge_trim_px=0`. Matching a Zygo PDF exactly may require adjusting these values against the PDF Size X/Y, P-V, and Power.

## CLI Usage

Scan numeric 2D datasets:

```bash
zygo-datax scan sample.datx
```

Explain DATX structure and key metadata:

```bash
zygo-datax structure sample.datx
```

Generate analysis report:

```bash
zygo-datax analyze sample.datx \
  --aperture-mm 40.24,41.16 \
  --dx-px 6 \
  --dy-px 6 \
  --edge-trim-px 3 \
  --target-pv 0.498 \
  --target-rms 0.091 \
  --target-power -0.292 \
  --out reports/sample
```

Export Zemax files:

```bash
zygo-datax zemax sample.datx \
  --aperture-mm 40.24,41.16 \
  --dx-px 6 \
  --dy-px 6 \
  --edge-trim-px 3 \
  --out reports/sample_zemax
```

By default, `zygo-datax zemax` writes all three Zemax map exports: raw, piston + tilt removed, and irregularity. For a single-map debug export, pass one of:

```bash
--map-kind raw
--map-kind tilt_removed
--map-kind irregularity
```

## Web Service

Run locally:

```bash
uvicorn zygo_datax.web.app:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Web workflow:

1. Choose a DATX file.
2. The browser calls `POST /suggest` and auto-fills aperture/crop values from the DATX valid aperture.
3. Adjust aperture/crop values if needed.
4. Click Analyze.
5. Review DATX structure, metrics, maps, summary, and downloads.
6. Download the full ZIP or individual analysis/Zemax files.

Web API routes:

- `GET /`: upload/analyze form.
- `POST /suggest`: read DATX metadata and suggest aperture/crop values.
- `POST /analyze`: run analysis and export all artifacts.
- `GET /api/runs/{run_id}`: JSON result for a previous run.
- `GET /runs/{run_id}/...`: generated files.
- `GET /health`: health check.

## Output Files

Analysis output:

```text
datx_tilt_removed_surface_lambda.png
datx_irregularity_surface_lambda.png
datx_intensity_fringe_pattern.png
datx_simulated_phase_fringe_pattern.png
datx_wavefront_surface_lambda.png
datx_pdf_comparison_summary.png
zernike_equivalent_terms.csv
wavefront_report.json
wavefront_report.html
```

`zernike_equivalent_terms.csv` writes Noll indices 1 through 20. Each row includes radial degree `n`, azimuthal degree `m`, the normalized `Zj` expression, and fitted surface coefficients in lambda, nanometers, and sag millimeters. The fit is still a rectangular-aperture least-squares equivalent for comparison, not a strict circular-aperture Zygo coefficient table.

Zemax output:

```text
zemax_grid_sag_raw.DAT
zemax_grid_sag_tilt_removed.DAT
zemax_grid_sag_irregularity.DAT
zemax_export_readme.txt
```

Extended Polynomial export was removed in v0.1.1. In Zemax/OpticStudio import checks, Grid Sag DAT preserved the measured DATX wave-error map because it carries the sampled rectangular grid directly. Extended Polynomial instead fits a continuous parametric sag surface, which can smooth or distort local measured structure and produce a sag map that differs materially from the DATX result. For this workflow, the measured discrete map is the useful artifact, so zygo-dataX now exports Grid Sag only.

The comparison below shows two Grid Sag imports on the left and center, and an Extended Polynomial import on the right. The fitted Extended Polynomial surface is visibly smoother and does not match the measured local wave-error structure.

![Zemax Grid Sag vs Extended Polynomial sag map comparison](docs/images/zemax-grid-sag-vs-extended-polynomial.jpg)

Web runs also include:

```text
input.datx
structure_summary.json
web_result.json
zygo-dataX-results.zip
```

## Zemax Grid Sag DAT Format

Each Grid Sag DAT file is a pure Zemax data file with no comment lines.

Header:

```text
nx ny delx dely unitflag xdec ydec
```

Current export convention:

- `unitflag=0`: mm
- `xdec=0.0`
- `ydec=0.0`
- CRLF newlines
- final blank line
- rows ordered from upper-left `-x,+y`, then left-to-right by row

Each grid row:

```text
z dz/dx dz/dy d2z/dxdy nodata
```

Valid points use:

```text
nodata = 0
```

Invalid or outside-aperture points use:

```text
0.0 0.0 0.0 0.0 1
```

This is expected. DATX valid apertures rarely fill a perfect rectangle, while Zemax Grid Sag requires a complete rectangular grid. The final `1` tells Zemax to ignore that grid point.

Y derivative and mixed derivative signs are adjusted for Zemax's positive-Y-up row convention.

## Docker

Build and run locally:

```bash
docker build --network=host -t zygo-datax:latest .
docker compose up -d
```

Default URL:

```text
http://127.0.0.1:8017
```

Health check:

```bash
curl http://127.0.0.1:8017/health
```

The container listens on internal port `8000`; `docker-compose.yml` maps host port `8017` to container port `8000`.

## GHCR Image

Published image:

```text
ghcr.io/yonggangg/zygo-datax:latest
ghcr.io/yonggangg/zygo-datax:0.1.1
```

Run directly from GHCR:

```bash
docker run -d \
  --name zygo-datax \
  --restart unless-stopped \
  -p 8017:8000 \
  -e ZYGO_DATAX_RUN_ROOT=/app/runs \
  -e MPLBACKEND=Agg \
  -v zygo-datax-runs:/app/runs \
  ghcr.io/yonggangg/zygo-datax:latest
```

## Portainer Deployment

### Option A: Use GHCR Image

In Portainer:

1. Go to **Stacks**.
2. Click **Add stack**.
3. Name it `zygo-datax`.
4. Use this stack file:

```yaml
services:
  zygo-datax:
    image: ghcr.io/yonggangg/zygo-datax:latest
    container_name: zygo-datax
    restart: unless-stopped
    ports:
      - "8017:8000"
    environment:
      ZYGO_DATAX_RUN_ROOT: /app/runs
      MPLBACKEND: Agg
    volumes:
      - zygo-datax-runs:/app/runs

volumes:
  zygo-datax-runs:
```

5. Deploy the stack.
6. Open `http://SERVER_IP:8017`.
7. Check `http://SERVER_IP:8017/health`.

### Option B: Build From Git Repository

In Portainer:

1. Go to **Stacks**.
2. Click **Add stack**.
3. Choose **Repository**.
4. Repository URL:

   ```text
   https://github.com/YonggangG/zygo-datax.git
   ```

5. Branch: `main`.
6. Compose path:

   ```text
   docker-compose.yml
   ```

7. Deploy.

## Validation Status

Validated locally with Side 1 and Side 4 Zygo DATX samples:

- DATX scan and structure extraction.
- Web upload and auto-suggest.
- Report generation with rainbow maps and three-panel summary.
- DATX intensity fringe rendering.
- Metrics generation.
- CLI `analyze`.
- CLI `zemax` default all-map export.
- Docker container health and real DATX upload.
- Grid Sag DAT file structure and nodata rows.

Current sample metrics may differ from original Zygo PDF RMS because Zygo's exact RMS mask/statistical convention is not fully exposed in the DATX file. P-V and Power have been cross-validated against the available Side 1 and Side 4 report values.

## Release

Current release:

```text
v0.1.1
```

GitHub:

```text
https://github.com/YonggangG/zygo-datax
```

GHCR:

```text
ghcr.io/yonggangg/zygo-datax
```

## Safety Notes

- DATX files may contain measurement metadata. Review files before sharing publicly.
- Large DATX uploads create large run folders and ZIP files. Clean old `runs/` data periodically.
- Confirm Zemax import behavior with a known reference sample before using exported files for formal optical design decisions.
