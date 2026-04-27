"""
mesh_builder.py — convert a 2-D height field into a watertight triangulated mesh.

Public API
----------
build(height_field, normal_map, config) -> (vertices, faces, vertex_normals | None)

    vertices       : float64 array, shape (N, 3)  — all vertex positions in mm
    faces          : int32   array, shape (M, 3)  — triangle indices into vertices
    vertex_normals : float64 array, shape (N, 3) or None

Coordinate system
-----------------
    X  : 0 → PLATE_WIDTH_MM  (image column direction, left to right)
    Y  : 0 → PLATE_HEIGHT_MM (image row direction, top → bottom of image)
    Z  : 0 → PLATE_DEPTH_MM + RELIEF_DEPTH_MM  (extrusion / height)

Mesh structure (two-layer grid)
--------------------------------
We maintain two coincident grids of (nrows × ncols) vertices:
    • top layer  — each vertex has Z = z_top[i, j]  (the displaced surface)
    • bottom layer — each vertex has Z = z_bot       (constant for either mode)

Vertex flat index layout
    top(i, j)  →  i * ncols + j               (range 0 … nrows*ncols-1)
    bot(i, j)  →  nrows*ncols + i*ncols + j   (range nrows*ncols … 2*nrows*ncols-1)

Winding order convention: CCW triangles produce outward-facing normals
(right-hand rule).  Every winding below is verified by cross-product check.
"""

import numpy as np


def build(height_field, normal_map, config):
    """Assemble vertices and faces for a watertight relief mesh."""
    nrows, ncols = height_field.shape
    if nrows < 2 or ncols < 2:
        raise ValueError(
            f"Height field too small ({nrows}×{ncols}). "
            "Reduce MESH_RESOLUTION or increase PLATE dimensions."
        )

    # ---- physical coordinate grids ----------------------------------------
    if config.PLATE_HEIGHT_MM is None:
        orig_aspect = nrows / ncols          # preserved by image_processor resize
        plate_height = config.PLATE_WIDTH_MM * orig_aspect
    else:
        plate_height = float(config.PLATE_HEIGHT_MM)

    x_step = config.PLATE_WIDTH_MM / (ncols - 1)   # mm between adjacent columns
    y_step = plate_height          / (nrows - 1)   # mm between adjacent rows

    col_coords = np.arange(ncols) * x_step          # shape (ncols,)
    row_coords = np.arange(nrows) * y_step          # shape (nrows,)
    xx, yy = np.meshgrid(col_coords, row_coords)    # shape (nrows, ncols)

    # ---- Z values ----------------------------------------------------------
    # Top surface: each vertex displaced by the height field value.
    z_top = config.PLATE_DEPTH_MM + height_field * config.RELIEF_DEPTH_MM  # (nrows, ncols)

    # Bottom surface: flat plane.
    #   embossed   → Z = 0         (full plate including base cuboid)
    #   relief_only → Z = PLATE_DEPTH_MM  (only the raised relief, no base)
    z_bot = 0.0 if config.MODE == "embossed" else float(config.PLATE_DEPTH_MM)

    # ---- vertex arrays -----------------------------------------------------
    top_verts = np.stack([xx, yy, z_top], axis=-1).reshape(-1, 3)        # (nrows*ncols, 3)
    bot_verts = np.stack([xx, yy, np.full_like(xx, z_bot)], axis=-1).reshape(-1, 3)

    all_verts = np.vstack([top_verts, bot_verts]).astype(np.float64)
    N = nrows * ncols   # offset to address a bottom vertex: bot(i,j) = N + top_idx(i,j)

    # ---- face construction -------------------------------------------------
    faces = np.vstack([
        _top_surface_faces(nrows, ncols),
        _bottom_surface_faces(nrows, ncols, N),
        _side_wall_faces(nrows, ncols, N),
    ]).astype(np.int32)

    # ---- per-vertex normals (top surface only, OBJ export) -----------------
    vertex_normals = None
    if normal_map is not None:
        vertex_normals = _build_vertex_normals(nrows, ncols, N, normal_map)

    return all_verts, faces, vertex_normals


# ---------------------------------------------------------------------------
# Surface construction helpers
# ---------------------------------------------------------------------------

def _top_surface_faces(nrows, ncols):
    """
    Build top-surface triangles with outward normal pointing in +Z.

    Each quad (i,j)→(i,j+1)→(i+1,j+1)→(i+1,j) is split into 2 triangles.
    Winding verified: tri(tl, tr, br) normal = (+Z direction).
        Let A=tl, B=tr, C=br with A=(0,0,*), B=(xs,0,*), C=(xs,ys,*):
        (B-A)×(C-A) = (xs,0,0)×(xs,ys,0) = (0,0, xs·ys) → +Z ✓
    """
    ii, jj = np.meshgrid(np.arange(nrows - 1), np.arange(ncols - 1), indexing="ij")

    tl = ii * ncols + jj          # top-left
    tr = ii * ncols + (jj + 1)   # top-right
    bl = (ii + 1) * ncols + jj   # bottom-left
    br = (ii + 1) * ncols + (jj + 1)  # bottom-right

    # Two CCW triangles per quad (normal +Z).
    tri1 = np.stack([tl, tr, br], axis=-1).reshape(-1, 3)
    tri2 = np.stack([tl, br, bl], axis=-1).reshape(-1, 3)
    return np.vstack([tri1, tri2])


def _bottom_surface_faces(nrows, ncols, N):
    """
    Build bottom-surface triangles with outward normal pointing in -Z.

    Winding is the reverse of the top surface (swap B and C):
        tri(tl, br, tr) → (B-A)×(C-A) = (xs,ys,0)×(xs,0,0) = (0,0,-xs·ys) → -Z ✓
    """
    ii, jj = np.meshgrid(np.arange(nrows - 1), np.arange(ncols - 1), indexing="ij")

    tl = N + ii * ncols + jj
    tr = N + ii * ncols + (jj + 1)
    bl = N + (ii + 1) * ncols + jj
    br = N + (ii + 1) * ncols + (jj + 1)

    tri1 = np.stack([tl, br, tr], axis=-1).reshape(-1, 3)   # reversed → -Z
    tri2 = np.stack([tl, bl, br], axis=-1).reshape(-1, 3)
    return np.vstack([tri1, tri2])


def _side_wall_faces(nrows, ncols, N):
    """
    Build the four perimeter walls connecting top surface to bottom surface.

    For each perimeter edge (two adjacent top vertices) we emit one quad (two
    triangles) connecting to the corresponding bottom vertices directly below.

    Winding is chosen so outward normals point away from the mesh interior.
    Each formula is verified via cross-product; derivations in comments below.
    """
    parts = []

    # ---- FRONT wall  (row=0, outward normal = -Y) --------------------------
    # Edge runs col 0 … ncols-2. Interior is in the +Y direction.
    # Verified: tri(bot_j, bot_jp1, top_jp1):
    #   B-A=(xs,0,0), C-A=(xs,0,dz) → cross=(0·dz-0·0, 0·xs-xs·dz, xs·0-0·xs)
    #   = (0, -xs·dz, 0) → -Y ✓  (dz = ztop - zbot > 0, xs > 0)
    j = np.arange(ncols - 1)
    bot_j   = N + j
    bot_jp1 = N + j + 1
    top_j   = j
    top_jp1 = j + 1
    parts.append(np.stack([bot_j,   bot_jp1, top_jp1], axis=-1))
    parts.append(np.stack([bot_j,   top_jp1, top_j  ], axis=-1))

    # ---- BACK wall  (row=nrows-1, outward normal = +Y) ---------------------
    # Edge runs col ncols-1 … 1 (reversed so outward is +Y).
    # Verified: tri(bot_jp1, bot_j, top_j):
    #   B-A=(-xs,0,0), C-A=(-xs,0,dz) → cross=(0,-xs·(-dz)-(-xs)·dz ?)
    #   Let's use: B-A=(base_bot+j - base_bot-j-1 coords)
    #   A=bot(r,j+1)=(x1,y_max,zb), B=bot(r,j)=(x0,y_max,zb), C=top(r,j)=(x0,y_max,zt)
    #   B-A=(-xs,0,0), C-A=(-xs,0,zt-zb)
    #   cross=(0·(zt-zb)-0·0, 0·(-xs)-(-xs)·(zt-zb), (-xs)·0-0·(-xs))=(0,xs·(zt-zb),0)→+Y ✓
    row = nrows - 1
    base_top = row * ncols
    base_bot = N + row * ncols
    bot_jp1_b = base_bot + j + 1
    bot_j_b   = base_bot + j
    top_j_b   = base_top + j
    top_jp1_b = base_top + j + 1
    parts.append(np.stack([bot_jp1_b, bot_j_b,   top_j_b  ], axis=-1))
    parts.append(np.stack([bot_jp1_b, top_j_b,   top_jp1_b], axis=-1))

    # ---- LEFT wall  (col=0, outward normal = -X) ---------------------------
    # Edge runs row 0 … nrows-2.
    # Verified: tri(bot_ip1, bot_i, top_i):
    #   A=bot(i+1,0)=(0,y1,zb), B=bot(i,0)=(0,y0,zb), C=top(i,0)=(0,y0,zt)
    #   B-A=(0,-ys,0), C-A=(0,-ys,zt-zb)
    #   cross=(-ys·(zt-zb)-0·(-ys), 0·0-0·(zt-zb), 0·(-ys)-(-ys)·0)
    #        =(-ys·(zt-zb), 0, 0) → -X ✓
    i = np.arange(nrows - 1)
    bot_ip1 = N + (i + 1) * ncols
    bot_i   = N + i * ncols
    top_i   = i * ncols
    top_ip1 = (i + 1) * ncols
    parts.append(np.stack([bot_ip1, bot_i,   top_i  ], axis=-1))
    parts.append(np.stack([bot_ip1, top_i,   top_ip1], axis=-1))

    # ---- RIGHT wall  (col=ncols-1, outward normal = +X) --------------------
    # Verified: tri(bot_i, bot_ip1, top_ip1):
    #   A=bot(i,c)=(x_max,y0,zb), B=bot(i+1,c)=(x_max,y1,zb), C=top(i+1,c)=(x_max,y1,zt)
    #   B-A=(0,ys,0), C-A=(0,ys,zt-zb)
    #   cross=(ys·(zt-zb)-0·ys, 0·0-0·(zt-zb), 0·ys-ys·0)=(ys·(zt-zb),0,0) → +X ✓
    col = ncols - 1
    bot_i_r   = N + i * ncols + col
    bot_ip1_r = N + (i + 1) * ncols + col
    top_ip1_r = (i + 1) * ncols + col
    top_i_r   = i * ncols + col
    parts.append(np.stack([bot_i_r,   bot_ip1_r, top_ip1_r], axis=-1))
    parts.append(np.stack([bot_i_r,   top_ip1_r, top_i_r  ], axis=-1))

    return np.vstack(parts)


def _build_vertex_normals(nrows, ncols, N, normal_map):
    """
    Assemble a per-vertex normal array for the whole mesh.

    Top-surface vertices receive normals from the computed normal map.
    Bottom and perimeter vertices default to geometric normals:
        bottom → (0, 0, -1), sides → geometric (will interpolate in OBJ renders).

    Note: vertices shared between the top surface and a side wall will receive
    the smooth top-surface normal; this produces a slight artefact at the plate
    edge in renders but does not affect mesh geometry or printing accuracy.
    """
    n_total = 2 * nrows * ncols
    vertex_normals = np.zeros((n_total, 3), dtype=np.float64)

    # Top surface: use height-derived normals.
    vertex_normals[:nrows * ncols] = normal_map.reshape(-1, 3)

    # Bottom surface: flat downward normal.
    vertex_normals[nrows * ncols:] = np.array([0.0, 0.0, -1.0])

    return vertex_normals
