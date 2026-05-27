# zygo-dataX v0.1.1 Release Notes

## Changes

- Zemax export is now Grid Sag only.
- Removed Extended Polynomial TXT/CSV export, CLI `--xy-order`, and web download links.
- Documented why Extended Polynomial was removed: Zemax checks showed the fitted continuous surface can differ materially from the sampled DATX wave-error map, while Grid Sag preserves the measured rectangular grid.
- Added `docs/images/zemax-grid-sag-vs-extended-polynomial.jpg` as the Zemax sag-map comparison screenshot.
- `zernike_equivalent_terms.csv` now outputs Noll terms 1 through 20.
- Zernike CSV and HTML report now include radial degree `n`, azimuthal degree `m`, and normalized `Zj` expression columns.
- Windows packaging metadata now targets version `0.1.1`.
- GHCR workflow default image tag is now `0.1.1`.

## Validation

- `python -m compileall src/zygo_datax`
- Real DATX CLI `analyze`
- Real DATX CLI `zemax`
- Public container upload through `https://zygo.claw.holocat.com/analyze`
- Docker container health check on `https://zygo.claw.holocat.com/health`

## Windows Build Note

The Python source package and CLI are prepared from Linux. Final Windows `.exe`, portable ZIP, and installer artifacts must be built on Windows with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_windows_launcher.ps1
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_portable.ps1
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_installer.ps1
```
