"""
exporter.py — write a mesh to STL or OBJ and report file statistics.

Public API
----------
export(vertices, faces, vertex_normals, config) -> pathlib.Path
    Returns the path to the written file.
"""

import os
import pathlib

import numpy as np


def export(vertices, faces, vertex_normals, config):
    """Validate the mesh, then write STL (numpy-stl) or OBJ (trimesh)."""
    out_dir = pathlib.Path(config.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    fmt = config.OUTPUT_FORMAT.lower()
    if fmt not in ("stl", "obj"):
        raise ValueError(f"OUTPUT_FORMAT must be 'stl' or 'obj', got '{fmt}'")

    out_path = out_dir / f"{config.OUTPUT_FILENAME}.{fmt}"

    _validate(vertices, faces)

    if fmt == "stl":
        _write_stl(vertices, faces, out_path)
    else:
        _write_obj(vertices, faces, vertex_normals, out_path)

    _print_stats(out_path, vertices)
    return out_path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(vertices, faces):
    """Use trimesh to check watertightness; warn but do not abort on failure."""
    try:
        import trimesh
        tm = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        if tm.is_watertight:
            print("  [validate] mesh is watertight ✓")
        else:
            print(
                "  [validate] WARNING: mesh is NOT watertight. "
                "Check MESH_RESOLUTION or report a bug."
            )
    except ImportError:
        pass   # trimesh not available; skip validation silently


# ---------------------------------------------------------------------------
# STL export via numpy-stl
# ---------------------------------------------------------------------------

def _write_stl(vertices, faces, path):
    from stl import mesh as stl_mesh

    data = np.zeros(len(faces), dtype=stl_mesh.Mesh.dtype)
    stl_obj = stl_mesh.Mesh(data)

    # Fancy indexing: vertices[faces] → shape (n_faces, 3, 3).
    stl_obj.vectors = vertices[faces].astype(np.float32)
    stl_obj.save(str(path))


# ---------------------------------------------------------------------------
# OBJ export via trimesh
# ---------------------------------------------------------------------------

def _write_obj(vertices, faces, vertex_normals, path):
    import trimesh

    kwargs = dict(vertices=vertices, faces=faces, process=False)
    if vertex_normals is not None:
        kwargs["vertex_normals"] = vertex_normals

    tm = trimesh.Trimesh(**kwargs)
    tm.export(str(path))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _print_stats(path, vertices):
    size_bytes = os.path.getsize(path)
    size_str = (
        f"{size_bytes / 1_048_576:.2f} MB"
        if size_bytes >= 1_048_576
        else f"{size_bytes / 1024:.1f} KB"
    )

    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    dims = maxs - mins

    print(f"  [export] written → {path}")
    print(f"           size    : {size_str}")
    print(
        f"           bounds  : "
        f"X={dims[0]:.2f} mm  Y={dims[1]:.2f} mm  Z={dims[2]:.2f} mm"
    )
