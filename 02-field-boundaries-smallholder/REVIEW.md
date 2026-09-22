# Technical review: RS-02 field boundaries for smallholdings

Reviewed twice over. Once as a senior remote sensing scientist would read an
internal method study before it goes to a programme board, and once as a
journal editor would read a submission. Findings are against
`02-field-boundaries-smallholder` at commit `5b63eae` plus 125 uncommitted
files.

Everything below was checked against the repository's own artefacts. Where a
number in this review differs from a number in the write-up, the computation is
given so you can rerun it.

**Verdict on the editorial test: NO.** The write-up describes a three-method
study. The repository holds a four-method study. The two disagree on which
methods were run, on three headline numbers, and on the paper's central claim.

**Verdict on the scientific claim.** The measurement work is careful and in
several places better than what the literature it is arguing with does. The
controls you invented, the null at matched object count and the matched object
budget, are the strongest part of it. The conclusion drawn from that work,
that the failure on India is a resolution floor belonging to the imagery, is
contradicted by the project's own data and has to be withdrawn or scoped.

---

## Phase 1. Inventory

| Item | State |
|---|---|
| Source modules in `src/` | 27 |
| Write-ups | `FINDINGS.md` (stage 1), `RESULTS.md` (stage 2), `COMPARISON.md` (stage 2b) |
| README | **absent**, at repo root and in RS-02 |
| Last commit | `5b63eae` RS-02 stage 2b: SAM ViT-H on Slovenia, the control |
| Uncommitted | 125 files (4 modified scripts, 2 modified tables, 119 untracked) |
| Figures | 5 PNGs, all from stage 2. Nothing from stage 2b |
| Dependency record | root `requirements.txt`, header states it covers RS-01 |
| Interpreters used | cpython-311 and cpython-314, both present in `src/__pycache__` |
| Credentials | none found anywhere |
| Licence | present at repo root |

Data and model weights are correctly excluded. `02-field-boundaries-smallholder/.gitignore`
carries `data/`, `models/`, `results/*/pred_*/`, and the root ignore adds
`*.tif` and `.venv/`. The 2.4 GB SAM checkpoint and the three FTW checkpoints
are outside version control, which is right.

### Open data compliance

Clean. Every input traces to Fields of The World under CC-BY-4.0, the FTW
released checkpoints, Sentinel-2 via the FTW chips, and the Meta SAM checkpoint
under Apache 2.0. No parcel data, client labels, internal imagery or scheme
data appears anywhere in `src/`, `results/` or the write-ups. I looked.

---

## Phase 2. Methodological audit

### What holds up

**The scoring convention is now consistent.** S-08 was a real two-fold error
and finding it by building a second independent scorer, rather than by staring
at the first, is the right instinct. `reconcile_ftw.py` earns its place in the
repository.

**The two controls are the contribution.** Most published segmentation
comparisons report recall at whatever settings each method happened to use, so
a method that emits 900 objects per chip appears to beat one that emits 175.
The Voronoi null and the matched object budget both close that hole, and they
close it in different directions, which is why having both matters. Slovenia
exposing the null as insufficient on its own, and the budget column being added
in response, is the study correcting itself mid-flight.

**The SAM threshold sweep is exact.** Three rounds of `sam_verify_filter.py`
to establish that loose generation then filtering reproduces a strict run
exactly, ending at 0 masks lost of 985, is more rigour than the SAM literature
usually applies to its own ablations. Pinning stability at 0.88 once sweeping
it broke exactness was the correct call.

**The grid measurement.** Measuring pixel ground size geodesically rather than
trusting a metadata field, then normalising to 10 m, catches a confound that a
lot of cross-country benchmark work walks straight into.

### What does not hold up

#### The central claim is contradicted by the project's own data

`COMPARISON.md` line 233 states: *"The three-pixel floor belongs to the
imagery. Two methods with nothing in common both collapse below it, and the one
that reads the imagery well elsewhere collapses there too."*

Both countries are the same Sentinel-2 at 10 m. If a floor belongs to the
imagery, then two parcels of the same physical width, in the same sensor,
scored by the same method, should be found at about the same rate whichever
country they sit in. They are not. Recall at matched ground width, IoU 0.5,
all three methods, computed from `parcel_contrast.csv` joined to each method's
`parcel_width_*.csv`:

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| under 20 m | FTW checkpoint | 0/196, 0.00% | 42/2,842, 1.48% | - |
| 20 to 30 m | FTW checkpoint | 1/245, 0.41% | 205/1,590, 12.89% | 31.6x |
| 30 to 50 m | FTW checkpoint | 5/867, 0.58% | 520/1,261, 41.24% | 71.5x |
| 50 m up | FTW checkpoint | 48/675, 7.11% | 750/1,138, 65.91% | 9.3x |
| under 20 m | watershed | 2/196, 1.02% | 154/2,842, 5.42% | 5.3x |
| 20 to 30 m | watershed | 12/245, 4.90% | 572/1,590, 35.97% | 7.3x |
| 30 to 50 m | watershed | 195/867, 22.49% | 799/1,261, 63.36% | 2.8x |
| 50 m up | watershed | 279/675, 41.33% | 832/1,138, 73.11% | 1.8x |
| under 20 m | SAM ViT-H true | 0/196, 0.00% | 79/2,842, 2.78% | - |
| 20 to 30 m | SAM ViT-H true | 4/245, 1.63% | 312/1,590, 19.62% | 12.0x |
| 30 to 50 m | SAM ViT-H true | 53/867, 6.11% | 481/1,261, 38.14% | 6.2x |
| 50 m up | SAM ViT-H true | 184/675, 27.26% | 722/1,138, 63.44% | 2.3x |

Read the 30 to 50 m row. Those parcels are three to five native pixels wide,
which is at or above the claimed floor. India returns 0.58% from the checkpoint
where Slovenia returns 41.24% for parcels of the same physical size in the same
sensor. The same ordering holds for an untrained watershed and for a foundation
model that has never seen a field, so it is not an artefact of any one method.

The grid-pixel framing hid this. Under 5 grid pixels means up to 30.3 m in
India and up to 20.7 m in Slovenia, with median parcels of 21.1 m and 12.4 m.
The cross-country comparison at matched grid width was comparing India's 21 m
parcels against Slovenia's 12 m parcels and calling them matched.

Standardising does not rescue it either. Applying Slovenia's per-contrast-bin
rates to India's contrast mix, for parcels under 5 grid pixels, predicts India
at 3.67%. India measures 0.91%. So composition explains part of the gap and
leaves a real residual.

What this does not establish is *what* the country difference is. The leading
candidate is label geometry: India is presence-only with five hand-drawn
parcels per chip, Slovenia is a complete cadastre, and IoU against a loosely
drawn polygon is depressed whatever the imagery shows. Parcel shape and
cropping calendar are the other two. None of those is resolution, which is the
point. The claim as written attributes to the sensor an effect the data locates
somewhere else.

#### The write-up describes a study that is two methods out of date

`COMPARISON.md` line 48 says *"Three methods over the same test chips"*. Line
266 says *"Anything about foundation models. SAM has not been run."* Line 304
carries O-07, *"SAM has not been run."*

SAM has been run. Roughly 16 hours on India across 398 chips and two
composites, roughly 10 hours on Slovenia, five threshold settings each,
ViT-H and a ViT-B calibration, all sitting in `results/*/sam_comparison_vit_h_min500.csv`
and 22 per-setting parcel tables. The write-up is the only public face of the
work and it says the largest single block of compute in the project never
happened.

#### Three headline numbers do not match the artefacts they cite

| Location | Write-up says | Artefact says | Source |
|---|---:|---:|---|
| Slovenia, watershed at FTW's 18-object budget | 0.170 | 0.0808 | `slovenia/segmenter_comparison_min500.csv`, `recall_at_ftw_budget` |
| India, watershed at FTW's 175-object budget | 0.100 | 0.1074 | `india/segmenter_comparison_min500.csv` |
| India, felzenszwalb at 175 objects | 0.029 | 0.0307 | `india/segmenter_comparison_min500.csv` |

The Slovenian error has a traceable cause. `compare_segmenters.py:304` uses
`np.interp`, which clamps below the sweep's edge, so the budget figure comes
from the coarsest measured setting, watershed 0.3 at 25.8 objects and 0.0808
recall. The write-up's Slovenia table omits that row. The 0.170 is the value at
54 objects, read off the truncated table in the document rather than the
generated column. The direction is in your favour here, since FTW's 0.222
against 0.081 is a wider win than against 0.170, but a number that was read off
the wrong table is a number that was read off the wrong table.

#### Two headline numbers have no generating code

`segmenter_comparison_min500.csv` carries `recall_at_ftw_budget`.
`sam_comparison_vit_h_min500.csv` does not. SAM's 0.153 and 0.151 at 175
objects per chip reproduce by hand interpolation between the 0.88 and 0.80
rows. I reproduced them and they are correct. There is no script that emits
them, so nobody else can.

#### The null is thinner than the conclusion resting on it

India, FTW: recall 0.0272, null 0.0220, gap +0.0052, from 3 null draws. Across
runs the null on that configuration has read between roughly -0.007 and +0.008.
The study's sharpest conclusion, that the released checkpoint on India performs
at or near chance, rests on a difference smaller than the control's own
run-to-run spread. The conclusion may well be right. Three draws cannot
establish it.

#### Intervals assume parcels are independent

`threshold_check.py` puts Clopper-Pearson intervals on parcel counts. India has
1,983 parcels across 398 chips, about 5 per chip. Slovenia has 6,831 across
185, about 37 per chip. Parcels in a chip share the scene, the season, the
cloud state, the annotator and the upsampling. The effective sample size is
closer to the chip count than the parcel count, so every interval in the
write-up is narrower than it should be, Slovenia's worst of all. This does not
overturn the large differences. It does overturn any of the close calls,
including the +0.0052 above.

#### The reported setting is selected on the reporting data

Watershed 0.02 is the maximum-gap row of the sweep that reports it, and it is
what `parcel_width_seg_watershed_min500.csv` carries under the unqualified
name. Same for felzenszwalb 100 and for SAM's 0.50/0.88. There is no held-out
split anywhere in the project. Each of those is the best of eight to ten
settings measured on the same parcels the result is quoted from.

#### Smaller methodological gaps

**No object precision on India.** Every India figure is recall. A method
emitting 917 objects per chip and one emitting 175 are compared on what they
find and never on what they invent. The null and the budget column bound this
indirectly. Neither is a precision measurement, and a reader will assume one
exists.

**Reconstruction validated synthetically only.** `MAX_RING_DIST = 3.0` is a
chosen constant. Every size figure in the project depends on the reconstructed
parcel rather than FTW's eroded mask, which makes that constant load-bearing,
and it has never been checked against an independently digitised parcel.

**Grid resolution never reconciled with the benchmark's own specification.**
`grid_pixel_m()` measures 6.067 m for India and 4.139 m for Slovenia and the
project treats that as authoritative. It probably is. It has not been compared
with what FTW states it shipped, so if the measurement is wrong every
normalised width in three documents is wrong with it.

**Boundary contrast is unvalidated.** `boundary_contrast` divides a one-pixel
Sobel band by the chip median. No check that it tracks what an analyst would
call a visible edge, and no check that it is stable between the two seasonal
windows. It is used as an explanatory variable in a two-way table, which is a
heavier load than an unvalidated measure should carry.

**Seeds and provenance.** 20260916 in `compare_segmenters.py`, 20260917 in
`sam_run.py`, no reason recorded for the difference. No run manifest records
which seed, which checkpoint, which interpreter or which package versions
produced any table, and two interpreters demonstrably ran the code.

**`sam_probe.py` is not in the repository.** The cost probe that chose ViT-H
over ViT-B and fixed `points_per_side` at 32 exists outside `src/`. Those two
choices shape every SAM number in the project and the reasoning behind them is
not reproducible.

---

## Phase 3. Findings

Sorted by severity. Blocking means the work cannot be published as it stands.
Major means a reviewer would require it before acceptance. Minor and editorial
are quality.

| # | Severity | Finding | Evidence |
|---|---|---|---|
| F-01 | **Blocking** | The floor claim attributes to the imagery an effect the data locates elsewhere. At matched ground width, same sensor, Slovenia beats India by 1.8x to 71.5x across all three methods and all four size bands | Phase 2 table |
| F-02 | **Blocking** | `COMPARISON.md` states SAM has not been run. About 26 hours of SAM compute and 24 result tables exist | `COMPARISON.md:48,266,304`; `results/*/sam_comparison_vit_h_min500.csv` |
| F-03 | **Blocking** | Three headline numbers disagree with the artefacts they cite, one by 2.1x | `COMPARISON.md:126,171`; both `segmenter_comparison_min500.csv` |
| F-04 | Major | FTW's India gap over the null is +0.0052 from 3 draws, smaller than the null's own run-to-run spread | `india/segmenter_comparison_min500.csv` |
| F-05 | Major | Intervals treat 1,983 and 6,831 parcels as independent when they cluster at 5 and 37 per chip | `threshold_check.py` |
| F-06 | Major | SAM's two budget-matched numbers have no generating code | `sam_comparison_vit_h_min500.csv` lacks `recall_at_ftw_budget` |
| F-07 | Major | Every reported setting is the best of its own sweep, measured on the data it is quoted from | all three sweeps |
| F-08 | Major | Stale calibration artefacts sit under authoritative filenames. `parcel_width_seg_sam_vit_h_true_min500.csv` is 1,168 bytes from 4 chips beside a 108,839-byte full run | `results/india/` |
| F-09 | Major | RS-02 has no pinned dependencies and two interpreters ran the code | root `requirements.txt` header; `src/__pycache__` |
| F-10 | Major | No object precision on India. Every figure is recall | `seg_score.py` |
| F-11 | Major | Measured grid resolution never checked against FTW's published specification | `ftw_common.py:grid_pixel_m` |
| F-12 | Major | Parcel reconstruction validated synthetically only, and `MAX_RING_DIST = 3.0` is load-bearing for every size figure | `ftw_common.py` |
| F-13 | Major | `sam_probe.py` absent from the repository, so the ViT-H and 32-point choices are unreproducible | `src/` listing |
| F-14 | Major | Boundary contrast unvalidated, yet used as an explanatory variable | `parcel_contrast.py:boundary_contrast` |
| F-15 | Minor | Two seeds, no recorded reason, no run manifest anywhere | `compare_segmenters.py:173`, `sam_run.py:258` |
| F-16 | Minor | `parcel_contrast.csv` carries no method or gradient-build column | `results/*/parcel_contrast.csv` |
| F-17 | Minor | The Slovenia table in `COMPARISON.md` omits rows the CSV carries, which is what produced F-03 | `COMPARISON.md:144-160` |
| F-18 | Minor | `object_count` counting labels after `drop_small` leaves gaps is correct and undocumented, in a study where object budget is the control | `compare_segmenters.py` |
| F-19 | Editorial | No README at repo root or in RS-02 | Phase 1 |
| F-20 | Editorial | `FINDINGS.md` and `RESULTS.md` predate stage 2b and do not link to it | file headers |
| F-21 | Editorial | 125 uncommitted files, including 22 per-setting tables and the two stale ones from F-08 | `git status` |

---

## Phase 4. Remediation

Ordered so that each step makes the next one cheaper.

**Before anything else, do not run `git add -A`.** It will commit the two stale
calibration files from F-08 under names that three documents treat as
authoritative. Delete those two first, then stage.

**Step 1, half a day, clears F-02, F-03, F-17, F-20, F-21.** Fix the write-up
against the artefacts. Delete O-07 and the foundation-model paragraph. Regenerate
the India and Slovenia tables from the CSVs rather than by hand, including every
row. Add the SAM sections. Cross-link the three documents. This is bookkeeping
and it is the difference between a repository that reads as careless and one
that reads as careful.

**Step 2, half a day, clears F-01.** Decide what the floor claim becomes. Two
honest options.

The cheap one: scope it to India and say so. *"Within India, recall collapses
below three native pixels for every method tested. Whether that threshold is a
property of 10 m imagery or of Indian parcels specifically is not established,
because at matched ground width Slovenian parcels of the same size are found
between two and seventy times more often."* That is defensible today and it
costs you nothing but a paragraph.

The expensive one, and the better paper: run the label registration test. Take
Slovenia's cadastral polygons and perturb them to match the geometric sloppiness
you would expect from five hand-drawn parcels, then rescore and see how much of
the country gap that buys. If it buys most of it, you have found something worth
writing up on its own, which is that presence-only hand-drawn benchmarks
understate model performance by a measurable factor. If it buys little, the
country difference is real and the remaining candidates narrow to parcel shape
and cropping calendar.

**Step 3, one hour of your time and an overnight run, clears F-04 and F-05.**
Raise `--null-draws` from 3 to 30 and switch the intervals to a chip-level
bootstrap. Both are small edits. The null rerun is the expensive part and it
runs unattended. After this, every close call in the project either survives or
it does not, and you will know which.

**Step 4, two hours, clears F-06, F-13, F-15, F-16.** Add
`recall_at_ftw_budget` to `aggregate()` in `sam_run.py` so the four-way table
is generated rather than interpolated by hand. Copy `sam_probe.py` into `src/`.
Write a `run_manifest.json` per results directory recording seed, checkpoint
SHA256, interpreter version and package versions. Add the method column to the
contrast table.

**Step 5, half a day, clears F-09 and F-19.** Pin RS-02's dependencies in
`02-field-boundaries-smallholder/requirements.txt` at the versions that produced
the tables, and settle on one interpreter. Write the README. See Phase 5.

**Step 6, one day, clears F-10.** Add object precision to `seg_score.py`,
defined as the fraction of emitted objects that best-match some labelled parcel
at IoU 0.5 or above. On India this is only computable against the five labelled
parcels per chip, so it is an upper bound on precision rather than precision,
and it has to be reported under that name. Say so in the column header, not in
a footnote.

**Step 7, when convenient, clears F-07, F-11, F-12, F-14.** Split the chips
into a tuning half and a reporting half and requote every best setting from the
reporting half. Check the measured grid against FTW's published specification
and record the comparison. Digitise ten parcels independently and check the
reconstruction against them. Check that boundary contrast correlates with the
two seasonal windows read separately, and with your own eye on twenty chips.

F-08, F-18 and the deletions fold into the steps above.

**What not to do.** Do not start stage 3. Three documents currently disagree
with the repository, and adding a district study on top of that makes the
inconsistency harder to unpick rather than easier. Steps 1 through 4 are about
three days of work and they turn this from a study a reviewer would reject into
one a reviewer would argue with, which is the goal.

---

## Phase 5. README

RS-02 has no README, and this is the finding a hiring manager hits first. They
will not read `COMPARISON.md` before they read something that tells them what
the project is.

It needs to open with the question and the answer in four sentences, before any
method. Something close to: the released Fields of The World checkpoint recovers
one Indian smallholding in thirty-seven and one Slovenian parcel in four and a
half; this project establishes that the difference is not explained by parcel
width alone; an untrained watershed and SAM both beat the checkpoint on India at
matched object budget while losing to it on Slovenia; the checkpoint has a
specific failure on Indian smallholdings rather than a general weakness.

Then, in order: what the data is and its licence, with the presence-only
labelling stated up front because it conditions every number. How to reproduce,
meaning the exact commands in order with their runtimes beside them, and the SAM
run flagged as 26 hours CPU so nobody starts it by accident. The four-way table,
generated.
The three controls in a paragraph each, because they are the contribution and a
reader skimming will otherwise miss them. Limitations, promoted from the end of
`COMPARISON.md` to a named section, with the country difference from F-01 first.
An artefact map naming which CSV backs which claim.

Two things to keep out. Any claim that the floor belongs to the imagery until
F-01 is settled. Any number not regenerable by a committed script.

One framing note for the career direction. The reason this project is worth
showing is not that you ran three segmenters. It is that you built two controls
that most published comparisons in this area do not use, and that those controls
changed the answer twice. Lead with that.

---

## Phase 6. Map

Not applicable as specified. RS-02 produces no classified map product, so the
cartographic checklist has nothing to run against.

The nearest equivalent is the figure set, and there the finding is a gap.
`figures/` holds five PNGs, all from stage 2. Stage 2b has produced none at all,
so the four-way comparison, the recall-against-object-budget curve, the contrast
two-way panel and a chip segmented four ways beside its truth are all missing.
The object budget control in particular is a figure, not a table. A curve of
recall against objects per chip with all four methods on it and a vertical line
at FTW's budget makes the entire argument in one glance, and it is roughly an
hour of `matplotlib` against tables that already exist.

Add that figure in step 1. It will do more for the write-up than the next two
pages of text.

---

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Pipeline runs end to end from clean state using only repository contents | **FAIL** | 125 uncommitted files; `sam_probe.py` absent (F-13); RS-02 dependencies unpinned (F-09) |
| 2 | Reported numbers reproduce within a stated tolerance | **FAIL** | No tolerance stated; three numbers disagree with their artefacts (F-03); two have no generating code (F-06) |
| 3 | No Blocking or Major finding open, or each documented with quantified effect | **FAIL** | Three Blocking, eleven Major |
| 4 | Every write-up number traces to a generated artefact | **FAIL** | F-03 and F-06. The remainder do trace, and the tables they trace to are untracked (F-21) |
| 5 | Map carries all required cartographic elements | **N/A** | No map product. Figure gap noted in Phase 6 |
| 6 | No hard-coded credentials, paths or asset IDs outside config | **PARTIAL** | No credentials anywhere, and no client or internal data anywhere, both verified. 22 tuned constants sit across 11 files with no central config |

---

## What this review does not say

It does not say the checkpoint works on India. It does not. Every method
measured, including one that was never trained on anything, finds more Indian
parcels than the released model does at matched object budget, and that result
survives all three controls.

It does not say the measurement work is weak. It is the strongest part, and the
null plus budget pair is genuinely better practice than most of what this is
being compared against.

What it says is that the write-up and the repository have drifted apart, and
that the one sentence a reader will remember, about a floor belonging to the
imagery, is the sentence the project's own data argues with hardest. Fix those
two and the rest is maintenance.
