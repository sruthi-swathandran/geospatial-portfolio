# RS-02 stage 1: what the reference data actually is

Field boundaries for Indian smallholdings from free Sentinel-2. Before any
model runs, this is what the benchmark data turns out to be, measured rather
than read off a paper.

Every number below traces to a file in `results/india/`. Where a number is an
estimate, a bound or an inference, it says so.

Data: [Fields of The World](https://source.coop/kerner-lab/fields-of-the-world),
India subset, with Slovenia as a control. CC-BY-4.0, imagery Copernicus / ESA.
Nothing here comes from any non-public source.

Every file below exists for both countries under `results/<country>/` and
`figures/<country>/`. Paths are written as India's; swap the country for the
control's.

---

## The short version

1. The chips are not on a 10 m grid. They are 256 pixels across 1,536 m, which
   is 6.07 m per pixel, and Sentinel-2's finest bands sample at 10 m. The grid
   is finer than the sensor.
2. 98.96% of every chip is unlabelled, and it is not empty ground. Each chip
   holds hundreds of visually distinct fields, of which five carry a label,
   clustered in one small patch.
3. Precision cannot be measured on this dataset. Recall and boundary agreement
   can.
4. 43% of reference parcels are smaller than 5 by 5 native Sentinel-2 pixels.
   That figure is the conservative end of a range; the true share is probably
   higher.
5. Slovenia, measured with the same code as a control, has **smaller** parcels
   than India and complete labels. So field size alone cannot explain any
   result India produces.

---

## What was measured

### The grid is 6.07 m and the sensor is 10 m

Measured geodesically from each chip's own transform over 80 chips:
**6.067 m per pixel**, both across and down. 256 pixels gives 1,553 m, and
1,536 m is 1,024 × 1.5 m, the footprint of the Airbus imagery the parcels were
digitised on. So FTW cut Sentinel-2 to the labelling image's footprint and
resampled it to a 256 square.

The resampling is arithmetic, not inference: a 10 m sensor cannot produce 6 m
pixels. What needed measuring was the method. Exactly **0.71% of neighbouring
pixels are identical**, against the 39% that nearest-neighbour upsampling from
10 m to 6.07 m would leave behind. The mean ratio of lag-2 to lag-1 absolute
differences is 1.88, above the 1.0 that independent fine detail would give.

Both say a smooth interpolator built the grid. So detail visible at scales
below 10 m was produced by that interpolator rather than observed by the
satellite. `figures/india/field_scale.png` shows the same parcel on both grids.

*Source: `results/india/interpolation_check.csv`, from `src/inspect_labels.py`.*

### The labels are presence-only, five parcels per chip

| | pixels | share |
|---|---:|---:|
| parcel interior | 924,166 | 0.71% |
| boundary ring | 420,339 | 0.32% |
| verified background | 0 | 0.00% |
| parcel, combined | 1,344,505 | 1.04% |
| unlabelled | 128,547,847 | 98.96% |

9,837 parcels across 1,982 chips. Median 5 parcels per chip, mean 4.96,
maximum 6, two chips with none. Not one of the 9,837 touches a chip edge, so
the annotators chose whole parcels and the size distribution is not truncated.

The three label rasters resolve to exactly three pixel states and no others:

| instance | 2class | 3class | meaning |
|---|---|---|---|
| > 0 | 1 | 1 | parcel interior |
| 0 | 0 | 2 | the parcel's own boundary ring |
| 0 | 3 | 3 | never looked at |

There is no verified background anywhere in the dataset. The only non-parcel
labelled pixels are the rings hugging the parcels themselves: 99.87% of ring
area sits within 3 pixels of an interior.

*Source: `results/india/label_coverage.csv`, `results/india/ring_check.csv`, from
`src/measure_fields.py`.*

### The instance mask is the parcel minus its edge

FTW erodes each parcel's outer pixel ring into a separate class, so that
adjacent parcels do not merge into one blob in a binary mask. Counting
instance pixels therefore measures the parcel with its edge removed, and
understates area.

Ring thickness, by exact Euclidean distance from each ring pixel to the
nearest interior pixel:

| distance | share |
|---:|---:|
| 1.00 | 78.67% |
| 1.41 | 18.07% |
| 2.00 and beyond | 3.14% |

1.00 is an orthogonal step and 1.41 the same ring reached diagonally, so
**96.74% of the ring is one pixel of parcel edge**. What lies beyond turns up
at sharp corners and where a parcel pinches thin enough to break its interior
into pieces. Giving the ring back raises total parcel area by 45.4%.

*Source: `results/india/ring_thickness.csv`, from `src/ring_thickness.py`.*

### Parcel size against what Sentinel-2 resolves

Reconstructed parcels, all 1,982 chips, converted at the measured 6.067 m
pixel and expressed in native 10 m Sentinel-2 pixels:

| | hectares | native 10 m px | pixels on a side |
|---|---:|---:|---:|
| p5 | 0.066 | 7 | 2.6 |
| p25 | 0.151 | 15 | 3.9 |
| **p50** | **0.302** | **30** | **5.5** |
| p75 | 0.604 | 60 | 7.8 |
| p95 | 1.598 | 160 | 12.6 |
| mean | 0.503 | 50 | 7.1 |

Share of parcels below a given size, in native Sentinel-2 pixels:

| smaller than | share |
|---|---:|
| 2 × 2 px (0.04 ha) | 0.94% |
| 3 × 3 px (0.09 ha) | 10.56% |
| 4 × 4 px (0.16 ha) | 26.53% |
| **5 × 5 px (0.25 ha)** | **43.01%** |
| 7 × 7 px (0.49 ha) | 68.36% |
| 10 × 10 px (1.00 ha) | 87.87% |

A parcel of 9 native pixels is 3 by 3. Its centre pixel is its only interior
and everything else is edge. Whatever a model outputs there, it is not tracing
a shape.

*Source: `results/india/field_sizes.csv`, from `src/measure_fields.py`.*

### The control: Slovenia, measured with the same code

The obvious objection to any India result is that the fields are simply too
small for anything to work, and that the evaluation rather than the model is
what failed. A country with complete labels answers that, and Slovenia answers
it better than expected.

| | India | Slovenia |
|---|---:|---:|
| chips | 1,982 | 2,177 |
| parcels | 9,837 | 69,435 |
| parcels touching a chip edge | 0 | 21,188 (30.5%) |
| untruncated parcels | 9,837 | 48,247 |
| grid pixel | 6.067 m | 4.139 m |
| median parcel | 0.302 ha | **0.223 ha** |
| median, native 10 m px | 30 | **22** |
| under 5 × 5 native px | 43.01% | **53.56%** |
| under 3 × 3 native px | 10.56% | **28.03%** |
| parcel interior, share of pixels | 0.71% | 9.77% |
| boundary ring | 0.32% | 2.41% |
| verified background | 0.00% | 87.82% |
| unlabelled | 98.96% | 0.00% |
| precision measurable | no | yes |

Slovenian parcels are smaller, not larger. Three further points push the same
way. Its imagery is upsampled harder, 10 m onto a 4.14 m grid against India's
6.07 m, so it carries more interpolated pixels per real observation. Its
parcels are rasterised on that finer grid, so they suffer less of the area
inflation that makes India's 0.302 ha an upper bound, which widens the real
size gap beyond what the table shows. And its ring is one pixel thick as well,
97.60% at Euclidean distance 1.41 or less, so the same reconstruction applies
unchanged.

Differences to carry forward rather than forget: India is 2016 imagery and
Slovenia 2021, and Slovenia's config lists 18 crop types where India lists
none. Per-chip statistics are not comparable between them either, since
complete labelling gives Slovenia a median of 19 parcels per chip against
India's 5, and leaves 361 chips with no parcel at all.

*Source: `results/slovenia/`, same scripts, `FTW_COUNTRY=slovenia`.*

---

## What this means for scoring

Unlabelled is not background. A model that found real parcels across the
other 98.96% of a chip would be charged a false positive for every one, and
`figures/india/chip_sparsity.png` shows that ground is full of fields. So any
precision, IoU or F1 computed over these masks without excluding value 3 is
not a weak number. It is not a number.

What the dataset supports:

- **recall** against the 9,837 drawn parcels
- **boundary agreement** inside a labelled parcel
- **size-stratified breakdowns** of both, which is the point of the project

What it cannot support:

- precision, false positive rate, or anything derived from them
- any claim about behaviour on ground nobody labelled

Stage 2 is built on that constraint rather than around it.

---

## Corrections made while measuring

Recorded because the corrected numbers are only trustworthy if the wrong ones
are visible too.

**C-01. The chips were called 10 m.** Stated as fact for several steps before
anything measured the transform. They are 6.067 m. Everything downstream is
now converted at the measured value and reported in native 10 m pixels, which
is the unit that governs resolvability.

**C-02. The first exploration read the wrong files.** It sampled GeoTIFFs
alphabetically, which returned 200 instance masks, and reported their geometry
as the imagery's. It also searched for label rasters by filename when the word
is in the path, and so reported zero.

**C-03. Chip footprints were reported as field areas.** `chips_india.parquet`
is the chip index, one row per chip. Read as field polygons it produced a
"size distribution" of 235 to 236 ha with almost no spread. A distribution
that flat should have been caught before it was printed.

**C-04. Parcel size was measured 31% low.** The instance mask was taken as the
parcel when it is the parcel minus its eroded edge. Fixed by
`ftw_common.full_fields()`, validated by eroding known parcels in a synthetic
dataset and reconstructing them: combined area returned to the original pixel
count exactly.

**C-05. A prediction dressed up as arithmetic.** Having found the aggregate
ring-to-interior ratio of 1.455, this project predicted the median would move
from 0.166 ha to 0.24 ha. It moved to 0.302. An aggregate area ratio does not
apply to a median, because a ring is a perimeter and small parcels gain
proportionally more from it than large ones. Total area rose 45.4% while the
median rose 82%.

**C-06. Orphaned ring pixels were handed to distant parcels.** Where erosion
destroys a small parcel entirely, its ring has no interior to return to.
Unconstrained nearest-neighbour assignment sent such pixels as far as 137
pixels away in testing. `full_fields()` now caps assignment at 3 pixels and
counts the remainder: 0.11% of ring area, in 19 of 400 chips.

**C-07. Ring thickness was read off the wrong test.** A 4-connected dilation
puts a one-pixel ring's diagonal corners at two steps, so "98.93% within 2
steps" was reported as a two-pixel band. Exact Euclidean distance shows one
pixel.

**C-08. The boundary ring was keyed off the wrong raster.** `semantic_2class`
value 0 means "not field", which is background OR boundary and cannot say
which. `semantic_3class` separates them: 0 background, 2 boundary. India has no
background at all, so the two agree there and the mistake was invisible for the
whole of stage 1.

Running the same code on Slovenia exposed it immediately. There `2class==0` is
87% of the chip, almost all verified background, so every parcel was dilated
three pixels into open ground. The run reported "boundary ring 90.23%",
"unlabelled 0.00%" and "parcel, combined 100.00%", and inflated parcel area by
55.4%. Those Slovenia numbers were wrong and are superseded by the table above.

The ring is `3class == 2`, everywhere. India's published figures are unaffected:
its cross-tab shows `2class==0` and `3class==2` covering the identical 43,224
pixels, and re-running moved parcel interior from 923,955 to 924,166 pixels,
0.0002% of the chip area.

The lesson is not about FTW. A constant was named after what a value meant in
the only country that had been looked at. Running on a second one was what
found it, and there was no test that could have.

**C-09. Truncated parcels were mixed in with whole ones.** India has no parcel
touching a chip edge, so the distinction cost nothing and was never made.
Slovenia has 21,188 of 69,435, and a truncated parcel understates its own size.
`measure_fields.py` now reports the untruncated set separately and treats it as
the honest one.

---

## Open, not resolved

**O-01. 0.302 ha here against 0.24 ha in the source paper.** Wang, Waldner and
Lobell report a 0.24 ha median for these labels. This project measures 0.302 ha
on the 6.07 m rasterisation FTW ships. The two are different quantities even
if both are right, since the paper measures vector polygons.

The likely mechanism is rasterisation bias. A polygon rasterised onto a coarse
grid gains area, and gains more if every touched pixel is included rather than
only pixels whose centre falls inside. At a median 82 grid pixels with a
perimeter near 36, a half-pixel outward bias would account for the difference.
This is a plausible explanation and an unverified one. FTW's documentation and
paper do not state how the masks were rasterised.

Consequence: **0.302 ha is an upper bound on the true parcel.** Every
"share smaller than" figure above is correspondingly a lower bound, so the real
sub-resolution share is probably worse than the table says. The conservative
number is the one quoted.

Settling it needs the original India vector polygons, which are published
separately and have not been fetched.

**O-02. Nothing has been validated against a model yet.** Every statement here
is about the reference data. No claim is made about what any model recovers.

---

## Files

| File | Written by | Holds |
|---|---|---|
| `results/india/field_sizes.csv` | `measure_fields.py` | one row per parcel, interior and reconstructed |
| `results/india/label_coverage.csv` | `measure_fields.py` | one row per chip, pixel counts by 3-class value |
| `results/india/ring_check.csv` | `measure_fields.py` | ring area within 1, 2 and 3 dilation steps |
| `results/india/ring_thickness.csv` | `ring_thickness.py` | exact distance distribution of the ring |
| `results/india/interpolation_check.csv` | `inspect_labels.py` | duplicate-pixel and lag-ratio tests |
| `figures/india/field_scale.png` | `figure_field_scale.py` | five parcels, two grids, the label |
| `figures/india/chip_sparsity.png` | `figure_field_scale.py` | whole chips with every label outlined |

Reproduce in this order, in the project venv:

```
python src\inspect_labels.py
python src\ring_thickness.py
python src\measure_fields.py
python src\figure_field_scale.py
```

`src/ftw_common.py` holds the paths and the parcel reconstruction, so no two
scripts can disagree about what a parcel is. It reads `FTW_COUNTRY`, defaulting
to india, and writes under `results/<country>/` and `figures/<country>/`. To
run the same pipeline on another FTW country:

```
set FTW_COUNTRY=slovenia
python src\ftw_download.py data download --countries slovenia -o data
python src\inspect_labels.py
```

`src/ftw_download.py` exists because source.coop refuses requests announcing
themselves as Python. It installs a browser User-Agent on urllib and hands the
same arguments to the same `ftw` command.
