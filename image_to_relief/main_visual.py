#!/usr/bin/env python3
"""
main_visual.py — visualise a relief mesh (STL / OBJ) from the output folder.

Usage
-----
    python main_visual.py                        # auto-picks most recent file
    python main_visual.py output/my_plate.stl   # specific file
    python main_visual.py --dir output/          # pick from a different directory
"""

import argparse
import pathlib
import sys

import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


SUPPORTED = (".stl", ".obj")


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------

def _pick_file(directory: pathlib.Path) -> pathlib.Path:
    """Return the most recently modified mesh file in the directory."""
    candidates = sorted(
        [p for p in directory.iterdir() if p.suffix.lower() in SUPPORTED],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print(f"No STL/OBJ files found in '{directory}'.", file=sys.stderr)
        sys.exit(1)

    if len(candidates) > 1:
        print("Available meshes (newest first):")
        for i, p in enumerate(candidates):
            print(f"  [{i}] {p.name}")
        choice = input("Enter number to view [0]: ").strip()
        idx = int(choice) if choice.isdigit() else 0
        return candidates[idx]

    return candidates[0]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(mesh_path: pathlib.Path):
    tm = trimesh.load(str(mesh_path), force="mesh")
    triangles = tm.triangles          # (n_faces, 3, 3) — world-space vertices

    # Colour faces by average Z height for a depth-cue effect.
    z_avg = triangles[:, :, 2].mean(axis=1)
    z_lo, z_hi = z_avg.min(), z_avg.max()
    if z_hi > z_lo:
        t = (z_avg - z_lo) / (z_hi - z_lo)
    else:
        t = np.zeros_like(z_avg)

    cmap = plt.get_cmap("copper")
    face_colors = cmap(t)

    # ---- figure layout -----------------------------------------------------
    fig = plt.figure(figsize=(12, 7))
    fig.patch.set_facecolor("#1a1a2e")

    # Three views: perspective, top, side.
    specs = [
        (131, 25, -45, "Perspective"),
        (132, 90,  -90, "Top (Z)"),
        (133,  0,  -90, "Front (Y)"),
    ]

    bounds = tm.bounds             # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
    centre = tm.centroid

    for pos, elev, azim, title in specs:
        ax = fig.add_subplot(pos, projection="3d")
        ax.set_facecolor("#0f0f1a")

        poly = Poly3DCollection(
            triangles,
            facecolors=face_colors,
            linewidths=0,
            antialiased=False,
        )
        ax.add_collection3d(poly)

        # Equal-ish aspect by setting limits to the bounding box.
        lo, hi = bounds
        max_range = (hi - lo).max() / 2
        ax.set_xlim(centre[0] - max_range, centre[0] + max_range)
        ax.set_ylim(centre[1] - max_range, centre[1] + max_range)
        ax.set_zlim(lo[2], lo[2] + 2 * max_range)

        ax.view_init(elev=elev, azim=azim)
        ax.set_title(title, color="white", pad=6, fontsize=9)
        ax.tick_params(colors="#888888", labelsize=6)
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.fill = False
            pane.set_edgecolor("#333355")
        ax.set_xlabel("X mm", color="#888888", fontsize=7, labelpad=2)
        ax.set_ylabel("Y mm", color="#888888", fontsize=7, labelpad=2)
        ax.set_zlabel("Z mm", color="#888888", fontsize=7, labelpad=2)

    # ---- info panel --------------------------------------------------------
    dims = bounds[1] - bounds[0]
    info = (
        f"{mesh_path.name}\n"
        f"{len(triangles):,} triangles   "
        f"{len(tm.vertices):,} vertices\n"
        f"X {dims[0]:.2f} mm   Y {dims[1]:.2f} mm   Z {dims[2]:.2f} mm\n"
        f"watertight: {'yes ✓' if tm.is_watertight else 'NO ✗'}"
    )
    fig.text(
        0.5, 0.01, info,
        ha="center", va="bottom",
        color="#cccccc", fontsize=8,
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#0f0f1a", edgecolor="#333355"),
    )

    fig.suptitle("image_to_relief — mesh preview", color="white", fontsize=11, y=0.98)
    plt.tight_layout(rect=[0, 0.08, 1, 0.96])
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Visualise a relief mesh.")
    parser.add_argument(
        "file",
        nargs="?",
        metavar="FILE",
        help="Path to an STL or OBJ file. Omit to pick from --dir.",
    )
    parser.add_argument(
        "--dir",
        default="output/",
        metavar="DIR",
        help="Directory to scan for meshes (default: output/).",
    )
    args = parser.parse_args()

    if args.file:
        mesh_path = pathlib.Path(args.file)
        if not mesh_path.exists():
            print(f"File not found: {mesh_path}", file=sys.stderr)
            sys.exit(1)
    else:
        mesh_path = _pick_file(pathlib.Path(args.dir))

    print(f"Loading: {mesh_path}")
    _render(mesh_path)


if __name__ == "__main__":
    main()
