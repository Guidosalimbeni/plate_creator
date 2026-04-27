#!/usr/bin/env python3
"""
image_to_relief — convert a raster image into a 3-D relief mesh (STL/OBJ).

Usage
-----
    python main.py                          # uses config.py in this directory
    python main.py --config my_config.py   # custom config file
"""

import argparse
import importlib.util
import sys
import time
import pathlib


def _load_config(config_path: str):
    """Dynamically import a Python file as the 'config' module."""
    path = pathlib.Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    spec = importlib.util.spec_from_file_location("config", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(f"Failed to load config '{path}': {exc}") from exc

    return module


def _validate_config(cfg):
    """Check required config fields and sensible values."""
    required = [
        "INPUT_IMAGE", "OUTPUT_DIR", "OUTPUT_FORMAT", "OUTPUT_FILENAME",
        "PLATE_WIDTH_MM", "PLATE_DEPTH_MM", "RELIEF_DEPTH_MM",
        "INVERT_RELIEF", "BLUR_RADIUS", "USE_NORMAL_MAP",
        "MESH_RESOLUTION", "MODE",
    ]
    for attr in required:
        if not hasattr(cfg, attr):
            raise ValueError(f"Config is missing required field: {attr}")

    if cfg.PLATE_WIDTH_MM <= 0:
        raise ValueError("PLATE_WIDTH_MM must be positive.")
    if cfg.PLATE_HEIGHT_MM is not None and cfg.PLATE_HEIGHT_MM <= 0:
        raise ValueError("PLATE_HEIGHT_MM must be positive or None.")
    if cfg.PLATE_DEPTH_MM < 0:
        raise ValueError("PLATE_DEPTH_MM must be >= 0.")
    if cfg.RELIEF_DEPTH_MM <= 0:
        raise ValueError("RELIEF_DEPTH_MM must be positive.")
    if cfg.MESH_RESOLUTION <= 0:
        raise ValueError("MESH_RESOLUTION must be positive.")
    if cfg.OUTPUT_FORMAT.lower() not in ("stl", "obj"):
        raise ValueError("OUTPUT_FORMAT must be 'stl' or 'obj'.")
    if cfg.MODE not in ("embossed", "relief_only"):
        raise ValueError("MODE must be 'embossed' or 'relief_only'.")
    if cfg.BLUR_RADIUS < 0:
        raise ValueError("BLUR_RADIUS must be >= 0.")


def _warn_large_mesh(height_field):
    """Print a warning if the mesh will be very large."""
    nrows, ncols = height_field.shape
    n_faces = 4 * (nrows - 1) * (ncols - 1) + 4 * (nrows + ncols - 2)
    if n_faces > 2_000_000:
        print(
            f"  [warn] large mesh: ~{n_faces:,} triangles "
            f"({nrows}×{ncols} vertices). Export may be slow and file large."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Convert a raster image to a 3-D relief mesh (STL/OBJ)."
    )
    parser.add_argument(
        "--config",
        default="config.py",
        metavar="PATH",
        help="Path to a config.py file (default: config.py in current directory).",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    print("=" * 60)
    print("  image_to_relief")
    print("=" * 60)

    # ---- load config -------------------------------------------------------
    print(f"\n[1/4] Loading config: {args.config}")
    try:
        cfg = _load_config(args.config)
        _validate_config(cfg)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  mode      : {cfg.MODE}")
    print(f"  image     : {cfg.INPUT_IMAGE}")
    print(f"  output    : {cfg.OUTPUT_DIR}{cfg.OUTPUT_FILENAME}.{cfg.OUTPUT_FORMAT}")
    print(f"  plate     : {cfg.PLATE_WIDTH_MM} × {cfg.PLATE_HEIGHT_MM or 'auto'} mm")
    print(f"  base depth: {cfg.PLATE_DEPTH_MM} mm   relief: {cfg.RELIEF_DEPTH_MM} mm")
    print(f"  resolution: {cfg.MESH_RESOLUTION} mm/vertex")

    # ---- process image -----------------------------------------------------
    print("\n[2/4] Processing image …")
    try:
        from image_processor import load_and_process
        height_field, normal_map = load_and_process(cfg)
    except (FileNotFoundError, ValueError) as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    nrows, ncols = height_field.shape
    print(f"  height field: {nrows} × {ncols} vertices")
    print(f"  value range : {height_field.min():.3f} … {height_field.max():.3f}")
    _warn_large_mesh(height_field)

    # ---- build mesh --------------------------------------------------------
    print("\n[3/4] Building mesh …")
    try:
        from mesh_builder import build
        vertices, faces, vertex_normals = build(height_field, normal_map, cfg)
    except ValueError as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  vertices : {len(vertices):,}")
    print(f"  triangles: {len(faces):,}")

    # ---- export ------------------------------------------------------------
    print("\n[4/4] Exporting …")
    try:
        from exporter import export
        out_path = export(vertices, faces, vertex_normals, cfg)
    except (IOError, OSError, ValueError) as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.perf_counter() - t0
    print(f"\nDone in {elapsed:.1f}s  →  {out_path}")


if __name__ == "__main__":
    main()
