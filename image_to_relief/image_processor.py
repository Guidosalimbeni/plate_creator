"""
image_processor.py — load a raster image and return a height field.

Public API
----------
load_and_process(config) -> (height_field, normal_map | None)
    height_field : np.ndarray, shape (nrows, ncols), dtype float64, values in [0, 1]
    normal_map   : np.ndarray, shape (nrows, ncols, 3) or None
"""

import numpy as np
from PIL import Image


def load_and_process(config):
    """Load image, resize to mesh resolution, blur, normalise, optionally invert."""
    img = _load_greyscale(config.INPUT_IMAGE)

    orig_h, orig_w = img.shape

    # Derive plate height from aspect ratio when not explicitly set.
    if config.PLATE_HEIGHT_MM is None:
        plate_height = config.PLATE_WIDTH_MM * (orig_h / orig_w)
    else:
        plate_height = float(config.PLATE_HEIGHT_MM)

    # Target vertex counts (at least 2 in each dimension).
    ncols = max(2, round(config.PLATE_WIDTH_MM / config.MESH_RESOLUTION))
    nrows = max(2, round(plate_height / config.MESH_RESOLUTION))

    # Resize with high-quality Lanczos filter.
    pil_img = Image.fromarray(img)
    pil_img = pil_img.resize((ncols, nrows), Image.LANCZOS)
    height_field = np.array(pil_img, dtype=np.float64)

    # Apply Gaussian blur to soften sharp transitions.
    if config.BLUR_RADIUS > 0:
        from scipy.ndimage import gaussian_filter
        height_field = gaussian_filter(height_field, sigma=config.BLUR_RADIUS)

    # Normalise to [0, 1].
    lo, hi = height_field.min(), height_field.max()
    if hi > lo:
        height_field = (height_field - lo) / (hi - lo)
    else:
        height_field = np.zeros_like(height_field)

    if config.INVERT_RELIEF:
        height_field = 1.0 - height_field

    # Compute surface normals from the height gradient when requested.
    normal_map = None
    if config.USE_NORMAL_MAP:
        normal_map = _compute_normal_map(
            height_field,
            config.RELIEF_DEPTH_MM,
            config.PLATE_WIDTH_MM / (ncols - 1),
            plate_height / (nrows - 1),
        )

    return height_field, normal_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_greyscale(path):
    """Open any Pillow-supported image and return a uint8 greyscale array."""
    try:
        img = Image.open(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input image not found: {path}")
    except Exception as exc:
        raise ValueError(f"Cannot open image '{path}': {exc}") from exc

    # Convert to greyscale regardless of original mode (RGB, RGBA, L, P …).
    img = img.convert("L")
    return np.array(img, dtype=np.float64)


def _compute_normal_map(height_field, relief_depth_mm, x_step_mm, y_step_mm):
    """
    Approximate surface normals from the height field gradient.

    At each vertex the surface tangent plane is spanned by:
        T_x = (x_step, 0, dz/dcol * x_step)
        T_y = (0, y_step, dz/drow * y_step)
    The normal N = T_x × T_y, then normalised.

    Simplifying (x_step and y_step cancel out in the cross product):
        N ∝ (-dz_dx, -dz_dy, 1)
    where dz_dx / dz_dy are the height-field gradients scaled by relief_depth_mm.
    """
    z = height_field * relief_depth_mm          # physical height values in mm

    # np.gradient uses central differences with edge handling.
    dz_drow = np.gradient(z, y_step_mm, axis=0)
    dz_dcol = np.gradient(z, x_step_mm, axis=1)

    # Normal: (-dz/dx, -dz/dy, 1) in (x, y, z) space.
    nx = -dz_dcol
    ny = -dz_drow
    nz = np.ones_like(nx)

    magnitude = np.sqrt(nx**2 + ny**2 + nz**2)
    return np.stack([nx / magnitude, ny / magnitude, nz / magnitude], axis=-1)
