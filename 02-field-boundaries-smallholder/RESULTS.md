# RS-02 stage 2: does the published method work on Indian smallholdings

Stage 1 measured the reference data. This runs the method against it.

What is being tested is FTW's own published approach rather than anything of
ours: free Sentinel-2 at 10 m, two seasonal windows stacked into eight
channels, a U-Net with an EfficientNet-B3 encoder, and a three-class head for
field interior, field boundary and background. That is the current open state
of the art for global field delineation and it is what anyone starting this
work today would pick up.

Every number traces to a file under `results/`. Where a number is a bound, an
inference or unexplained, it says so.

---

## The short version

1. The method works on Slovenia and does not work on India, using the same
   weights, with both countries in the checkpoint's training set.
2. On four of every five Indian test chips the model labels most of the scene
   as field boundary. There is no interior anywhere in those chips, so no
   parcel in them can be matched at any threshold.
3. Recall against parcel width shows a threshold near three native pixels
   across. Below it, delineation does not happen.
4. Our India object recall of 0.053 sits inside FTW's own published range for
   India without fine-tuning, which runs 0.03 to 0.14 across three pre-training
   sets. Our scoring has been checked against theirs and matches. What is still
   unexplained is narrower: a model trained on FTW minus India scores 0.14
   while checkpoints that include India score 0.053.

---

## What was run

| | |
|---|---|
| checkpoints | `2_Class_CCBY`, `3_Class_CCBY`, `3_Class_FULL` |
| architecture | U-Net, EfficientNet-B3, 8 input channels, `ignore_index` 3 |
| input | window_b then window_a, 4 bands each, divided by 3000 |
| splits | India 399 test chips, Slovenia 228 |
| hardware | 6-core CPU, no GPU, 7 to 9 chips per second |

`ftw model test` could not be used. It hardcodes `num_workers=12`, Windows
spawns rather than forks, and twelve processes each re-importing torch and
lightning exhaust the pagefile. `src/run_inference.py` runs FTW's own dataset
class and preprocessing with no workers, so the pipeline is theirs and only the
loop is ours.

### How it is scored, and what is withheld

Pixel metrics follow FTW exactly: the 2-class mask, field is 1, and value 3
excluded. Their trainer sets `ignore_index=3` and their test passes it to every
metric, so these are comparable to their published figures.

Object metrics match each labelled parcel against the best-overlapping
connected component of the prediction, counting IoU above 0.5 as found.

Object **precision** is computed for Slovenia and withheld for India. On
presence-only labels a predicted parcel with no match may be a real field
nobody drew. FTW's `get_object_level_metrics` takes no ignore index and counts
every unmatched prediction as a false positive, which on India charges the
model for finding real parcels. The FTW paper reaches the same conclusion:
*"We report recall metrics only for India since it has presence-only labels."*

---

## Results

| | India CC-BY | India FULL | Slovenia CC-BY | Slovenia FULL | FTW published, India |
|---|---:|---:|---:|---:|---:|
| pixel IoU | 0.248 | 0.229 | 0.430 | 0.595 | 0.57 |
| pixel recall | 0.253 | 0.233 | 0.455 | 0.635 | 0.63 |
| pixel precision | 0.931 | 0.931 | 0.886 | 0.904 | |
| object recall | 0.060 | 0.053 | 0.181 | 0.289 | 0.14 |
| object precision | withheld | withheld | 0.251 | 0.312 | |

All figures are the 3-class checkpoints. Training on fifteen extra countries
moves Slovenia a long way and moves India slightly backwards.

Our Slovenia FULL row sits almost on FTW's published India row, 0.595 against
0.57 and 0.635 against 0.63. That is the calibration check: when the model
works, this scorer returns numbers in the published range.

*Source: `results/score_summary_3class_full.csv` and its CC-BY counterpart.*

### Two-class against three-class

The 2-class checkpoint predicts extent rather than parcels. On India it painted
92.8% of a chip as field, which becomes one connected component, and a 45 pixel
parcel measured against a 60,000 pixel component gives an IoU near 0.0007.
Object recall came out at 0.1%, which is arithmetic rather than a measurement.
Delineation belongs to the 3-class head and its boundary class, which is what
`ftw inference polygonize` consumes.

---

## Why India fails: boundary saturation

| | median boundary share | median field share | chips over half boundary |
|---|---:|---:|---:|
| India | 63.6% | 28.5% | 321 of 399 |
| Slovenia | 4.9% | 0.1% | 0 of 228 |

On 321 of 399 Indian test chips the model calls more than half the scene field
boundary. Those chips contain no interior, so nothing in them can match at any
IoU threshold regardless of parcel size or shape. `figures/india/
predictions_3class_full.png` shows three such crops where the entire 400 m
window is boundary.

The model is arguably not mistaken. Stage 1 measured the median Indian parcel
at about five native pixels across. In a wall-to-wall mosaic of parcels that
size, most ground genuinely does lie within a boundary's width of an edge. The
resolution limit does not appear as a blurred outline. It appears as a scene
where the model finds edges everywhere and has nowhere left to put an interior.

Slovenia's 87 chips predicting no field at all are a different case and not a
failure: those chips are forested hills with almost nothing labelled either.

*Source: `results/saturation_3class_full.csv`.*

---

## Why parcels fail: width, not area

Recall against the parcel's narrow dimension, measured as the pixel count
across its largest inscribed circle:

| width, native 10 m px | India found | Slovenia found |
|---|---:|---:|
| under 2 | 0.0% | 3.2% |
| 2 to 3 | 0.0% | 25.0% |
| 3 to 4 | 1.4% | 50.4% |
| 4 to 5 | 5.5% | 58.7% |
| 5 to 7 | 8.1% | 67.4% |
| 7 to 10 | 12.9% | 73.7% |
| 10 to 15 | 17.0% | 71.3% |
| over 15 | 30.0% | 82.4% |

Slovenia steps from 3.2% to 50.4% between two and four pixels across, then
flattens near 70 to 80%. Its area curve over the same parcels climbs steadily
with no step in it. **Width shows a threshold where area shows a gradient**,
and the threshold sits where a one to two pixel boundary on each side stops
leaving an interior.

Measured as a correlation the two look alike: width +0.548 against area +0.525
for Slovenia, +0.230 against +0.218 for India. Width and area are strongly
correlated in any real parcel set, so that comparison cannot separate them.
The shape of the curve can, and does.

India stays flat and low at every width, topping out at 30% above fifteen
pixels across, because saturation is a scene-level failure that a parcel's own
dimensions cannot escape.

*Source: `results/<country>/parcel_width_3class_full.csv`.*

---

## Checking our scoring against FTW's own code

`src/verify_against_ftw.py` runs FTW's scoring functions over the exact
prediction rasters scored above.

| | our scorer | FTW's own code |
|---|---:|---:|
| India pixel IoU | 0.229 | 0.2293 |
| India pixel precision | 0.931 | 0.9308 |
| India pixel recall | 0.233 | 0.2333 |
| Slovenia pixel IoU | 0.595 | 0.5950 |
| Slovenia pixel precision | 0.904 | 0.9039 |
| Slovenia pixel recall | 0.635 | 0.6351 |

Identical to every digit reported. The pixel scoring here is theirs.

Object recall differs, and the reason is the counting unit.

| | our parcels | their shapes | our recall | their recall |
|---|---:|---:|---:|---:|
| India | 1,983 | 2,059 | 0.053 | 0.048 |
| Slovenia | 6,831 | 10,429 | 0.289 | 0.190 |

Their truth shapes come from `rasterio.features.shapes` on the 2-class mask, so
a parcel whose eroded interior pinches into disconnected pieces counts once per
piece. Slovenia's strip fields produce 3,598 such extra fragments. Counting
parcels answers whether a field was found; counting fragments answers whether a
blob was found. Both figures are reported here and the parcel count is the one
used elsewhere in this document.

### What their object precision does on presence-only labels

Their function on India returns 99 true positives against 116,258 false
positives, an object precision of **0.0009**. The model produces roughly 291
field polygons per Indian chip and at most five of them can ever match a label.
That is the presence-only problem stated by FTW's own code rather than argued
for here, and it is why object precision is withheld for India throughout.

*Source: `results/ftw_own_scoring_3class_full.csv`.*

---

## Corrections made during stage 2

**S-01. A 2-class extent model was judged on parcel delineation.** Object
recall of 0.1% on India was reported before noticing that a single connected
region spanning a chip fails IoU against every parcel by arithmetic. The
3-class head is the one that separates parcels.

**S-02. FTW's metrics were called meaningless on presence-only data.** Said as
a guess and wrong for the pixel metrics, which pass `ignore_index=3` and are
sound. It holds only for their object metrics, which take no ignore index, and
the paper says as much itself.

**S-03. The seasonal window ordering was flagged as inconsistent.** India's
window_a is July to November and Slovenia's is May to August, which are both
the main growing season. The convention is consistent and the concern was
wrong.

**S-04. A median was read as an absence.** Slovenia's "median 2 pixels
predicted" looked like model failure. The median Slovenian test chip carries
2.12% labelled parcel and many are forest, and the correlation between
predicted and labelled coverage is +0.933.

**S-05. Width was predicted to separate found from missed much more cleanly
than area.** It is better by a margin too small to claim, in both countries.
What survives is the curve shape rather than the correlation.

**S-06. The first comparison figure sampled chips alphabetically**, landed in
one forested Slovenian area, and made a correct result look like a dead one.
Figures now sample across the measured size range.

**S-07. The gap with the published India numbers was overstated.** This
document first reported ours as "roughly a third of theirs" by comparing
against their best India row. Their own India results without fine-tuning span
0.03, 0.05 and 0.14 object recall across three pre-training sets, and ours at
0.053 sits inside that range. The narrower question that survives is why a
model trained on FTW minus India beats checkpoints that include it.

---

## Open, not resolved

**O-03. A model trained without India beats checkpoints trained with it.** FTW
report object recall 0.14 for a model pre-trained on FTW minus India and tested
on India without fine-tuning, alongside 0.03 for a France-pretrained model and
0.05 for an AI4Boundaries-pretrained one. We measure 0.053 with the released
CC-BY and FULL checkpoints, both of which include India in training. Our figure
sits inside their range, so the framing is not that we score far below them. It
is that seeing the country in training should help and appears not to.

Three explanations were named and all three have now been tested.

**The scorer is ruled out.** FTW's own metrics over our predictions return our
pixel numbers to four decimals and our object recall within the counting-unit
difference described above.

**`--postprocess` is ruled out.** No postprocess function exists in `ftw` or
`ftw_cli`, and the flag's only code path calls `out.copy()` on the metrics file
path, a string. It cannot run in this version, so no number here or in the
paper can depend on it.

**Polygonization is ruled out as a cause of low recall.** `ftw_cli.polygonize`
adds `simplify`, `min_size`, `max_size` and `close_interiors`. Filtering small
polygons raises precision by discarding spurious predictions and cannot raise
recall.

What remains is the model or its training. Their Table 5 rows come from models
they trained per experiment, not from the released checkpoints, and nothing in
the paper reports per-country results for the checkpoints we ran. Reproducing
their training is out of reach on a 2 GB GPU, so **this stays open, narrowed to
one candidate.** The India figures here remain a lower bound.

**O-04. The polygonize step has not been run end to end.** Its source has been
read and its parameters are known, but no scored comparison of polygonized
output against raw rasters exists. It is expected to raise precision rather
than recall.

**O-05. No fine-tuning has been attempted.** The published checkpoint is what
anyone would pick up, so what it does untouched is the honest thing to report
first. FTW's own Table 5 shows fine-tuning moving India's object recall from
0.14 to 0.19, so it helps and does not transform.

**O-06. Licensing cuts against the better model.** The FULL checkpoint trains
on Latvia, Portugal, South Africa and Lithuania, whose labels are CC-BY-NC or
non-commercial. The cleanly licensed CC-BY checkpoint is the weaker one, which
matters for anyone planning to build a product on this.

---

## Files

| File | Written by | Holds |
|---|---|---|
| `results/<c>/pred_3class_full/` | `run_inference.py` | one prediction raster per test chip |
| `results/<c>/score_parcels_3class_full.csv` | `score_predictions.py` | one row per parcel, best IoU, found |
| `results/<c>/parcel_width_3class_full.csv` | `analyse_width.py` | the same parcels with width added |
| `results/score_summary_3class_full.csv` | `score_predictions.py` | pixel and object metrics per country |
| `results/saturation_3class_full.csv` | `analyse_width.py` | boundary share per country |
| `results/ftw_own_scoring_3class_full.csv` | `verify_against_ftw.py` | FTW's own metrics over our predictions |
| `figures/recall_by_size_3class_full.png` | `score_predictions.py` | recall against area |
| `figures/recall_by_width_3class_full.png` | `analyse_width.py` | recall against width and area |
| `figures/<c>/predictions_3class_full.png` | `figure_predictions.py` | parcels across the size range |

Reproduce, per country, with `FTW_COUNTRY` set:

```
python src\run_inference.py --ckpt models\3class_full.ckpt --classes 3 --tag _full
python src\score_predictions.py --classes 3 --tag _full
python src\analyse_width.py --classes 3 --tag _full
python src\figure_predictions.py --rows 6
```

Checkpoints come from `ftw model download` through `src/ftw_download.py`, which
adds a browser User-Agent because source.coop refuses requests announcing
themselves as Python.
