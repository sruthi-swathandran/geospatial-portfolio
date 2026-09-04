"""
RS-01 configuration — the decisions, in one place, with the reasoning.

Every later script imports from here. Keeping the choices in a file rather than
scattered through notebooks is what makes the project reproducible, and the
comments are what make it defensible in an interview.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT = Path(__file__).resolve().parent.parent      # 01-sentinel1-flood-extent/
DATA = PROJECT / "data"
RESULTS = PROJECT / "results"
LABELS_DIR = DATA / "sen1floods11"

for _p in (DATA, RESULTS, LABELS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Event
# --------------------------------------------------------------------------
EVENT = "India"
EVENT_ID = 3                       # Sen1Floods11 event id
BBOX = [92.1507, 24.8471, 94.1634, 28.2848]   # Brahmaputra + Barak basins, NE India
RELATIVE_ORBIT = 77
ORBIT_STATE = "descending"

# --------------------------------------------------------------------------
# Scenes — chosen from the find_scenes.py output
# --------------------------------------------------------------------------
# FLOOD: three consecutive frames on 2016-08-12, all VV+VH, relative orbit 77.
# Three items rather than one because a single IW frame is ~250 km along-track
# and the AOI spans ~380 km; they mosaic into one pass.
FLOOD_DATE = "2016-08-12"
FLOOD_ITEMS = [
    "S1A_IW_GRDH_1SDV_20160812T234622_20160812T234651_012574_013B43",
    "S1A_IW_GRDH_1SDV_20160812T234651_20160812T234716_012574_013B43",
    "S1A_IW_GRDH_1SDV_20160812T234716_20160812T234741_012574_013B43",
]

# REFERENCE: 2016-07-19, same relative orbit, same overpass time (23:46), and
# crucially also VV+VH.
#
# Why not 2016-07-31, which is closer in time (12 days rather than 24)?
# Because it is single-polarisation (1SSV = VV only). Comparing a VV+VH flood
# scene against a VV-only reference would leave VH with nothing to difference
# against, and VH is the channel that usually separates open water best.
# The 12 extra days cost less than losing a polarisation.
REFERENCE_DATE = "2016-07-19"
REFERENCE_ITEMS = [
    "S1A_IW_GRDH_1SDV_20160719T234621_20160719T234650_012224_012FB2",
    "S1A_IW_GRDH_1SDV_20160719T234650_20160719T234715_012224_012FB2",
    "S1A_IW_GRDH_1SDV_20160719T234715_20160719T234740_012224_012FB2",
]

# HONEST CAVEAT, to be stated in the README rather than buried:
# 19 July 2016 is mid-monsoon in Assam. It is a *pre-event* reference, not a
# dry one — parts of the floodplain may already have been inundated. A true
# low-water baseline would come from the pre-monsoon (Feb-Apr 2016) on the same
# orbit, at the cost of seasonal differences in vegetation backscatter.
# Phase 5 tests both and reports the difference in flooded-area estimate;
# that sensitivity is a finding, not a nuisance.
DRY_SEASON_SEARCH = ("2016-02-01", "2016-04-15")   # searched later, same orbit

# --------------------------------------------------------------------------
# Collections
# --------------------------------------------------------------------------
MPC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"

S1_COLLECTION = "sentinel-1-rtc"   # radiometrically terrain corrected, on MPC
DEM_COLLECTION = "cop-dem-glo-30"
GSW_COLLECTION = "jrc-gsw"
LANDCOVER_COLLECTION = "esa-worldcover"

# --------------------------------------------------------------------------
# Processing parameters
# --------------------------------------------------------------------------
TARGET_CRS = "EPSG:32646"      # UTM 46N — covers the AOI; metres, so areas are honest
TARGET_RES = 10                # metres
CHUNK = 2048                   # dask chunk size in pixels

SPECKLE_WINDOW = 5             # Lee filter window
OTSU_TILE = 512                # tile size for adaptive thresholding (full scenes)

# Sen1Floods11 stores a per-event VH threshold in its metadata; for the India
# event it is -21.56 dB. That is the value the dataset authors used, derived at
# SCENE scale. Having it lets us test "a single well-chosen event threshold"
# against "a threshold estimated per chip" — which turns out to be the crux.
EVENT_VH_THRESHOLD = -21.56

# Physical bounds on where a water threshold can plausibly sit for Sentinel-1
# sigma0 in dB. Open water is a specular reflector: it is DARK. Land, even wet
# bare soil, rarely falls below these. If an automatic threshold lands above
# them it is not separating water from land, it is splitting the land
# distribution in half — which is precisely how Otsu fails on a chip that
# contains little or no water.
MAX_WATER_THRESHOLD_VH = -15.0
MAX_WATER_THRESHOLD_VV = -12.0
SLOPE_MAX_DEG = 5.0            # above this, radar shadow/layover dominates
GSW_PERMANENT_MIN = 80         # JRC occurrence % counted as permanent water
