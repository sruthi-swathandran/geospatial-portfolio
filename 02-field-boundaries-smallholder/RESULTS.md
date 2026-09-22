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

## Where this sits

`FINDINGS.md` measures the reference data before any model runs. `RESULTS.md`
runs FTW's published method against it. `COMPARISON.md` puts two classical
methods and a foundation model beside that checkpoint over the same chips, and
that is where the current headline numbers live. A technical review of all
three documents is in `REVIEW.md`. The gaps it found that change how these
numbers should be read are listed under Known gaps in `COMPARISON.md`.

---

## The short version

1. The method works on Slovenia and does not work on India, using the same
   weights, with both countries in the checkpoint's training set.
2. On four of every five Indian test chips the model labels most of the scene
   as field boundary. There is no interior anywhere in those chips, so no
   parcel in them can be matched at any threshold.
3. Recall against parcel width shows a threshold near three native pixels
   across. Below it the released checkpoint finds 1 parcel in 441, which is
   0.23% with a 95% interval of [0.01, 1.26].
4. Our India object recall is 0.027 against reconstructed parcels, and 0.053 in
   FTW's own convention, which scores against the eroded interior. The 0.053 is
   the figure that compares to theirs, and it sits inside FTW's published range
   for India without fine-tuning, which runs 0.03 to 0.14 across three
   pre-training sets. Our scoring has been checked against theirs and matches.
   What is still unexplained is narrower: a model trained on FTW minus India
   scores 0.14 while checkpoints that include India score 0.053 on the same
   terms.

---
Stage 2b tests whether that number is about the imagery or about the
checkpoint, by running untrained methods over the same chips. See
COMPARISON.md.

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
| object recall | 0.030 | 0.027 | 0.145 | 0.222 | 0.14 |
| object precision | withheld | withheld | 0.201 | 0.240 | |

All figures are the 3-class checkpoints. Object recall and precision here are
measured against reconstructed parcels, while FTW's published column is in
their convention against eroded interiors, where our India FULL figure would
read 0.053 rather than 0.027. See S-08. Training on fifteen extra countries
moves Slovenia a long way and leaves India where it was, 59 parcels found
against 54 out of 1,983, which is inside the noise.

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

**Stage 2b puts that explanation in doubt.** The labelled Slovenian parcels
are about half the width of the labelled Indian ones, 22.0 m median against
42.5 m, with 64.9% of them under 30 m against India's 22.2%. If densely packed
small parcels drove the saturation, Slovenia should saturate harder, and it
does not: 18 objects per chip there against 175 here. What holds the argument
back is that India's labels are presence-only, and an annotator drawing five
parcels by hand is likely to pick visible ones, so the true Indian parcel
population may run smaller than its labelled median says. See the cross-country
table in `COMPARISON.md` and F-01 in `REVIEW.md`.

Slovenia's 87 chips predicting no field at all are a different case and not a
failure: those chips are forested hills with almost nothing labelled either.

*Source: `results/saturation_3class_full.csv`.*

---

## Why parcels fail: width, not area

Recall against the parcel's narrow dimension, measured as the pixel count
across its largest inscribed circle:

| width, native 10 m px | India found | Slovenia found |
|---|---:|---:|
| under 2 | 0.0% | 1.5% |
| 2 to 3 | 0.4% | 13.0% |
| 3 to 4 | 0.2% | 36.3% |
| 4 to 5 | 1.1% | 47.6% |
| 5 to 7 | 3.7% | 62.1% |
| 7 to 10 | 6.4% | 69.6% |
| 10 to 15 | 15.1% | 69.6% |
| over 15 | 30.0% | 82.4% |

Slovenia steps from 1.5% to 36.3% between two and four pixels across, then
climbs more slowly and flattens near 70%. Its area curve over the same parcels climbs steadily
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

| | our parcels | their shapes | our recall, FTW convention | their recall |
|---|---:|---:|---:|---:|
| India | 1,983 | 2,059 | 0.053 | 0.048 |
| Slovenia | 6,831 | 10,429 | 0.289 | 0.190 |

Both recall columns here are measured against eroded interiors so that they are
like for like. Against reconstructed parcels the same predictions give 0.027
and 0.222. See S-08.

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

**S-08. Object IoU was measured against the eroded instance mask.** C-04
established that FTW's instance raster is the parcel with its outer ring
removed, and every size figure in this project is quoted on the reconstructed
parcel. The object scorer was not. It passed the eroded mask as truth, so
predictions were matched against a target smaller than the field it stands
for. A shrunken target is easier to hit, and erosion takes proportionally more
from a small parcel, so the effect is largest exactly where this project's
claims live. India's object recall moves from 0.053 to 0.027 and Slovenia's
from 0.289 to 0.222, factors of 1.95 and 1.30. Slovenia's object precision
moves from 0.312 to 0.240. Slovenia's width curve moves from 3.2% found under
two native pixels and 50.4% at three to four, to 1.5% and 36.3%. Every pixel
metric is unchanged, because those never touched the instance raster.

FTW's own `get_object_level_metrics` takes `semantic_2class` as truth, where
value 1 is the interior, so the eroded target is their convention as well. The
0.053 is therefore the figure to set beside their published India range of
0.03 to 0.14, and 0.027 is the figure for the question of whether the tool
finds fields. Both belong here with the convention named, which is what S-07
now says.

This surfaced because a scorer written later for stage 2b disagreed with the
original by a factor of two on the same predictions. `reconcile_ftw.py` runs
every combination of truth raster and prediction class and writes
`results/<country>/scorer_reconciliation.csv`, which located the cause instead
of guessing at it. Three separate code paths now return the same India
figures.

---

## Open, not resolved

**O-03. A model trained without India beats checkpoints trained with it.** FTW
report object recall 0.14 for a model pre-trained on FTW minus India and tested
on India without fine-tuning, alongside 0.03 for a France-pretrained model and
0.05 for an AI4Boundaries-pretrained one. We measure 0.053 in their convention 
with the released CC-BY and FULL checkpoints, both of which include India in 
training.Our figure sits inside their range, so the framing is not that we score
far below them. It is that seeing the country in training should help and 
appears not to.

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
