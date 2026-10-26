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

Every FTW figure up to finding 17 is for FTW's v1 checkpoint of October 2024,
the one stage 2 ran. FTW has released three more since then, and v3 does much
better on India. Findings 18 and 19 run the later releases and read watershed
and SAM against them, and the README's headline now uses v3 (B-24). Finding 21
fine-tunes v3 B7 on India's own train chips.

---

## Findings

1. On India, three methods that were never trained on anything beat the trained
   checkpoint at a matched object budget. SAM reaches 0.158, watershed 0.107,
   felzenszwalb 0.031, against FTW's 0.027. SAM's figure is on colour
   infrared; on natural colour it reaches 0.152. Its first run, on
   inputs that were not the composites intended, gave 0.153 and 0.151; see
   B-23.
2. On Slovenia the checkpoint wins and wins economically. It reaches 0.222 from
   20 objects per chip. Watershed, rerun coarse enough to be read at that
   budget, reaches 0.059. Felzenszwalb and SAM were not, so their figures there
   are upper bounds rather than measurements. See B-08.
3. FTW's Indian output barely clears its own null, measured properly. At 200
   draws rather than three, random Voronoi cells of the same count average
   0.0209 against the checkpoint's 0.0272. Three draws in 200 reached it, two
   above and one level, and the best reached 0.0308, above the trained model, on cells that never
   saw the imagery. The gap is +0.0063, about twelve parcels in 1,983, and it
   clears the null at roughly one draw in seventy. Real, and small enough that
   the three-draw version in the table below could not have established it.
4. The checkpoint does not shatter Indian parcels, it misses them. It emits
   175 objects per chip into scenes holding five labelled parcels, and 74.4%
   of those parcels have no predicted object touching them at all. Watershed,
   at 676 objects per chip, touches every one and cuts 38.2% into five pieces
   or more. Two opposite failures that this document described as one until
   the objects were counted. See B-16.
5. SAM spends about the same budget as the checkpoint and puts it in the
   right places. On the first 100 test chips, 494 parcels, SAM on colour
   infrared emits 196 objects per chip against FTW's 175 and has an object
   over 89.9% of the parcels where FTW reaches 24.7%. It leaves 30.0% covered
   by exactly one object, against FTW's 18.2% and watershed's 7.1%. Since one
   object covering one parcel is the precondition for a good IoU, this is
   where its recall advantage comes from. Reaching a parcel means an object
   overlaps it, short of finding it at IoU 0.5. The first run, on the wrong
   bands (B-23), gave 91.3% and 33.0%.
6. Watershed clears its null across the entire sweep, from 40 objects per chip
   to 917, with a gap running +0.018 to +0.196 that never reaches zero. A
   margin that survives a twentyfold range of settings is not a parameter
   fluke.
7. The floor at three native pixels is soft. Watershed finds 14 of 441 parcels
   below it, 3.17% against 30.74% above. SAM finds 5 on natural colour and 6
   on colour infrared. FTW finds 1. Parcels that
   narrow are recoverable about a tenth as often, rather than never.
8. Above ten native pixels on India the ordering changes again. SAM finds
   50.79% of those parcels, watershed 23.02% and FTW 17.46%. For large Indian
   fields a foundation model with three channels beats the trained model with
   eight by nearly three times.
9. The floor is not explained by parcel width. At matched ground width, in the
   same sensor and by the same method, Slovenian parcels are found between 1.7
   and 41.0 times more often than Indian ones of the same size. Whatever
   separates the two countries is not resolution. See What this says.
10. Everything here is still poor in absolute terms. One parcel in six at FTW's
   object budget is not a usable field map for India.
11. On Slovenia, where the cadastre is complete and precision is therefore
    measurable, the checkpoint is right 42.1% of the time from 20 objects per
    chip and watershed 4.4% of the time from 291. Nine and a half times, and
    the clearest evidence here that FTW is a good model failing on India
    rather than a weak model everywhere.
12. Label geometry does not explain the country gap. Measured against the image
    gradient on rings cut in metres, Indian and Slovenian labels are displaced
    by +4.13 m and +3.80 m. In the widest band India's labels are the better
    placed of the two, +1.81 m against +2.23 m, and India is still found 8.3
    times less often. Below that India's labels are worse by 1.4 to 1.7 times
    while the recall gap runs 19 to 41 times, which a difference of a few
    metres cannot produce. The explanation this document carried through three
    versions is wrong. See B-15.
13. Indian labelled boundaries carry a weaker gradient than Slovenian ones.
    Against each parcel's own interior, so that no chip statistic enters, the
    gradient on the Indian line runs 1.297x the gradient inside the field
    against Slovenia's 1.588x, and on 14.2% of Indian parcels it is no higher
    than inside against 7.2% in Slovenia. The gap widens with parcel size
    instead of narrowing. Blind checks against two people agree with it
    weakly and above chance, a rank score of 0.742 with p = 0.0004 for the
    second over 60 parcels, short of the 0.75 set beforehand. So this is a
    difference between countries in how sharp the drawn edge is. It does not say which parcels have an edge a person can see.
14. Choosing each method's setting on the data it is reported from was worth
    almost nothing. Over 40 chip-level splits per country, picking on one half
    and reading on the other moves recall by between -0.002 and +0.007, and
    eleven of the twelve method and country pairs choose the same setting in
    every split.
15. Parcel shape does not explain the country gap. Slovenian parcels are more
    strip-like than Indian ones, but giving Slovenia India's mix of widths and
    shapes moves FTW's ratio only from 11.52 to 10.66 times, 3% of the gap on a
    log scale. For watershed and SAM India's compact parcels are the easier
    mix. See What this says.
16. The seasonal windows are a part of the Indian failure, and a small part.
    FTW's second Indian image is from March to June, the dry months after the
    rabi harvest. Given the kharif image twice in its place, the checkpoint
    finds 4.79% of Indian parcels against 2.72%; given only the dry-season
    image, 1.01%, no better than chance. In Slovenia every change to the
    windows costs recall. The best arrangement still leaves India 4.6 times
    below Slovenia. See What this says.
17. An image from December to February, when rabi crops stand, does not
    rescue the checkpoint. Put in place of the dry-season image it helps by
    about as much as a second copy of the kharif image does, and no more, in
    both rabi seasons tested. Given the rabi image alone, FTW does no better
    than as shipped, while watershed finds about as many boundaries in it as in
    the kharif image. The best arrangement leaves FTW about four times below
    Slovenia. See What this says.
18. FTW's later checkpoints do much better on India, and the gap to Slovenia
    narrows without closing. v3, released in November 2025 with a new loss,
    new class weights and more augmentation, finds 12.91% of Indian parcels
    with an EfficientNet-B7 encoder and 10.29% with B3, against v1's 2.72%.
    Nearly all of the gain is above its null, so it comes from better placed
    boundaries. It does better on Slovenia too, 33.06% against 22.22%, and
    India rises from 0.12 to 0.39 of Slovenia with the same checkpoint. The
    gain is on parcels 30 m and wider; below that every checkpoint stays near
    1%. v2 is worse than v1 in both countries. See What this says.
19. Watershed and SAM still beat FTW on India at its own object count, by
    less. Against v3 B7 at 245 objects per chip, watershed reaches 14.83%, 1.92
    points ahead, and SAM on colour infrared 18.31% from 222 objects, 5.40
    ahead. Against v1 the margins were 8.01 and 13.05. On Slovenia v3 B7 beats
    every SAM composite while drawing about a quarter of their objects, where
    v1 was level with SAM. See What this says.
20. Weak edges are enough to explain most of the gap, in a test on Slovenia.
    Blurring Slovenian chips until their labelled edges measure like India's
    closes 0.585 of FTW v3 B7's gap to India on parcels 20 m and wider, and
    0.581 of watershed's read at its unblurred object count. The rules for
    reading it were committed before it ran. It shows these methods depend on
    edge contrast enough to explain most of the gap. Blur also softens texture
    inside fields, and the edge measure it is calibrated on agrees only weakly
    with two people's eyes. See What this says.
21. Fine-tuning v3 B7 on India's own train chips helps India a little and
    costs Slovenia. Trained on India alone, it finds 15.13% of Indian test
    parcels against v3's 12.91%, from 108.8 objects per chip against 245.3,
    and at that count it beats watershed and draws level with SAM, which
    reverses finding 19 for this model. Slovenia falls from 33.06% to 19.48%.
    Trained on India with Slovenian chips mixed in, Slovenia holds and India
    gains nothing measurable. The recipe and the rules for reading it were
    committed before training. See What this says.

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
produces. Two composites were meant to be run, because choosing whichever
three bands flattered the argument would stack the deck: true colour, which is
what a person would look at, and false colour, which puts the near infrared
where vegetation contrast lives. Neither is what SAM received. FTW stores each
window as red, green, blue and near infrared, and the code assumed blue came
first. The run called true colour gave SAM blue, green and red in its red,
green and blue channels, and the run called false colour gave it near infrared,
blue and green. Both intended composites have since been run as well. The
tables carry all four, each labelled by what SAM was given; see B-23. The
checkpoint is Apache 2.0.

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

An object is a distinct label left in a chip after the minimum size filter
below, and objects per chip is the mean of that count over chips.
`object_count` counts the labels present instead of taking the highest label,
because the filter deletes labels and leaves gaps in the numbering, so the
highest label overstates the count by however many were dropped.

`figures/recall_by_object_budget.png` draws this control for both countries.
Interpolation clamps when the budget falls outside a method's sweep, and a
clamped figure is a bound rather than a measurement. Every table below carries
a column saying which happened. All six Indian figures beside FTW's own are
interpolated. All six Slovenian ones are clamped in the main table; watershed
has since been measured at 0.059 with its sweep extended, so five remain
bounds, felzenszwalb and the four SAM composites.

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
| SAM ViT-H natural colour | 0.50/0.88 | 195 | 0.089 | 0.167 | 0.020 | +0.147 |
| SAM ViT-H natural colour | 0.60/0.88 | 194 | 0.089 | 0.166 | 0.021 | +0.145 |
| SAM ViT-H natural colour | 0.70/0.88 | 190 | 0.085 | 0.164 | 0.018 | +0.146 |
| SAM ViT-H natural colour | 0.80/0.88 | 176 | 0.056 | 0.152 | 0.018 | +0.135 |
| SAM ViT-H natural colour | 0.88/0.88 | 135 | 0.010 | 0.130 | 0.012 | +0.117 |
| SAM ViT-H colour infrared | 0.50/0.88 | 222 | 0.149 | 0.183 | 0.028 | +0.155 |
| SAM ViT-H colour infrared | 0.60/0.88 | 222 | 0.148 | 0.183 | 0.026 | +0.157 |
| SAM ViT-H colour infrared | 0.70/0.88 | 218 | 0.144 | 0.181 | 0.019 | +0.162 |
| SAM ViT-H colour infrared | 0.80/0.88 | 201 | 0.123 | 0.174 | 0.022 | +0.152 |
| SAM ViT-H colour infrared | 0.88/0.88 | 155 | 0.055 | 0.145 | 0.017 | +0.128 |
| SAM ViT-H, blue-green-red | 0.50/0.88 | 184 | 0.051 | 0.156 | 0.019 | +0.137 |
| SAM ViT-H, blue-green-red | 0.60/0.88 | 184 | 0.051 | 0.156 | 0.022 | +0.134 |
| SAM ViT-H, blue-green-red | 0.70/0.88 | 180 | 0.043 | 0.155 | 0.018 | +0.136 |
| SAM ViT-H, blue-green-red | 0.80/0.88 | 167 | 0.023 | 0.146 | 0.015 | +0.131 |
| SAM ViT-H, blue-green-red | 0.88/0.88 | 129 | 0.008 | 0.121 | 0.012 | +0.110 |
| SAM ViT-H, NIR-blue-green | 0.50/0.88 | 213 | 0.127 | 0.172 | 0.021 | +0.151 |
| SAM ViT-H, NIR-blue-green | 0.60/0.88 | 212 | 0.127 | 0.172 | 0.025 | +0.147 |
| SAM ViT-H, NIR-blue-green | 0.70/0.88 | 208 | 0.118 | 0.170 | 0.023 | +0.147 |
| SAM ViT-H, NIR-blue-green | 0.80/0.88 | 192 | 0.103 | 0.162 | 0.021 | +0.142 |
| SAM ViT-H, NIR-blue-green | 0.88/0.88 | 147 | 0.038 | 0.139 | 0.015 | +0.123 |

At FTW's budget of 175 objects per chip:

| method | recall at 175 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.027 | 0.022 | +0.005 | single setting |
| watershed | 0.107 | 0.017 | +0.091 | interpolated |
| felzenszwalb | 0.031 | 0.016 | +0.015 | interpolated |
| SAM ViT-H natural colour | 0.152 | 0.017 | +0.134 | interpolated |
| SAM ViT-H colour infrared | 0.158 | 0.019 | +0.138 | interpolated |
| SAM ViT-H, blue-green-red | 0.151 | 0.017 | +0.134 | interpolated |
| SAM ViT-H, NIR-blue-green | 0.153 | 0.019 | +0.135 | interpolated |

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
similar. 6,831 parcels, on grid pixels 4.138 m across and 6.002 m tall
(B-18), about 37 parcels per chip.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 20 | 0.000 | 0.222 | 0.007 | +0.215 |
| watershed | 0.005 | 785 | 0.311 | 0.209 | 0.025 | +0.184 |
| watershed | 0.01 | 672 | 0.333 | 0.248 | 0.025 | +0.223 |
| watershed | 0.02 | 521 | 0.360 | 0.297 | 0.024 | +0.273 |
| watershed | 0.05 | 291 | 0.360 | 0.348 | 0.020 | +0.328 |
| watershed | 0.08 | 184 | 0.307 | 0.331 | 0.016 | +0.315 |
| watershed | 0.1 | 143 | 0.258 | 0.307 | 0.015 | +0.292 |
| watershed | 0.13 | 102 | 0.194 | 0.259 | 0.012 | +0.246 |
| watershed | 0.16 | 77 | 0.151 | 0.219 | 0.009 | +0.210 |
| watershed | 0.2 | 55 | 0.104 | 0.171 | 0.006 | +0.165 |
| watershed | 0.3 | 26 | 0.031 | 0.081 | 0.003 | +0.078 |
| felzenszwalb | 25 | 902 | 0.217 | 0.035 | 0.024 | +0.011 |
| felzenszwalb | 50 | 762 | 0.295 | 0.116 | 0.025 | +0.091 |
| felzenszwalb | 100 | 462 | 0.305 | 0.214 | 0.022 | +0.192 |
| felzenszwalb | 150 | 314 | 0.243 | 0.203 | 0.024 | +0.180 |
| felzenszwalb | 200 | 234 | 0.181 | 0.178 | 0.020 | +0.158 |
| felzenszwalb | 300 | 156 | 0.109 | 0.129 | 0.015 | +0.114 |
| felzenszwalb | 400 | 118 | 0.066 | 0.098 | 0.013 | +0.085 |
| felzenszwalb | 800 | 65 | 0.017 | 0.037 | 0.006 | +0.030 |
| SAM ViT-H natural colour | 0.50/0.88 | 113 | 0.233 | 0.295 | 0.013 | +0.282 |
| SAM ViT-H natural colour | 0.60/0.88 | 113 | 0.232 | 0.295 | 0.014 | +0.281 |
| SAM ViT-H natural colour | 0.70/0.88 | 112 | 0.231 | 0.295 | 0.015 | +0.280 |
| SAM ViT-H natural colour | 0.80/0.88 | 106 | 0.209 | 0.286 | 0.013 | +0.272 |
| SAM ViT-H natural colour | 0.88/0.88 | 86 | 0.157 | 0.257 | 0.013 | +0.244 |
| SAM ViT-H colour infrared | 0.50/0.88 | 102 | 0.170 | 0.259 | 0.012 | +0.247 |
| SAM ViT-H colour infrared | 0.60/0.88 | 101 | 0.169 | 0.259 | 0.013 | +0.246 |
| SAM ViT-H colour infrared | 0.70/0.88 | 99 | 0.166 | 0.257 | 0.012 | +0.245 |
| SAM ViT-H colour infrared | 0.80/0.88 | 92 | 0.143 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H colour infrared | 0.88/0.88 | 74 | 0.097 | 0.212 | 0.011 | +0.201 |
| SAM ViT-H, blue-green-red | 0.50/0.88 | 103 | 0.194 | 0.276 | 0.013 | +0.264 |
| SAM ViT-H, blue-green-red | 0.60/0.88 | 103 | 0.194 | 0.276 | 0.014 | +0.262 |
| SAM ViT-H, blue-green-red | 0.70/0.88 | 102 | 0.190 | 0.274 | 0.012 | +0.262 |
| SAM ViT-H, blue-green-red | 0.80/0.88 | 96 | 0.173 | 0.264 | 0.012 | +0.252 |
| SAM ViT-H, blue-green-red | 0.88/0.88 | 79 | 0.119 | 0.234 | 0.010 | +0.224 |
| SAM ViT-H, NIR-blue-green | 0.50/0.88 | 101 | 0.155 | 0.249 | 0.014 | +0.235 |
| SAM ViT-H, NIR-blue-green | 0.60/0.88 | 100 | 0.155 | 0.248 | 0.012 | +0.237 |
| SAM ViT-H, NIR-blue-green | 0.70/0.88 | 99 | 0.151 | 0.246 | 0.013 | +0.234 |
| SAM ViT-H, NIR-blue-green | 0.80/0.88 | 92 | 0.130 | 0.236 | 0.013 | +0.223 |
| SAM ViT-H, NIR-blue-green | 0.88/0.88 | 73 | 0.085 | 0.206 | 0.010 | +0.196 |

At FTW's budget of 20 objects per chip:

| method | recall at 20 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.222 | 0.007 | +0.215 | single setting |
| watershed | 0.081 | 0.003 | +0.078 | clamped, sweep stops at 26 objects |
| felzenszwalb | 0.037 | 0.006 | +0.030 | clamped, sweep stops at 65 objects |
| SAM ViT-H natural colour | 0.257 | 0.013 | +0.244 | clamped, sweep stops at 86 objects |
| SAM ViT-H colour infrared | 0.212 | 0.011 | +0.201 | clamped, sweep stops at 74 objects |
| SAM ViT-H, blue-green-red | 0.234 | 0.010 | +0.224 | clamped, sweep stops at 79 objects |
| SAM ViT-H, NIR-blue-green | 0.206 | 0.010 | +0.196 | clamped, sweep stops at 73 objects |

Every row but FTW's is clamped, so read them as ceilings. Each one is the value
at the coarsest setting that method was actually run at, and every method's
recall falls as its object count falls, so the value at 20 objects is below what
the column shows. SAM on natural colour appears to edge past FTW's 0.222 with
0.257 while spending 86 objects per chip against 20, and watershed drops from
0.348 at 291 objects to 0.081 at 26. FTW's win on Slovenia is therefore wider
than this table can say, and how much wider is not measurable without rerunning
the other methods at coarser settings. That is B-08.

Watershed has since been run coarse enough. `src\season_test.py` extends its
sweep to h 0.6, which comes down to 2.5 objects per chip, and on the way it
reproduces all ten published settings exactly. Read at FTW's budget:

| method | recall at 20 objects/chip | how |
|---|---:|---|
| watershed | 0.059 | interpolated, sweep extended to h 0.6 in `season_test.py` |

That is a measurement where the table above has a ceiling of 0.081, and it
puts FTW 3.7 times ahead of watershed in Slovenia at the same object count.
Felzenszwalb and SAM remain ceilings.

This is the control. FTW was trained on Slovenia with complete labels, and on
Slovenia it beats every untrained method at a fraction of the object budget.
Had it not, the scoring machinery would be the story rather than India.

---

## Reading the two together

Watershed appears to win Slovenia on the gap column, +0.328 against +0.215, and
that reading is wrong. It spends 291 objects per chip to FTW's 20. Gap over a
null rewards object count in the same direction the raw recall does, just less
steeply, which is why the budget column exists. That mistake was made here and
caught by Slovenia; see B-02.

Read at matched budget, the two countries invert:

| | Slovenia, 20 objects | India, 175 objects |
|---|---:|---:|
| FTW 3-class FULL | 0.222 | 0.027 |
| SAM ViT-H colour infrared | at most 0.212 | 0.158 |
| watershed | 0.059 | 0.107 |
| felzenszwalb | at most 0.037 | 0.031 |

The checkpoint beats everything on the country it trained on with complete
labels, and loses to a foundation model by 5.8 times and to an untrained
gradient by 4 times on India.

---

## Width bands

The same parcels binned by the pixel count across the largest inscribed circle,
in native 10 m pixels. SAM at threshold 0.50, classical methods at their best
setting, which is `h` 0.02 for India and 0.05 for Slovenia.

**India**

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 2 | 196 | 0.00% | 1.02% | 0.51% | 1.02% | 0.51% | 1.02% |
| 2 to 3 | 245 | 0.41% | 4.90% | 1.63% | 1.63% | 2.04% | 0.82% |
| 3 to 4 | 503 | 0.20% | 17.10% | 6.96% | 7.75% | 6.56% | 7.16% |
| 4 to 5 | 364 | 1.10% | 29.95% | 12.36% | 15.38% | 11.81% | 15.38% |
| 5 to 7 | 347 | 3.75% | 48.41% | 27.38% | 29.39% | 25.07% | 26.80% |
| 7 to 10 | 202 | 6.44% | 40.59% | 43.07% | 46.53% | 38.12% | 44.06% |
| 10 and over | 126 | 17.46% | 23.02% | 50.79% | 52.38% | 50.79% | 50.79% |

**Slovenia**

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 2 | 2,163 | 0.51% | 3.74% | 2.82% | 1.90% | 2.64% | 1.62% |
| 2 to 3 | 1,229 | 7.89% | 21.32% | 15.62% | 11.96% | 14.56% | 12.12% |
| 3 to 4 | 1,193 | 18.86% | 42.92% | 29.76% | 25.31% | 27.75% | 24.14% |
| 4 to 5 | 547 | 34.00% | 57.95% | 44.79% | 38.94% | 41.32% | 35.65% |
| 5 to 7 | 827 | 48.49% | 68.80% | 59.73% | 52.24% | 55.86% | 50.67% |
| 7 to 10 | 553 | 66.18% | 75.23% | 74.86% | 70.71% | 69.80% | 67.09% |
| 10 and over | 319 | 72.73% | 69.91% | 80.56% | 76.80% | 77.12% | 75.55% |

Four things in those tables.

**The floor is soft.** Below three native pixels on India, watershed finds 14 of
441 parcels, 3.17% against 30.74% above. SAM finds 5 on natural colour and 6
on colour infrared, and FTW finds 1. A
tenfold collapse rather than a wall.

**The gap is widest in the middle.** At 4 to 5 pixels, where the median Indian
parcel sits, watershed manages 29.95% and FTW 1.10%. The checkpoint fails
hardest at the sizes that dominate Indian agriculture.

**Watershed turns over and SAM does not.** Watershed peaks at 48.41% in the 5
to 7 band and falls to 23.02% above 10. At 676 objects per chip its cells
average about 97 grid pixels, so a large parcel gets cut into several and none
reaches IoU 0.5. That is a property of a fixed cutting scale rather than a
statement about large fields, and Slovenia shows the same turn at the same
place, 75.23% falling to 69.91%. SAM's curve rises the whole way in both
countries.

**Above ten pixels on India, SAM is the best method by a wide margin.** 50.79%
against watershed's 23.02% and FTW's 17.46%. For an Indian project working on
large fields, a foundation model reading three channels beats the trained model
reading eight, and it beats the classical method that wins everywhere else in
the table. That is the one place in this study where a method is close to
usable on India.

---

## What the methods emit

Recall says what a method finds. It says nothing about what it invents, which
is F-10 in `REVIEW.md` and was open until now.

Ordinary precision is not computable on India, and saying so is half the
answer. Five parcels per chip are drawn and 98.96% of each chip was never
labelled, so an object over unlabelled ground may be a perfectly good field
nobody recorded. Two things are computable.

**Fragmentation**, which works in both countries: how many predicted objects
overlap one labelled parcel. A method that cuts one field into ten pieces
shows it here whatever the labelling.

| on India, all 1,983 parcels | objects/chip | parcels with no object | covered by exactly one | cut into 5 or more |
|---|---:|---:|---:|---:|
| FTW 3-class FULL | 175.0 | 74.4% | 18.9% | 0.3% |
| watershed 0.02 | 675.9 | 0.0% | 7.2% | 38.2% |

SAM costs 75 seconds per chip to regenerate, so it was measured on the first
100 test chips rather than all 399, 99 of which carry labels. Those chips run
slightly small, a median parcel
of 6.21 grid pixels against 7.00 across the country, so the three methods are
compared below on the same 494 parcels rather than against the full-set figures
above.

| on the same 494 parcels | objects/chip | parcels with no object | covered by exactly one | cut into 5 or more |
|---|---:|---:|---:|---:|
| FTW 3-class FULL | 175.0 | 75.3% | 18.2% | 0.0% |
| **SAM ViT-H colour infrared 0.50** | **195.6** | **10.1%** | **30.0%** | **8.9%** |
| SAM ViT-H NIR-blue-green 0.50, first run | 190.4 | 8.7% | 33.0% | 8.5% |
| watershed 0.02 | 675.9 | 0.0% | 7.1% | 30.8% |

The SAM rows are the most useful thing in this section. On colour infrared,
the input intended, SAM spends close to the checkpoint's budget, 196 objects
per chip against 175, and puts at least one object over 89.9% of these
parcels where the checkpoint reaches 24.7%. Reaching a parcel means an object
overlaps it, which is short of finding it at IoU 0.5. SAM also leaves 30.0%
covered by exactly one object, the precondition for clearing IoU 0.5, against
FTW's 18.2% and watershed's 7.1%. Its recall advantage on India comes from
where it puts its objects, since it emits about as many as FTW. The first
run's near infrared, blue and green (B-23) gave 91.3% and 33.0%, so the input
error moved these by 1.4 and 3.0 points and left the reading as it was.
Across all 1,983 Indian parcels, the checkpoint reaches 25.6% and leaves
74.4% untouched, as in the first table.

| on Slovenia | objects/chip | parcels with no object | covered by exactly one | cut into 5 or more |
|---|---:|---:|---:|---:|
| FTW 3-class FULL | 19.5 | 53.3% | 39.4% | 0.1% |
| watershed 0.05 | 290.7 | 0.0% | 12.3% | 28.5% |

These are opposite failures. The checkpoint emits 175 objects into an Indian
chip and three quarters of the labelled parcels there receive nothing at all,
so its objects are somewhere other than the fields. Watershed reaches every
parcel and shreds four in ten. A write-up that calls both of them
over-segmentation is describing one of them wrongly, which is B-16.

The 500 square metre filter is not what causes the misses. Run with no filter
at all, FTW emits 292 objects per chip instead of 175 and still leaves 62.3%
of parcels untouched. About a sixth of the misses are the filter deleting
fragments the model did find, and five sixths are the model finding nothing.
The matched object count stays at exactly 54 either way, so none of the 46,679
sub-threshold objects would have scored: FTW's polygonize default is deleting
only junk. Both counts are rows of `precision_summary.csv`, 116,335 objects
without the filter and 69,656 with it, over the 398 chips that carry labels.
The 62.3% is `precision_ftw_min0.csv`.

**Matched object share**, which is precision on Slovenia and a floor on India.
It is a different figure from the 0.240 object precision in `RESULTS.md`,
though both count the same 1,518 matched objects. That one divides by all
6,322 connected components FTW emits over the 228 Slovenian test chips, with
no size filter; this one by the 3,609 objects left after the 500 m² filter on
the 185 chips that carry labels.

| method | India, floor | Slovenia, precision |
|---|---:|---:|
| FTW 3-class FULL | 0.08% | **42.06%** |
| SAM ViT-H colour infrared 0.50 | 0.41% | not measured |
| SAM ViT-H NIR-blue-green 0.50, first run | 0.42% | not measured |
| watershed | 0.18% | 4.43% |

Read the Slovenian column. The checkpoint is right about 42% of the time while
emitting 20 objects per chip, and watershed is right 4.4% of the time while
emitting 291. Recall alone had watershed within striking distance of FTW on
that country; precision puts a factor of nine and a half between them. This is the
strongest evidence in the project that FTW is a good model failing on India
rather than a weak model everywhere, and it took measuring what the methods
invent to see it.

The Indian column compares methods against each other and nothing else. Both
numbers are floors, and they are low because 98.96% of the chip carries no
label to match against.

*Source: `precision_<method>_min500.csv` in each country, written by
`src\precision.py`.*

---

## Were the settings fitted to the data they are reported on

Every figure in this document comes from the best setting of a sweep, chosen
on the same parcels it is then quoted from. That is F-07, and the size of the
resulting optimism had never been measured.

It is now, and it is small. Chips are shuffled and cut in half, the best
setting is chosen on one half and read on the other, forty times per country.

| method | India optimism | India setting | Slovenia optimism | Slovenia setting |
|---|---:|---|---:|---|
| watershed | +0.0016 | 0.02 in 62% of splits | -0.0016 | 0.05 in 100% |
| felzenszwalb | -0.0005 | 100 in 100% | +0.0001 | 100 in 100% |
| SAM ViT-H blue-green-red | -0.0011 | 0.50 in 100% | +0.0045 | 0.50 in 100% |
| SAM ViT-H NIR-blue-green | -0.0012 | 0.50 in 100% | +0.0066 | 0.50 in 100% |
| SAM ViT-H natural colour | +0.0004 | 0.50 in 100% | +0.0020 | 0.50 in 100% |
| SAM ViT-H colour infrared | -0.0015 | 0.50 in 100% | -0.0019 | 0.50 in 100% |

The largest optimism anywhere is +0.0066 on a recall of 0.249, about 2.7%
relative, and every figure in the table sits well inside the chip-level
intervals in Known gaps. Eleven of the twelve pairs pick the identical setting
in every single split, so the parameter was never free enough to fit. India's
watershed at 62% is the one near-tie, between h of 0.02 and its neighbours,
and the published and held-out values differ by 0.0016 regardless.

Two limits on that. It tests selection among settings within a sweep, so the
choices fixed by convention rather than tuned, IoU 0.5 and the 500 square metre
filter and which composites to run, are not covered. And it tests raw recall at
the chosen setting rather than the budget-matched column, which interpolates
across settings and so selects differently.

*Source: `holdout_selection.csv` in each country, written by
`src\holdout.py`.*

---

## The same width band in both countries

The floor claim says the limit is the imagery. Both countries are Sentinel-2 at
10 m, so a parcel of a given physical width should be found at about the same
rate in each if that is true. It is not.

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| under 20 m | FTW 3-class FULL | 0/196, 0.00% | 11/2,163, 0.51% | not readable |
| 20 to 30 m | FTW 3-class FULL | 1/245, 0.41% | 97/1,229, 7.89% | 19.3x |
| 30 to 50 m | FTW 3-class FULL | 5/867, 0.58% | 411/1,740, 23.62% | 41.0x |
| 50 m up | FTW 3-class FULL | 48/675, 7.11% | 999/1,699, 58.80% | 8.3x |
| under 20 m | watershed | 2/196, 1.02% | 81/2,163, 3.74% | 3.7x |
| 20 to 30 m | watershed | 12/245, 4.90% | 262/1,229, 21.32% | 4.4x |
| 30 to 50 m | watershed | 195/867, 22.49% | 829/1,740, 47.64% | 2.1x |
| 50 m up | watershed | 279/675, 41.33% | 1208/1,699, 71.10% | 1.7x |
| under 20 m | SAM ViT-H natural colour | 1/196, 0.51% | 61/2,163, 2.82% | 5.5x |
| 20 to 30 m | SAM ViT-H natural colour | 4/245, 1.63% | 192/1,229, 15.62% | 9.6x |
| 30 to 50 m | SAM ViT-H natural colour | 80/867, 9.23% | 600/1,740, 34.48% | 3.7x |
| 50 m up | SAM ViT-H natural colour | 246/675, 36.44% | 1165/1,699, 68.57% | 1.9x |

Widths are in metres here rather than native pixels, because the two countries
sit on grids of different fineness. India's chips measure 6.067 m per grid
pixel and Slovenia's 4.138 by 6.002 m, both upsampled from the same 10 m
source, so a
band cut in grid pixels covers a different physical size in each country. An
earlier version of this comparison made that mistake and it hid the effect
below by about half. See B-09.

Read the 30 to 50 m row. Those parcels are three to five native pixels wide,
which is at or above the floor. The checkpoint returns 0.58% on India and
23.62% on Slovenia for parcels of the same physical size in the same sensor.
Watershed and SAM show the same ordering, so it is not an artefact of any one
method.

---

## What this says

**Within India the floor is real and its cause is not established.** Every
method collapses below three native pixels, and the two that read the imagery
well elsewhere collapse there too. That is a solid description of Indian
parcels. Attributing it to the resolution of the imagery goes further than the
data supports, because the same imagery at the same physical parcel size
performs between two and forty times better in Slovenia.

**Label geometry was the leading candidate and it is now ruled out.** The
argument was that India is presence-only with five hand-drawn parcels per chip
while Slovenia is a complete cadastre, so IoU against a loosely drawn polygon
would be depressed whatever the imagery showed. `src\label_registration.py`
tests it by walking each parcel's boundary inward and outward through the image
gradient and asking where the strongest edge actually sits.

Measured on rings cut every six metres of ground in both countries, the two
sets of labels are displaced by similar amounts: India's sit +4.13 m inside the
strongest edge and Slovenia's +3.80 m, with a median unsigned displacement of
6.00 m in each. Both clear their own nulls by a wide margin, 38.8% of Indian
parcels peaking on the drawn edge against 13.1% when the walk is given a
gradient field from an unrelated chip, and 47.6% against 14.9% in Slovenia.

| ground width | India label offset | India recall | Slovenia label offset | Slovenia recall |
|---|---:|---:|---:|---:|
| under 20 m | +9.92 m | 0.00% | +5.92 m | 0.51% |
| 20 to 30 m | +6.64 m | 0.41% | +3.79 m | 7.89% |
| 30 to 50 m | +3.91 m | 0.58% | +2.71 m | 23.62% |
| 50 m up | **+1.81 m** | 7.11% | +2.23 m | 58.80% |

Read the last row. Among parcels over 50 m across India's labels are the
better placed of the two, +1.81 m against +2.23 m, and India is still found 8.3
times less often. A hypothesis that predicts the opposite of the data is
finished. In the narrower bands India's labels are worse, by 1.4x to 1.7x, so
label quality contributes something there, and the recall gap in those same
bands runs 19x to 41x, which a few metres of displacement cannot produce.

The estimator behind that table is checked against displacements it was given
before it was pointed at real labels. Run `src\label_registration.py
--self-test`: 300 correctly drawn synthetic parcels all read as correctly drawn
with a median gain of exactly 1.000, and 300 displaced by two pixels all read as
displaced. Two earlier versions of the measurement failed, both in ways that
produced confident numbers; see B-13 and B-14.

**What may carry part of it is edge sharpness.** The gradient on Indian
labelled boundaries is lower, relative to the field inside, than on Slovenian
ones from the same sensor. Measured as the gradient on the drawn boundary
divided by the gradient inside that same parcel, so that no chip statistic
enters the comparison:

| | India | Slovenia |
|---|---:|---:|
| gradient on the line over gradient inside, median | 1.297x | 1.588x |
| share where the line's gradient is no higher than inside | 14.2% | 7.2% |
| by width, 20 to 30 m | 1.118x | 1.257x |
| by width, 30 to 50 m | 1.236x | 1.441x |
| by width, 50 m up | 1.420x | 2.005x |

The gap widens as parcels get larger, which is not the shape a resolution
artefact takes. Only parcels wide enough to survive two erosions can be
measured, 1,467 of 1,983 in India and 4,307 of 6,823 in Slovenia, so this is
silent about the narrowest band in each country.

A 1.2x deficit in edge gradient looked too small to explain a 6 to 29 times
recall gap, and this paragraph said it could not. Tested directly, it can
explain most of it: softening Slovenia's edges to India's level closes more
than half of the gap for FTW v3 and for watershed (B-28, and the edge test
below). Parcel shape and FTW's two seasonal windows were the other candidates,
and both are tested below. An
earlier version of this paragraph said the windows were set for a European
calendar, which FTW's own configuration contradicts; see B-22.

*Source: `label_registration.csv` in each country.*

**Checked blind against two people, the measure agrees weakly.**
`src\contrast_panel.py` draws 20 Indian parcels, five from each quartile of the
measure, in shuffled order with the value hidden. Each parcel appears twice,
plain and outlined. One analyst, the author, marked those with a boundary she
could see along the line before any value was shown. The bars were set before
scoring: a rank score of 0.75 or more with permutation p under 0.05 would count
as tracking visibility, and 0.60 or more as weak.

She marked 6 of 20. The rank score, the share of marked and unmarked pairs in
which the measure puts the marked parcel higher, is 0.655, with p = 0.16 over
20,000 shuffles of her answers. Weak. Four of the six sit among the six highest
measured. The other two score 1.015 and 1.001, where the measure reads the line
as no sharper than the field. One of them, looked at after scoring, is a bright
patch against darker ground whose brightness fades over several pixels, so
inside and outside differ clearly with no sharp step at the line. That is the
likely gap between the two readings. The measure responds to how sharp the edge
is, and the eye also responds to a plain difference in brightness.

Those crops were drawn with red and blue swapped (B-23). So a second panel was
drawn in natural colour, from 20 parcels neither earlier panel had shown, and
judged against the same bars. She marked 10 of 20. The rank score is 0.650,
with p = 0.14: weak again, within half a hundredth of the first. The two
parcels the measure ranks highest are both marked and the three lowest are
not; in between the two readings part company in both directions, with four
marked parcels measuring only 1.10 to 1.16. The swapped colours were not
hiding agreement.

An earlier panel was spent without a valid score, when the example numbers in
the instructions were scored in place of real judgements. Its 20 parcels were
kept out of both scored panels. One person and 20 parcels a panel cannot
separate weak agreement from moderate, and two panels agreeing on weak is
reason to stop drawing them rather than to try for a pass. A second analyst
would test something new.

So a second person judged 60 parcels: the 40 of both scored panels and 20 new
ones drawn the same way, five from each quartile, from parcels no panel had
shown. `src\contrast_second.py` drew all 60 in natural colour, in one shuffled
order, so the panel a parcel came from could not be told. The author judged
the 20 new ones first, and nothing was scored until both had finished. The
bars stayed as above, and the primary reading was set as the second person's
score over all 60. The design was committed before the draw, in `2917a0f`, and
the draw before any answer, in `c30c1ac`.

| judge | parcels | n | marked visible | rank score | permutation p | reading |
|---|---|---:|---:|---:|---:|---|
| second person | all 60 | 60 | 29 | 0.742 | 0.0004 | weak |
| second person | panel 20260925 | 20 | 9 | 0.606 | 0.2309 | weak |
| second person | panel 20261012 | 20 | 11 | 0.788 | 0.0155 | tracks what a person sees |
| second person | new 20 | 20 | 9 | 0.808 | 0.0098 | tracks what a person sees |
| author | all 60 | 60 | 25 | 0.664 | 0.0150 | weak |
| author | panel 20260925 | 20 | 6 | 0.655 | 0.1572 | weak |
| author | panel 20261012 | 20 | 10 | 0.650 | 0.1449 | weak |
| author | new 20 | 20 | 9 | 0.707 | 0.0668 | weak |

The second person's score over all 60 is 0.742, with p = 0.0004. By the rule
that is weak, 0.008 below the bar, and F-14 stays scoped. It is also the first
reading clearly above chance: shuffled answers did as well about 4 times in
10,000. The author's 60, her two earlier panels and the new 20, give 0.664 with
p = 0.015. Recomputed here, her two earlier panels reproduce their recorded
scores to the fourth decimal, which checks that her old answers were matched
to the right parcels.

Most of the second person's shortfall is on panel 20260925, at 0.606, where
the author was also weakest. On the other 40 parcels the second person scores
0.788 and 0.808. Twenty parcels are too few to read alone and the rule was set
on all 60, so the per-panel rows describe and do not decide.

| parcels | n | both visible | both not | second only | author only | agree | kappa |
|---|---:|---:|---:|---:|---:|---:|---:|
| all 60 | 60 | 22 | 28 | 7 | 3 | 0.83 | 0.67 |
| panel 20260925 | 20 | 6 | 11 | 3 | 0 | 0.85 | 0.69 |
| panel 20261012 | 20 | 8 | 7 | 3 | 2 | 0.75 | 0.50 |
| new 20 | 20 | 8 | 10 | 1 | 1 | 0.90 | 0.80 |

The two people agree on 50 of 60 parcels, kappa 0.67, above the 0.40 set in
advance, and the second person called a few more parcels visible, 29 against
25. The swapped
colours of the author's first panel changed little: on its 20 parcels the two
agree on 17. So the eye is a consistent reference here, and the measure agrees
with it less well than the two people agree with each other. It stays a
difference in edge sharpness between countries, now shown to beat chance
against a person, and it is still not a visibility score per parcel.

*Source: `results/india/contrast_second_scores.csv` and
`contrast_second_agreement.csv`, with both judges' answers beside the key in
`contrast_second_answers.csv`; the panels are in `figures/contrast_second/`.*

*Source: `results/india/contrast_panel_scores.csv`, one row per scored panel;
the natural colour panel's key is `contrast_panel_key.csv` and the first
scored panel's is `contrast_panel_key_spent_2.csv`;
`figures/contrast_panel_india.png` shows the natural colour panel.*

**Parcel shape is ruled out.** Slovenian parcels are more strip-like than Indian
ones. Taking a parcel's area over the square of its width, which is 1 for a
square and the length over the width for a rectangle, the median Slovenian
parcel scores 2.98 and the median Indian one 1.83. Among parcels 20 to 30 m
wide, 46% of Slovenia's score 4 or more against 9% of India's. If strips are
easier to recover than blocks of the same width, that alone could open a gap
at matched width.

`src\shape_test.py` puts each parcel in a cell by width band and elongation
band and recomputes Slovenia's recall with each cell weighted by India's share
of parcels in it. The bars were written into the script before it ran: shape
accounts for a large part of the gap if it explains half or more of it on a log
scale, a part if a fifth or more, and little below that.

| method | India | Slovenia | Slovenia, India's widths | Slovenia, India's widths and shapes | ratio, widths | ratio, widths and shapes | share from shape | six-band check |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 2.72% | 22.22% | 31.37% | 29.03% | 11.52x | 10.66x | +0.03 [+0.01, +0.05] | +0.04 |
| watershed | 24.61% | 34.84% | 48.04% | 49.34% | 1.95x | 2.00x | -0.04 [-0.08, -0.01] | -0.04 |
| SAM ViT-H, blue-green-red | 15.63% | 27.62% | 37.97% | 39.69% | 2.43x | 2.54x | -0.05 [-0.09, -0.01] | -0.06 |
| SAM ViT-H natural colour | 16.69% | 29.54% | 40.63% | 42.05% | 2.43x | 2.52x | -0.04 [-0.08, -0.00] | -0.04 |

Shape explains 3% of FTW's gap, with an interval from 1% to 5%. For watershed
and SAM the share is negative, meaning India's compact parcels are the easier
mix for them and matching on shape widens the gap a little. Cutting elongation
into six bands at the pooled sextiles gives the same answer. Watershed here is
at its best setting, h 0.02 in India and 0.05 in Slovenia, the same files as
the cross-country table.

| method | ground width | India | Slovenia | Slovenia, India's shapes | ratio | ratio after |
|---|---|---:|---:|---:|---:|---:|
| FTW 3-class FULL | under 20 m | 0/196, 0.00% | 0.51% | 0.18% | not readable | not readable |
| FTW 3-class FULL | 20 to 30 m | 1/245, 0.41% | 7.89% | 4.38% | 19.3x | 10.7x |
| FTW 3-class FULL | 30 to 50 m | 5/867, 0.58% | 23.62% | 18.41% | 41.0x | 31.9x |
| FTW 3-class FULL | 50 m up | 48/675, 7.11% | 58.80% | 60.00% | 8.3x | 8.4x |
| watershed | under 20 m | 2/196, 1.02% | 3.74% | 3.24% | 3.7x | 3.2x |
| watershed | 20 to 30 m | 12/245, 4.90% | 21.32% | 19.59% | 4.4x | 4.0x |
| watershed | 30 to 50 m | 195/867, 22.49% | 47.64% | 48.85% | 2.1x | 2.2x |
| watershed | 50 m up | 279/675, 41.33% | 71.10% | 74.15% | 1.7x | 1.8x |
| SAM ViT-H, blue-green-red | under 20 m | 1/196, 0.51% | 2.64% | 1.94% | 5.2x | 3.8x |
| SAM ViT-H, blue-green-red | 20 to 30 m | 5/245, 2.04% | 14.56% | 13.55% | 7.1x | 6.6x |
| SAM ViT-H, blue-green-red | 30 to 50 m | 76/867, 8.77% | 32.01% | 32.55% | 3.7x | 3.7x |
| SAM ViT-H, blue-green-red | 50 m up | 228/675, 33.78% | 64.39% | 69.30% | 1.9x | 2.1x |
| SAM ViT-H natural colour | under 20 m | 1/196, 0.51% | 2.82% | 1.99% | 5.5x | 3.9x |
| SAM ViT-H natural colour | 20 to 30 m | 4/245, 1.63% | 15.62% | 13.92% | 9.6x | 8.5x |
| SAM ViT-H natural colour | 30 to 50 m | 80/867, 9.23% | 34.48% | 35.12% | 3.7x | 3.8x |
| SAM ViT-H natural colour | 50 m up | 246/675, 36.44% | 68.57% | 72.78% | 1.9x | 2.0x |

Within the narrow bands, shape does matter to FTW on the Slovenian side. Given
India's shapes, its Slovenian recall at 20 to 30 m falls from 7.89% to 4.38%,
measured on 1,229 parcels. The Indian side of those ratios is 1 and 5 parcels
found, and even halved the gap there is ten times or more. Most of FTW's Indian
hits are over 50 m, where shape changes nothing.

*Source: `results/shape_test.csv` and `shape_test_bands.csv`.*

**The seasonal windows are a part of it, and a small part.** FTW gives each chip
two images, from date ranges it sets per country in `data_config_<country>.json`.
In Slovenia window_b follows window_a in the same season. In India it comes
first: March to June 2016, the dry months after the rabi harvest, then July to
November 2016 for kharif. Neither covers December to February, when rabi crops
are standing.

| country | window | dates | red, median | blue, median | blue, 95th percentile | NDVI, median | edge strength |
|---|---|---|---:|---:|---:|---:|---:|
| India | window_a | July to November 2016 | 1058 | 609 | 837 | 0.35 | 0.424 |
| India | window_b | March to June 2016 | 1652 | 901 | 1187 | 0.17 | 0.401 |
| Slovenia | window_a | May to August 2021 | 351 | 312 | 666 | 0.82 | 0.328 |
| Slovenia | window_b | September to October 2021 | 258 | 282 | 583 | 0.83 | 0.338 |

India's window_b is brighter in red and in blue and carries half the NDVI of
window_a, 0.17 against 0.35, so most of what it shows is bare ground after the
harvest. Slovenia's two windows are about equally green, 0.82 and 0.83, partly
because many of its test chips are forest. Edge strength is computed on each
chip's own stretch, so it compares windows only loosely. An earlier version of
this table read band 1 as blue, and band 1 is red (B-23).

`src\season_test.py` runs the released checkpoint four ways over every test
chip: as shipped, with the windows swapped, and with each window given twice.
The shipped run matches the published predictions to within 1 pixel of 26
million in India and 3 of 15 million in Slovenia, which is thread-count
noise, and every published recall comes back exactly. The reading was set in
the script before it ran: FTW leans on a window if feeding it that window twice
moves recall outside the shipped run's interval.

| what the model was given | India objects/chip | India recall | India null | Slovenia objects/chip | Slovenia recall | Slovenia null |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 175.0 | 2.72% [1.72, 3.89] | 1.93% | 19.5 | 22.22% [18.52, 25.97] | 0.52% |
| swapped | 186.8 | 3.68% [2.48, 5.01] | 2.22% | 21.5 | 21.42% [17.98, 24.77] | 0.55% |
| a twice | 169.4 | 4.79% [3.39, 6.34] | 1.95% | 16.6 | 15.21% [11.95, 18.87] | 0.51% |
| b twice | 116.9 | 1.01% [0.50, 1.57] | 1.21% | 8.9 | 10.60% [7.69, 13.59] | 0.26% |

| what the model was given | India parcels gained | India parcels lost | India change | Slovenia parcels gained | Slovenia parcels lost | Slovenia change |
|---|---:|---:|---:|---:|---:|---:|
| swapped | 40 | 21 | +0.96 [+0.05, +1.92] | 285 | 340 | -0.81 [-1.97, +0.29] |
| a twice | 64 | 23 | +2.07 [+0.91, +3.27] | 207 | 686 | -7.01 [-8.51, -5.51] |
| b twice | 17 | 51 | -1.71 [-2.83, -0.61] | 98 | 892 | -11.62 [-13.60, -9.75] |

In Slovenia the model uses both images. Given window_a twice it loses about a
third of what it found, and given window_b twice about half. In India the second image works
against it. Given the kharif image twice, FTW finds 95 parcels where it found
54, a change of +2.07 points [+0.91, +3.27] with whole chips resampled in
pairs. Given the dry-season image twice, it falls to 1.01% at 117 objects per
chip, no better than the 1.21% that random cells reach at that count.

The rule set before the run also asked whether swapping the order moves recall
outside the shipped interval, and in neither country does it. The chip by chip
comparison, added after the run, finds a small gain from swapping in India,
+0.96 points [+0.05, +1.92], and none in Slovenia. It sits at the edge of its
interval and the reading does not rest on it.

| country | what the model was given | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---|---:|---:|---:|---:|
| India | shipped | 0/196, 0.00% | 1/245, 0.41% | 5/867, 0.58% | 48/675, 7.11% |
| India | swapped | 0/196, 0.00% | 2/245, 0.82% | 6/867, 0.69% | 65/675, 9.63% |
| India | a twice | 0/196, 0.00% | 3/245, 1.22% | 16/867, 1.85% | 76/675, 11.26% |
| India | b twice | 0/196, 0.00% | 1/245, 0.41% | 5/867, 0.58% | 14/675, 2.07% |
| Slovenia | shipped | 11/2,163, 0.51% | 97/1,229, 7.89% | 411/1,740, 23.62% | 999/1,699, 58.80% |
| Slovenia | swapped | 13/2,163, 0.60% | 98/1,229, 7.97% | 403/1,740, 23.16% | 949/1,699, 55.86% |
| Slovenia | a twice | 7/2,163, 0.32% | 56/1,229, 4.56% | 266/1,740, 15.29% | 710/1,699, 41.79% |
| Slovenia | b twice | 4/2,163, 0.18% | 67/1,229, 5.45% | 227/1,740, 13.05% | 426/1,699, 25.07% |

The gain from dropping the dry-season image is largest on the widest Indian
parcels, 11.26% against 7.11% over 50 m.

Watershed, run on each window's gradient alone and read at FTW's object count:

| gradient from | India, at 175 objects/chip | Slovenia, at 20 objects/chip |
|---|---:|---:|
| both windows stacked | 10.74% [8.98, 12.57] | 5.93% [5.00, 6.92] |
| window_a alone | 9.56% [7.97, 11.24] | 4.35% [3.64, 5.07] |
| window_b alone | 6.04% [4.76, 7.35] | 5.83% [4.99, 6.68] |

In India the kharif image carries clearly more of the boundaries than the
dry-season one, with intervals that do not overlap. In Slovenia neither window
clearly wins. Stacking the two does not dilute the signal in either country.

By the rule set before the run, season is a candidate cause of the India gap:
one window carries clearly less of the boundaries in India and not in
Slovenia. Its size is limited. The best arrangement leaves FTW at 4.79% in
India against 22.22% in Slovenia, 4.6 times lower, and at 11.26% against
58.80% over 50 m. Taking the dry-season image away helps the checkpoint
without making it work. Neither window shows December to February, when rabi
crops are standing; that is tested next.

SAM was not rerun on window_b. It already reads window_a alone, the better of
the two, and watershed has answered the question that rerun would ask.

*Source: `season_ftw.csv`, `season_ftw_parcels.csv`,
`season_watershed_budget.csv` and `season_windows.csv` in each country.*

**An image from December to February does not rescue the checkpoint.** Both
rabi seasons around FTW's year were built for every Indian test chip: December
2015 to February 2016, whose harvest window_b shows, and December 2016 to
February 2017, after the kharif window_a shows. `src\rabi_probe.py` first
checked that FTW's own chips could be rebuilt from the Planetary Computer
archive with FTW's download recipe. On three chips, every window reproduces,
well inside a bar of 0.98 correlation and 2% median difference set before
running:

| chip | window | scene date | lowest band correlation | largest median difference |
|---|---|---|---:|---:|
| g0_0030 | window_a | 2016-11-25 | 0.9921 | 0.04% |
| g0_0030 | window_b | 2016-04-29 | 0.9945 | 0.07% |
| g0_0073 | window_a | 2016-07-15 | 0.9977 | 0.06% |
| g0_0073 | window_b | 2016-03-27 | 0.9976 | 0.00% |
| g0_0091 | window_a | 2016-11-12 | 0.9969 | 0.04% |
| g0_0091 | window_b | 2016-04-26 | 0.9975 | 0.11% |

That also shows which scenes FTW used. On one of the three chips its July to
November image is from mid-July, when kharif crops are just sown. On the other
two it is from late November, after the kharif harvest. Three chips cannot say
how often each happens.

`src\rabi_download.py` then built one image per chip and season, taking the
first scene whose own scene classification put under 5% of the chip under
cloud, shadow or no data. Chips over 10% were left out by a rule set in
`src\rabi_test.py` before any image was scored. That removed 49 chips in
2015-16, among them one where the archive listed a scene over the chip that
held no data there.

| season | chips | at or under 10% chip cloud | December | January | February |
|---|---:|---:|---:|---:|---:|
| 2016-17 | 399 | 399 | 177 | 40 | 182 |
| 2015-16 | 399 | 350 | 97 | 148 | 105 |

`src\rabi_test.py` gives FTW the rabi image, r, in four arrangements beside
the shipped run, all on the same chips, and runs watershed on its gradient.
Its readings were committed before the test ran.

| what the model was given | 2016-17 objects/chip | 2016-17 recall | 2016-17 null | 2015-16 objects/chip | 2015-16 recall | 2015-16 null |
|---|---:|---:|---:|---:|---:|---:|
| shipped, b then a | 175.0 | 2.72% | 1.98% | 175.9 | 2.70% | 2.05% |
| a twice | 169.4 | 4.79% | 2.03% | 175.0 | 5.35% | 2.09% |
| rabi for b, r then a | 197.9 | 4.74% | 2.39% | 197.5 | 4.03% | 2.22% |
| a then rabi | 209.9 | 5.50% | 2.59% | 214.4 | 4.66% | 2.44% |
| rabi twice | 117.8 | 2.27% | 1.48% | 114.9 | 1.09% | 1.19% |

| gradient from | 2016-17 | 2015-16 |
|---|---:|---:|
| b and a, as published | 10.74% | 11.23% |
| a alone | 9.56% | 10.14% |
| r alone | 10.08% | 9.81% |
| a and r | 11.19% | 13.07% |

| method | comparison | 2016-17 | 2015-16 |
|---|---|---:|---:|
| FTW | rabi for b against shipped | +2.02 [+1.06, +2.98] | +1.32 [+0.40, +2.30] |
| FTW | rabi for b against a twice | -0.05 [-1.32, +1.21] | -1.32 [-2.76, +0.12] |
| FTW | a then rabi against shipped | +2.77 [+1.61, +3.93] | +1.96 [+1.03, +3.00] |
| FTW | rabi twice against shipped | -0.45 [-1.56, +0.65] | -1.61 [-2.81, -0.46] |
| FTW | a twice against shipped | +2.07 [+0.91, +3.27] | +2.65 [+1.50, +3.90] |
| watershed | r alone against a alone | +0.52 [-0.98, +1.96] | -0.33 [-2.25, +1.61] |
| watershed | a and r against b and a | +0.45 [-1.11, +1.93] | +1.84 [+0.20, +3.50] |
| watershed | a and r against a alone | +1.62 [+0.39, +2.89] | +2.93 [+1.35, +4.57] |

Read against those rules, in both seasons:

- **A rabi image helps the checkpoint**, by +2.02 and +1.32 points over the
  shipped run, intervals above zero.
- **It does not help beyond dropping the dry-season image.** Against a second
  copy of the kharif image it changes recall by -0.05 and -1.32 points, and
  neither interval is above zero. The gain comes from removing March to June.
  The rabi crops add nothing to it.
- **The rabi image does not carry more of the visible boundaries than
  kharif.** Watershed on each alone differs by +0.52 and -0.33 points, the
  seasons disagreeing in sign. Adding rabi to the published stack helps
  watershed in 2015-16, +1.84, and not clearly in 2016-17, +0.45, so by the
  rule that both seasons must agree it is unresolved.
- **Season is at most a minor cause of the India gap.** The best arrangement
  reaches 5.50% and 5.35%, under the third of Slovenia's 22.22% the rule set
  as the bar.

Given the rabi image twice, FTW does no better than as shipped in 2016-17 and
worse in 2015-16, level with its null. Watershed on the same image does about
as well as on kharif. The boundaries are in the rabi image and the checkpoint
does not read them, which is the same pattern as the rest of this study.

Two caveats. The arrangements with a rabi image in them emit 197.5 to 214.4
objects per chip against the shipped 175, and their null rises by 0.2 to 0.6
points with that, so a little of their gain is object count; the comparison
with a second kharif copy, at 169 to 175 objects, does not carry it. And two
comparisons the script printed were not among the readings set beforehand:
"a then rabi" is the best arrangement in 2016-17, and watershed on kharif and
rabi stacked beats kharif alone in both seasons. They are reported and not
relied on.

*Source: `rabi_match.csv`, `rabi_scenes.csv` and `rabi_test_<season>_*.csv`
in `results/india`. The images themselves are rebuilt from the scene list.*

**FTW's later checkpoints change the size of the Indian failure.** Everything
above used FTW's v1 checkpoint, which this project called the released state
of the art. FTW had released three more by the time this work began: v2 in
September 2025, trained with the two windows in random order, v3 "PRUE" in
November 2025, with a log-cosh Dice loss, new class weights and more
augmentation, and v3.1 in December 2025, the same recipe trained only on CC-BY
and CC0 data (B-24). None was trained without India.

`src\newer_checkpoints.py` runs seven checkpoints from those releases over the
same chips and scores them the same way, with its readings committed before it
ran. Each is a U-Net with an EfficientNet encoder taking the same eight
channels, divided by 3000 with window_b first, as FTW's own test command does
for every release. ftw-tools 1.4.3 cannot load the v3 checkpoints, so the
script builds the network directly. Checked on v1 first, its predictions
differ from the published ones in 1 pixel of 26.1 million in India and 3 of
14.9 million in Slovenia.

| checkpoint | licence | India objects/chip | India recall | India null | Slovenia objects/chip | Slovenia recall | Slovenia null | India over Slovenia |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v1 full | mixed | 175.0 | 2.72% [1.76, 3.88] | 2.15% | 19.5 | 22.22% [18.62, 25.99] | 0.56% | 0.122 [0.077, 0.178] |
| v1 cc-by | CC-BY | 84.0 | 2.98% [1.97, 4.10] | 0.72% | 13.4 | 14.46% [11.26, 17.41] | 0.37% | 0.206 [0.132, 0.305] |
| v2 full | mixed | 76.3 | 1.71% [1.06, 2.58] | 0.71% | 18.2 | 19.27% [16.03, 22.35] | 0.60% | 0.089 [0.053, 0.139] |
| v3 full b3 | mixed | 223.3 | 10.29% [8.51, 12.30] | 2.69% | 19.3 | 28.78% [24.98, 32.42] | 0.63% | 0.357 [0.285, 0.454] |
| v3 full b7 | mixed | 245.3 | 12.91% [10.66, 15.08] | 2.50% | 20.5 | 33.06% [29.00, 36.73] | 0.58% | 0.391 [0.316, 0.478] |
| v3.1 cc-by b3 | CC-BY | 154.7 | 8.22% [6.60, 9.92] | 1.34% | 12.1 | 16.81% [13.36, 20.10] | 0.32% | 0.489 [0.369, 0.656] |
| v3.1 cc-by b7 | CC-BY | 224.6 | 11.40% [9.38, 13.41] | 2.17% | 15.2 | 22.44% [18.55, 26.12] | 0.39% | 0.508 [0.397, 0.651] |

398 labelled Indian chips and 185 Slovenian, 1,983 and 6,831 parcels.

| country | checkpoint | against | recall change | change above null |
|---|---|---|---:|---:|
| India | v1 cc-by | v1 full | +0.25 [-0.91, +1.41] | +1.68 [+0.52, +2.85] |
| India | v2 full | v1 full | -1.01 [-1.91, -0.15] | +0.44 [-0.62, +1.39] |
| India | v3 full b3 | v1 full | +7.56 [+5.94, +9.23] | +7.03 [+5.41, +8.73] |
| India | v3 full b7 | v1 full | +10.19 [+8.37, +12.15] | +9.83 [+7.93, +11.75] |
| India | v3.1 cc-by b3 | v1 full | +5.50 [+4.03, +7.12] | +6.30 [+4.79, +7.95] |
| India | v3.1 cc-by b7 | v1 full | +8.67 [+6.92, +10.54] | +8.66 [+6.76, +10.65] |
| India | v3.1 cc-by b3 | v1 cc-by | +5.24 [+3.93, +6.64] | +4.62 [+3.19, +6.11] |
| Slovenia | v1 cc-by | v1 full | -7.76 [-9.21, -6.28] | -7.57 [-9.15, -6.05] |
| Slovenia | v2 full | v1 full | -2.96 [-4.50, -1.35] | -3.00 [-4.58, -1.43] |
| Slovenia | v3 full b3 | v1 full | +6.56 [+4.73, +8.31] | +6.48 [+4.73, +8.12] |
| Slovenia | v3 full b7 | v1 full | +10.83 [+8.90, +12.56] | +10.81 [+8.91, +12.52] |
| Slovenia | v3.1 cc-by b3 | v1 full | -5.42 [-7.98, -2.93] | -5.18 [-7.94, -2.68] |
| Slovenia | v3.1 cc-by b7 | v1 full | +0.22 [-1.96, +2.11] | +0.39 [-1.80, +2.28] |
| Slovenia | v3.1 cc-by b3 | v1 cc-by | +2.34 [+0.13, +4.32] | +2.39 [+0.21, +4.30] |

Read against the rules in the script's docstring:

- **v3 does better on India, from better placed boundaries.** Every v3 and
  v3.1 checkpoint beats v1 with an interval above zero, and its gain above its
  own null is nearly as large, so object count, 155 to 245 per chip against
  v1's 175, explains little of it.
- **The gap to Slovenia narrows and stays under the bar.** With v3 full, India
  stands at 0.357 and 0.391 of Slovenia against v1's 0.122. The rule asked for
  a lower end of one third, and the lower ends are 0.285 and 0.316. The two
  v3.1 checkpoints pass it, at 0.489 and 0.508, for a reason the rule was not
  written to catch: they lose more on Slovenia than on India. FTW describes
  them as trained only on CC-BY or CC0 data and lists Slovenia's labels as
  CC-BY-SA-4.0, so Slovenia was probably left out of their training. That has
  not been confirmed. The fair comparison across countries is the v3 full
  pair, where both countries were in training.
- **v2 is worse than v1** in both countries, by 1.01 points in India and 2.96
  in Slovenia. Shuffling the window order in training did not help on its own.

By ground width, India first and Slovenia second:

| checkpoint | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---:|---:|---:|---:|
| v1 full | 0.00% | 0.41% | 0.58% | 7.11% |
| v1 cc-by | 0.00% | 0.00% | 0.46% | 8.15% |
| v2 full | 0.00% | 0.00% | 0.23% | 4.74% |
| v3 full b3 | 1.02% | 0.82% | 3.34% | 25.33% |
| v3 full b7 | 0.00% | 1.22% | 4.96% | 31.11% |
| v3.1 cc-by b3 | 1.02% | 0.41% | 1.85% | 21.33% |
| v3.1 cc-by b7 | 0.00% | 0.82% | 3.92% | 28.15% |

Parcels per band: under 20 m 196, 20 to 30 m 245, 30 to 50 m 867, 50 m up 675.

| checkpoint | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---:|---:|---:|---:|
| v1 full | 0.51% | 7.89% | 23.62% | 58.80% |
| v1 cc-by | 0.46% | 4.96% | 15.63% | 37.96% |
| v2 full | 0.23% | 4.48% | 18.79% | 54.68% |
| v3 full b3 | 2.27% | 14.48% | 34.48% | 67.04% |
| v3 full b7 | 3.61% | 20.26% | 40.98% | 71.69% |
| v3.1 cc-by b3 | 1.34% | 6.43% | 20.63% | 40.08% |
| v3.1 cc-by b7 | 2.13% | 13.51% | 27.13% | 49.97% |

Parcels per band: under 20 m 2,163, 20 to 30 m 1,229, 30 to 50 m 1,740, 50 m up 1,699.

The gain is on wider parcels. With B7, parcels 50 m and wider go from 7.11% to
31.11% in India and those 30 to 50 m across from 0.58% to 4.96%. Under 30 m no
checkpoint passes 1.22%. At equal width the countries still differ: 50 m and
up, v3 B7 finds 31.11% in India and 71.69% in Slovenia.

**Watershed and SAM still beat it on India, by less.** Every matched-budget
comparison above was made at v1's object count. `src\budget_newer.py` reads
watershed and SAM again at each later checkpoint's count. It was written after
the checkpoint results were seen, and its own rules were committed before it
ran. It first reproduced every published watershed and SAM figure to four
places in both countries. SAM draws at most 222 objects per Indian chip and at
least 72 per Slovenian one, so it often cannot reach the budget. It is then
read at its nearest setting, and a verdict stands only when it favours the side
drawing fewer objects. India first, then Slovenia:

| checkpoint | objects/chip | FTW recall | method | read at | recall | minus FTW | reading |
|---|---:|---:|---|---:|---:|---:|---|
| v1 full | 175.0 | 2.72% | watershed | 175.0 | 10.74% | +8.01 [+6.28, +9.78] | method ahead |
| v1 full | 175.0 | 2.72% | SAM colour infrared | 175.0 | 15.78% | +13.05 [+10.99, +15.26] | method ahead |
| v1 full | 175.0 | 2.72% | SAM NIR-blue-green | 175.0 | 15.34% | +12.62 [+10.56, +14.66] | method ahead |
| v1 full | 175.0 | 2.72% | SAM natural colour | 175.0 | 15.17% | +12.44 [+10.40, +14.57] | method ahead |
| v1 full | 175.0 | 2.72% | SAM blue-green-red | 175.0 | 15.11% | +12.39 [+10.47, +14.48] | method ahead |
| v3 full b3 | 223.3 | 10.29% | watershed | 223.3 | 13.71% | +3.43 [+1.83, +4.98] | method ahead |
| v3 full b3 | 223.3 | 10.29% | SAM colour infrared | 222.4 | 18.31% | +8.02 [+6.03, +9.85] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM NIR-blue-green | 212.6 | 17.25% | +6.96 [+5.10, +8.86] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM natural colour | 194.6 | 16.69% | +6.40 [+4.53, +8.27] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM blue-green-red | 184.5 | 15.63% | +5.35 [+3.53, +7.22] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | watershed | 245.3 | 14.83% | +1.92 [+0.21, +3.59] | method ahead |
| v3 full b7 | 245.3 | 12.91% | SAM colour infrared | 222.4 | 18.31% | +5.40 [+3.38, +7.23] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM NIR-blue-green | 212.6 | 17.25% | +4.34 [+2.42, +6.20] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM natural colour | 194.6 | 16.69% | +3.78 [+1.97, +5.70] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM blue-green-red | 184.5 | 15.63% | +2.72 [+0.81, +4.59] | method ahead, stands under P2 |
| v3.1 cc-by b3 | 154.7 | 8.22% | watershed | 154.7 | 9.19% | +0.98 [-0.64, +2.66] | level |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM colour infrared | 155.3 | 14.52% | +6.30 [+4.60, +8.26] | unresolved under P2 |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM NIR-blue-green | 154.7 | 14.28% | +6.06 [+4.26, +7.74] | method ahead |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM natural colour | 154.7 | 14.03% | +5.81 [+4.03, +7.50] | method ahead |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM blue-green-red | 154.7 | 13.79% | +5.57 [+3.73, +7.42] | method ahead |
| v3.1 cc-by b7 | 224.6 | 11.40% | watershed | 224.6 | 13.78% | +2.39 [+0.75, +3.98] | method ahead |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM colour infrared | 222.4 | 18.31% | +6.91 [+5.09, +8.82] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM NIR-blue-green | 212.6 | 17.25% | +5.85 [+3.95, +7.77] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM natural colour | 194.6 | 16.69% | +5.30 [+3.43, +7.20] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM blue-green-red | 184.5 | 15.63% | +4.24 [+2.32, +6.16] | method ahead, stands under P2 |

| checkpoint | objects/chip | FTW recall | method | read at | recall | minus FTW | reading |
|---|---:|---:|---|---:|---:|---:|---|
| v1 full | 19.5 | 22.22% | watershed | 19.5 | 5.93% | -16.29 [-19.32, -13.16] | FTW ahead |
| v1 full | 19.5 | 22.22% | SAM colour infrared | 73.8 | 21.21% | -1.01 [-3.58, +1.50] | level |
| v1 full | 19.5 | 22.22% | SAM NIR-blue-green | 72.7 | 20.63% | -1.60 [-4.08, +0.83] | level |
| v1 full | 19.5 | 22.22% | SAM natural colour | 85.9 | 25.72% | +3.50 [+1.10, +5.93] | unresolved under P2 |
| v1 full | 19.5 | 22.22% | SAM blue-green-red | 78.8 | 23.38% | +1.16 [-1.31, +3.70] | level |
| v3 full b3 | 19.3 | 28.78% | watershed | 19.3 | 5.86% | -22.92 [-26.33, -19.60] | FTW ahead |
| v3 full b3 | 19.3 | 28.78% | SAM colour infrared | 73.8 | 21.21% | -7.57 [-10.17, -4.92] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM NIR-blue-green | 72.7 | 20.63% | -8.15 [-10.72, -5.58] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM natural colour | 85.9 | 25.72% | -3.06 [-5.40, -0.64] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM blue-green-red | 78.8 | 23.38% | -5.40 [-7.96, -2.90] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | watershed | 20.5 | 6.27% | -26.78 [-30.17, -23.22] | FTW ahead |
| v3 full b7 | 20.5 | 33.06% | SAM colour infrared | 73.8 | 21.21% | -11.84 [-14.51, -9.15] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM NIR-blue-green | 72.7 | 20.63% | -12.43 [-15.09, -9.77] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM natural colour | 85.9 | 25.72% | -7.33 [-9.93, -4.72] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM blue-green-red | 78.8 | 23.38% | -9.68 [-12.38, -6.80] | FTW ahead, stands under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | watershed | 12.1 | 3.44% | -13.37 [-16.57, -10.08] | FTW ahead |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM colour infrared | 73.8 | 21.21% | +4.41 [+1.48, +7.66] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM NIR-blue-green | 72.7 | 20.63% | +3.82 [+0.97, +6.64] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM natural colour | 85.9 | 25.72% | +8.92 [+6.31, +11.86] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM blue-green-red | 78.8 | 23.38% | +6.57 [+3.80, +9.73] | unresolved under P2 |
| v3.1 cc-by b7 | 15.2 | 22.44% | watershed | 15.2 | 4.49% | -17.95 [-21.28, -14.30] | FTW ahead |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM colour infrared | 73.8 | 21.21% | -1.23 [-4.03, +1.89] | level |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM NIR-blue-green | 72.7 | 20.63% | -1.82 [-4.63, +0.96] | level |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM natural colour | 85.9 | 25.72% | +3.28 [+0.40, +6.00] | unresolved under P2 |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM blue-green-red | 78.8 | 23.38% | +0.94 [-1.88, +4.02] | level |

- **India.** At v3 B7's 245 objects per chip, watershed is ahead by 1.92
  points, interval +0.21 to +3.59, and SAM on colour infrared by 5.40 from 222
  objects. Against v1 the same margins were 8.01 and 13.05. Against v3.1 cc-by
  B3 watershed is level. SAM on colour infrared is unresolved there, since its
  nearest setting draws 155.3 objects against FTW's 154.7.
- **Slovenia.** v3 B7 beats watershed by 26.78 points and every SAM composite
  by 7.33 to 12.43, drawing 20.5 objects per chip against SAM's 72.7 to 85.9,
  so that verdict stands. Against v1, SAM was level there or unresolved. v3.1
  cc-by B7, which probably did not see Slovenia, is level with three SAM
  composites and unresolved against the fourth.

So the pattern this study describes holds with the best public checkpoint. On
India an untrained method beats the trained model at the same object count,
and on Slovenia it loses. What changed is the size: the trained model's Indian
deficit is now a few points where it was a factor of five, and the country gap
is a factor of about two and a half where it was eight.

*Source: `newer_checkpoints*.csv` and `budget_newer.csv` in `results/`, with
the per-chip files in `results/<country>/newer_ckpt/` and
`results/<country>/watershed_chips_min500.csv`.*

**Weak edges are enough to explain most of the gap, tested on Slovenia.**
The edge measure above says Indian field edges are weaker than Slovenian ones.
It does not say a model cares. `src\edge_test.py` tests that from the other
side: if weak edges cost a model this much, softening Slovenia's edges until
they measure like India's should cost it a large part of the gap. The design
and the rules for reading it were committed before anything ran, in
`b1272f2`.

Slovenia's 185 labelled test chips were split at random into 60 for
calibration and 125 for scoring. On the calibration chips a Gaussian blur of
rising width, the same on the ground in both directions though Slovenian
pixels are 4.14 m wide and 6.00 m tall, was applied to every band of both
windows, and the median edge over interior measured as above. It falls
steadily, and meets India's 1.297 at 14.5 m. That is a heavy blur, smearing an
edge over roughly 34 m of ground. On the scoring chips the median at 14.5 m is
1.267, within the 0.05 the rules allowed. FTW v3 B7 and watershed at h 0.05
were then run on the scoring chips with no blur and at 14.5 m. With no blur
both reproduce the published per-parcel results exactly, all 4,286 parcels.

The reading is the share of the Slovenia to India gap that the blur closes,
(S0 - S1) / (S0 - I), with S0 and S1 Slovenia's recall without and with the
blur and I India's, by width band. For all parcels 20 m and wider, India's
recall is weighted to Slovenia's mix of widths. Intervals resample the scoring
chips 2,000 times. The rules called weak edges a credible main cause for a
method if the share is 0.5 or more with a lower end of 0.25 or more.

| method | band | Slovenia | blurred | India | share closed | reading |
|---|---|---:|---:|---:|---:|---|
| FTW v3 B7 | 20 to 30 m | 16.64% | 5.82% | 1.22% | 0.702 [0.593, 0.815] |  |
| FTW v3 B7 | 30 to 50 m | 38.34% | 17.52% | 4.96% | 0.624 [0.559, 0.693] |  |
| FTW v3 B7 | 50 m up | 69.32% | 49.66% | 31.11% | 0.514 [0.437, 0.607] |  |
| FTW v3 B7 | 20 m up | 43.95% | 26.09% | 13.41% | 0.585 [0.523, 0.666] | credible main cause |
| watershed | 20 to 30 m | 19.22% | 6.90% | 4.90% | 0.860 [0.718, 1.010] |  |
| watershed | 30 to 50 m | 45.31% | 20.29% | 22.49% | 1.097 [0.984, 1.225] |  |
| watershed | 50 m up | 69.13% | 55.90% | 41.33% | 0.476 [0.385, 0.566] |  |
| watershed | 20 m up | 47.23% | 29.68% | 24.78% | 0.782 [0.691, 0.890] | credible main cause |
| watershed, matched objects | 20 to 30 m | 19.22% | 10.77% | 4.90% | 0.590 [0.447, 0.723] |  |
| watershed, matched objects | 30 to 50 m | 45.31% | 28.07% | 22.49% | 0.755 [0.654, 0.861] |  |
| watershed, matched objects | 50 m up | 69.13% | 57.36% | 41.33% | 0.423 [0.308, 0.531] |  |
| watershed, matched objects | 20 m up | 47.23% | 34.20% | 24.78% | 0.581 [0.498, 0.665] | credible main cause |

The blur also cut the objects each method emits, FTW's from 18.2 per chip to
11.9 and watershed's from 298.5 to 118.2, and fewer, larger objects lose recall
on their own. FTW sets its own count, so its drop is how it responds to the
blur. Watershed's count is a setting, so after the first reading one more part
was added, marked as added in the script: watershed swept across h on the
blurred chips and read at its unblurred 298.5 objects per chip, as the budget
column reads every method. About a quarter of watershed's first share came
from the object count. What remains, 0.581, sits beside FTW's 0.585.

Two things limit what this shows. Blur lowers edge contrast and also smooths
texture inside and across fields, so watershed at 30 to 50 m falls below
India's own recall, which an edge effect alone would not do. And the blur is
calibrated on the edge measure, which agrees only weakly with two people's
eyes. So edge contrast at India's measured level is enough to cost FTW v3 more
than half of its gap in every width band, and watershed more than half below
50 m. The blurred chips stand in for India's on this one measure only, and
about two fifths of FTW v3's gap is left to something else.

*Source: `results/edge_test.csv` and `results/edge_test_matched.csv`, with the
calibration in `results/slovenia/edge_test_calibration.csv` and the per-parcel
and per-chip rows beside it.*

**Fine-tuning v3 B7 on India helps India a little and costs Slovenia.**
Every FTW figure so far is a released checkpoint, untouched.
`kaggle/finetune_v3.py` fine-tunes v3 full B7 on a free Kaggle GPU, from the
released weights, with v3's own loss, class weights and ignore index, at a
tenth of its learning rate, for 20 epochs. v3 had already trained on India,
whose masks mark fields and boundaries and leave everything else unknown, so
this tests more weight on India and not a first sight of it. One arm trains
on India's 1,261 labelled train chips alone. The other adds as many Slovenian
train chips each epoch, which carry the background India's labels lack. Each
arm keeps the epoch with the best recall on India's 300 val chips. The recipe
was committed in `543f646` with the readings in `src\finetune_score.py`,
before any training, and the test chips were then read once, through the same
code that scored v3.

The first run's files were lost when its Kaggle session ended. The recipe was
run again, unchanged, as a saved version, and it printed the same loss, val
recall and object count at every epoch of both arms, to every digit shown. The
first run's console is kept in `results/finetune/run1_console.txt`.

| country | checkpoint | objects per chip | recall | interval | null | above null |
|---|---|---:|---:|---:|---:|---:|
| india | v3 full b7 | 245.3 | 12.91% | [10.84, 15.27] | 2.50% | 10.41% |
| india | v3 b7 ft india | 108.8 | 15.13% | [12.93, 17.47] | 0.71% | 14.42% |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | [11.39, 15.79] | 1.13% | 12.44% |
| slovenia | v3 full b7 | 20.5 | 33.06% | [29.15, 36.64] | 0.58% | 32.48% |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | [16.91, 21.92] | 0.90% | 18.59% |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | [31.36, 38.81] | 0.67% | 34.51% |

| test | checkpoint | difference | interval | reading |
|---|---|---:|---:|---|
| T1 India recall minus v3 | v3 b7 ft india | +2.22 | [+0.86, +3.63] | helps on India, from better placed boundaries |
| T2 India above null minus v3 | v3 b7 ft india | +4.02 | [+2.62, +5.41] |  |
| T4 India over Slovenia minus v3 | v3 b7 ft india | 0.386 | [0.293, 0.489] |  |
| T5 Slovenia recall minus v3 | v3 b7 ft india | -13.57 | [-15.46, -11.64] |  |
| T1 India recall minus v3 | v3 b7 ft india+slovenia | +0.66 | [-0.60, +1.91] | no gain on India |
| T2 India above null minus v3 | v3 b7 ft india+slovenia | +2.03 | [+0.69, +3.31] |  |
| T4 India over Slovenia minus v3 | v3 b7 ft india+slovenia | -0.005 | [-0.046, 0.033] |  |
| T5 Slovenia recall minus v3 | v3 b7 ft india+slovenia | +2.12 | [+1.16, +3.33] |  |

The India arm meets T1 and T2: 2.22 points more Indian parcels, with an
interval from +0.86 to +3.63, and 4.02 more above its null. It draws 108.8
objects per chip where v3 drew 245.3, so the gain does not come from drawing
more. T3 reads watershed at that count, where it finds 5.71% and FTW leads by
9.42 points, the reverse of finding 19. The cost is Slovenia, down 13.57
points to 19.48% while drawing more objects there, 47.8 per chip against 20.5.
India's labels hold no background, and twenty epochs on them alone taught the
model less about what is not a field. T4 passes, the ratio of India to
Slovenia rising from 0.391 to 0.776, but it passes because Slovenia fell.
India's own recall moved 2.22 points.

The mixed arm keeps Slovenia, up 2.12 points to 35.18%, and fails T1 on India,
+0.66 with an interval from -0.60 to +1.91. It reaches v3's Indian recall with
141.1 objects per chip in place of 245.3, so T2 holds and watershed at that
count falls 5.40 points behind it. By the rules one arm helps and the other
does not, so the gain is reported for the India arm and not as an effect of
fine-tuning in general.

SAM was read at the same counts after the report above had been seen, so as
description only. SAM cannot draw fewer than about 129 to 155 objects on an
Indian chip, depending on the composite, so against the India arm it is read
there, with more objects than FTW:

| method, India | objects per chip | recall | minus FTW | interval | reading |
|---|---:|---:|---:|---:|---|
| v3 b7 ft india | 108.8 | 15.13% |  |  |  |
| SAM colour infrared | 155.3 | 14.52% | -0.61 | [-2.52, +1.46] | level |
| SAM NIR-blue-green | 146.8 | 13.87% | -1.26 | [-3.22, +0.71] | level |
| SAM natural colour | 135.4 | 12.96% | -2.17 | [-4.13, -0.10] | FTW ahead, stands under P2 |
| SAM blue-green-red | 128.7 | 12.15% | -2.98 | [-4.94, -1.01] | FTW ahead, stands under P2 |

With more objects and no lead, SAM no longer beats FTW on India once FTW has
been fine-tuned there. By ground width, the India arm's gain sits at 30 to 50
m, 4.96% to 7.50%, and above 50 m, 31.11% to 34.07%. Between 20 and 30 m it
finds one parcel more of 245.

Three limits. One recipe was run, with one learning rate and one seed, all set
in advance and none tuned, so a better recipe may exist. Each arm's kept epoch
is the best of 20 noisy val readings, which flatters its val figure; the test
chips were not part of that choice. And the fine-tuned weights inherit v3
FULL's noncommercial terms, so they are not published.

*Source: `results/finetune_scores.csv`, `finetune_tests.csv`,
`finetune_budget.csv`, `finetune_sam.csv` and `finetune_widths.csv`, the val
logs in `results/finetune/<arm>/`, and the per-chip and per-parcel rows in
`results/<country>/newer_ckpt/v3_b7_ft_*`.*

**Above the floor, the method is the lever.** Between three and ten native
pixels an untrained watershed finds between five and thirteen times as many
Indian parcels as the v1 checkpoint, and above ten pixels SAM finds three
times as many. Whatever is stopping FTW there is not a lack of signal, and its
v3 checkpoint recovers part of that ground (finding 18).

**The advice that follows differs by parcel size.** For Indian ground where
fields are under about 30 m across, nothing in this study recovers them at a
usable rate and the honest answer is that the problem is open. For ground above
that, the model is the lever: the v1 checkpoint left a great deal on the table,
v3 recovers part of it, and fine-tuning on India's own chips adds a little
more at the cost of Slovenia (finding 21). For large fields specifically, SAM at 50.79% is the first result
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
been shown a field. B-23 records which three channels each SAM figure used. Its Indian result says something about how much structure
the imagery carries, rather than something about foundation models for
agriculture. Published work exists on SAM for field boundaries from Sentinel-2,
including FieldSeg at 10 m and a Canadian prairies dataset built this way, none
of which has been read here beyond its title.

**That width is the only thing that matters.** The district work in stage 3
found Jodhpur, which holds more test parcels than any other district, 84, with
the widest parcels of any district holding 30 or more, 7.40 native pixels
median and none below the threshold, still at 0.048 recall, 4 of its 84.
That figure was first read from a profile scored the pre-S-08 way and holds
on the current scoring; the profile has been rewritten (errata round below). That was
written off as an anecdote until contrast was measured at national scale, and
it now reads as the first sighting of the effect in What this says rather than
as a curiosity.

**That the Slovenian margin is quantified.** Five of the seven figures at
Slovenia's object budget remain bounds, felzenszwalb and the four SAM
composites. Watershed has been measured there; the others have not. See B-08. Against v3, SAM loses while drawing
more objects, so v3's margin over SAM there does stand (finding 19).

**That v3 is the best FTW can do.** Only its B3 and B7 encoders were run. B5
and the standard-weight variants were not, and nothing here was fine-tuned.

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

**B-08. The Slovenian comparison at matched budget is mostly bounds.** No competing method was run coarse enough to reach 20 objects per
chip. The clamped figures are each method's value at its own coarsest setting,
which is above 20 in every case, so each overstates that method. FTW's Slovenian
win is wider than the table shows and the margin is not measurable from what has
been run. Watershed has since been measured there at 0.059, with its sweep
extended in `season_test.py`. The others remain bounds: felzenszwalb, and
since B-23 four SAM composites rather than two.

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
Slovenian recall as [21.24, 23.23] where resampling chips gives [18.56, 25.88].
No conclusion in this document turns on it, since the differences it reports
are five-fold and larger, and every interval was still too narrow.

---

**B-13. The label registration test was built twice before it worked.** The
first version translated each parcel's boundary band rigidly across a
49-offset window and kept the strongest gradient. It put 64% of parcels at the
edge of the search window, 33 of 125 exactly on its corner, and matched its own
null to within 2.7 m. The median Indian parcel is 6.2 grid pixels wide, so
shifting a band three pixels carries it onto the neighbours, and maximising
gradient over a rigid shift finds whichever direction holds more edges rather
than the parcel's own. The rewrite walks along the boundary normal instead, so
the ring follows the parcel however far it moves.

**B-14. The second version could not score the drawn position at all.** A
signed distance transform reads +1 on the first pixel outside a mask and -1 on
the last pixel inside, with nothing between, so the ring cut at radius zero
with half-width 0.5 selected no pixels. The drawn boundary scored nan on every
parcel and could never win, the reported gain printed as nan, and the smallest
displacement the run could report was one whole pixel. Both of these produced
confident-looking numbers and were caught by a sanity line in the output rather
than by the result looking wrong. The estimator now ships with a self-test
against known displacements.

**B-15. Boundary contrast was overstated by its denominator.** Dividing the
edge gradient by the chip's median put 33.5% of Indian boundaries below their
surroundings against 7.9% in Slovenia. Stage 2 found four of five Indian chips
are called mostly boundary, so that denominator is inflated by scene texture in
exactly the country the claim was about. Measured against each parcel's own
interior the Indian figure is 14.2%, less than half, while Slovenia barely
moves from 7.9% to 7.2%. The overstated pair was never published; it was
reported in working notes and corrected before it reached this document.

**B-16. The checkpoint was described as shattering Indian parcels.** It does
the opposite. It emits 175 objects per chip and leaves 74.4% of labelled
parcels with nothing touching them, while watershed at 676 objects reaches
every parcel and cuts 38.2% into five pieces or more. Finding 4 inferred
fragmentation from the object count without counting what the objects overlap.

**B-17. Selection optimism was assumed to matter and does not.** Every setting
in this document is the best of its sweep chosen on the reporting data, which
the review raised as a Major finding. Measured over 40 chip-level splits per
country it moves recall by at most +0.0066, and eleven of twelve method and
country pairs pick the same setting in every split.

**B-18. The two countries are not on the same kind of grid, and this project
assumed they were.** Fields of The World ships India on non-square degree
pixels chosen so that a pixel is square on the ground, 6.069 m by 6.068 m. It
ships Slovenia on square degree pixels, which at latitude 46.6 come out 4.138 m
across and 6.002 m tall, taller than wide by 1.450. `grid_pixel_m()` measures
the geodesic width of a chip and divides by its pixel count, so it returns the
east to west size and nothing else, and `seg_score.parcel_width_px` compounds
that by running a distance transform with no sampling argument, which counts a
step north as the same length as a step east. Correct on India by luck of how
FTW built it. Wrong on Slovenia in proportion to how the parcel is oriented.
Found by `src\grid_check.py`, written to close F-11, which the review had
filed as a formality.

**B-19. Every Slovenian parcel width was understated, and a third of them were
in the wrong band.** The corrected ground width runs 1.275x the published one
at the median and 1.505x at the ninetieth percentile. Slovenia's median parcel
is 30.4 m rather than 22.0 m, its share under 30 m is 49.7% rather than 64.9%,
and 2,280 of 6,831 parcels move band. India moves by 1.002x and no parcel
changes band, which is the control.

Nothing method-related moves, because no width enters a recall figure. What
moves is every table cut by width. The headline that Slovenia outperforms India
at matched ground width was **1.8 to 71.5 times** and is **1.7 to 41.0 times**:

<!-- check_tables: historical columns 3,4,5,6 -->
| band | India | Slovenia, was | Slovenia, after B-19 | ratio was | after B-19 |
|---|---:|---:|---:|---:|---:|
| 20 to 30 m | 0.41% | 12.89% | 7.81% | 31.6x | 19.1x |
| 30 to 50 m | 0.58% | 41.24% | 23.62% | 71.5x | 41.0x |
| 50 m up | 7.11% | 65.91% | 58.80% | 9.3x | 8.3x |

B-20 moved the 20 to 30 m row once more, to 7.89% and 19.3x. The conclusion
is unchanged and its size was overstated by up to 43%, the 30 to 50 m row
falling from 71.5x to 41.0x. Slovenia still beats India at matched ground width by every method in
every band, so resolution is still ruled out and so is label geometry.

The label registration walk carried the same fault, cutting its rings at whole
pixels, so the displacement figures reported before this were measuring
different ground distances in the two countries. Rings are now cut every six
metres and the transform is given `sampling`, so India reads +4.13 m and
Slovenia +3.80 m on the same basis. `src\width_ground.py` measures the
correction and `src\apply_width_fix.py` applies it to all 68 affected tables
per country, keeping the old column as `width_native_px_published`.

**B-20. The 500 square metre filter acted at 720 in Slovenia.** Every script
turned the filter into a pixel count by dividing by `grid_pixel_m()` squared,
the east to west size times itself. That is 17.1 m² in Slovenia, where a pixel
covers 24.8 m² of ground, so the filter dropped every object under 29 pixels,
720 m², for every Slovenian method and setting. India's pixels are square on
the ground, so its count is 14 either way and no Indian figure moves. Found
while documenting `object_count` for F-18.

Rerun at 20 pixels, recall moves by at most 0.006 anywhere. FTW stays at 0.222,
watershed's best goes from 0.345 to 0.348, felzenszwalb's from 0.209 to 0.214,
and both SAM composites move by under 0.001. FTW now emits 19.5 objects per
chip where it emitted 18.3, and its matched object share, which is precision
on Slovenia, falls from 44.91% to 42.06%: the objects the old filter removed
are small and mostly match nothing. Watershed's falls from 4.52% to 4.43%, so
the precision gap between the two was tenfold and is nine and a half times. In
the cross-country table the Slovenian 20 to 30 m figures move from 7.81% to
7.89% for FTW and from 20.91% to 21.32% for watershed, and the headline range
stays 1.7 to 41.0 times. The SAM rerun took about ten hours, and the log it
replaced is kept as `sam_raw_vit_h_p32_min500_at720m2.csv.gz`, compressed (P-02).

**B-21. Every Slovenian area was understated by 1.450, and a stage 1 claim
reverses.** Areas were computed the same way, pixel count times
`grid_pixel_m()` squared. `measure_fields.py` and `score_predictions.py` now
take each chip's own pixel area from `ftw_common.chip_pixel_xy_m`. Slovenia's
median untruncated parcel is 0.325 ha where it was published at 0.223 ha, and
42.62% of parcels sit under 5 by 5 native pixels where 53.56% was published.

`FINDINGS.md` said Slovenian parcels are smaller than Indian ones. By area
they are not: the medians are 0.325 ha and 0.303 ha. They are narrower, 30.4 m
against 42.3 m at the median (B-19), so for a similar area they are longer
strips, and more of them are very small, 20.26% under 3 by 3 native pixels
against 10.46%. The control argument survives in the form that matters, since
Slovenia still beats India at matched ground width in every band by every
method.

India moves too, by half a per cent, because area now comes from each chip's
own pixel where it came from the average of the first 80 chips. Its median is
0.303 ha where 0.302 ha was published. The regenerated Slovenian width tables
match `width_ground.py` on all 6,831 parcels to floating point precision, so
the scoring code now writes ground widths directly and `apply_width_fix.py` is
not needed for new runs.

**B-22. FTW's windows were said to follow a European calendar.** This document
and the README said the two seasonal windows were chosen for a European
calendar rather than a kharif and rabi one. FTW's own configuration for India
sets them at March to June and July to November 2016, so window_a does cover
kharif. The real problem is narrower: India's window_b is the dry season after
the rabi harvest, and no window covers December to February, when rabi crops
are standing. The statement was written without checking
`data_config_india.json` and was found when `season_test.py` printed the dates.
The test it called for has since run; see What this says.

**B-23. SAM was never given true or false colour.** FTW stores each window's
bands as red, green, blue and near infrared. The files name them `B04`, `B03`,
`B02` and `B08`, FTW's own downloader asks for them in that order, and on
India's dry-season chips band 1 is the brightest of the three visible bands,
as red is over bare soil. `sam_run.py` assumed blue came first. The composite
it called true colour therefore put blue in SAM's red channel and red in its
blue channel, and the one it called false colour gave SAM near infrared, blue
and green, where colour infrared is near infrared, red and green. Every SAM
figure in this document came from those two inputs. They are real measurements
of SAM on those inputs and are now labelled that way, as SAM ViT-H
blue-green-red and SAM ViT-H NIR-blue-green.

Both intended composites have since been run on every test chip, into the same
log, and the rerun reproduced every published value of the first two exactly.
On India at FTW's object count, colour infrared reaches 0.158 and natural
colour 0.152, against 0.153 and 0.151 for the first run, so the error moved
SAM's headline by half a point. The intended composites fit parcels more
closely: at SAM's loosest setting, median IoU rises from 0.127 to 0.149 on
colour infrared and from 0.051 to 0.089 on natural colour. In Slovenia natural
colour gains most, 0.295 against 0.276 at the loosest setting, and every SAM
figure there is still a ceiling at FTW's budget. Natural colour now carries the
cross-country table, the shape test and the budget figure, and colour infrared
carries the Indian headline and the map. Precision and fragmentation on the
100-chip subset, which finding 5 quotes, and the SAM row of the ring sweep were
rerun on colour infrared in the errata round of October 2026 and the reading of
each held; the first run's figures are kept beside them.

The same assumption reached three other places. The 20 crops on the contrast
panel were drawn with red and blue swapped, so the analyst judged them in
those colours. `contrast_panel.py` still draws that panel the same way when
redrawn from its key, and a second panel of 20 new parcels was drawn in
natural colour and judged in the errata round, with the same result. The figures from `figure_predictions.py`,
`figure_field_scale.py` and `compare_inputs.py` used bands 4, 3 and 2 as
colour infrared and so showed near infrared, blue and green; they are redrawn.
And the window table added for B-22 read band 1 as blue when it is red. It now
carries red, blue and NDVI, each read by name.

FTW, watershed, felzenszwalb, label registration and the edge contrast measure
are untouched, since each reads every band in file order. Every script now
looks bands up by their names in the file, through `ftw_common.band_index`.
Found while checking how a December to February image could be matched to
FTW's chips.

**B-24. The checkpoint tested was called the released state of the art after
FTW had replaced it.** Every FTW figure in stages 2 and 2b came from the v1
release of October 2024. FTW published v2 in September 2025 and v3 in November
2025, before this work began, and its own tools now list v1 as legacy.
`RESULTS.md` called v1 the current open state of the art, and the README and
its citation called it the released state of the art. On India v3 finds 12.91%
against v1's 2.72%. The comparison and its controls stand, and the headline is
now stated against v3 (findings 18 and 19). Found while checking what FTW
reports for India with and without fine-tuning.

**B-25. The data licence was given as CC BY 4.0 for all of FTW.** FTW's dataset
page lists a licence for each country's source labels, and FTW's README for the
Slovenian labels gives CC-BY-SA-4.0. The FULL checkpoints also carry the terms
of the noncommercial datasets they were trained on. The README's data table
and Reproducing below now say so. No number changes.

**B-26. SAM's objects per chip were averaged over parcels.** `sam_run.py` took
the mean of SAM's object count over parcel rows instead of over chips, so a
chip counted once for each labelled parcel it held. Every other method is
counted per chip. In India, where chips hold about five parcels each, this
moved SAM's counts by one object or less and no recall at three places. In
Slovenia, where chips hold 37 parcels on average and the number varies from
chip to chip, it overstated them by 15 to 18%. Colour infrared's coarsest
setting draws 74 objects per chip where 87 was published. For natural colour
it is 86 where 99 was published. Those figures were already ceilings at FTW's budget, so no
reading changes. The object counts in the sweep and budget tables and the
clamped notes are corrected. Found while drawing FTW v3 on the budget figure,
because `budget_newer.py` counts per chip and its SAM counts did not match the
tables.

**B-27. Two width bands reported an interval their label disowned.** Width
bands with fewer than ten found parcels are labelled as falling back to the
parcel-level interval, and `bootstrap_ci.py` says so in a comment and in its
`governs` column. The code took the union of the parcel and chip intervals for
every row all the same. Where the chip bootstrap reached lower, the reported
lower end came from it. In India the 20 to 30 m band reported 0.00 to 2.25%
where the parcel interval is 0.01 to 2.25%, and the 30 to 50 m band 0.12 to
1.34% where it is 0.19 to 1.34%. Those rows now report the parcel interval, as
labelled. No other row changes, no figure quoted elsewhere moves, and the
error only ever widened an interval.

**B-28. The edge gradient was ruled out by argument, not by test.** The width
band paragraph said a 1.2x deficit in edge gradient "cannot by itself explain a
6 to 29 times recall gap". A ratio of gradients and a ratio of recalls are on
different scales, and nothing tied one to the other, so the size of the first
said little about the second. Tested by softening Slovenia's edges until they
measure like India's (finding 20, and the edge test below), the deficit closes
0.585 of the gap for FTW v3 B7 and 0.581 for watershed at a matched object
count, over parcels 20 m and wider. The sentence is withdrawn and the
paragraph now cites the test. No figure changes.

### Errata round, October 2026

An audit of the repository at `4375154` on 12 October 2026 listed 25 problems
no document recorded, A-01 to A-25, and 13 stale passages in `src/`, D-01 to
D-13. They keep the audit's numbers here. Every logged correction above was
already fixed in the document that logged it; these are older files and
sentences the fixes never reached, and figures with no file behind them.

**A-01. The stage 3 district profile was stale.** `district_profile.csv` was
committed 37 seconds before the S-08 fix and never rewritten, so its recall
was scored against the eroded interior and pooled to 0.053 where the
project's figure is 0.027. It is rewritten on the current scoring, names its
checkpoint and scoring in two columns, and gives width and area in native
10 m pixels by name. It is also too thin for district claims: 133 districts
hold 1 to 17 test chips, median 2, and 4 to 84 parcels, median 10. The README
and `district_profile.py` now say it is a sampling map. Jodhpur's 0.048 holds
under both scorings, 4 of 84.

**A-02. India's row had dropped out of the stage 2 summary.**
`score_predictions.py` wrote `score_summary_3class_full.csv` fresh on every
run, so a Slovenia-only run on 3 October removed India's row while
`RESULTS.md` still cited it. It now replaces only the countries it scored, and
the file is regenerated with both; India's row returns exactly as last
published. The same run rewrote India's per-parcel table, whose areas still
used one pixel size for every chip. With each chip's own pixel area (B-21),
`hectares` moves by +0.57% at the median and +0.79% on average, from −1.66% to
+4.71%, and `native_10m_px` by +0.54% at the median. In
`score_bins_3class_full.csv` five size bins gain or lose a few parcels and two
bin recalls move, 0.0446 to 0.0445 and 0.0967 to 0.0945. No IoU or found value
changes, and no document quotes those bins.

**A-03. Finding 5 set two samples side by side.** "No object on 74.4%" is FTW
over all 1,983 Indian parcels; "FTW reaches 24.7%" is FTW over SAM's 494-parcel
subset, where the matching pair is 75.3% untouched. Each figure is now given
with its own sample, and "reaches" is said to mean an object overlaps the
parcel, which is short of finding it at IoU 0.5.

**A-04. Two precisions for one checkpoint on Slovenia.** `RESULTS.md`'s 0.240
and the 42.06% matched object share here count the same 1,518 matched objects
over different denominators, 6,322 unfiltered components on 228 chips against
3,609 filtered objects on the 185 labelled chips. Both documents now say so.

**A-05, A-06, A-16, A-24.** Counts that predated later work: five Slovenian
budget figures remain bounds, felzenszwalb and the four SAM composites B-23
left, where the text said three; eleven of twelve method and country pairs pick the same setting in every
split, not seven of eight; B-18 cut the cross-country ratios by up to 43%, not
forty per cent; and edge contrast was measured on 4,307 of 6,823 Slovenian
parcels, not 6,827.

**A-07, A-08, A-20, A-25.** `RESULTS.md` no longer opens by calling v1 the
state of the art. `FINDINGS.md` and `ftw_common.SOURCE` give the per-country
licence. A missing space in O-03 is restored. The hardware is a six-core CPU
with no GPU throughout; O-03 had said training was out of reach on a 2 GB GPU.

**A-09, A-22.** `REVIEW.md`'s acceptance table now shows each criterion at
`5b63eae` beside its state now, and its status section, dated 12 October,
says that Phases 1 to 6 describe the repository as first reviewed.

**A-10. The run manifest named the wrong commit.** It was written before the
commit holding its outputs, so it recorded the previous commit with
uncommitted changes. `run_manifest.py` now ignores its own file when checking
the tree, and the run order runs it after committing. The one fingerprint
that failed against a clone, `comparison_tables.md`, was line endings, not
content; see the follow-up below.

**A-11, A-13. Quoted figures with no file behind them.** `bootstrap_ci.py` now
writes `results/bootstrap_ci.csv` and `threshold_check.py` writes
`threshold_check.csv`, so the README's intervals and `RESULTS.md`'s
[0.01, 1.26] trace to files. FTW's unfiltered run is a row of
`precision_summary.csv`: 116,335 objects, 292.3 per chip, and 46,679 more than
the filtered run's 69,656.

**A-12. One recall, three intervals.** Known gaps now explains that each script
seeds its own chip bootstrap, so the same recall carries intervals differing in
the second decimal.

**A-14. The run order left out scripts that produced cited outputs.**
Reproducing now names every script that writes something a document cites,
including `pick_district.py`, whose `chip_district.csv` three others read,
and `build_map.py`, and lists the four diagnostics that write nothing cited.

**A-15, A-17, A-18, A-19, A-23.** `FINDINGS.md`'s short version gave 1,536 m
over 256 pixels as 6.07 m; it is 256 pixels of 6.067 m, about 1,553 m, and the
17 m against the labelling footprint is stated as unexplained. Its ring table
splits 2.00 to 3.00 pixels, 3.15%, from the 0.11% left unassigned beyond three.
Slovenia's section gives both pixel dimensions. SAM's subset is the first 100
test chips, 99 of them labelled. Three null draws "beat" FTW where two beat it
and one tied.

**A-21. `RESULTS.md`'s Slovenian width curve predated B-19.** Its table and
correlations came from widths measured on square pixels. On the corrected
widths Slovenian recall rises steadily from 0.5% under two pixels to 66.2% at
seven to ten, with no step between two and four, and the correlations are
+0.531 for width against +0.513 for area in Slovenia, +0.223 against +0.225 in
India. The section no longer claims that width shows a threshold where area
shows a gradient. India's row is unchanged.

**D-01 to D-13.** Thirteen docstrings, comments and printed messages carried
figures the documents had since corrected: Slovenia's edge-truncated parcels,
the median parcel area, label coverage, the field share each checkpoint
predicts, the cross-country range, SAM's timing and filtering equivalence, the
recall FTW's convention gives, references to an O-11 that does not exist, and
which map layers are flagged as clamped. Each now carries the current figure
and its file. None fed a result.

**Rerun in this round, readings set before running.** B-23 left three results
on the wrong SAM inputs. Each is rerun on what was intended.

- The 100-chip precision subset on colour infrared at 0.50. Finding 5 stands
  if SAM on colour infrared still covers more of the 494 parcels with exactly
  one object than FTW's 18.2%, at an object count within a quarter of FTW's
  175 per chip. If it does not, finding 5 is rewritten to what was measured.
- The SAM row of the ring sweep, on the same chips. F-12's statement for SAM
  stands if no cap moves its recall by more than two parcels in 494.
- A fresh blind contrast panel of 20 parcels the first never showed, drawn in
  natural colour, scored against the bars `contrast_panel.py` set before the
  first: 0.75 with p under 0.05 closes F-14, 0.60 is weak, and below 0.60 the
  documents stop calling the measure contrast.

All three have run.

- **Precision subset: finding 5 stands.** On colour infrared SAM emits 195.6
  objects per chip, 12% above FTW's 175, and covers 30.0% of the 494 parcels
  with exactly one object against FTW's 18.2%. It reaches 89.9% where FTW
  reaches 24.7%, against 91.3% on the first run's inputs. Its matched share,
  the floor on Indian precision, is 0.41% against 0.42%.
  `precision_sam_vit_h_cir_0p5_min500.csv` and `precision_summary.csv`.
- **Ring sweep: F-12's SAM statement stands.** 79 of 494 at the published cap,
  81 at 12 m and 80 at 18 and 24 m, so no cap moves SAM by more than two
  parcels. `ring_sensitivity_sam_cir.csv`.
- **Contrast panel: weak again.** In natural colour, on 20 parcels no earlier
  panel showed, the rank score is 0.650 with p = 0.14, against 0.655 and
  p = 0.16 on the first. Between 0.60 and 0.75, so F-14 stays scoped and the
  measure stays a difference between countries. `contrast_panel_scores.csv`.

So nothing now rests on the swapped composites except the first panel's marks,
which the second panel repeats.

**Follow-up, 13 October 2026.** A check of the round at `03717fb` found six
slips, N-01 to N-06, none changing a finding, table or figure.

- **N-01.** `build_comparison.py` wrote `comparison_tables.md` in text mode on
  Windows, where Python turns each line ending into CRLF, and
  `run_manifest.py` hashed those raw bytes, so the fingerprint never matched
  a clone, where git stores LF. `comparison_tables.md`, the one text output
  fingerprinted that way, failed on every clone; that was the whole of the
  A-10 mismatch, and its content matched. Text outputs are now hashed with LF
  line endings, and `build_comparison.py` writes LF. A `--compare` against a
  manifest from before this change reports those files as a change of kind,
  once.
- **N-02.** The A-02 entry above said parcel areas moved by about 0.1%. They
  moved by +0.57% at the median; it now gives the figures.
- **N-03.** `REVIEW.md`'s status section was edited on 13 October under a
  12 October date. It is dated 13 October.
- **N-04.** "About three points" covered two figures, 1.4 and 3.0 points.
- **N-05.** The four marked parcels measure 1.10 to 1.16, not 1.17.
- **N-06.** `sam_probe.py` still printed watershed's +0.197 and FTW's +0.008,
  the same stale figures D-07 fixed in `sam_run.py`. It prints +0.1955 and
  +0.0052 and names the file.

**Second follow-up, 13 October 2026.** A check at `dd33fbe` found three
descriptions of the manifest, M-01 to M-03, that no longer matched it.

- **M-01.** `run_manifest.py`'s docstring described two kinds of fingerprint.
  It now lists the text kind beside CSVs and other files, with the same six
  suffixes the code uses.
- **M-02.** The N-01 entry above put the CRLF in a Windows working copy. It
  now puts it in `build_comparison.py`'s output, where it came from, since git
  checks out LF on Windows too.
- **M-03.** `REVIEW.md`'s F-15 row said every output was hashed column by
  column. It now says only CSVs are.

**Polish list, 23 October 2026.** A list of four items on `fbc08ab` found one
fix, B-27 above, and three smaller things, P-01 to P-03.

- **P-01.** The README's first two findings now sit between
  `<!-- headline -->` and `<!-- /headline -->`, which GitHub does not show, so
  a check on the top-level README can compare its RS-02 figures against them.
- **P-02.** The superseded SAM log for Slovenia, 24.8 MB, is committed gzipped
  at 2.1 MB. Nothing reads it. `run_manifest.py` now hashes a `.csv.gz` on its
  text, so its column hashes are the ones the plain file had; only its name
  changes in the manifest.
- **P-03.** The two live SAM logs, 45.6 MB for Slovenia and 12.6 MB for India,
  stay plain, since `sam_run.py` appends to them as a resume log and stage 3
  may extend them. `budget_newer.py` and `null_strength.py` now read a
  `.csv.gz` in their place when the plain file is absent, so compressing them
  later is a change of file name and nothing else.

**Story round, 23 October 2026.** The README read as a study of FTW v1, two
releases old, with v3 in a later finding. It now leads with v3 wherever v3 was
measured. H-01 to H-04; no published figure changes.

- **H-01.** The README opens with a short summary: the question, the answer so
  far, three numbers and what to use today.
- **H-02.** Finding 3's width table gives FTW v3 B7 where it gave v1, with
  v1's ratios kept in the text, and a new figure,
  `figures/recall_by_width.png`, draws v3 and watershed by width in both
  countries. `src/figure_width.py` draws it and writes
  `results/recall_by_width.csv` from the per-parcel files, with intervals over
  whole chips or, below ten found parcels, at parcel level as B-27 has it.
- **H-03.** Finding 5 now gives v3 B7 beside v1: no object on 27.0% of Indian
  parcels against 74.4%, and 46.0% of the 126 fields over about 100 m found
  against 17.5%. The README's 50.8% for SAM on those fields had no generated
  file behind it. It is SAM on natural colour at the 0.50 threshold the width
  tables use; colour infrared gives 52.4%. Both are now in
  `results/reach_by_method.csv`, and the README names the composite. Findings 6
  and 7, measured with v1 only, now say so.
- **H-04.** The README counted 26 corrections after B-27 was added. It counts
  27.

---

## Known gaps

These come from the review in `REVIEW.md` and they change how the numbers above
should be read. The full list of 21 findings is in that document.

**The null at three draws, now measured at 200.** Closed. FTW's Indian gap is
+0.0063 against a null whose standard deviation is 0.0030, and 3 draws in 200
of random cells reached the checkpoint, two above it and one level. The direction holds and the
magnitude is now known. Run `src\null_strength.py` to reproduce it.

**Intervals treated parcels as independent, now measured by chip.** Closed, and
the correction is larger than expected. Resampling whole chips rather than
parcels widens FTW's Slovenian interval from [21.24, 23.23] to
[18.56, 25.88], which is 3.68 times wider, and its Indian interval from
[2.05, 3.54] to [1.71, 3.88], 1.45 times wider. Slovenia suffers more because
it carries about 37 parcels per chip against India's 5, so its parcels repeat
each other more. Every interval this project has published should be read at
the chip-level width. Run `src\bootstrap_ci.py` to reproduce it; it writes
`results/bootstrap_ci.csv`. Other scripts carry their own chip bootstrap with
their own seed and draw count, so the same recall shows slightly different
intervals in different tables: FTW v1's India figure is [1.71, 3.88] here,
[1.72, 3.89] in `season_ftw.csv` and [1.76, 3.88] in `newer_checkpoints.csv`,
and Slovenia's [18.56, 25.88], [18.52, 25.97] and [18.62, 25.99]. The
differences are resampling noise in the second decimal. Width bands
holding fewer than ten found parcels fall back to the parcel-level interval,
because a bootstrap over chips cannot resolve a tail it almost never samples.

**Every reported setting is the best of its own sweep.** Closed, and it was
worth at most +0.0066 of recall. See the held-out section above.

**Precision on India is a floor rather than a figure.** Closed as far as the
labelling allows. Fragmentation is measured in both countries and precision is
measured on Slovenia, where the cadastre is complete. India's 98.96%
unlabelled ground means its matched-object share can only bound precision from
below, and no amount of computation changes that.

**SAM's precision is not measured at all.** Its segmentations are not kept on
disk and a full pass costs 26 hours, so `precision.py` refuses rather than
guessing. The claim that SAM is the best method above ten native pixels
therefore rests on recall alone.

**Boundary contrast agrees weakly with the eye, and above chance.** It is
measured against each parcel's own interior, which removes the chip from the
comparison, and the machinery behind it passes a self-test against known
displacements. Checked blind against the author on two panels of 20 parcels it
scored 0.655 and 0.650, p = 0.16 and 0.14. A second person then judged those
40 and 20 more: 0.742 over 60, p = 0.0004, just under the 0.75 bar, with the
two people agreeing at kappa 0.67. It is a difference in edge sharpness
between countries and should not be read per parcel.

The edge test, finding 20, now checks the measure from the model side.
Blurring Slovenia until its edges read like India's by this measure costs FTW
v3 and watershed more than half of the gap, so the models respond to what the
measure reads. Whether the measure reads what a person sees is a separate
question, and the edge test cannot answer it, since its blur was set by the
measure. The second person answers it in part, and REVIEW F-14 stays
scoped.

**The measured grid is now reconciled, and it was wrong.** Not the
measurement itself, which was right about the east to west size, but the
assumption that one number describes a pixel. Slovenia's are 1.450 times taller
than wide. See B-18 and B-19. What is still not checked is the north to south
figure against anything FTW publishes, since the reconciliation here is against
the chips rather than against a specification.

**SAM on the intended composites, now run.** Natural colour and colour
infrared were run on every test chip in both countries, about 26 hours of CPU,
and moved SAM's Indian figure at FTW's budget by half a point (B-23). The
100-chip precision subset and the SAM row of the ring sweep were rerun on
colour infrared in October 2026; both readings held.

**Parcel shape and the seasonal windows, now tested.** Shape explains 3% of
FTW's country gap and none of the other methods'. India's dry-season window
costs FTW about two points of recall, a real effect and a small one. An image
from December to February was built for every chip in two seasons and does no
better than a second kharif image (finding 17). SAM on window_b was skipped
because watershed answers the same question.

**FTW's later checkpoints, now tested.** Seven checkpoints from v1 to v3.1
were run on every test chip, and watershed and SAM were read again at their
object counts (findings 18 and 19). v3 B5 and the standard-weight variants were
not run. No checkpoint was fine-tuned on India. FTW's own Table 5 reports a
model trained without India moving from 0.14 to 0.19 object recall when
fine-tuned on it, in FTW's scoring.

**The parcel reconstruction, now bounded.** FTW ships each parcel as an eroded
interior and a separate boundary class, and `ftw_common.full_fields` gives each
boundary pixel back to the nearest interior if one sits within three grid
pixels. Every area, width and recall figure here is measured against parcels
rebuilt that way, and the cap had only been checked on synthetic parcels.
Three grid pixels is about 18 m in India and, after B-18, between 12 m and
18 m in Slovenia depending on direction. `src\ring_sensitivity.py` rebuilds the
parcels with the cap at 12, 18 and 24 m of ground on each chip's own pixel
size, scores the same segmentations against every version, and checks that
the published cap reproduces the published recall to the fourth decimal. It
does, for every method in both countries.

India, 1,983 test parcels:

| cap | ring left out | median area | median width | under 30 m | FTW 3-class FULL recall | watershed recall | felzenszwalb recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 px, published | 0.17% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0842 |
| 12 m | 4.03% | 0.314 ha | 42.3 m | 22.29% | 0.0272 | 0.2471 | 0.0837 |
| 18 m | 0.21% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0837 |
| 24 m | 0.13% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0837 |

Slovenia, 6,831 parcels:

| cap | ring left out | median area | median width | under 30 m | FTW 3-class FULL recall | watershed recall | felzenszwalb recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 px, published | 1.07% | 0.315 ha | 30.4 m | 49.66% | 0.2222 | 0.3484 | 0.2137 |
| 12 m | 1.83% | 0.315 ha | 30.4 m | 49.76% | 0.2227 | 0.3467 | 0.2136 |
| 18 m | 0.89% | 0.317 ha | 30.4 m | 49.64% | 0.2222 | 0.3474 | 0.2137 |
| 24 m | 0.68% | 0.317 ha | 30.4 m | 49.61% | 0.2222 | 0.3474 | 0.2137 |

No recall moves by more than 0.0017 across the caps, and no median width by
more than 0.1 m. The one visible effect is India at 12 m, where 4.03% of the
ring goes unassigned and the median area falls by about 3%. The cross-country
comparison, which is the claim the cap could most plausibly have bent:

| cap | ground width | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| 3 px, published | 20 to 30 m | 1/245, 0.41% | 97/1,229, 7.89% | 19.3x |
| 3 px, published | 30 to 50 m | 5/867, 0.58% | 411/1,740, 23.62% | 41.0x |
| 3 px, published | 50 m up | 48/675, 7.11% | 999/1,699, 58.80% | 8.3x |
| 12 m | 20 to 30 m | 1/228, 0.44% | 97/1,221, 7.94% | 18.1x |
| 12 m | 30 to 50 m | 5/867, 0.58% | 416/1,737, 23.95% | 41.5x |
| 12 m | 50 m up | 48/674, 7.12% | 998/1,695, 58.88% | 8.3x |
| 18 m | 20 to 30 m | 1/244, 0.41% | 97/1,224, 7.92% | 19.3x |
| 18 m | 30 to 50 m | 5/867, 0.58% | 415/1,745, 23.78% | 41.2x |
| 18 m | 50 m up | 48/675, 7.11% | 996/1,695, 58.76% | 8.3x |
| 24 m | 20 to 30 m | 1/245, 0.41% | 97/1,223, 7.93% | 19.4x |
| 24 m | 30 to 50 m | 5/867, 0.58% | 415/1,747, 23.76% | 41.2x |
| 24 m | 50 m up | 48/675, 7.11% | 996/1,695, 58.76% | 8.3x |

The ratios sit between 18.1 and 19.4 times, 41.0 and 41.5 times, and at 8.3
times in every case. The Indian counts behind them are small, 1 and 5 parcels
found in the two narrower bands, and that is true at every cap, so the cap is
not what makes them fragile.

SAM keeps no segmentations, so it was regenerated for the sweep on the first
100 Indian test chips, the ones `precision.py` used, at 0.50. On the first
run's near infrared, blue and green, the published cap reproduces the main run
on those chips exactly, 80 of 494 parcels and a recall of 0.1619, which also
shows the regeneration is deterministic. At 12 m it finds one parcel more,
0.1640, and at 18 and 24 m it is back at 0.1619. On colour infrared, rerun in
October 2026 from the segmentations `precision.py` cached, the published cap
reproduces the main run's 79 of 494, 0.1599; 12 m finds 81 and 18 and 24 m
find 80. No cap moves SAM by more than two parcels on either input.

This bounds the reconstruction. Validating it still needs parcels digitised
independently of FTW.

**What produced these numbers, now recorded.** `src\run_manifest.py` writes
`results/run_manifest.json`: the git commit, the interpreter, every package
pinned in `requirements.txt` against its installed version, the SHA-256 of each
checkpoint in `models/`, every seed set in `src/` with its line, and a hash of
every output, column by column for a CSV. In the project's `.venv`, Python
3.11.9, all 15 pins match. The seeds that drive runs are date-style constants
set when each script was written, so the two the review flagged differ because
their scripts were written a day apart. Two small fixed seeds sit outside that
pattern: 11 for the label registration self-test, and 12345 for the contrast
panel's permutation test, which is where the p = 0.16 in F-14 comes from.

The compiled-module cache showed both the system Python 3.14 and the `.venv`'s
3.11 loading this code between 21 and 23 September, so outputs written in those
days could have come from either. Every script that wrote outputs then was
rerun under the `.venv` and compared with a manifest taken beforehand: the
Indian sweep at every setting, Indian precision and held-out selection, ground
widths and label registration in both countries, and the 200-draw null. Of 222
recorded outputs, 179 came back byte for byte identical. In the 42 Indian sweep
tables every IoU, recall and width column is identical, and only `hectares` and
`native_10m_px` moved, by the per-chip pixel area B-21 introduced.
`precision_summary.csv` came back with the same three rows in a different
order, because `precision.py` appended the row it rewrote; it now sorts. The
Indian SAM run was not repeated at 16 hours, but the F-12 subset reproduced it
exactly on the first 100 test chips, 99 of which carry labels. No reported
number depends on which interpreter wrote it.

---

## Reproducing

Open data throughout. Field labels and imagery from Fields of The World, under
the licence FTW lists for each country (B-25), FTW's released checkpoints from
v1 to v3.1, and the Meta SAM checkpoint under Apache 2.0. District polygons from geoBoundaries under CC BY 4.0. The
December to February images are Copernicus Sentinel-2 L2A scenes read from
Microsoft's Planetary Computer, listed scene by scene in `rabi_scenes.csv`.

Stage 1's commands close `FINDINGS.md` and stage 2's close `RESULTS.md`; this
block continues from them, and with those two it names every script in `src/`
that writes something a document cites.

```
python src\compare_inputs.py --countries india,slovenia --chips 40
python src\verify_against_ftw.py --classes 3 --tag _full
python src\compare_segmenters.py --country india
python src\compare_segmenters.py --country slovenia
python src\sam_probe.py --country india --limit 8
python src\sam_verify_filter.py --country india --limit 4
python src\sam_run.py --country india --model vit_h --composites true,false
python src\sam_run.py --country slovenia --model vit_h --composites true,false
python src\sam_run.py --country india --model vit_h --composites rgb,cir
python src\sam_run.py --country slovenia --model vit_h --composites rgb,cir
python src\grid_check.py --country india
python src\grid_check.py --country slovenia
python src\width_ground.py --country india
python src\width_ground.py --country slovenia
python src\apply_width_fix.py --country india
python src\apply_width_fix.py --country slovenia
python src\build_comparison.py
python src\null_strength.py --country india --method ftw --draws 200
python src\label_registration.py --self-test
python src\label_registration.py --country india
python src\label_registration.py --country slovenia
python src\parcel_contrast.py --country india
python src\contrast_panel.py --country india --redraw
python src\contrast_second.py --part redraw
python src\contrast_second.py --part score --force
python src\ring_sensitivity.py --country india
python src\ring_sensitivity.py --country slovenia
python src\shape_test.py
python src\season_test.py --country india
python src\season_test.py --country slovenia
python src\rabi_probe.py --part availability
python src\rabi_probe.py --part match --chips 3
python src\rabi_download.py --season 2016-17
python src\rabi_download.py --season 2015-16
python src\rabi_test.py --season 2016-17
python src\rabi_test.py --season 2015-16
python src\newer_checkpoints.py --part download
python src\newer_checkpoints.py --part run
python src\newer_checkpoints.py --part report
python src\budget_newer.py --part watershed
python src\budget_newer.py --part report
python src\edge_test.py --part calibrate
python src\edge_test.py --part run
python src\edge_test.py --part report
python src\edge_test.py --part matched
python src\finetune_score.py --part check
python src\finetune_score.py --part run
python src\finetune_score.py --part report
python src\finetune_score.py --part sam
python src\precision.py --country india --method ftw
python src\precision.py --country india --method ftw --min-size-m2 0
python src\precision.py --country india --method watershed --setting 0.02
python src\precision.py --country india --method sam --composite false --limit 100
python src\precision.py --country india --method sam --composite cir --limit 100
python src\ring_sensitivity.py --country india --methods sam --limit 100
python src\ring_sensitivity.py --country india --methods sam --limit 100 --composite cir
python src\precision.py --country slovenia --method ftw
python src\precision.py --country slovenia --method watershed --setting 0.05
python src\holdout.py --country india
python src\holdout.py --country slovenia
python src\bootstrap_ci.py --country india --by-width
python src\bootstrap_ci.py --country slovenia --by-width
python src\figure_budget.py
python src\figure_width.py
python src\pick_district.py
python src\district_profile.py
python src\district_plan.py
python src\threshold_check.py --country india
python src\threshold_check.py --country india --width-file parcel_width_seg_watershed_min500.csv
python src\threshold_check.py --country india --width-file parcel_width_seg_ftw_min500.csv
python src\reconcile_ftw.py --country india
python src\build_map.py
python src\build_comparison.py
python src\check_tables.py
python src\check_style.py --triples
python src\run_manifest.py
```

`pick_district.py` writes `chip_district.csv`, which `district_profile.py`,
`district_plan.py` and `threshold_check.py` read, so it runs before them.
`run_manifest.py` runs last and after committing, so the commit it records is
the one holding the outputs it hashes. Four scripts are diagnostics that
print and write nothing a document cites: `diagnose_download.py`,
`explore_ftw.py`, `inspect_ftw_api.py` and `inspect_inference.py`.
`contrast_panel.py` without `--redraw` draws a fresh blind panel and retires
the current one, so it is not part of a rerun.
`contrast_second.py --part draw` refuses once its key exists and `judge`
asks a person for answers, so a rerun redraws the images and scores the saved
sheets.
`finetune_score.py` needs the two checkpoints `kaggle/finetune_v3.py` writes
on a Kaggle GPU, as its docstring describes; they are not committed.
`edge_test.py` runs its parts in the order listed, each reading the one
before, and `matched` reuses its saved sweep unless given `--redo`.

The nulls are seeded, so the comparison runs reproduce to the digit. Runtime on
a CPU-only machine is about 27 minutes for India and 25 for Slovenia on the
classical sweep. SAM is about 16 hours for India and 10 for Slovenia across both
composites, at roughly 75 seconds per chip per composite, and each 100-chip
precision subset about two hours, which its ring sweep then reuses from
`data/sam_cache/`, and `sam_run.py`
appends as it goes so an interrupted run resumes. `season_test.py` takes about
ten minutes per country, `rabi_download.py` 30 to 60 minutes a season and
`rabi_test.py` about 15, `newer_checkpoints.py` about 20 for seven
checkpoints and `budget_newer.py` about 5. `build_comparison.py` takes
seconds and reads only the CSVs.

Outputs land in `results/<country>/`:

| file | what it holds |
|---|---|
| `segmenter_comparison_min500.csv` | one row per classical method and setting |
| `sam_comparison_vit_h_min500.csv` | one row per SAM composite and setting |
| `sam_raw_vit_h_p32_min500.csv` | per-chip SAM output, the resume log |
| `score_parcels_seg_<method>_min500.csv` | per-parcel IoU |
| `parcel_width_seg_<method>_min500.csv` | the same with the width column |
| `parcel_contrast.csv` | per-parcel edge over chip median, superseded by `label_registration.csv` (B-15); carries its measure and gradient build |
| `null_draws_ftw.csv` | every null draw behind finding 3 |
| `label_registration.csv` | per-parcel edge displacement and contrast |
| `contrast_panel_key.csv` | the 20 parcels on the natural colour panel, with their values |
| `contrast_panel_key_spent_2.csv` | the first scored panel, drawn with red and blue swapped |
| `contrast_panel_key_spent_1.csv` | the earlier panel, spent without a valid score |
| `contrast_panel_scores.csv` | the analyst's marks and the rank score |
| `contrast_second_key.csv` | the 60 parcels shown to the second person, with their values and source panel |
| `contrast_second/sheet_second.csv`, `sheet_author.csv` | each judge's y or n per parcel |
| `contrast_second_answers.csv` | the key with both judges' answers |
| `contrast_second_scores.csv` | the rank score per judge, over all 60 and per source panel |
| `contrast_second_agreement.csv` | agreement and kappa between the two judges |
| `ring_sensitivity_truth.csv` | parcel area, width and unassigned ring at each reconstruction cap |
| `ring_sensitivity.csv` | recall by method at each cap |
| `ring_sensitivity_bands.csv` | recall by method and ground width band at each cap |
| `precision_<method>_min500.csv` | per-parcel fragmentation, and object counts |
| `precision_summary.csv` | one row per precision run, with its object count, including FTW unfiltered |
| `ring_sensitivity_sam.csv`, `ring_sensitivity_sam_cir.csv` | SAM recall at each cap on the first 100 test chips, per composite |
| `threshold_check.csv` | the recall intervals by district group and width that `RESULTS.md` quotes |
| `district_profile.csv` | stage 3 sampling map, per district: chips, parcels, width and FTW v1 recall |
| `chip_district.csv` | the district each chip falls in, from geoBoundaries |
| `holdout_selection.csv` | what choosing a setting on the reporting data cost |
| `parcel_width_ground.csv` | parcel width in metres on rectangular pixels |
| `scorer_reconciliation.csv` | truth and prediction combinations, for S-08 |
| `season_ftw.csv` | FTW recall with its two windows rearranged four ways |
| `season_ftw_parcels.csv` | per-parcel IoU for each arrangement |
| `season_watershed.csv` | watershed on each window, every setting to h 0.6 |
| `season_watershed_budget.csv` | the same, read at FTW's object count |
| `season_windows.csv` | per chip and window, red, blue, NDVI and edge strength |
| `rabi_availability.csv` | India only: December to February scenes per chip, both seasons |
| `rabi_match.csv` | India only: FTW's chips rebuilt from every archive scene tried |
| `rabi_scenes.csv` | India only: the rabi scene used per chip, with its chip cloud |
| `rabi_test_<season>_*.csv` | India only: FTW and watershed given the rabi image |
| `newer_ckpt/<checkpoint>_chips.csv` | per chip, each FTW checkpoint's parcels, hits, objects and null |
| `newer_ckpt/<checkpoint>_parcels.csv` | per parcel IoU and width for each checkpoint |
| `watershed_chips_min500.csv` | per chip, watershed hits and objects at every setting to h 0.6 |
| `probe/` | the 5-chip ViT-B timing probe that chose ViT-H |

`shape_test.csv` and `shape_test_bands.csv` sit in `results/` itself, since
they compare the two countries, as does `bootstrap_ci.csv`, the chip-level
intervals for both, and so do `newer_checkpoints.csv`, its
`_changes`, `_gap` and `_widths` tables, and `budget_newer.csv`.

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
