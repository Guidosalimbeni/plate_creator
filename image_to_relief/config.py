# ---------------------------------------------------------------------------
# image_to_relief — default configuration
# Edit this file, then run:  python main.py
# ---------------------------------------------------------------------------

# --- I/O -------------------------------------------------------------------
INPUT_IMAGE     = "input/my_image.png"   # path to source image (PNG/JPG/TIFF)
OUTPUT_DIR      = "output/"              # destination directory
OUTPUT_FORMAT   = "stl"                  # "stl" or "obj"
OUTPUT_FILENAME = "relief_plate"         # file stem; extension added automatically

# --- Physical dimensions (millimetres) -------------------------------------
PLATE_WIDTH_MM  = 100.0   # real-world width of the output plate
PLATE_HEIGHT_MM = None    # None = auto-derived from image aspect ratio
PLATE_DEPTH_MM  = 3.0     # thickness of the base cuboid beneath the relief
RELIEF_DEPTH_MM = 3.0     # maximum extrusion height of relief above plate surface

# --- Relief mapping --------------------------------------------------------
INVERT_RELIEF   = False   # True → dark pixels extrude MORE (dark = raised)
BLUR_RADIUS     = 1.0     # Gaussian blur sigma applied before displacement (0 = off)
USE_NORMAL_MAP  = False   # derive per-vertex normals from height gradient (OBJ only)

# --- Mesh resolution -------------------------------------------------------
MESH_RESOLUTION = 0.25    # target mm between adjacent vertices (lower = finer mesh)

# --- Output mode -----------------------------------------------------------
# "embossed"    → full solid plate + relief extruded upward from top surface
# "relief_only" → only the raised relief solid, bottom sits at Z = PLATE_DEPTH_MM
MODE = "embossed"
