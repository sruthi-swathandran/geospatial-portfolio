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

Stage 1 is in `FINDINGS.md` and stage 2 in `RESULTS.md`. A technical review of
all three is in `REVIEW.md`, and the gaps it found that change how these numbers
should be read are listed under Known gaps below.

---

## Findings

1. On India, three methods that were never trained on anything beat the trained
   checkpoint at a matched object budget. SAM reaches 0.153, watershed 0.107,
   felzenszwalb 0.031, against FTW's 0.027.
2. On Slovenia the checkpoint wins and wins economically. It reaches 0.222 from
   18 objects per chip. No competing method was run coarse enough to be read at
   that budget, so their figures there are upper bounds rather than
   measurements. See B-08.
3. FTW's Indian output barely clears its own null, measured properly. At 200
   draws rather than three, random Voronoi cells of the same count average
   0.0209 against the checkpoint's 0.0272. Three draws in 200 beat it outright
   and the best reached 0.0308, above the trained model, on cells that never
   saw the imagery. The gap is +0.0063, about twelve parcels in 1,983, and it
   clears the null at roughly one draw in seventy. Real, and small enough that
   the three-draw version in the table below could not have established it.
4. The checkpoint shatters on India. It emits 175 objects per chip into scenes
   holding five labelled parcels, against 18 per chip on Slovenia where about
   37 exist. The boundary saturation measured in stage 2, where 321 of 399
   Indian chips are called more than half boundary, appears here as fragmented
   output.
5. Watershed clears its null across the entire sweep, from 40 objects per chip
   to 917, with a gap running +0.018 to +0.196 that never reaches zero. A
   margin that survives a twentyfold range of settings is not a parameter
   fluke.
6. The floor at three native pixels is soft. Watershed finds 14 of 441 parcels
   below it, 3.17% against 30.74% above. SAM finds 6. FTW finds 1. Parcels that
   narrow are recoverable about a tenth as often, rather than never.
7. Above ten native pixels on India the ordering changes again. SAM finds
   50.79% of those parcels, watershed 23.02% and FTW 17.46%. For large Indian
   fields a foundation model with three channels beats the trained model with
   eight by nearly three times.
8. The floor is not explained by parcel width. At matched ground width, in the
   same sensor and by the same method, Slovenian parcels are found between 1.8
   and 71.5 times more often than Indian ones of the same size. Whatever
   separates the two countries is not resolution. See What this says.
9. Everything here is still poor in absolute terms. One parcel in six at FTW's
   object budget is not a usable field map for India.

---

## What was run

Four methods over the same test chips, 399 for India and 228 for Slovenia,
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

**SAM ViT-H, automatic mask generation.** A foundation model that has never
seen a field boundary or a satellite image in training. It takes three 8-bit
channels where FTW's model sees eight bands across two seasons, so it enters
handicapped and that handicap has to be read alongside every number it
produces. Two composites are run rather than one, because choosing whichever
three bands flattered the argument would stack the deck: true colour is what a
person would look at, false colour puts the near infrared where vegetation
contrast lives. The checkpoint is Apache 2.0.

Both classical methods and SAM see no labels, no fine-tuning and no
pre-training on anything related. The classical pair sees the full eight-band
stack, the same input FTW's model gets.

SAM is run at five confidence settings. Its mask generator applies both score
filters before overlap suppression, so generating once at a loose threshold and
filtering afterwards reproduces a strict run exactly. That equivalence was
verified to the mask on 985 masks with none lost and none gained, which is what
makes a five-point sweep affordable at 75 seconds per chip. Stability is pinned
at 0.88 throughout, because sweeping it breaks the equivalence.

---

## How it is scored

Every labelled parcel is matched against whichever object covers most of it,
and that pair's IoU is the parcel's score. Recall is the share of parcels
scoring at least 0.5. Objects with no label under them are ignored rather than
counted as errors, because 98.96% of an Indian chip was never labelled and
scoring those would measure the annotation instead of the method.

Truth is the reconstructed parcel, the instance mask with its eroded boundary
ring given back. See S-08 in `RESULTS.md` for why that matters and what it
costs.

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

`figures/recall_by_object_budget.png` draws this control for both countries.
Interpolation clamps when the budget falls outside a method's sweep, and a
clamped figure is a bound rather than a measurement. Every table below carries
a column saying which happened. All five Indian figures are interpolated. Four
of the five Slovenian ones are clamped.

**A minimum object size.** FTW's own `polygonize` drops anything under 500
square metres, so scoring its raw argmax output would count specks its shipped
pipeline deletes. The same filter is applied to every method, which is fairer
to FTW and closer to how any of these would be deployed. It works out at 14
grid pixels for India and 29 for Slovenia.

Every table in this document is written by `src\build_comparison.py` from the
result CSVs. None of them is typed by hand. That script exists because three
numbers here were once wrong for exactly that reason, which B-06 records.

---

## India

398 of 399 chips carry at least one labelled parcel. 1,983 parcels, 6.067 m
grid.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 175 | 0.000 | 0.027 | 0.022 | +0.005 |
| watershed | 0.005 | 917 | 0.349 | 0.233 | 0.051 | +0.182 |
| watershed | 0.01 | 816 | 0.349 | 0.244 | 0.051 | +0.193 |
| watershed | 0.02 | 676 | 0.333 | 0.246 | 0.051 | +0.196 |
| watershed | 0.05 | 446 | 0.296 | 0.219 | 0.037 | +0.182 |
| watershed | 0.08 | 319 | 0.235 | 0.182 | 0.033 | +0.149 |
| watershed | 0.1 | 261 | 0.195 | 0.156 | 0.025 | +0.131 |
| watershed | 0.13 | 196 | 0.134 | 0.124 | 0.018 | +0.106 |
| watershed | 0.16 | 149 | 0.089 | 0.088 | 0.016 | +0.072 |
| watershed | 0.2 | 103 | 0.048 | 0.053 | 0.007 | +0.046 |
| watershed | 0.3 | 40 | 0.009 | 0.019 | 0.001 | +0.018 |
| felzenszwalb | 25 | 1,404 | 0.234 | 0.028 | 0.057 | -0.029 |
| felzenszwalb | 50 | 1,165 | 0.266 | 0.061 | 0.053 | +0.009 |
| felzenszwalb | 100 | 666 | 0.218 | 0.084 | 0.045 | +0.039 |
| felzenszwalb | 150 | 437 | 0.144 | 0.065 | 0.037 | +0.028 |
| felzenszwalb | 200 | 323 | 0.103 | 0.052 | 0.031 | +0.021 |
| felzenszwalb | 300 | 213 | 0.047 | 0.042 | 0.022 | +0.020 |
| felzenszwalb | 400 | 163 | 0.019 | 0.027 | 0.014 | +0.013 |
| felzenszwalb | 800 | 96 | 0.004 | 0.012 | 0.006 | +0.006 |
| SAM ViT-H true colour | 0.50/0.88 | 185 | 0.051 | 0.156 | 0.019 | +0.137 |
| SAM ViT-H true colour | 0.60/0.88 | 184 | 0.051 | 0.156 | 0.022 | +0.134 |
| SAM ViT-H true colour | 0.70/0.88 | 181 | 0.043 | 0.155 | 0.018 | +0.136 |
| SAM ViT-H true colour | 0.80/0.88 | 167 | 0.023 | 0.146 | 0.015 | +0.131 |
| SAM ViT-H true colour | 0.88/0.88 | 129 | 0.008 | 0.121 | 0.012 | +0.110 |
| SAM ViT-H false colour | 0.50/0.88 | 213 | 0.127 | 0.172 | 0.021 | +0.151 |
| SAM ViT-H false colour | 0.60/0.88 | 212 | 0.127 | 0.172 | 0.025 | +0.147 |
| SAM ViT-H false colour | 0.70/0.88 | 208 | 0.118 | 0.170 | 0.023 | +0.147 |
| SAM ViT-H false colour | 0.80/0.88 | 192 | 0.103 | 0.162 | 0.021 | +0.142 |
| SAM ViT-H false colour | 0.88/0.88 | 147 | 0.038 | 0.139 | 0.015 | +0.123 |

At FTW's budget of 175 objects per chip:

| method | recall at 175 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.027 | 0.022 | +0.005 | single setting |
| watershed | 0.107 | 0.017 | +0.091 | interpolated |
| felzenszwalb | 0.031 | 0.016 | +0.015 | interpolated |
| SAM ViT-H true colour | 0.151 | 0.017 | +0.134 | interpolated |
| SAM ViT-H false colour | 0.153 | 0.019 | +0.135 | interpolated |

Every figure in that table sits inside its method's measured sweep, so the
Indian comparison is a measurement throughout.

The null column comes from three draws, which is the sweep's default and is
ample everywhere the gap runs to +0.09 or beyond. It is not ample for FTW's
row. `src\null_strength.py` remeasures that one at 200 draws without rerunning
any segmentation, and it puts the null at 0.0209 with a standard deviation of
0.0030, so FTW's gap is +0.0063 rather than the +0.005 shown here. Every draw
is kept in `results/india/null_draws_ftw.csv`.

Felzenszwalb is barely above its null anywhere and below it at the finest
setting. It was designed for three-channel photographs and warns when handed
eight bands, so its weak showing is partly about the algorithm and partly about
the input. It is reported because a baseline you only run once is not a
baseline.

---

## Slovenia

185 of 228 chips carry at least one labelled parcel; the rest are forest and
similar. 6,831 parcels, 4.139 m grid, about 37 parcels per chip.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 18 | 0.000 | 0.222 | 0.005 | +0.217 |
| watershed | 0.005 | 706 | 0.302 | 0.202 | 0.025 | +0.177 |
| watershed | 0.01 | 620 | 0.325 | 0.242 | 0.026 | +0.216 |
| watershed | 0.02 | 492 | 0.355 | 0.292 | 0.025 | +0.267 |
| watershed | 0.05 | 282 | 0.356 | 0.345 | 0.020 | +0.325 |
| watershed | 0.08 | 180 | 0.303 | 0.328 | 0.018 | +0.310 |
| watershed | 0.1 | 140 | 0.254 | 0.305 | 0.014 | +0.291 |
| watershed | 0.13 | 101 | 0.191 | 0.257 | 0.011 | +0.245 |
| watershed | 0.16 | 76 | 0.150 | 0.217 | 0.009 | +0.208 |
| watershed | 0.2 | 54 | 0.103 | 0.170 | 0.009 | +0.161 |
| watershed | 0.3 | 26 | 0.031 | 0.081 | 0.003 | +0.078 |
| felzenszwalb | 25 | 581 | 0.193 | 0.030 | 0.024 | +0.006 |
| felzenszwalb | 50 | 567 | 0.284 | 0.110 | 0.024 | +0.086 |
| felzenszwalb | 100 | 382 | 0.298 | 0.209 | 0.023 | +0.186 |
| felzenszwalb | 150 | 268 | 0.238 | 0.201 | 0.022 | +0.180 |
| felzenszwalb | 200 | 202 | 0.179 | 0.177 | 0.019 | +0.158 |
| felzenszwalb | 300 | 135 | 0.107 | 0.128 | 0.015 | +0.112 |
| felzenszwalb | 400 | 101 | 0.066 | 0.097 | 0.011 | +0.086 |
| felzenszwalb | 800 | 54 | 0.016 | 0.035 | 0.005 | +0.030 |
| SAM ViT-H true colour | 0.50/0.88 | 112 | 0.194 | 0.276 | 0.013 | +0.263 |
| SAM ViT-H true colour | 0.60/0.88 | 112 | 0.193 | 0.275 | 0.013 | +0.263 |
| SAM ViT-H true colour | 0.70/0.88 | 110 | 0.189 | 0.274 | 0.013 | +0.260 |
| SAM ViT-H true colour | 0.80/0.88 | 105 | 0.172 | 0.264 | 0.014 | +0.250 |
| SAM ViT-H true colour | 0.88/0.88 | 85 | 0.118 | 0.233 | 0.010 | +0.223 |
| SAM ViT-H false colour | 0.50/0.88 | 112 | 0.154 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H false colour | 0.60/0.88 | 112 | 0.154 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H false colour | 0.70/0.88 | 110 | 0.151 | 0.246 | 0.013 | +0.233 |
| SAM ViT-H false colour | 0.80/0.88 | 102 | 0.129 | 0.236 | 0.012 | +0.224 |
| SAM ViT-H false colour | 0.88/0.88 | 82 | 0.084 | 0.206 | 0.011 | +0.196 |

At FTW's budget of 18 objects per chip:

| method | recall at 18 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.222 | 0.005 | +0.217 | single setting |
| watershed | 0.081 | 0.003 | +0.078 | clamped, sweep stops at 26 objects |
| felzenszwalb | 0.035 | 0.005 | +0.030 | clamped, sweep stops at 54 objects |
| SAM ViT-H true colour | 0.233 | 0.010 | +0.223 | clamped, sweep stops at 85 objects |
| SAM ViT-H false colour | 0.206 | 0.011 | +0.196 | clamped, sweep stops at 82 objects |

Four of those five are clamped, so read them as ceilings. Each one is the value
at the coarsest setting that method was actually run at, and every method's
recall falls as its object count falls, so the value at 18 objects is below what
the column shows. SAM's 0.233 appears to edge past FTW's 0.222 while spending
85 objects per chip against 18, and watershed drops from 0.345 at 282 objects
to 0.081 at 26. FTW's win on Slovenia is therefore wider than this table can
say, and how much wider is not measurable without rerunning the other three
methods at coarser settings. That is B-08.

This is the control. FTW was trained on Slovenia with complete labels, and on
Slovenia it beats every untrained method at a fraction of the object budget.
Had it not, the scoring machinery would be the story rather than India.

---

## Reading the two together

Watershed appears to win Slovenia on the gap column, +0.325 against +0.217, and
that reading is wrong. It spends 282 objects per chip to FTW's 18. Gap over a
null rewards object count in the same direction the raw recall does, just less
steeply, which is why the budget column exists. That mistake was made here and
caught by Slovenia; see B-02.

Read at matched budget, the two countries invert:

| | Slovenia, 18 objects | India, 175 objects |
|---|---:|---:|
| FTW 3-class FULL | 0.222 | 0.027 |
| SAM ViT-H false colour | at most 0.206 | 0.153 |
| watershed | at most 0.081 | 0.107 |
| felzenszwalb | at most 0.035 | 0.031 |

The checkpoint beats everything on the country it trained on with complete
labels, and loses to a foundation model by 5.7 times and to an untrained
gradient by 4 times on India.

---

## Width bands

The same parcels binned by the pixel count across the largest inscribed circle,
in native 10 m pixels. SAM at threshold 0.50, classical methods at their best
setting, which is `h` 0.02 for India and 0.05 for Slovenia.

**India**

| width, native 10 m px | parcels | FTW | watershed | SAM true | SAM false |
|---|---:|---:|---:|---:|---:|
| under 2 | 196 | 0.00% | 1.02% | 0.51% | 1.02% |
| 2 to 3 | 245 | 0.41% | 4.90% | 2.04% | 0.82% |
| 3 to 4 | 503 | 0.20% | 17.10% | 6.56% | 7.16% |
| 4 to 5 | 364 | 1.10% | 29.95% | 11.81% | 15.38% |
| 5 to 7 | 347 | 3.75% | 48.41% | 25.07% | 26.80% |
| 7 to 10 | 202 | 6.44% | 40.59% | 38.12% | 44.06% |
| 10 and over | 126 | 17.46% | 23.02% | 50.79% | 50.79% |

**Slovenia**

| width, native 10 m px | parcels | FTW | watershed | SAM true | SAM false |
|---|---:|---:|---:|---:|---:|
| under 2 | 2,842 | 1.48% | 5.42% | 3.80% | 2.74% |
| 2 to 3 | 1,590 | 12.89% | 35.97% | 24.40% | 21.01% |
| 3 to 4 | 706 | 36.26% | 60.06% | 42.63% | 34.56% |
| 4 to 5 | 555 | 47.57% | 67.57% | 53.15% | 51.17% |
| 5 to 7 | 620 | 62.10% | 72.90% | 63.71% | 61.61% |
| 7 to 10 | 369 | 69.65% | 77.51% | 76.15% | 71.27% |
| 10 and over | 149 | 72.48% | 63.09% | 77.18% | 75.17% |

Four things in those tables.

**The floor is soft.** Below three native pixels on India, watershed finds 14 of
441 parcels, 3.17% against 30.74% above. SAM true finds 6 and FTW finds 1. A
tenfold collapse rather than a wall.

**The gap is widest in the middle.** At 4 to 5 pixels, where the median Indian
parcel sits, watershed manages 29.95% and FTW 1.10%. The checkpoint fails
hardest at the sizes that dominate Indian agriculture.

**Watershed turns over and SAM does not.** Watershed peaks at 48.41% in the 5
to 7 band and falls to 23.02% above 10. At 676 objects per chip its cells
average about 97 grid pixels, so a large parcel gets cut into several and none
reaches IoU 0.5. That is a property of a fixed cutting scale rather than a
statement about large fields, and Slovenia shows the same turn at the same
place, 77.51% falling to 63.09%. SAM's curve rises the whole way in both
countries.

**Above ten pixels on India, SAM is the best method by a wide margin.** 50.79%
against watershed's 23.02% and FTW's 17.46%. For an Indian project working on
large fields, a foundation model reading three channels beats the trained model
reading eight, and it beats the classical method that wins everywhere else in
the table. That is the one place in this study where a method is close to
usable on India.

---

## The same width band in both countries

The floor claim says the limit is the imagery. Both countries are Sentinel-2 at
10 m, so a parcel of a given physical width should be found at about the same
rate in each if that is true. It is not.

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| under 20 m | FTW 3-class FULL | 0/196, 0.00% | 42/2,842, 1.48% | not readable |
| 20 to 30 m | FTW 3-class FULL | 1/245, 0.41% | 205/1,590, 12.89% | 31.6x |
| 30 to 50 m | FTW 3-class FULL | 5/867, 0.58% | 520/1,261, 41.24% | 71.5x |
| 50 m up | FTW 3-class FULL | 48/675, 7.11% | 750/1,138, 65.91% | 9.3x |
| under 20 m | watershed | 2/196, 1.02% | 154/2,842, 5.42% | 5.3x |
| 20 to 30 m | watershed | 12/245, 4.90% | 572/1,590, 35.97% | 7.3x |
| 30 to 50 m | watershed | 195/867, 22.49% | 799/1,261, 63.36% | 2.8x |
| 50 m up | watershed | 279/675, 41.33% | 832/1,138, 73.11% | 1.8x |
| under 20 m | SAM ViT-H true | 1/196, 0.51% | 108/2,842, 3.80% | 7.4x |
| 20 to 30 m | SAM ViT-H true | 5/245, 2.04% | 388/1,590, 24.40% | 12.0x |
| 30 to 50 m | SAM ViT-H true | 76/867, 8.77% | 596/1,261, 47.26% | 5.4x |
| 50 m up | SAM ViT-H true | 228/675, 33.78% | 791/1,138, 69.51% | 2.1x |

Widths are in metres here rather than native pixels, because the two countries
sit on grids of different fineness. India's chips measure 6.067 m per grid
pixel and Slovenia's 4.139 m, both upsampled from the same 10 m source, so a
band cut in grid pixels covers a different physical size in each country. An
earlier version of this comparison made that mistake and it hid the effect
below by about half. See B-09.

Read the 30 to 50 m row. Those parcels are three to five native pixels wide,
which is at or above the floor. The checkpoint returns 0.58% on India and
41.24% on Slovenia for parcels of the same physical size in the same sensor.
Watershed and SAM show the same ordering, so it is not an artefact of any one
method.

---

## What this says

**Within India the floor is real and its cause is not established.** Every
method collapses below three native pixels, and the two that read the imagery
well elsewhere collapse there too. That is a solid description of Indian
parcels. Attributing it to the resolution of the imagery goes further than the
data supports, because the same imagery at the same physical parcel size
performs between two and seventy times better in Slovenia.

The leading candidate for the country difference is label geometry. India is
presence-only with five hand-drawn parcels per chip, Slovenia is a complete
cadastre, and IoU against a loosely drawn polygon is depressed whatever the
imagery shows. Parcel shape and cropping calendar are the other two candidates.
None of them is resolution, which is the point. Separating them needs the label
registration test described in `REVIEW.md`, which has not been run.

**Above the floor, the method is the lever.** Between three and ten native
pixels an untrained watershed finds between five and thirteen times as many
Indian parcels as the released checkpoint, and above ten pixels SAM finds three
times as many. Whatever is stopping FTW there is not a lack of signal.

**The advice that follows differs by parcel size.** For Indian ground where
fields are under about 30 m across, nothing in this study recovers them at a
usable rate and the honest answer is that the problem is open. For ground above
that, the model is the lever and the released checkpoint is leaving a great deal
on the table. For large fields specifically, SAM at 50.79% is the first result
in this project that a product could be built on.

---

## What this does not say

**That any of these is a usable method for India.** One parcel in six at FTW's
object budget is not a field map. These are measuring instruments for how much
signal is present, not products.

**That FTW is broken everywhere.** On Slovenia it beats every baseline at a
fifth of their object budget. The failure is specific to a country whose labels
are presence-only and whose parcels are small, and stage 2 could not tell those
two apart either.

**That SAM is doing field boundary delineation.** It is segmenting an image into
regions, some of which happen to coincide with fields. It sees three 8-bit
channels of one season against FTW's eight bands across two, and it has never
been shown a field. Its Indian result says something about how much structure
the imagery carries, rather than something about foundation models for
agriculture. Published work exists on SAM for field boundaries from Sentinel-2,
including FieldSeg at 10 m and a Canadian prairies dataset built this way, none
of which has been read here beyond its title.

**That width is the only thing that matters.** The district work in stage 3
found Jodhpur with the widest parcels in the Indian test set, 7.35 native
pixels median and none below the threshold, still at 0.048 recall. Boundary
contrast was measured afterwards to test the arid-ground explanation and the
measurement is in `results/<country>/parcel_contrast.csv`. It is not reported
here because the measure itself has not been validated against anything. See
Known gaps.

**That the Slovenian margin is quantified.** Four of the five figures at
Slovenia's object budget are clamped. See B-08.

---

## Corrections

**B-01. The first comparison had no control for object count.** Watershed at
651 objects per chip appeared to beat FTW before any null existed, and the
sweep's own shape gave it away: median IoU climbed monotonically with object
count, from 0.002 at nine objects per chip to 0.308 at 651. That is the metric
rewarding volume. Nothing was reported from that version.

**B-02. Gap over a null was treated as sufficient.** It is not, because a
method with more objects has more room above its null. Slovenia exposed this:
watershed led on gap, +0.325 against +0.217, while spending fifteen times the
objects, and at matched budget FTW won. The budget column was added afterwards
and is now what the comparison rests on.

**B-03. FTW's 500 square metre polygonize default was blamed for halving its
India recall.** It does not. Running with the filter disabled left recall at
0.027, identical. The claim was made from a plausible mechanism rather than a
measurement and was retracted the same day.

**B-04. The width floor was described as absolute.** Stage 2 said delineation
does not happen below three native pixels, which was true of FTW at 1 parcel in
441 and false of the imagery. Watershed finds 3.17% there. The floor is a
tenfold collapse and should be written as one.

**B-05. A diagnostic run overwrote the main India comparison table.** A run at
minimum size zero wrote to the same filenames as the main run, leaving that
directory with mixed provenance: FTW tables from one run, classical tables from
another. Caught by reading `git status` before committing rather than by
anything in the code. Output filenames now carry the minimum size.

**B-06. Three numbers in this document disagreed with the files they cited.**
Slovenia's watershed figure at FTW's budget read 0.170 where the generated
column says 0.081, a factor of 2.1. India's watershed read 0.100 against 0.107
and felzenszwalb 0.029 against 0.031. The Slovenian error has a traceable
cause: `np.interp` clamps below the edge of a sweep, so the budget figure comes
from the watershed 0.3 row at 26 objects, and the Slovenia table in this
document had that row missing. The figure was read off the truncated table
rather than the generated column. Every table here is now written by
`src\build_comparison.py` and no number in this document is typed by hand.

**B-07. This document said SAM had not been run after it had been run.** About
26 hours of CPU across both countries, five settings and two composites, sat in
`results/` while the open items still listed it as missing. Caught by the review
in `REVIEW.md`, not by anything in the workflow.

**B-08. The Slovenian comparison at matched budget is four bounds and one
measurement.** No competing method was run coarse enough to reach 18 objects per
chip. The clamped figures are each method's value at its own coarsest setting,
which is above 18 in every case, so each overstates that method. FTW's Slovenian
win is wider than the table shows and the margin is not measurable from what has
been run.

**B-09. Cross-country width bands were cut in grid pixels.** India's grid is
6.067 m and Slovenia's 4.139 m, so a band of five grid pixels means 30.3 m in
one country and 20.7 m in the other. Comparing India's 21 m median parcels
against Slovenia's 12 m ones and calling the bands matched hid about half of the
country difference. Cross-country bands are now cut in metres.

**B-10. Slovenian chips were described as holding about 32 parcels.** 6,831
parcels across 185 labelled chips is about 37.

**B-11. The null ran at three draws where the gap needed more.** FTW's Indian
null read 0.022 from three draws and 0.0209 from two hundred, which moved the
gap from +0.005 to +0.0063. Three draws was never enough to separate those,
since the null's own standard deviation at that setting is 0.0030. The sweep
still runs three draws, because everywhere else the gap is thirty times that
spread; the one row that needed more is remeasured on its own.

**B-12. Every published interval assumed parcels were independent.** They sit
about 5 to a chip in India and 37 in Slovenia, sharing the scene, the season,
the cloud state and the annotator, so the effective sample size is nearer the
chip count than the parcel count. Clopper-Pearson on parcels gave FTW's
Slovenian recall as [21.23, 23.21] where resampling chips gives [18.55, 25.87].
No conclusion in this document turns on it, since the differences it reports
are five-fold and larger, and every interval was still too narrow.

---

## Known gaps

These come from the review in `REVIEW.md` and they change how the numbers above
should be read. The full list of 21 findings is in that document.

**The null at three draws, now measured at 200.** Closed. FTW's Indian gap is
+0.0063 against a null whose standard deviation is 0.0030, and 3 draws in 200
of random cells beat the checkpoint outright. The direction holds and the
magnitude is now known. Run `src\null_strength.py` to reproduce it.

**Intervals treated parcels as independent, now measured by chip.** Closed, and
the correction is larger than expected. Resampling whole chips rather than
parcels widens FTW's Slovenian interval from [21.23, 23.21] to
[18.55, 25.87], which is 3.69 times wider, and its Indian interval from
[2.05, 3.54] to [1.71, 3.88], 1.45 times wider. Slovenia suffers more because
it carries about 37 parcels per chip against India's 5, so its parcels repeat
each other more. Every interval this project has published should be read at
the chip-level width. Run `src\bootstrap_ci.py` to reproduce it. Width bands
holding fewer than ten found parcels fall back to the parcel-level interval,
because a bootstrap over chips cannot resolve a tail it almost never samples.

**Every reported setting is the best of its own sweep**, chosen on the same
parcels the result is quoted from. There is no held-out split in this project.

**Precision is not measured on India.** Every Indian figure here is recall.
The null and the budget column bound over-segmentation indirectly, and neither
is a precision measurement.

**Boundary contrast is unvalidated**, which is why the Jodhpur question stays
open rather than being answered with the numbers already computed.

**The measured grid has not been reconciled with FTW's published
specification.** 6.067 m and 4.139 m are measured geodesically from the chips.
If that measurement is wrong then every normalised width in three documents is
wrong with it.

---

## Reproducing

Open data throughout. Field labels and imagery from Fields of The World under
CC BY 4.0, the FTW released checkpoints, and the Meta SAM checkpoint under
Apache 2.0. District polygons from geoBoundaries under CC BY 4.0.

```
python src\compare_segmenters.py --country india
python src\compare_segmenters.py --country slovenia
python src\sam_run.py --country india --model vit_h
python src\sam_run.py --country slovenia --model vit_h
python src\build_comparison.py
python src\null_strength.py --country india --method ftw --draws 200
python src\bootstrap_ci.py --country india --by-width
python src\bootstrap_ci.py --country slovenia --by-width
python src\check_tables.py
python src\figure_budget.py
python src\threshold_check.py --country india --width-file parcel_width_seg_watershed_min500.csv
python src\threshold_check.py --country india --width-file parcel_width_seg_ftw_min500.csv
python src\reconcile_ftw.py --country india
```

The nulls are seeded, so the comparison runs reproduce to the digit. Runtime on
a CPU-only machine is about 27 minutes for India and 25 for Slovenia on the
classical sweep. SAM is about 16 hours for India and 10 for Slovenia across both
composites, at roughly 75 seconds per chip per composite, and `sam_run.py`
appends as it goes so an interrupted run resumes. `build_comparison.py` takes
seconds and reads only the CSVs.

Outputs land in `results/<country>/`:

| file | what it holds |
|---|---|
| `segmenter_comparison_min500.csv` | one row per classical method and setting |
| `sam_comparison_vit_h_min500.csv` | one row per SAM composite and setting |
| `sam_raw_vit_h_p32_min500.csv` | per-chip SAM output, the resume log |
| `score_parcels_seg_<method>_min500.csv` | per-parcel IoU |
| `parcel_width_seg_<method>_min500.csv` | the same with the width column |
| `parcel_contrast.csv` | per-parcel boundary contrast, unvalidated |
| `null_draws_ftw.csv` | every null draw behind finding 3 |
| `scorer_reconciliation.csv` | truth and prediction combinations, for S-08 |
| `probe/` | the 5-chip ViT-B timing probe that chose ViT-H |

Filenames carrying a setting, such as `parcel_width_seg_watershed_0p02_min500.csv`,
are the ones to cite. The short forms without a setting hold whichever setting
scored best, which is `h` 0.02 for India and 0.05 for Slovenia on watershed and
`scale` 100 for felzenszwalb in both. `build_comparison.py` prints that mapping
on every run.

The generated tables are written to `results/comparison_tables.md`. If a number
in this document disagrees with that file, this document is wrong.
`check_tables.py` enforces that: it pulls every number out of every table here
and fails if one of them appears in no generated table. Run it before any commit
that touches this document.
