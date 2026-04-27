# image_to_relief

Convert a raster image (PNG / JPG / TIFF) into a 3-D relief mesh (STL or OBJ) suitable for use as an etching plate on a printing press.

## Install

```bash
cd image_to_relief
pip install -r requirements.txt
```

## Quick start

1. Place your source image in the `input/` directory.
2. Edit `config.py` to set `INPUT_IMAGE` and adjust dimensions / mode.
3. Run:

```bash
python main.py
```

The output file is written to `output/` (default `output/relief_plate.stl`).

To use a different config file:

```bash
python main.py --config path/to/my_config.py
```

## Output modes

### `embossed` (default)

Produces a **solid rectangular plate** with the image relief extruded upward from the top face — analogous to a rubber stamp or letterpress block.

```
Z
↑  ___/‾\_____   ← displaced top surface (PLATE_DEPTH + relief)
│ |           |
│ |   base    |  ← solid cuboid, height = PLATE_DEPTH_MM
│ |___________|
└──────────────→ X
```

### `relief_only` / intaglio

The base plate is subtracted; only the **raised relief** geometry is produced as a closed solid. The bottom face sits at `Z = PLATE_DEPTH_MM`. Useful for intaglio plates where the recessed areas hold ink — machine the plate, then the relief stands proud.

```
Z
↑  ___/‾\_____   ← displaced top surface
│ |           |  ← relief solid only (no base below PLATE_DEPTH)
│ ‾‾‾‾‾‾‾‾‾‾‾   ← flat bottom at Z = PLATE_DEPTH_MM
└──────────────→ X
```

## Key config options

| Field | Default | Meaning |
|---|---|---|
| `PLATE_WIDTH_MM` | 100.0 | Physical width of the output plate |
| `PLATE_HEIGHT_MM` | None | Physical height; `None` = auto from image aspect ratio |
| `PLATE_DEPTH_MM` | 5.0 | Base plate thickness in mm |
| `RELIEF_DEPTH_MM` | 3.0 | Maximum height of the raised relief above the plate surface |
| `MESH_RESOLUTION` | 1.0 | Approximate mm between adjacent mesh vertices |
| `INVERT_RELIEF` | False | `True` → dark pixels raise more (useful for intaglio) |
| `BLUR_RADIUS` | 1.0 | Gaussian blur sigma (0 = off); smooths sharp pixel edges |
| `MODE` | `"embossed"` | `"embossed"` or `"relief_only"` |
| `OUTPUT_FORMAT` | `"stl"` | `"stl"` or `"obj"` |

## Mesh resolution trade-off

`MESH_RESOLUTION` controls the vertex spacing in mm:

| Resolution | 100 × 100 mm plate | Triangles | Approx. STL size |
|---|---|---|---|
| 2.0 mm | 51 × 51 vertices | ~10 k | < 1 MB |
| 1.0 mm | 101 × 101 vertices | ~40 k | ~2 MB |
| 0.5 mm | 201 × 201 vertices | ~160 k | ~8 MB |
| 0.1 mm | 1001 × 1001 vertices | ~4 M | ~200 MB |

Finer meshes capture more image detail but are slower to export and slice. For most etching plates, **0.5 – 1.0 mm** is a good starting point.

## Notes

- All output meshes are validated for watertightness via `trimesh`; a warning is printed if the mesh is not manifold.
- For printing press use, the image may need to be **horizontally mirrored** in your image editor before processing so that the printed impression reads correctly.
