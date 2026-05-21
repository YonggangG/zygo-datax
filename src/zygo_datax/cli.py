"""Command line interface for zygo-dataX."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .core import discover_datx_datasets, export_datx_zemax, generate_datx_wavefront_report, inspect_datx_hdf5, summarize_datx_structure


def _aperture_mm(value: str) -> tuple[float, float]:
    parts = [float(p.strip()) for p in value.split(",")]
    if len(parts) != 2 or parts[0] <= 0 or parts[1] <= 0:
        raise argparse.ArgumentTypeError("aperture must be width_mm,height_mm")
    return parts[0], parts[1]


def main() -> None:
    parser = argparse.ArgumentParser(prog="zygo-datax")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="List numeric 2D datasets in a DATX file")
    scan.add_argument("file")

    report = sub.add_parser("analyze", help="Generate wavefront/fringe/Zernike report and metrics")
    report.add_argument("file")
    report.add_argument("--out", default="reports/zygo_datax")
    report.add_argument("--dataset", help="Optional exact HDF5 surface dataset path")
    report.add_argument("--wavelength-nm", type=float, help="Override DATX wavelength")
    report.add_argument("--aperture-mm", type=_aperture_mm, required=True, help="Report aperture width_mm,height_mm")
    report.add_argument("--dx-px", type=int, default=0)
    report.add_argument("--dy-px", type=int, default=0)
    report.add_argument("--edge-trim-px", type=int, default=0)
    report.add_argument("--target-pv", type=float)
    report.add_argument("--target-rms", type=float)
    report.add_argument("--target-power", type=float)

    zemax = sub.add_parser("zemax", help="Export Zemax Grid Sag DAT and Extended Polynomial terms")
    zemax.add_argument("file")
    zemax.add_argument("--out", default="reports/zygo_datax_zemax")
    zemax.add_argument("--dataset", help="Optional exact HDF5 surface dataset path")
    zemax.add_argument("--aperture-mm", type=_aperture_mm, required=True, help="Report aperture width_mm,height_mm")
    zemax.add_argument("--map-kind", choices=("all", "raw", "tilt_removed", "irregularity"), default="all")
    zemax.add_argument("--dx-px", type=int, default=0)
    zemax.add_argument("--dy-px", type=int, default=0)
    zemax.add_argument("--edge-trim-px", type=int, default=0)
    zemax.add_argument("--xy-order", type=int, default=4)

    inspect = sub.add_parser("inspect", help="Inspect DATX HDF5 structure")
    inspect.add_argument("file")
    inspect.add_argument("--out", default="reports/zygo_datax_inspect")

    structure = sub.add_parser("structure", help="Explain readable DATX datasets and key metadata")
    structure.add_argument("file")
    structure.add_argument("--dataset", help="Optional exact HDF5 surface dataset path")

    args = parser.parse_args()
    if args.cmd == "scan":
        print(json.dumps([asdict(item) for item in discover_datx_datasets(args.file)], indent=2))
    elif args.cmd == "analyze":
        result = generate_datx_wavefront_report(
            args.file,
            Path(args.out),
            report_aperture_mm=args.aperture_mm,
            dataset_path=args.dataset,
            wavelength_nm=args.wavelength_nm,
            dx_px=args.dx_px,
            dy_px=args.dy_px,
            edge_trim_px=args.edge_trim_px,
            target_pv=args.target_pv,
            target_rms=args.target_rms,
            target_power=args.target_power,
        )
        print(json.dumps(asdict(result), indent=2))
    elif args.cmd == "zemax":
        if args.map_kind == "all":
            exports = {
                map_kind: asdict(
                    export_datx_zemax(
                        args.file,
                        Path(args.out),
                        report_aperture_mm=args.aperture_mm,
                        dataset_path=args.dataset,
                        map_kind=map_kind,
                        dx_px=args.dx_px,
                        dy_px=args.dy_px,
                        edge_trim_px=args.edge_trim_px,
                        xy_order=args.xy_order,
                    )
                )
                for map_kind in ("raw", "tilt_removed", "irregularity")
            }
            print(json.dumps({"mode": "zygo_datx_zemax_export_all", "exports": exports}, indent=2))
        else:
            result = export_datx_zemax(
                args.file,
                Path(args.out),
                report_aperture_mm=args.aperture_mm,
                dataset_path=args.dataset,
                map_kind=args.map_kind,
                dx_px=args.dx_px,
                dy_px=args.dy_px,
                edge_trim_px=args.edge_trim_px,
                xy_order=args.xy_order,
            )
            print(json.dumps(asdict(result), indent=2))
    elif args.cmd == "inspect":
        result = inspect_datx_hdf5(args.file, Path(args.out))
        print(json.dumps(asdict(result), indent=2))
    else:
        result = summarize_datx_structure(args.file, dataset_path=args.dataset)
        print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
