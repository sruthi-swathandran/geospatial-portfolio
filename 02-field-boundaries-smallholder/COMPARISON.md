# RS-02 stage 2b: is it the imagery or the checkpoint?

Stage 2 measured FTW's released checkpoints on India and Slovenia. India came
back at 0.027 object recall against Slovenia's 0.222, with a threshold near
three native pixels of parcel width below which almost nothing was found.

That result has two readings and they lead to opposite advice. If 10 m imagery
cannot carry a parcel that narrow, then someone planning a project should buy
finer imagery. If FTW's checkpoint is failing to extract what the imagery does
carry, they should try a different method. Nothing in stage 2 separates the
two, because every number in it came from one model family.

This stage separates them by running methods that share nothing with FTW over
the same chips, scored by the same function.

---

## Findings

1. At a matched object budget the trained checkpoint and an untrained
   watershed change places between the two countries. Slovenia, where FTW
   trained on complete labels: 0.222 against 0.170. India, where labels are
   presence-only and parcels are small: 0.027 against 0.100.
2. FTW's Indian output sits at its own null. Recall 0.027 against a null of
   0.019 on 1,983 parcels, a gap of +0.008 that is about two standard errors.
   Scattering the same number of random cells over the scene performs
   comparably.
3. The checkpoint shatters on India. It emits 175 objects per chip into scenes
   holding five labelled parcels, against 18 per chip on Slovenia where about
   32 exist. The boundary saturation measured in stage 2, where 321 of 399
   Indian chips are called more than half boundary, appears here as fragmented
   output.
4. Watershed clears its null by +0.13 to +0.20 across a twenty-fold range of
   settings, from 917 objects per chip down to 103. A margin that survives that
   range is not a parameter fluke.
5. The floor at three native pixels is soft, not absolute. Watershed finds 14
   of 441 parcels below it, 3.17% with an interval of [1.75, 5.27] that
   excludes zero, against 30.74% above it. Sub-three-pixel parcels are
   recoverable about a tenth as often, rather than never.
6. Watershed is still poor. One parcel in ten at FTW's object budget is not a
   usable field map. Both things hold: the Indian imagery is hard, and the
   checkpoint is not reading what is in it.

---

## What was run

Three methods over the same test chips, 399 for India and 228 for Slovenia,
through one scoring function in `src/seg_score.py`.

**FTW 3-class FULL.** The released checkpoint, read from the prediction
rasters written in stage 2. Objects are the connected components of the field
class.

**Watershed on a multi-band gradient.** Every band of both seasonal windows is
percentile-stretched, the Sobel magnitude is averaged across bands and lightly
smoothed, and basins are grown from the h-minima of that surface. The parameter
`h` controls how finely it cuts. This is what an image analyst would reach for
on this problem and it was trained on nothing.

**Felzenszwalb.** A second opinion with different behaviour, so a poor
classical result cannot be blamed on one algorithm's quirks. Its `scale`
parameter plays the same role as `h`.

Both classical methods see the full eight-band stack, the same input FTW's
model gets. Neither has been fine-tuned, pre-trained or shown a label.

---

## How it is scored

Every labelled parcel is matched against whichever object covers most of it,
and that pair's IoU is the parcel's score. Recall is the share of parcels
scoring at least 0.5. Objects with no label under them are ignored rather than
counted as errors, because 98.96% of an Indian chip was never labelled and
scoring those would measure the annotation instead of the method.

Truth is the reconstructed parcel, the instance mask with its eroded boundary
ring given back. See S-08 in RESULTS.md for why that matters and what it costs.

Three controls make the comparison mean something.

**A null at matched object count.** Best-overlap matching rewards producing
more objects, because a method that cuts a chip into six hundred pieces has
better odds of one piece fitting a parcel than a method that produces twelve.
So every setting is paired with a null: the same number of Voronoi cells from
random seeds, with the imagery ignored entirely, averaged over three draws.
The gap between a method and its null is what the method earned. The null
matches count but not size distribution, so it is a floor rather than a twin.

**A matched object budget.** The gap does not control for object count on its
own, because a method with more objects has more room above its null. Every
method is therefore also read at FTW's object count, interpolated between the
measured settings on either side. This column is what the head-to-head
comparison rests on.

**A minimum object size.** FTW's own `polygonize` drops anything under 500
square metres, so scoring its raw argmax output would count specks its shipped
pipeline deletes. The same filter is applied to every method, which is fairer
to FTW and closer to how any of these would be deployed. It works out at 14
grid pixels for India and 29 for Slovenia.

---

## India

398 of 399 chips carry at least one labelled parcel. 1,983 parcels, 6.067 m
grid.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | | 175 | 0.000 | 0.027 | 0.019 | +0.008 |
| watershed | 0.005 | 917 | 0.349 | 0.233 | 0.058 | +0.175 |
| watershed | 0.01 | 816 | 0.349 | 0.244 | 0.057 | +0.186 |
| watershed | 0.02 | 676 | 0.333 | 0.246 | 0.050 | +0.197 |
| watershed | 0.05 | 446 | 0.296 | 0.219 | 0.041 | +0.178 |
| watershed | 0.1 | 261 | 0.195 | 0.156 | 0.025 | +0.131 |
| watershed | 0.2 | 103 | 0.048 | 0.053 | 0.008 | +0.045 |
| felzenszwalb | 25 | 1,403 | 0.234 | 0.028 | 0.057 | -0.029 |
| felzenszwalb | 50 | 1,165 | 0.266 | 0.062 | 0.057 | +0.004 |
| felzenszwalb | 100 | 666 | 0.218 | 0.084 | 0.048 | +0.036 |
| felzenszwalb | 200 | 323 | 0.103 | 0.052 | 0.033 | +0.019 |
| felzenszwalb | 400 | 163 | 0.019 | 0.027 | 0.014 | +0.013 |
| felzenszwalb | 800 | 96 | 0.004 | 0.012 | 0.006 | +0.005 |

At FTW's budget of 175 objects per chip: **FTW 0.027, watershed 0.100,
felzenszwalb 0.029.**

Watershed's figure is an interpolation between two measured settings, 103
objects at 0.053 and 261 at 0.156, so it sits inside the sweep rather than
being extrapolated past its edge.

Felzenszwalb is barely above its null anywhere and below it at the finest
setting. It was designed for three-channel photographs and warns when handed
eight bands, so its weak showing is partly about the algorithm and partly about
the input. It is reported because a baseline you only run once is not a
baseline.

---

## Slovenia

185 of 228 chips carry at least one labelled parcel; the rest are forest and
similar. 6,831 parcels, 4.139 m grid.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | | 18 | 0.000 | 0.222 | 0.006 | +0.217 |
| watershed | 0.005 | 706 | 0.302 | 0.202 | 0.024 | +0.178 |
| watershed | 0.01 | 620 | 0.325 | 0.242 | 0.027 | +0.215 |
| watershed | 0.02 | 492 | 0.355 | 0.292 | 0.024 | +0.268 |
| watershed | 0.05 | 282 | 0.356 | 0.345 | 0.022 | +0.324 |
| watershed | 0.1 | 141 | 0.254 | 0.305 | 0.015 | +0.290 |
| watershed | 0.2 | 54 | 0.103 | 0.170 | 0.008 | +0.162 |
| felzenszwalb | 25 | 581 | 0.193 | 0.030 | 0.025 | +0.005 |
| felzenszwalb | 50 | 567 | 0.284 | 0.110 | 0.024 | +0.086 |
| felzenszwalb | 100 | 381 | 0.298 | 0.209 | 0.023 | +0.186 |
| felzenszwalb | 200 | 203 | 0.179 | 0.177 | 0.019 | +0.158 |
| felzenszwalb | 400 | 101 | 0.066 | 0.097 | 0.012 | +0.085 |
| felzenszwalb | 800 | 54 | 0.016 | 0.035 | 0.006 | +0.029 |

At FTW's budget of 18 objects per chip: **FTW 0.222, watershed 0.170,
felzenszwalb 0.035.**

Both classical figures are clamped, because 18 objects per chip sits below the
coarsest setting either method reached. Their true values at that budget are
lower than shown, so the Slovenian comparison is tilted in their favour and the
checkpoint still wins it.

This is the control. FTW was trained on Slovenia with complete labels, and on
Slovenia it beats an untrained method by a clear margin. Had it not, the
scoring machinery would be the story rather than India.

---

## Reading the two together

Watershed appears to win Slovenia on the gap column, +0.324 against +0.217, and
that reading is wrong. It spends 282 objects per chip to FTW's 18. Gap over a
null rewards object count in the same direction the raw recall does, just less
steeply, which is why the budget column exists. That mistake was made here and
caught by Slovenia; see B-02.

Read at matched budget, the two countries invert:

| | Slovenia | India |
|---|---:|---:|
| FTW 3-class FULL | 0.222 | 0.027 |
| watershed | 0.170 | 0.100 |
| ratio | FTW 1.3x ahead | watershed 3.7x ahead |

The checkpoint beats an untrained gradient and watershed on the country it
trained on with complete labels, and loses to it by nearly four times on India.

---

## Width bands

The same 1,983 Indian parcels, binned by the pixel count across the largest
inscribed circle, scored for FTW and for watershed at its best setting.

| width, native 10 m px | parcels | FTW found | watershed found |
|---|---:|---:|---:|
| under 2 | 196 | 0.0% | 1.0% |
| 2 to 3 | 245 | 0.4% | 4.9% |
| 3 to 4 | 503 | 0.2% | 17.1% |
| 4 to 5 | 364 | 1.1% | 30.0% |
| 5 to 7 | 347 | 3.7% | 48.4% |
| 7 to 10 | 202 | 6.4% | 40.6% |
| 10 and over | 126 | 17.5% | 23.0% |

Three things in that table.

**The floor is soft.** Below three native pixels watershed finds 14 of 441,
3.17% with an interval of [1.75, 5.27], against 30.74% above. A tenfold
collapse rather than a wall. FTW finds 1 of 441 there, 0.23%.

**The gap between them is widest in the middle.** At 4 to 5 pixels, where the
median Indian parcel sits, watershed manages 30.0% and FTW 1.1%. At 10 pixels
and over they are close, 23.0% against 17.5%. The checkpoint fails hardest at
exactly the sizes that dominate Indian agriculture.

**Watershed's curve is not monotonic.** It peaks at 48.4% in the 5 to 7 band
and falls to 23.0% above 10. At 676 objects per chip its cells average about 97
grid pixels, so a large parcel gets cut into several and none reaches IoU 0.5.
That is a property of a fixed cutting scale, not a statement about large
fields. FTW's curve rises monotonically instead.

---

## What this says

The three-pixel floor belongs to the imagery. Two methods with nothing in
common both collapse below it, and the one that reads the imagery well
elsewhere collapses there too.

Everything above the floor belongs to the method. Between three and ten pixels
an untrained watershed finds between five and thirteen times as many parcels as
the released checkpoint. Whatever is stopping FTW there is not a lack of signal.

The advice that follows differs by parcel size. For ground where fields are
under about 30 m across, finer imagery is the only thing that helps, and no
choice of model rescues it. For ground above that, the model is the lever, and
the released checkpoint is leaving a great deal on the table.

---

## What this does not say

**That watershed is a usable method.** One parcel in ten at matched budget is
not a field map. It is a measuring instrument for how much signal is present,
not a product.

**That FTW is broken everywhere.** On Slovenia it beats both baselines
comfortably. The failure is specific to a country whose labels are
presence-only and whose parcels are small, and stage 2 could not tell those two
apart either.

**That width is the only thing that matters.** The district work in stage 3
found Jodhpur with the widest parcels in the Indian test set, 7.35 native
pixels median and none below the threshold, still at 0.048 recall. In arid
ground the fields are wide and the imagery has little to separate one from the
next. That is a contrast failure rather than a resolution failure and it needs
its own treatment.

**Anything about foundation models.** SAM has not been run. See O-07.

---

## Corrections

**B-01. The first comparison had no control for object count.** Watershed at
651 objects per chip appeared to beat FTW before any null existed, and the
sweep's own shape gave it away: median IoU climbed monotonically with object
count, from 0.002 at nine objects per chip to 0.308 at 651. That is the metric
rewarding volume. Nothing was reported from that version.

**B-02. Gap over a null was treated as sufficient.** It is not, because a
method with more objects has more room above its null. Slovenia exposed this:
watershed led on gap, +0.324 against +0.217, while spending fifteen times the
objects, and at matched budget FTW won. The budget column was added afterwards
and is now what the comparison rests on.

**B-03. FTW's 500 square metre polygonize default was blamed for halving its
India recall.** It does not. Running with the filter disabled left recall at
0.027, identical. The claim was made from a plausible mechanism rather than a
measurement and was retracted the same day.

**B-04. The width floor was described as absolute.** Stage 2 said delineation
does not happen below three native pixels, which was true of FTW at 1 parcel in
441 and false of the imagery. Watershed finds 3.17% there with an interval that
excludes zero. The floor is a tenfold collapse and should be written as one.

**B-05. A diagnostic run overwrote the main India comparison table.** A run at
minimum size zero wrote to the same filenames as the main run, leaving that
directory with mixed provenance: FTW tables from one run, classical tables from
another. Caught by reading `git status` before committing rather than by
anything in the code. Output filenames now carry the minimum size.

---

## Open items

**O-07. SAM has not been run.** The comparison holds a trained model and two
classical methods, and no foundation model. SAM takes three 8-bit channels
against FTW's eight bands across two seasons, so it enters handicapped and that
has to be stated wherever its number appears. Published work exists on SAM for
field boundaries from Sentinel-2, including FieldSeg at 10 m and a Canadian
prairies dataset built this way, none of which has been read here beyond its
title.

**O-08. The null matches object count but not size distribution.** Voronoi
cells from uniform random seeds are more uniform in size than watershed basins.
A null that resampled the method's own size distribution would be a tighter
control. The present one is a floor, and a method that fails to clear a floor
has certainly learned nothing.

**O-09. Felzenszwalb was run outside its design envelope.** It expects three
channels and warns when handed eight. Its weak result is therefore not clean
evidence about classical segmentation in general, only about this algorithm on
this input.

**O-10. Why does the checkpoint shatter on India?** 175 objects per chip
against 18 on Slovenia. Boundary saturation is the mechanism, since a chip
called mostly boundary has no interior left to connect, but what drives the
model into that state is unknown. Presence-only training labels are the obvious
suspect and testing it needs training runs this hardware cannot do.

---

## Reproducing

Open data throughout. Field labels and imagery from Fields of The World,
district polygons from geoBoundaries under CC BY 4.0.

```
python src\compare_segmenters.py --country india
python src\compare_segmenters.py --country slovenia
python src\threshold_check.py --country india --width-file parcel_width_seg_watershed_min500.csv
python src\threshold_check.py --country india --width-file parcel_width_seg_ftw_min500.csv
python src\reconcile_ftw.py --country india
```

The null is seeded, so both comparison runs reproduce to the digit. Runtime is
about fifteen minutes for India and thirty for Slovenia on a CPU-only machine,
the difference being that Slovenian chips carry far more parcels to score.

Outputs land in `results/<country>/`:

| file | what it holds |
|---|---|
| `segmenter_comparison_min500.csv` | one row per method and setting |
| `score_parcels_seg_<method>_min500.csv` | per-parcel IoU at the best setting |
| `parcel_width_seg_<method>_min500.csv` | the same with the width column |
| `scorer_reconciliation.csv` | truth and prediction combinations, for S-08 |
