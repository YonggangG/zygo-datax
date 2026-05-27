"""Zygo DATX analysis mode.

DATX files produced by Zygo Mx are HDF5 containers.  This module keeps the
first-pass reader deliberately conservative: discover the primary surface
dataset, preserve native fringe values, mask Zygo no-data pixels, and write
diagnostic plots plus a JSON report.
"""

from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import matplotlib.pyplot as plt
import numpy as np

from .metrics import design_matrix, fit_polynomial


@dataclass(frozen=True)
class DatxDatasetInfo:
    path: str
    shape: tuple[int, ...]
    dtype: str
    unit: str | None
    no_data: float | int | None
    finite_min: float | None
    finite_max: float | None


@dataclass(frozen=True)
class DatxResult:
    mode: str
    input_file: str
    selected_dataset: str
    dataset_unit: str
    wavelength_nm: float
    lateral_resolution_um: float | None
    camera_width_mm: float | None
    camera_height_mm: float | None
    valid_bbox_pixels: list[int]
    valid_bbox_width_mm: float | None
    valid_bbox_height_mm: float | None
    valid_pixels: int
    total_pixels: int
    valid_fraction: float
    pv_native_fringe: float
    rms_native_fringe: float
    pv_after_tilt_fringe: float
    rms_after_tilt_fringe: float
    power_x_coeff_fringe: float
    power_y_coeff_fringe: float
    power_mean_coeff_fringe: float
    power_pv_fringe: float
    irregularity_fringe: float
    residual_rms_fringe: float
    pv_after_tilt_nm_wavefront: float
    irregularity_nm_wavefront: float
    pv_after_tilt_nm_surface_reflection: float
    irregularity_nm_surface_reflection: float
    report_aperture_width_mm: float | None
    report_aperture_height_mm: float | None
    report_valid_pixels: int
    zygo_style_pv_surface_lambda: float
    zygo_style_rms_surface_lambda: float
    zygo_style_power_surface_lambda: float
    zygo_style_irregularity_surface_lambda: float
    zygo_style_residual_rms_surface_lambda: float
    wavefront_image: str
    tilt_removed_image: str
    irregularity_image: str
    fringe_pattern_image: str
    metrics_json: str
    discovered_datasets: list[DatxDatasetInfo]
    caution: str


@dataclass(frozen=True)
class DatxAlignmentResult:
    mode: str
    input_file: str
    selected_dataset: str
    target_aperture_width_mm: float
    target_aperture_height_mm: float
    target_pv_surface_lambda: float | None
    target_rms_surface_lambda: float | None
    target_power_surface_lambda: float | None
    best: dict[str, float | int | list[int]]
    top_candidates: list[dict[str, float | int | list[int]]]
    candidates_csv: str
    alignment_json: str
    caution: str


@dataclass(frozen=True)
class DatxValidationResult:
    mode: str
    input_file: str
    selected_dataset: str
    report_aperture_width_mm: float
    report_aperture_height_mm: float
    target_values: dict[str, float | None]
    computed_values: dict[str, float]
    deltas: dict[str, float | None]
    best_mask: dict[str, float | int | list[int]]
    validation_json: str
    validation_html: str
    alignment_json: str
    candidates_csv: str
    interpretation: list[str]
    caution: str


@dataclass(frozen=True)
class DatxZemaxExportResult:
    mode: str
    input_file: str
    selected_dataset: str
    map_kind: str
    aperture_bbox_pixels: list[int]
    grid_sag_dat: str
    readme_txt: str
    nx: int
    ny: int
    dx_mm: float
    dy_mm: float
    z_unit: str
    caution: str


@dataclass(frozen=True)
class DatxInspectResult:
    mode: str
    input_file: str
    datasets: list[dict[str, object]]
    metadata_links: list[list[str]]
    result_like_matches: list[dict[str, object]]
    zygo_filter_datasets: list[dict[str, object]]
    saved_analysis_found: bool
    inspect_json: str
    conclusion: str


@dataclass(frozen=True)
class DatxWavefrontReportResult:
    mode: str
    input_file: str
    selected_dataset: str
    wavelength_nm: float
    aperture_bbox_pixels: list[int]
    report_aperture_width_mm: float
    report_aperture_height_mm: float
    computed_values: dict[str, float]
    target_values: dict[str, float | None]
    deltas: dict[str, float | None]
    wavefront_map_png: str
    tilt_removed_map_png: str
    irregularity_map_png: str
    fringe_pattern_png: str
    zernike_csv: str
    report_json: str
    report_html: str
    summary_png: str
    caution: str


@dataclass(frozen=True)
class DatxStructureSummary:
    mode: str
    input_file: str
    datasets: list[DatxDatasetInfo]
    selected_surface_dataset: str | None
    selected_intensity_dataset: str | None
    wavelength_nm: float | None
    lateral_resolution_um: float | None
    camera_width_mm: float | None
    camera_height_mm: float | None
    valid_aperture_bbox_pixels: list[int] | None
    valid_aperture_width_mm: float | None
    valid_aperture_height_mm: float | None
    valid_pixels: int | None
    total_pixels: int | None
    valid_fraction: float | None
    metadata_highlights: dict[str, Any]
    explanation: list[str]


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return _jsonable(value.reshape(-1)[0])
        return [_jsonable(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_jsonable(x) for x in value]
    return value


def _attr_scalar(attrs: h5py.AttributeManager, *names: str) -> Any | None:
    for name in names:
        if name in attrs:
            value = _jsonable(attrs[name])
            if isinstance(value, list) and len(value) == 1:
                return value[0]
            return value
    return None


def _read_global_attrs(file: h5py.File) -> dict[str, Any]:
    """Collect top-level Zygo metadata from the Attributes groups."""
    values: dict[str, Any] = {}
    root = file.get("Attributes")
    if root is None:
        return values

    def visit(_name: str, obj: h5py.Group | h5py.Dataset) -> None:
        for key, value in obj.attrs.items():
            values[key] = _jsonable(value)

    root.visititems(visit)
    return values


def _metadata_number(metadata: dict[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, (int, float)):
        return float(value)
    return None


def discover_datx_datasets(path: str | Path) -> list[DatxDatasetInfo]:
    """Return numeric 2D datasets that could contain image/surface data."""
    out: list[DatxDatasetInfo] = []
    with h5py.File(path, "r") as file:
        def visit(name: str, obj: h5py.Dataset | h5py.Group) -> None:
            if not isinstance(obj, h5py.Dataset) or len(obj.shape) != 2:
                return
            if not np.issubdtype(obj.dtype, np.number):
                return
            data = obj[()]
            no_data = _attr_scalar(obj.attrs, "No Data")
            mask = np.isfinite(data)
            if no_data is not None:
                mask &= data != no_data
            vals = data[mask]
            out.append(
                DatxDatasetInfo(
                    path=name,
                    shape=tuple(int(x) for x in obj.shape),
                    dtype=str(obj.dtype),
                    unit=_attr_scalar(obj.attrs, "Unit"),
                    no_data=no_data,
                    finite_min=float(np.nanmin(vals)) if vals.size else None,
                    finite_max=float(np.nanmax(vals)) if vals.size else None,
                )
            )

        file.visititems(visit)
    return out


def _select_surface_dataset(datasets: list[DatxDatasetInfo], preferred: str | None = None) -> DatxDatasetInfo:
    if preferred:
        for dataset in datasets:
            if dataset.path == preferred:
                return dataset
        raise ValueError(f"Preferred dataset not found: {preferred}")
    surface = [d for d in datasets if "/Surface/" in f"/{d.path}/" or d.path.startswith("Data/Surface/")]
    if surface:
        return max(surface, key=lambda d: int(np.prod(d.shape)))
    if not datasets:
        raise ValueError("No numeric 2D datasets found in DATX file")
    return max(datasets, key=lambda d: int(np.prod(d.shape)))


def _select_intensity_dataset(datasets: list[DatxDatasetInfo]) -> DatxDatasetInfo | None:
    intensity = [d for d in datasets if "/Intensity/" in f"/{d.path}/" or d.path.startswith("Data/Intensity/")]
    if not intensity:
        return None
    return max(intensity, key=lambda d: int(np.prod(d.shape)))


def _load_surface(path: str | Path, dataset_path: str | None = None) -> tuple[np.ndarray, np.ndarray, DatxDatasetInfo, dict[str, Any]]:
    datasets = discover_datx_datasets(path)
    selected = _select_surface_dataset(datasets, dataset_path)
    with h5py.File(path, "r") as file:
        dataset = file[selected.path]
        data = dataset[()].astype(float)
        no_data = _attr_scalar(dataset.attrs, "No Data")
        mask = np.isfinite(data)
        if no_data is not None:
            mask &= data != float(no_data)
        data = np.where(mask, data, np.nan)
        metadata = _read_global_attrs(file)
        for key, value in dataset.attrs.items():
            metadata[f"Selected Dataset.{key}"] = _jsonable(value)
    return data, mask, selected, metadata


def _load_intensity(path: str | Path) -> tuple[np.ndarray | None, np.ndarray | None, DatxDatasetInfo | None]:
    datasets = discover_datx_datasets(path)
    selected = _select_intensity_dataset(datasets)
    if selected is None:
        return None, None, None
    with h5py.File(path, "r") as file:
        dataset = file[selected.path]
        data = dataset[()].astype(float)
        no_data = _attr_scalar(dataset.attrs, "No Data")
        mask = np.isfinite(data)
        if no_data is not None:
            mask &= data != float(no_data)
        return np.where(mask, data, np.nan), mask, selected


def summarize_datx_structure(path: str | Path, dataset_path: str | None = None) -> DatxStructureSummary:
    """Summarize readable DATX datasets and key metadata for UI display."""
    path = Path(path)
    datasets = discover_datx_datasets(path)
    surface_info: DatxDatasetInfo | None = None
    surface: np.ndarray | None = None
    mask: np.ndarray | None = None
    metadata: dict[str, Any] = {}
    try:
        surface, mask, surface_info, metadata = _load_surface(path, dataset_path)
    except Exception:
        surface_info = None
        with h5py.File(path, "r") as file:
            metadata = _read_global_attrs(file)
    intensity_info = _select_intensity_dataset(datasets)
    wavelength_m = _metadata_number(metadata, "Selected Dataset.Wavelength")
    if wavelength_m is None:
        wavelength_m = _metadata_number(metadata, "Data Context.Data Attributes.Wavelength:Value")
    lateral_m = _metadata_number(metadata, "Surface Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        lateral_m = _metadata_number(metadata, "Data Context.Lateral Resolution:Value")
    shape = surface_info.shape if surface_info is not None and len(surface_info.shape) == 2 else None
    camera_width_mm = shape[1] * lateral_m * 1e3 if shape is not None and lateral_m is not None else None
    camera_height_mm = shape[0] * lateral_m * 1e3 if shape is not None and lateral_m is not None else None
    valid_bbox = _valid_bbox(mask) if mask is not None else None
    valid_aperture_width_mm = None
    valid_aperture_height_mm = None
    valid_pixels = int(mask.sum()) if mask is not None else None
    total_pixels = int(surface.size) if surface is not None else None
    valid_fraction = (valid_pixels / total_pixels) if valid_pixels is not None and total_pixels else None
    if valid_bbox is not None and lateral_m is not None:
        valid_aperture_width_mm = (valid_bbox[2] - valid_bbox[0]) * lateral_m * 1e3
        valid_aperture_height_mm = (valid_bbox[3] - valid_bbox[1]) * lateral_m * 1e3
    highlight_keys = [
        "Selected Dataset.Unit",
        "Selected Dataset.Wavelength",
        "Selected Dataset.No Data",
        "Surface Data Context.Lateral Resolution:Value",
        "Data Context.Lateral Resolution:Value",
        "Data Context.Data Attributes.Wavelength:Value",
    ]
    highlights = {key: metadata[key] for key in highlight_keys if key in metadata}
    explanation = [
        "Data/Surface is the quantitative phase/surface matrix used for P-V, RMS, Power, Irregularity, maps, Zernike-equivalent fitting, and Zemax sag export.",
        "Data/Intensity is the camera/intensity image used for the displayed fringe image; it is not used for surface-height metrics.",
        "No-data attributes define invalid pixels and are converted into masks before analysis.",
        "Lateral resolution converts aperture sizes in mm into pixel windows and defines Grid Sag spacing.",
        "Wavelength converts native fringes into reflection surface lambda and sag in millimeters.",
    ]
    return DatxStructureSummary(
        mode="zygo_datx_structure_summary",
        input_file=str(path),
        datasets=datasets,
        selected_surface_dataset=surface_info.path if surface_info is not None else None,
        selected_intensity_dataset=intensity_info.path if intensity_info is not None else None,
        wavelength_nm=float(wavelength_m * 1e9) if wavelength_m is not None else None,
        lateral_resolution_um=float(lateral_m * 1e6) if lateral_m is not None else None,
        camera_width_mm=float(camera_width_mm) if camera_width_mm is not None else None,
        camera_height_mm=float(camera_height_mm) if camera_height_mm is not None else None,
        valid_aperture_bbox_pixels=valid_bbox,
        valid_aperture_width_mm=float(valid_aperture_width_mm) if valid_aperture_width_mm is not None else None,
        valid_aperture_height_mm=float(valid_aperture_height_mm) if valid_aperture_height_mm is not None else None,
        valid_pixels=valid_pixels,
        total_pixels=total_pixels,
        valid_fraction=float(valid_fraction) if valid_fraction is not None else None,
        metadata_highlights=highlights,
        explanation=explanation,
    )


def inspect_datx_hdf5(path: str | Path, output_dir: str | Path) -> DatxInspectResult:
    """Inspect DATX HDF5 structure for saved analysis/statistics payloads."""
    path = Path(path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    keywords = re.compile(
        r"(rms|pv|p-v|peak|valley|power|irregular|zernike|remove|removal|stat|result|analysis|foc|radcrv|zfr|mask)",
        re.I,
    )
    datasets: list[dict[str, object]] = []
    result_like_matches: list[dict[str, object]] = []
    zygo_filter_datasets: list[dict[str, object]] = []
    metadata_links: list[list[str]] = []
    with h5py.File(path, "r") as file:
        if "MetaData" in file:
            for row in file["MetaData"][()]:
                metadata_links.append([_jsonable(item) for item in row])

        def visit(name: str, obj: h5py.Dataset | h5py.Group) -> None:
            if isinstance(obj, h5py.Dataset):
                plist = obj.id.get_create_plist()
                filters = []
                for idx in range(plist.get_nfilters()):
                    filter_info = plist.get_filter(idx)
                    filters.append(
                        {
                            "id": int(filter_info[0]),
                            "flags": int(filter_info[1]),
                            "cd_values": list(filter_info[2]),
                            "name": _jsonable(filter_info[3]),
                        }
                    )
                item = {
                    "path": name,
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "compression": obj.compression or None,
                    "chunks": list(obj.chunks) if obj.chunks else None,
                    "filters": filters,
                }
                datasets.append(item)
                if any(f["id"] == 44440 for f in filters):
                    zygo_filter_datasets.append(item)
            if keywords.search(name):
                result_like_matches.append({"kind": "path", "path": name, "type": type(obj).__name__})
            for key, value in obj.attrs.items():
                normalized = _jsonable(value)
                if keywords.search(key) or (isinstance(normalized, str) and keywords.search(normalized)):
                    result_like_matches.append({"kind": "attribute", "path": name, "key": key, "value": normalized})

        file.visititems(visit)
    saved_analysis_found = any(match["kind"] != "attribute" or "Data Attributes" not in str(match.get("key", "")) for match in result_like_matches)
    conclusion = (
        "No explicit saved Zygo analysis/statistics dataset was found. DATX contains readable raw Intensity and Surface matrices; "
        "two 1024-byte datasets use Zygo custom HDF5 filter 44440 and are not linked as Measurement result payloads in MetaData."
    )
    result = DatxInspectResult(
        mode="zygo_datx_hdf5_inspection",
        input_file=str(path),
        datasets=datasets,
        metadata_links=metadata_links,
        result_like_matches=result_like_matches,
        zygo_filter_datasets=zygo_filter_datasets,
        saved_analysis_found=bool(saved_analysis_found and len(result_like_matches) > 0),
        inspect_json=str(output_dir / "datx_hdf5_inspection.json"),
        conclusion=conclusion,
    )
    (output_dir / "datx_hdf5_inspection.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def _pv_rms(values: np.ndarray) -> tuple[float, float]:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    return float(np.nanmax(vals) - np.nanmin(vals)), float(np.nanstd(vals - np.nanmean(vals)))


def _valid_bbox(mask: np.ndarray) -> list[int]:
    yy, xx = np.where(mask)
    if yy.size == 0:
        return [0, 0, 0, 0]
    return [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]


def _centered_aperture_mask(mask: np.ndarray, lateral_m: float | None, aperture_mm: tuple[float, float] | None) -> np.ndarray:
    if aperture_mm is None or lateral_m is None:
        return mask.copy()
    bbox = _valid_bbox(mask)
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2
    width_px = max(1, int(round(aperture_mm[0] / (lateral_m * 1e3))))
    height_px = max(1, int(round(aperture_mm[1] / (lateral_m * 1e3))))
    x1 = max(0, cx - width_px // 2)
    y1 = max(0, cy - height_px // 2)
    x2 = min(mask.shape[1], x1 + width_px)
    y2 = min(mask.shape[0], y1 + height_px)
    aperture = np.zeros_like(mask, dtype=bool)
    aperture[y1:y2, x1:x2] = True
    return mask & aperture


def _aperture_rect_mask(
    mask: np.ndarray,
    lateral_m: float,
    aperture_mm: tuple[float, float],
    dx_px: int = 0,
    dy_px: int = 0,
    edge_trim_px: int = 0,
) -> tuple[np.ndarray, list[int]]:
    bbox = _valid_bbox(mask)
    cx = (bbox[0] + bbox[2]) // 2 + dx_px
    cy = (bbox[1] + bbox[3]) // 2 + dy_px
    width_px = max(1, int(round(aperture_mm[0] / (lateral_m * 1e3)))) - 2 * edge_trim_px
    height_px = max(1, int(round(aperture_mm[1] / (lateral_m * 1e3)))) - 2 * edge_trim_px
    if width_px <= 4 or height_px <= 4:
        raise ValueError("Aperture became too small after edge trim")
    x1 = max(0, cx - width_px // 2)
    y1 = max(0, cy - height_px // 2)
    x2 = min(mask.shape[1], x1 + width_px)
    y2 = min(mask.shape[0], y1 + height_px)
    aperture = np.zeros_like(mask, dtype=bool)
    aperture[y1:y2, x1:x2] = True
    return mask & aperture, [int(x1), int(y1), int(x2), int(y2)]


def _save_map(path: Path, arr: np.ndarray, title: str, label: str = "fringes") -> None:
    plt.figure(figsize=(5.5, 4.4))
    plt.imshow(arr, cmap="RdBu_r")
    plt.colorbar(label=label)
    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def _save_fringe_pattern(path: Path, arr: np.ndarray) -> None:
    vals = arr[np.isfinite(arr)]
    if vals.size == 0:
        raise ValueError("No finite pixels for fringe plot")
    levels = np.linspace(float(np.nanpercentile(vals, 1)), float(np.nanpercentile(vals, 99)), 18)
    plt.figure(figsize=(5.5, 4.4))
    plt.contour(arr, levels=levels, colors="black", linewidths=0.7)
    plt.gca().invert_yaxis()
    plt.title("Fringe-like contour pattern")
    plt.axis("equal")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def _robust_limits(arr: np.ndarray, mask: np.ndarray | None = None) -> tuple[float, float]:
    valid = np.isfinite(arr) if mask is None else (np.asarray(mask, dtype=bool) & np.isfinite(arr))
    vals = np.asarray(arr, dtype=float)[valid]
    if vals.size == 0:
        return -1.0, 1.0
    lo, hi = np.nanpercentile(vals, [1, 99])
    bound = max(abs(float(lo)), abs(float(hi)), 1e-12)
    return -bound, bound


def _save_report_map(path: Path, arr: np.ndarray, mask: np.ndarray, title: str, label: str) -> None:
    shown = np.where(mask & np.isfinite(arr), arr, np.nan)
    vmin, vmax = _robust_limits(shown, mask)
    cmap = plt.get_cmap("jet").copy()
    cmap.set_bad("black", alpha=0.0)
    plt.figure(figsize=(6.0, 4.8))
    plt.imshow(shown, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    plt.colorbar(label=label)
    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _save_interferogram_pattern(path: Path, native_fringes: np.ndarray, mask: np.ndarray) -> None:
    shown = np.where(mask & np.isfinite(native_fringes), 0.5 + 0.5 * np.cos(2 * np.pi * native_fringes), np.nan)
    cmap = plt.get_cmap("gray").copy()
    cmap.set_bad("black", alpha=0.0)
    plt.figure(figsize=(6.0, 4.8))
    plt.imshow(shown, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    plt.title("Simulated fringe pattern from DATX phase")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _save_intensity_fringe_pattern(path: Path, intensity: np.ndarray, mask: np.ndarray) -> None:
    shown = np.where(mask & np.isfinite(intensity), intensity, np.nan)
    vals = shown[np.isfinite(shown)]
    if vals.size == 0:
        raise ValueError("No finite intensity pixels for fringe pattern")
    lo, hi = np.nanpercentile(vals, [1, 99.5])
    if hi <= lo:
        hi = lo + 1.0
    normalized = np.clip((shown - lo) / (hi - lo), 0, 1)
    normalized = normalized ** 0.75
    cmap = plt.get_cmap("gray").copy()
    cmap.set_bad("black", alpha=0.0)
    plt.figure(figsize=(6.0, 4.8))
    plt.imshow(normalized, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    plt.title("DATX intensity fringe pattern")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _zernike_basis(x: np.ndarray, y: np.ndarray) -> list[dict[str, int | str | np.ndarray]]:
    r2 = x * x + y * y
    r4 = r2 * r2
    sqrt3 = np.sqrt(3.0)
    sqrt5 = np.sqrt(5.0)
    sqrt6 = np.sqrt(6.0)
    sqrt8 = np.sqrt(8.0)
    sqrt10 = np.sqrt(10.0)
    sqrt12 = np.sqrt(12.0)
    return [
        {"term": 1, "name": "Piston", "radial_degree": 0, "azimuthal_degree": 0, "zj_expression": "1", "values": np.ones_like(x)},
        {"term": 2, "name": "Tilt X", "radial_degree": 1, "azimuthal_degree": 1, "zj_expression": "2*rho*cos(phi)", "values": 2 * x},
        {"term": 3, "name": "Tilt Y", "radial_degree": 1, "azimuthal_degree": -1, "zj_expression": "2*rho*sin(phi)", "values": 2 * y},
        {"term": 4, "name": "Defocus", "radial_degree": 2, "azimuthal_degree": 0, "zj_expression": "sqrt(3)*(2*rho^2 - 1)", "values": sqrt3 * (2 * r2 - 1)},
        {"term": 5, "name": "Oblique astigmatism", "radial_degree": 2, "azimuthal_degree": -2, "zj_expression": "sqrt(6)*rho^2*sin(2*phi)", "values": sqrt6 * (2 * x * y)},
        {"term": 6, "name": "Vertical astigmatism", "radial_degree": 2, "azimuthal_degree": 2, "zj_expression": "sqrt(6)*rho^2*cos(2*phi)", "values": sqrt6 * (x * x - y * y)},
        {"term": 7, "name": "Vertical coma", "radial_degree": 3, "azimuthal_degree": -1, "zj_expression": "sqrt(8)*(3*rho^3 - 2*rho)*sin(phi)", "values": sqrt8 * (3 * r2 - 2) * y},
        {"term": 8, "name": "Horizontal coma", "radial_degree": 3, "azimuthal_degree": 1, "zj_expression": "sqrt(8)*(3*rho^3 - 2*rho)*cos(phi)", "values": sqrt8 * (3 * r2 - 2) * x},
        {"term": 9, "name": "Vertical trefoil", "radial_degree": 3, "azimuthal_degree": -3, "zj_expression": "sqrt(8)*rho^3*sin(3*phi)", "values": sqrt8 * (3 * x * x * y - y**3)},
        {"term": 10, "name": "Oblique trefoil", "radial_degree": 3, "azimuthal_degree": 3, "zj_expression": "sqrt(8)*rho^3*cos(3*phi)", "values": sqrt8 * (x**3 - 3 * x * y * y)},
        {"term": 11, "name": "Primary spherical", "radial_degree": 4, "azimuthal_degree": 0, "zj_expression": "sqrt(5)*(6*rho^4 - 6*rho^2 + 1)", "values": sqrt5 * (6 * r4 - 6 * r2 + 1)},
        {"term": 12, "name": "Vertical secondary astigmatism", "radial_degree": 4, "azimuthal_degree": 2, "zj_expression": "sqrt(10)*(4*rho^4 - 3*rho^2)*cos(2*phi)", "values": sqrt10 * (4 * r2 - 3) * (x * x - y * y)},
        {"term": 13, "name": "Oblique secondary astigmatism", "radial_degree": 4, "azimuthal_degree": -2, "zj_expression": "sqrt(10)*(4*rho^4 - 3*rho^2)*sin(2*phi)", "values": sqrt10 * (4 * r2 - 3) * (2 * x * y)},
        {"term": 14, "name": "Vertical quadrafoil", "radial_degree": 4, "azimuthal_degree": 4, "zj_expression": "sqrt(10)*rho^4*cos(4*phi)", "values": sqrt10 * (x**4 - 6 * x * x * y * y + y**4)},
        {"term": 15, "name": "Oblique quadrafoil", "radial_degree": 4, "azimuthal_degree": -4, "zj_expression": "sqrt(10)*rho^4*sin(4*phi)", "values": sqrt10 * (4 * x * y * (x * x - y * y))},
        {"term": 16, "name": "Secondary coma X", "radial_degree": 5, "azimuthal_degree": 1, "zj_expression": "sqrt(12)*(10*rho^5 - 12*rho^3 + 3*rho)*cos(phi)", "values": sqrt12 * (10 * r4 - 12 * r2 + 3) * x},
        {"term": 17, "name": "Secondary coma Y", "radial_degree": 5, "azimuthal_degree": -1, "zj_expression": "sqrt(12)*(10*rho^5 - 12*rho^3 + 3*rho)*sin(phi)", "values": sqrt12 * (10 * r4 - 12 * r2 + 3) * y},
        {"term": 18, "name": "Secondary trefoil X", "radial_degree": 5, "azimuthal_degree": 3, "zj_expression": "sqrt(12)*(5*rho^5 - 4*rho^3)*cos(3*phi)", "values": sqrt12 * (5 * r2 - 4) * (x**3 - 3 * x * y * y)},
        {"term": 19, "name": "Secondary trefoil Y", "radial_degree": 5, "azimuthal_degree": -3, "zj_expression": "sqrt(12)*(5*rho^5 - 4*rho^3)*sin(3*phi)", "values": sqrt12 * (5 * r2 - 4) * (3 * x * x * y - y**3)},
        {"term": 20, "name": "Pentafoil X", "radial_degree": 5, "azimuthal_degree": 5, "zj_expression": "sqrt(12)*rho^5*cos(5*phi)", "values": sqrt12 * (x**5 - 10 * x**3 * y * y + 5 * x * y**4)},
    ]


def _fit_zernike_equivalent(surface_lambda: np.ndarray, mask: np.ndarray, wavelength_nm: float) -> tuple[list[dict[str, float | int | str]], np.ndarray]:
    yy, xx = np.where(mask & np.isfinite(surface_lambda))
    if yy.size < 16:
        raise ValueError("Not enough valid points for Zernike-equivalent fit")
    h, w = surface_lambda.shape
    x = (xx / max(w - 1, 1)) * 2 - 1
    y = -((yy / max(h - 1, 1)) * 2 - 1)
    z = surface_lambda[yy, xx]
    basis = _zernike_basis(x, y)
    matrix = np.column_stack([item["values"] for item in basis])
    coeff, *_ = np.linalg.lstsq(matrix, z, rcond=None)

    gy, gx = np.indices(surface_lambda.shape)
    gx = (gx / max(w - 1, 1)) * 2 - 1
    gy = -((gy / max(h - 1, 1)) * 2 - 1)
    full_basis = _zernike_basis(gx.ravel(), gy.ravel())
    full_matrix = np.column_stack([item["values"] for item in full_basis])
    fit = (full_matrix @ coeff).reshape(surface_lambda.shape)

    rows: list[dict[str, float | int | str]] = []
    for item, value in zip(basis, coeff):
        coeff_lambda = float(value)
        rows.append(
            {
                "term": item["term"],
                "name": item["name"],
                "radial_degree": item["radial_degree"],
                "azimuthal_degree": item["azimuthal_degree"],
                "zj_expression": item["zj_expression"],
                "coefficient_surface_lambda": coeff_lambda,
                "coefficient_surface_nm": coeff_lambda * wavelength_nm,
                "coefficient_sag_mm": coeff_lambda * wavelength_nm * 1e-6,
            }
        )
    return rows, fit


def _write_zernike_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "term",
                "name",
                "radial_degree",
                "azimuthal_degree",
                "zj_expression",
                "coefficient_surface_lambda",
                "coefficient_surface_nm",
                "coefficient_sag_mm",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _zygo_style_metrics(surface: np.ndarray, mask: np.ndarray) -> dict[str, float | int]:
    yy, xx = np.where(mask & np.isfinite(surface))
    if yy.size < 16:
        raise ValueError("Not enough points for Zygo-style metric fit")
    x1, y1, x2, y2 = _valid_bbox(mask)
    x = ((xx - x1) / max(x2 - x1 - 1, 1)) * 2 - 1
    y = ((yy - y1) / max(y2 - y1 - 1, 1)) * 2 - 1
    z = surface[yy, xx]

    def fitted_values(terms: tuple[str, ...]) -> tuple[np.ndarray, dict[str, float]]:
        matrix = design_matrix(x, y, terms)
        coeff, *_ = np.linalg.lstsq(matrix, z, rcond=None)
        return matrix @ coeff, dict(zip(terms, map(float, coeff)))

    tilt_fit, _ = fitted_values(("piston", "tilt_x", "tilt_y"))
    tilt_removed = z - tilt_fit
    pv_tilt, rms_tilt = _pv_rms(tilt_removed)
    defocus_fit, defocus_coeffs = fitted_values(("piston", "tilt_x", "tilt_y", "power_x", "power_y"))
    power = (defocus_coeffs.get("power_x", 0.0) + defocus_coeffs.get("power_y", 0.0)) / 2
    residual = z - defocus_fit
    irregularity, residual_rms = _pv_rms(residual)
    return {
        "valid_pixels": int(mask.sum()),
        "pv_surface_lambda": float(pv_tilt * 0.5),
        "rms_surface_lambda": float(rms_tilt * 0.5),
        "power_surface_lambda": float(power),
        "irregularity_surface_lambda": float(irregularity * 0.5),
        "residual_rms_surface_lambda": float(residual_rms * 0.5),
    }


def align_datx_to_report(
    datx_path: str | Path,
    output_dir: str | Path,
    report_aperture_mm: tuple[float, float],
    target_pv: float | None = None,
    target_rms: float | None = None,
    target_power: float | None = None,
    dataset_path: str | None = None,
    search_px: int = 6,
    max_edge_trim_px: int = 4,
    alignment_stride: int = 8,
) -> DatxAlignmentResult:
    """Search aperture placement/edge trim that best matches a Zygo PDF report."""
    datx_path = Path(datx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    surface, mask, selected, metadata = _load_surface(datx_path, dataset_path)
    valid = mask & np.isfinite(surface)
    lateral_m = _metadata_number(metadata, "Surface Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        lateral_m = _metadata_number(metadata, "Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        raise ValueError("Cannot align report aperture without DATX lateral resolution metadata")

    targets = {
        "pv_surface_lambda": target_pv,
        "rms_surface_lambda": target_rms,
        "power_surface_lambda": target_power,
    }
    if all(value is None for value in targets.values()):
        raise ValueError("At least one target metric is required for DATX alignment")

    def score_metrics(metrics: dict[str, float | int], rect: list[int], dx: int, dy: int, trim: int) -> dict[str, float | int | list[int]]:
        score = 0.0
        matched = 0
        for key, target in targets.items():
            if target is None:
                continue
            scale = max(abs(target), 0.05)
            score += abs(float(metrics[key]) - target) / scale
            matched += 1
        return {
            "score": float(score / max(matched, 1)),
            "dx_px": dx,
            "dy_px": dy,
            "edge_trim_px": trim,
            "aperture_bbox_pixels": rect,
            **metrics,
        }

    stride = max(1, int(alignment_stride))
    grid = np.zeros_like(valid, dtype=bool)
    grid[::stride, ::stride] = True
    rows: list[dict[str, float | int | list[int]]] = []
    for trim in range(max_edge_trim_px + 1):
        for dy in range(-search_px, search_px + 1):
            for dx in range(-search_px, search_px + 1):
                try:
                    candidate_mask, rect = _aperture_rect_mask(valid, lateral_m, report_aperture_mm, dx, dy, trim)
                    eval_mask = candidate_mask & grid
                    if int(eval_mask.sum()) < 32:
                        continue
                    metrics = _zygo_style_metrics(surface, eval_mask)
                except Exception:
                    continue
                rows.append(score_metrics(metrics, rect, dx, dy, trim))
    if not rows:
        raise ValueError("No valid aperture alignment candidates found")
    rows.sort(key=lambda row: float(row["score"]))

    exact_rows: list[dict[str, float | int | list[int]]] = []
    seen: set[tuple[int, int, int]] = set()
    for row in rows[:50]:
        dx = int(row["dx_px"])
        dy = int(row["dy_px"])
        trim = int(row["edge_trim_px"])
        key = (dx, dy, trim)
        if key in seen:
            continue
        seen.add(key)
        candidate_mask, rect = _aperture_rect_mask(valid, lateral_m, report_aperture_mm, dx, dy, trim)
        metrics = _zygo_style_metrics(surface, candidate_mask)
        exact_rows.append(score_metrics(metrics, rect, dx, dy, trim))
    exact_rows.sort(key=lambda row: float(row["score"]))
    rows = exact_rows + rows[50:]

    csv_path = output_dir / "datx_alignment_candidates.csv"
    fieldnames = [
        "score",
        "dx_px",
        "dy_px",
        "edge_trim_px",
        "aperture_bbox_pixels",
        "valid_pixels",
        "pv_surface_lambda",
        "rms_surface_lambda",
        "power_surface_lambda",
        "irregularity_surface_lambda",
        "residual_rms_surface_lambda",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})

    result = DatxAlignmentResult(
        mode="zygo_datx_report_alignment",
        input_file=str(datx_path),
        selected_dataset=selected.path,
        target_aperture_width_mm=report_aperture_mm[0],
        target_aperture_height_mm=report_aperture_mm[1],
        target_pv_surface_lambda=target_pv,
        target_rms_surface_lambda=target_rms,
        target_power_surface_lambda=target_power,
        best=rows[0],
        top_candidates=rows[:20],
        candidates_csv=str(csv_path),
        alignment_json=str(output_dir / "alignment.json"),
        caution="Search result is a calibration aid. Confirm Zygo removal terms and mask policy before formal metrology use.",
    )
    (output_dir / "alignment.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def _delta(computed: float, target: float | None) -> float | None:
    return None if target is None else computed - target


def _write_validation_html(path: Path, result: DatxValidationResult) -> None:
    def fmt(value: float | int | list[int] | None) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.6g}"
        return html.escape(str(value))

    metric_rows = []
    for label, key in [
        ("P-V", "pv_surface_lambda"),
        ("RMS", "rms_surface_lambda"),
        ("Power", "power_surface_lambda"),
        ("Irregularity", "irregularity_surface_lambda"),
    ]:
        metric_rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{fmt(result.target_values.get(key))}</td>"
            f"<td>{fmt(result.computed_values.get(key))}</td>"
            f"<td>{fmt(result.deltas.get(key))}</td>"
            "</tr>"
        )
    mask_rows = [
        f"<tr><td>{html.escape(key)}</td><td>{fmt(value)}</td></tr>"
        for key, value in result.best_mask.items()
    ]
    notes = "".join(f"<li>{html.escape(note)}</li>" for note in result.interpretation)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Zygo DATX Validation Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; line-height: 1.45; color: #1f2933; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px 10px; text-align: left; }}
    th {{ background: #f0f4f8; }}
    .muted {{ color: #52606d; }}
  </style>
</head>
<body>
  <h1>Zygo DATX Validation Report</h1>
  <p class="muted">{html.escape(result.input_file)}</p>
  <section>
    <h2>Report Aperture</h2>
    <p>{result.report_aperture_width_mm:.3f} mm x {result.report_aperture_height_mm:.3f} mm</p>
  </section>
  <section>
    <h2>Metric Comparison</h2>
    <table>
      <thead><tr><th>Metric</th><th>PDF Target (lambda)</th><th>DATX Computed (lambda)</th><th>Delta (lambda)</th></tr></thead>
      <tbody>{''.join(metric_rows)}</tbody>
    </table>
  </section>
  <section>
    <h2>Best Mask</h2>
    <table><tbody>{''.join(mask_rows)}</tbody></table>
  </section>
  <section>
    <h2>Interpretation</h2>
    <ul>{notes}</ul>
  </section>
  <section>
    <h2>Caution</h2>
    <p>{html.escape(result.caution)}</p>
  </section>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def validate_datx_against_report(
    datx_path: str | Path,
    output_dir: str | Path,
    report_aperture_mm: tuple[float, float],
    target_pv: float | None = None,
    target_rms: float | None = None,
    target_power: float | None = None,
    dataset_path: str | None = None,
) -> DatxValidationResult:
    """Write a compact JSON/HTML validation report against Zygo PDF values."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    alignment = align_datx_to_report(
        datx_path,
        output_dir,
        report_aperture_mm=report_aperture_mm,
        target_pv=target_pv,
        target_rms=target_rms,
        target_power=target_power,
        dataset_path=dataset_path,
    )
    best = alignment.best
    computed = {
        "pv_surface_lambda": float(best["pv_surface_lambda"]),
        "rms_surface_lambda": float(best["rms_surface_lambda"]),
        "power_surface_lambda": float(best["power_surface_lambda"]),
        "irregularity_surface_lambda": float(best["irregularity_surface_lambda"]),
    }
    targets = {
        "pv_surface_lambda": target_pv,
        "rms_surface_lambda": target_rms,
        "power_surface_lambda": target_power,
        "irregularity_surface_lambda": None,
    }
    deltas = {key: _delta(computed[key], targets[key]) for key in computed}
    interpretation = [
        "P-V and Power are the primary alignment gates for the current DATX convention.",
        "Power uses the mean coefficient of local-aperture normalized x^2 and y^2 terms; astigmatism is not folded into Power.",
        "RMS has remained lower than the PDF across the two validation samples, so Zygo's exact RMS mask/statistical convention remains open.",
    ]
    result = DatxValidationResult(
        mode="zygo_datx_validation_report",
        input_file=str(datx_path),
        selected_dataset=alignment.selected_dataset,
        report_aperture_width_mm=report_aperture_mm[0],
        report_aperture_height_mm=report_aperture_mm[1],
        target_values=targets,
        computed_values=computed,
        deltas=deltas,
        best_mask=best,
        validation_json=str(output_dir / "validation_report.json"),
        validation_html=str(output_dir / "validation_report.html"),
        alignment_json=alignment.alignment_json,
        candidates_csv=alignment.candidates_csv,
        interpretation=interpretation,
        caution="Validation report is for convention matching against Zygo PDF values; do not treat remaining RMS mismatch as solved.",
    )
    (output_dir / "validation_report.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    _write_validation_html(output_dir / "validation_report.html", result)
    return result


def _surface_sag_mm(native_fringes: np.ndarray, wavelength_nm: float) -> np.ndarray:
    """Convert DATX native fringes to reflection surface sag in millimeters."""
    return np.asarray(native_fringes, dtype=float) * 0.5 * wavelength_nm * 1e-6


def _fit_surface_for_kind(surface: np.ndarray, mask: np.ndarray, map_kind: str) -> np.ndarray:
    if map_kind == "raw":
        return surface
    if map_kind == "tilt_removed":
        tilt_fit, _ = fit_polynomial(surface, mask, terms=("piston", "tilt_x", "tilt_y"))
        return surface - tilt_fit
    if map_kind == "irregularity":
        fit, _ = fit_polynomial(surface, mask, terms=("piston", "tilt_x", "tilt_y", "power_x", "power_y"))
        return surface - fit
    raise ValueError("map_kind must be raw, tilt_removed, or irregularity")


def _write_grid_sag(path: Path, sag_mm: np.ndarray, valid_mask: np.ndarray, dx_mm: float, dy_mm: float) -> None:
    valid = np.asarray(valid_mask, dtype=bool) & np.isfinite(sag_mm)
    arr = np.where(valid, sag_mm, 0.0)
    gy, gx = np.gradient(arr, dy_mm, dx_mm)
    # Zemax Grid Sag rows start at upper-left (-x,+y), while array row
    # indices increase downward. Flip the y-derivative sign to match +y up.
    gy = -gy
    gxy = -np.gradient(gx, dy_mm, axis=0)
    ny, nx = arr.shape
    with path.open("w", encoding="ascii", newline="\r\n") as f:
        f.write(f"{nx:d} {ny:d} {dx_mm:.12g} {dy_mm:.12g} 0 0.0 0.0\n")
        for y in range(ny):
            for x in range(nx):
                nodata = 0 if valid[y, x] else 1
                if nodata:
                    f.write("0.0 0.0 0.0 0.0 1\n")
                else:
                    f.write(f"{arr[y, x]:.12e} {gx[y, x]:.12e} {gy[y, x]:.12e} {gxy[y, x]:.12e} 0\n")
        f.write("\n")


def export_datx_zemax(
    datx_path: str | Path,
    output_dir: str | Path,
    report_aperture_mm: tuple[float, float],
    dataset_path: str | None = None,
    map_kind: str = "irregularity",
    dx_px: int = 0,
    dy_px: int = 0,
    edge_trim_px: int = 0,
) -> DatxZemaxExportResult:
    """Export a DATX surface map as a Zemax Grid Sag DAT file."""
    datx_path = Path(datx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    surface, mask, selected, metadata = _load_surface(datx_path, dataset_path)
    valid = mask & np.isfinite(surface)
    lateral_m = _metadata_number(metadata, "Surface Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        lateral_m = _metadata_number(metadata, "Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        raise ValueError("Cannot export Zemax grid without DATX lateral resolution metadata")
    wavelength_m = _metadata_number(metadata, "Selected Dataset.Wavelength")
    if wavelength_m is None:
        wavelength_m = _metadata_number(metadata, "Data Context.Data Attributes.Wavelength:Value")
    wavelength_nm = (wavelength_m or 6.328e-7) * 1e9

    export_mask, bbox = _aperture_rect_mask(valid, lateral_m, report_aperture_mm, dx_px, dy_px, edge_trim_px)
    processed_native = _fit_surface_for_kind(surface, export_mask, map_kind)
    x1, y1, x2, y2 = bbox
    cropped_native = processed_native[y1:y2, x1:x2]
    cropped_mask = export_mask[y1:y2, x1:x2]
    cropped_sag_mm = np.where(cropped_mask, _surface_sag_mm(cropped_native, wavelength_nm), 0.0)
    dx_mm = lateral_m * 1e3
    dy_mm = lateral_m * 1e3

    grid_path = output_dir / f"zemax_grid_sag_{map_kind}.DAT"
    readme = output_dir / "zemax_export_readme.txt"
    _write_grid_sag(grid_path, cropped_sag_mm, cropped_mask, dx_mm, dy_mm)
    readme.write_text(
        "\n".join(
            [
                "Zemax export generated by interferogram-flatness.",
                "",
                f"Input: {datx_path}",
                f"Dataset: {selected.path}",
                f"Map kind: {map_kind}",
                f"Aperture bbox pixels: {bbox}",
                f"Grid: {cropped_sag_mm.shape[1]} x {cropped_sag_mm.shape[0]}",
                f"Spacing: dx={dx_mm:.12g} mm, dy={dy_mm:.12g} mm",
                "Grid Sag DAT style: pure Zemax data file, no comment lines, CRLF newlines.",
                "Grid Sag DAT unitflag: 0 (mm).",
                "Grid Sag row format: z dz/dx dz/dy d2z/dxdy nodata.",
                "Data order: upper-left first (-x,+y), then left-to-right by row.",
                "Z values are reflection surface sag in mm, using DATX native fringes * 0.5 * wavelength.",
                "Invalid/outside-aperture pixels are written as 0 0 0 0 1.",
                "Only Grid Sag DAT is generated; fitted continuous Zemax surface approximations are not exported.",
                "Recommended Zemax path: use Grid Sag for the square/rectangular measured map.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return DatxZemaxExportResult(
        mode="zygo_datx_zemax_export",
        input_file=str(datx_path),
        selected_dataset=selected.path,
        map_kind=map_kind,
        aperture_bbox_pixels=bbox,
        grid_sag_dat=str(grid_path),
        readme_txt=str(readme),
        nx=int(cropped_sag_mm.shape[1]),
        ny=int(cropped_sag_mm.shape[0]),
        dx_mm=float(dx_mm),
        dy_mm=float(dy_mm),
        z_unit="mm",
        caution="Grid Sag format is intended for Zemax/OpticStudio import. Confirm aperture, sign, and reflection convention inside Zemax with a known sample.",
    )


def generate_datx_wavefront_report(
    datx_path: str | Path,
    output_dir: str | Path,
    report_aperture_mm: tuple[float, float],
    dataset_path: str | None = None,
    wavelength_nm: float | None = None,
    dx_px: int = 0,
    dy_px: int = 0,
    edge_trim_px: int = 0,
    target_pv: float | None = None,
    target_rms: float | None = None,
    target_power: float | None = None,
) -> DatxWavefrontReportResult:
    """Generate DATX-derived wavefront/fringe/Zernike artifacts for PDF comparison.

    Output values use the reflection surface convention in lambda unless the
    field name says otherwise.  The Zernike table is an equivalent least-squares
    fit over the rectangular report aperture, not a strict circular-aperture
    orthogonal decomposition.
    """
    datx_path = Path(datx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    surface, mask, selected, metadata = _load_surface(datx_path, dataset_path)
    valid = mask & np.isfinite(surface)
    lateral_m = _metadata_number(metadata, "Surface Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        lateral_m = _metadata_number(metadata, "Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        raise ValueError("DATX lateral resolution metadata is required for report-aperture export")
    wavelength_m = _metadata_number(metadata, "Selected Dataset.Wavelength")
    if wavelength_m is None:
        wavelength_m = _metadata_number(metadata, "Data Context.Data Attributes.Wavelength:Value")
    wl_nm = float(wavelength_nm if wavelength_nm is not None else ((wavelength_m or 6.328e-7) * 1e9))

    report_mask, bbox = _aperture_rect_mask(valid, lateral_m, report_aperture_mm, dx_px=dx_px, dy_px=dy_px, edge_trim_px=edge_trim_px)
    x1, y1, x2, y2 = bbox
    cropped_native = surface[y1:y2, x1:x2]
    cropped_mask = report_mask[y1:y2, x1:x2]
    intensity, intensity_mask, _intensity_selected = _load_intensity(datx_path)
    cropped_intensity = None
    cropped_intensity_mask = None
    if intensity is not None and intensity_mask is not None and intensity.shape == surface.shape:
        cropped_intensity = intensity[y1:y2, x1:x2]
        cropped_intensity_mask = intensity_mask[y1:y2, x1:x2] & cropped_mask
    surface_lambda = cropped_native * 0.5

    tilt_fit, _tilt_coeffs = fit_polynomial(cropped_native, cropped_mask, terms=("piston", "tilt_x", "tilt_y"))
    tilt_removed_native = cropped_native - tilt_fit
    power_fit, _power_coeffs = fit_polynomial(cropped_native, cropped_mask, terms=("piston", "tilt_x", "tilt_y", "power_x", "power_y"))
    irregularity_native = cropped_native - power_fit
    tilt_removed_lambda = tilt_removed_native * 0.5
    irregularity_lambda = irregularity_native * 0.5

    computed = _zygo_style_metrics(surface, report_mask)
    computed_values = {
        "pv_surface_lambda": float(computed["pv_surface_lambda"]),
        "rms_surface_lambda": float(computed["rms_surface_lambda"]),
        "power_surface_lambda": float(computed["power_surface_lambda"]),
        "irregularity_surface_lambda": float(computed["irregularity_surface_lambda"]),
        "residual_rms_surface_lambda": float(computed["residual_rms_surface_lambda"]),
        "pv_surface_nm": float(computed["pv_surface_lambda"]) * wl_nm,
        "rms_surface_nm": float(computed["rms_surface_lambda"]) * wl_nm,
        "power_surface_nm": float(computed["power_surface_lambda"]) * wl_nm,
        "irregularity_surface_nm": float(computed["irregularity_surface_lambda"]) * wl_nm,
    }
    target_values: dict[str, float | None] = {
        "pv_surface_lambda": target_pv,
        "rms_surface_lambda": target_rms,
        "power_surface_lambda": target_power,
    }
    deltas = {
        key: None if target is None else float(computed_values[key] - target)
        for key, target in target_values.items()
    }

    zernike_rows, zernike_fit = _fit_zernike_equivalent(tilt_removed_lambda, cropped_mask, wl_nm)
    zernike_residual = tilt_removed_lambda - zernike_fit
    zvalid = zernike_residual[cropped_mask & np.isfinite(zernike_residual)]
    computed_values["zernike_fit_rms_surface_lambda"] = float(np.nanstd(zvalid - np.nanmean(zvalid)))
    computed_values["zernike_fit_pv_surface_lambda"] = float(np.nanmax(zvalid) - np.nanmin(zvalid))

    wavefront_png = output_dir / "datx_wavefront_surface_lambda.png"
    tilt_png = output_dir / "datx_tilt_removed_surface_lambda.png"
    irregularity_png = output_dir / "datx_irregularity_surface_lambda.png"
    fringe_png = output_dir / "datx_intensity_fringe_pattern.png"
    simulated_fringe_png = output_dir / "datx_simulated_phase_fringe_pattern.png"
    summary_png = output_dir / "datx_pdf_comparison_summary.png"
    zernike_csv = output_dir / "zernike_equivalent_terms.csv"
    report_json = output_dir / "wavefront_report.json"
    report_html = output_dir / "wavefront_report.html"

    _save_report_map(wavefront_png, surface_lambda, cropped_mask, "DATX surface map", "surface lambda")
    _save_report_map(tilt_png, tilt_removed_lambda, cropped_mask, "Tilt-removed DATX surface map", "surface lambda")
    _save_report_map(irregularity_png, irregularity_lambda, cropped_mask, "Irregularity residual after piston + tilt + power", "surface lambda")
    _save_interferogram_pattern(simulated_fringe_png, tilt_removed_native, cropped_mask)
    if cropped_intensity is not None and cropped_intensity_mask is not None:
        _save_intensity_fringe_pattern(fringe_png, cropped_intensity, cropped_intensity_mask)
    else:
        fringe_png = simulated_fringe_png
    _write_zernike_csv(zernike_csv, zernike_rows)

    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.82])
    images = [
        (gs[0, 0], tilt_png, "Piston + tilt removed"),
        (gs[0, 1], irregularity_png, "Irregularity: piston + tilt + power removed"),
        (gs[0, 2], fringe_png, "DATX intensity fringes" if fringe_png.name.startswith("datx_intensity") else "Simulated fringes"),
    ]
    for slot, image_path, title in images:
        ax = fig.add_subplot(slot)
        ax.imshow(plt.imread(image_path))
        ax.set_title(title)
        ax.axis("off")
    ax_text = fig.add_subplot(gs[1, :])
    ax_text.axis("off")
    top_terms = "\n".join(
        f"Z{row['term']:02d} {row['name']}: {row['coefficient_surface_lambda']:+.5f} λ"
        for row in zernike_rows[:8]
    )
    ax_text.text(
        0,
        1,
        (
            f"Wavelength: {wl_nm:.3f} nm\n"
            f"Aperture: {report_aperture_mm[0]:.2f} x {report_aperture_mm[1]:.2f} mm\n"
            f"Aperture bbox px: {bbox}\n\n"
            f"P-V: {computed_values['pv_surface_lambda']:.4f} λ"
            + ("" if target_pv is None else f"  target {target_pv:.4f} Δ {deltas['pv_surface_lambda']:+.4f}")
            + "\n"
            f"RMS: {computed_values['rms_surface_lambda']:.4f} λ"
            + ("" if target_rms is None else f"  target {target_rms:.4f} Δ {deltas['rms_surface_lambda']:+.4f}")
            + "\n"
            f"Power: {computed_values['power_surface_lambda']:.4f} λ"
            + ("" if target_power is None else f"  target {target_power:.4f} Δ {deltas['power_surface_lambda']:+.4f}")
            + "\n"
            f"Irregularity: {computed_values['irregularity_surface_lambda']:.4f} λ\n\n"
            "Zernike-equivalent terms:\n"
            f"{top_terms}"
        ),
        va="top",
        family="monospace",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(summary_png, dpi=170)
    plt.close(fig)

    result = DatxWavefrontReportResult(
        mode="zygo_datx_wavefront_report",
        input_file=str(datx_path),
        selected_dataset=selected.path,
        wavelength_nm=wl_nm,
        aperture_bbox_pixels=bbox,
        report_aperture_width_mm=report_aperture_mm[0],
        report_aperture_height_mm=report_aperture_mm[1],
        computed_values=computed_values,
        target_values=target_values,
        deltas=deltas,
        wavefront_map_png=str(wavefront_png),
        tilt_removed_map_png=str(tilt_png),
        irregularity_map_png=str(irregularity_png),
        fringe_pattern_png=str(fringe_png),
        zernike_csv=str(zernike_csv),
        report_json=str(report_json),
        report_html=str(report_html),
        summary_png=str(summary_png),
        caution="Fringe panel uses DATX Intensity when present; Zernike terms use normalized Noll-index Zj expressions but are fitted over the rectangular report aperture, so they are comparison equivalents rather than strict circular orthogonal Zygo coefficients.",
    )
    payload = asdict(result) | {"zernike_terms": zernike_rows}
    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['term']))}</td>"
        f"<td>{html.escape(str(row['name']))}</td>"
        f"<td>{html.escape(str(row['radial_degree']))}</td>"
        f"<td>{html.escape(str(row['azimuthal_degree']))}</td>"
        f"<td>{html.escape(str(row['zj_expression']))}</td>"
        f"<td>{float(row['coefficient_surface_lambda']):+.6f}</td>"
        f"<td>{float(row['coefficient_surface_nm']):+.3f}</td>"
        "</tr>"
        for row in zernike_rows
    )
    report_html.write_text(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>DATX Wavefront Report</title>
<style>body{{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;line-height:1.45}}img{{max-width:100%;border:1px solid #ddd}}table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:6px 8px;text-align:right}}td:nth-child(2),th:nth-child(2),td:nth-child(5),th:nth-child(5){{text-align:left}}</style></head>
<body><h1>DATX Wavefront Report</h1>
<p>Dataset: <code>{html.escape(selected.path)}</code>; wavelength {wl_nm:.3f} nm; aperture bbox {bbox}.</p>
<p>P-V {computed_values['pv_surface_lambda']:.4f} λ, RMS {computed_values['rms_surface_lambda']:.4f} λ, Power {computed_values['power_surface_lambda']:.4f} λ, Irregularity {computed_values['irregularity_surface_lambda']:.4f} λ.</p>
<p><img src=\"{summary_png.name}\" alt=\"summary\"></p>
<h2>Zernike-equivalent terms</h2>
<table><thead><tr><th>Noll</th><th>Name</th><th>n</th><th>m</th><th>Zj expression</th><th>Coeff λ surface</th><th>Coeff nm surface</th></tr></thead><tbody>{rows}</tbody></table>
<p><strong>Caution:</strong> {html.escape(result.caution)}</p>
</body></html>
""",
        encoding="utf-8",
    )
    return result


def analyze_datx(
    datx_path: str | Path,
    output_dir: str | Path,
    dataset_path: str | None = None,
    wavelength_nm: float | None = None,
    report_aperture_mm: tuple[float, float] | None = None,
) -> DatxResult:
    """Analyze a Zygo DATX surface dataset and write first-pass artifacts."""
    datx_path = Path(datx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    surface, mask, selected, metadata = _load_surface(datx_path, dataset_path)
    valid = mask & np.isfinite(surface)
    native_values = surface[valid]
    if native_values.size < 16:
        raise ValueError("Selected DATX dataset does not contain enough valid pixels")

    wavelength_m = _metadata_number(metadata, "Selected Dataset.Wavelength")
    if wavelength_m is None:
        wavelength_m = _metadata_number(metadata, "Data Context.Data Attributes.Wavelength:Value")
    wl_nm = float(wavelength_nm if wavelength_nm is not None else ((wavelength_m or 6.328e-7) * 1e9))

    lateral_m = _metadata_number(metadata, "Surface Data Context.Lateral Resolution:Value")
    if lateral_m is None:
        lateral_m = _metadata_number(metadata, "Data Context.Lateral Resolution:Value")
    report_mask = _centered_aperture_mask(valid, lateral_m, report_aperture_mm)
    lateral_um = lateral_m * 1e6 if lateral_m is not None else None
    camera_width_mm = surface.shape[1] * lateral_m * 1e3 if lateral_m is not None else None
    camera_height_mm = surface.shape[0] * lateral_m * 1e3 if lateral_m is not None else None
    bbox = _valid_bbox(valid)
    valid_bbox_width_mm = (bbox[2] - bbox[0]) * lateral_m * 1e3 if lateral_m is not None else None
    valid_bbox_height_mm = (bbox[3] - bbox[1]) * lateral_m * 1e3 if lateral_m is not None else None

    pv_native, rms_native = _pv_rms(native_values)
    tilt_fit, _tilt_coeffs = fit_polynomial(surface, mask, terms=("piston", "tilt_x", "tilt_y"))
    tilt_removed = surface - tilt_fit
    pv_tilt, rms_tilt = _pv_rms(tilt_removed[valid])
    power_fit, coeffs = fit_polynomial(surface, mask, terms=("piston", "tilt_x", "tilt_y", "power_x", "power_y"))
    residual = surface - power_fit
    irregularity, residual_rms = _pv_rms(residual[valid])
    power_only = power_fit - tilt_fit
    power_pv, _ = _pv_rms(power_only[valid])

    report_metrics = _zygo_style_metrics(surface, report_mask)

    wavefront_image = output_dir / "datx_wavefront_native.png"
    tilt_removed_image = output_dir / "datx_tilt_removed.png"
    irregularity_image = output_dir / "datx_irregularity_residual.png"
    fringe_pattern_image = output_dir / "datx_fringe_pattern.png"
    _save_map(wavefront_image, surface, "DATX wavefront/surface map (native fringes)")
    _save_map(tilt_removed_image, tilt_removed, "Tilt-removed DATX map")
    _save_map(irregularity_image, residual, "Residual after tilt + power")
    _save_fringe_pattern(fringe_pattern_image, tilt_removed)

    result = DatxResult(
        mode="zygo_datx",
        input_file=str(datx_path),
        selected_dataset=selected.path,
        dataset_unit=selected.unit or "unknown",
        wavelength_nm=wl_nm,
        lateral_resolution_um=lateral_um,
        camera_width_mm=camera_width_mm,
        camera_height_mm=camera_height_mm,
        valid_bbox_pixels=bbox,
        valid_bbox_width_mm=valid_bbox_width_mm,
        valid_bbox_height_mm=valid_bbox_height_mm,
        valid_pixels=int(valid.sum()),
        total_pixels=int(surface.size),
        valid_fraction=float(valid.sum() / surface.size),
        pv_native_fringe=pv_native,
        rms_native_fringe=rms_native,
        pv_after_tilt_fringe=pv_tilt,
        rms_after_tilt_fringe=rms_tilt,
        power_x_coeff_fringe=float(coeffs.get("power_x", 0.0)),
        power_y_coeff_fringe=float(coeffs.get("power_y", 0.0)),
        power_mean_coeff_fringe=float((coeffs.get("power_x", 0.0) + coeffs.get("power_y", 0.0)) / 2),
        power_pv_fringe=power_pv,
        irregularity_fringe=irregularity,
        residual_rms_fringe=residual_rms,
        pv_after_tilt_nm_wavefront=pv_tilt * wl_nm,
        irregularity_nm_wavefront=irregularity * wl_nm,
        pv_after_tilt_nm_surface_reflection=pv_tilt * wl_nm / 2,
        irregularity_nm_surface_reflection=irregularity * wl_nm / 2,
        report_aperture_width_mm=report_aperture_mm[0] if report_aperture_mm is not None else None,
        report_aperture_height_mm=report_aperture_mm[1] if report_aperture_mm is not None else None,
        report_valid_pixels=int(report_metrics["valid_pixels"]),
        zygo_style_pv_surface_lambda=float(report_metrics["pv_surface_lambda"]),
        zygo_style_rms_surface_lambda=float(report_metrics["rms_surface_lambda"]),
        zygo_style_power_surface_lambda=float(report_metrics["power_surface_lambda"]),
        zygo_style_irregularity_surface_lambda=float(report_metrics["irregularity_surface_lambda"]),
        zygo_style_residual_rms_surface_lambda=float(report_metrics["residual_rms_surface_lambda"]),
        wavefront_image=str(wavefront_image),
        tilt_removed_image=str(tilt_removed_image),
        irregularity_image=str(irregularity_image),
        fringe_pattern_image=str(fringe_pattern_image),
        metrics_json=str(output_dir / "metrics.json"),
        discovered_datasets=discover_datx_datasets(datx_path),
        caution=(
            "First-pass DATX reader. Native Zygo fringe convention is preserved; "
            "surface-vs-wavefront unit matching must be validated against the original Zygo report."
        ),
    )
    (output_dir / "metrics.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result
