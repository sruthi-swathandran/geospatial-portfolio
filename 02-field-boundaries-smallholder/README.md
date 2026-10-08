# Field boundaries for Indian smallholdings from Sentinel-2

Running a published field-boundary model on new ground is easy. The hard part
is working out whether a poor result means the imagery is too coarse or the
model is wrong, because the two lead to opposite advice: buy finer imagery, or
change method. This project separates them for Indian smallholdings, using
Fields of The World (FTW) with Slovenia as the control.

This page is the summary. `COMPARISON.md` has the full method, every table and
the corrections log. The [interactive map](https://sruthi-swathandran.github.io/geospatial-portfolio/02-field-boundaries-smallholder/docs/) puts every test chip on the
ground and shows what each method found on it.

---

## What holds

**1. On India the method fails, and the imagery carries more than it finds.**
The released FTW checkpoint recovers 2.7% of labelled Indian parcels. Read at
the same object count the checkpoint emits, 175 per chip, methods never trained
on a field boundary do better:

| method, India, at 175 objects per chip | recall |
|---|---:|
| SAM ViT-H, colour infrared | 0.158 |
| watershed | 0.107 |
| felzenszwalb | 0.031 |
| FTW 3-class checkpoint | 0.027 |

SAM on natural colour reaches 0.152. Its first run was given the wrong bands,
because the code took FTW's band order to start with blue, and reached 0.153
and 0.151. Rerun on the composites intended, the result barely moved (B-23).

The checkpoint barely clears chance. Random Voronoi cells at the same count,
which never see the imagery, average 0.0209 over 200 draws, and 3 of those 200
draws beat it.

**2. On Slovenia the same checkpoint works.** It recovers 22.2% of parcels from
20 objects per chip, and 42.1% of the objects it emits match a real parcel,
against 4.4% for watershed. Slovenia has a complete cadastre, so that is
precision. Read at the same 20 objects per chip, watershed recovers 5.9%. FTW
is a good model failing on India.

**3. Resolution does not explain the Indian failure.** Both countries are the
same 10 m Sentinel-2. If the imagery set the limit, a parcel of a given ground
width would be found about as often in each. It is not:

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| 20 to 30 m | FTW | 0.41% | 7.89% | 19.3x |
| 30 to 50 m | FTW | 0.58% | 23.62% | 41.0x |
| 50 m up | FTW | 7.11% | 58.80% | 8.3x |
| 30 to 50 m | watershed | 22.49% | 47.64% | 2.1x |
| 50 m up | watershed | 41.33% | 71.10% | 1.7x |
| 30 to 50 m | SAM ViT-H natural colour | 9.23% | 34.48% | 3.7x |
| 50 m up | SAM ViT-H natural colour | 36.44% | 68.57% | 1.9x |

Slovenia wins every band by every method, 1.7 to 41.0 times. Its labelled
parcels are also narrower than India's, 30.4 m against 42.3 m at the median.

**4. Neither do the Indian labels.** India's labels are hand-drawn, five per
chip. Measured against the image gradient, among parcels over 50 m across they
sit closer to the visible edge than Slovenia's, +1.81 m against +2.23 m, and
India is still found 8.3 times less often.

**5. The checkpoint misses Indian parcels.** It puts no object at all on 74.4%
of them. SAM, spending a similar budget on 100 test chips, reaches 91.3% of
labelled parcels where FTW reaches 24.7%, measured on its first run's inputs.
On the largest Indian fields, over about 100 m across, SAM recovers 50.8%
against FTW's 17.5%, the one result here close to practical use.

**6. Nor does parcel shape.** Slovenian parcels are more strip-like than
India's. Given India's mix of widths and shapes, Slovenia is still found 10.7
times as often by FTW, against 11.5 times when only widths are matched.

**7. Nor does the season, beyond a small part.** FTW's second image for India
is from March to June, the dry months after the rabi harvest, and it works
against the checkpoint. Given the kharif image twice instead, FTW finds 4.79%
of Indian parcels against 2.72%. An image from December to February, when
rabi crops are standing, helps by the same amount and no more, in both rabi
seasons tested. The best arrangement still leaves India about four times
below Slovenia.

**What is still open** is why the checkpoint does not read Indian field edges.
Width, shape, label placement and season are each measured and none explains
the gap. The labelled Indian boundaries carry a weaker image gradient than
Slovenia's, 1.297 times their interior against 1.588, but a blind check
against one analyst agreed with that measure only weakly. Given the rabi image
alone, FTW does no better than as shipped while watershed finds about as many
boundaries in it as in kharif, so the edges are in the imagery and the model
does not use them. India was in the checkpoint's training data, which makes
that harder to explain, and retraining on Indian chips is the test not yet
run.

![Recall against objects emitted per chip](figures/recall_by_object_budget.png)

---

## Why the comparison is at a matched object count

Recall rewards producing more objects: a method that cuts a chip into six
hundred pieces has better odds of one fitting a parcel. The first version of
this comparison let each method choose its own count, and watershed appeared to
beat FTW. Every figure here is read at the checkpoint's own count, beside a
random-cell null at the same count, after FTW's own 500 m² minimum object size
is applied to every method. `COMPARISON.md` explains each control.

---

## Limits

- **Indian labels are presence-only.** Five parcels per chip are drawn and
  98.96% of each chip carries no label, so India gives recall and only a floor
  on precision.
- **Most Slovenian figures at the budget are bounds.** Watershed has been
  measured there. Felzenszwalb and SAM were not run coarse enough to reach 20
  objects per chip.
- **The parcel reconstruction is bounded, not validated.** FTW erodes each
  parcel's edge and this project gives it back. Varying that step moves no
  recall by more than 0.0017, but it has never been checked against
  independently digitised parcels.
- **A few SAM figures rest on its first run.** Precision on 100 chips and the
  reconstruction sweep used near infrared, blue and green (B-23).
- **The contrast measure rests on one analyst's eye** and 20 parcels.
- **Settings were chosen on the data they are reported from.** Measured on 40
  held-out splits, that is worth at most 0.0066 of recall.
- **Intervals resample whole chips**, since parcels in one chip share a scene.
  FTW's headline figures are 2.72% [1.71, 3.88] in India and 22.22%
  [18.56, 25.88] in Slovenia.

---

## How far to trust it

`REVIEW.md` is a technical review of the project written with an AI
assistant, Claude. It is not independent peer review. It lists 21 findings,
and every one is now closed or scoped with the reason stated.

`COMPARISON.md` carries 23 corrections, B-01 to B-23, each with the published
value, the corrected one and why the first was wrong. The largest: FTW ships Slovenia on pixels 4.14 m across and 6.00 m
tall, and treating them as square had overstated the cross-country gap by up to
forty per cent. The conclusion survived the correction.

Two checks guard the numbers. `src\check_tables.py` fails if any number in a
table in `COMPARISON.md` cannot be traced to a table generated from the result
files. `results/run_manifest.json` records the interpreter, package versions,
checkpoint hashes, seeds and a hash of every output, and
`src\run_manifest.py --compare` says whether a rerun reproduced them.

---

## Data and running it

Open data only. Nothing here comes from any private, client or internal source.

| source | what | licence |
|---|---|---|
| [Fields of The World](https://source.coop/kerner-lab/fields-of-the-world) | chips, labels, released checkpoints | CC-BY-4.0 |
| Copernicus Sentinel-2 | the imagery behind the chips | Copernicus / ESA terms |
| Copernicus Sentinel-2 L2A via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) | the December to February images | Copernicus / ESA terms |
| [Segment Anything](https://github.com/facebookresearch/segment-anything) | SAM ViT-H checkpoint | Apache 2.0 |
| [geoBoundaries](https://www.geoboundaries.org/) | district polygons | CC BY 4.0 |
| [Sentinel-2 cloudless 2020](https://s2maps.eu) by EOX | background of the interactive map only | CC BY-NC-SA 4.0 |

399 Indian test chips and 228 Slovenian, 1,983 and 6,831 labelled parcels,
scored by object recall at IoU 0.5. CPU only, Python 3.11.9:

```
pip install torch==2.14.0 torchvision==0.29.0 ^
    --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The full run order is at the end of `COMPARISON.md`. The classical sweep takes
about half an hour per country and SAM about 16 hours for India.

`FINDINGS.md` measures the reference data before any model runs, `RESULTS.md`
runs FTW against it, `COMPARISON.md` sets the other methods beside it, and
`REVIEW.md` is the technical review of all three.

Stage 3, a district-level breakdown across Indian agro-climatic zones, is
started and not finished.

---

## Licence and citation

Code is released under the MIT Licence. The data carry their own terms, listed
above. This work contains modified Copernicus Sentinel data, processed through
the Fields of The World benchmark.

Suggested citation:

> Swathandran, S. (2026). *Field boundaries for Indian smallholdings from
> Sentinel-2: what the released state of the art recovers, and what an untrained
> baseline recovers beside it.*
> github.com/sruthi-swathandran/geospatial-portfolio

Questions and issues: please open a GitHub issue on this repository.
