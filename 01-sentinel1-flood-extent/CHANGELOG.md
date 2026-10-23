# Changelog

Every entry gives the superseded value, the corrected value, and why the first
one was wrong. Nothing is silently overwritten. Where a number appeared in an
earlier version of `README.md` or `docs/index.html`, it is listed here so a
reader who saw it can find out what happened to it.

---

## 2026 review round (methodological audit)

Full findings in `REVIEW.md`. Corrections below are the ones that changed a
published number. No method was changed: these are corrections of measurement
and reporting errors.

### C-01 Area comparisons counted predicted water on unlabelled pixels

**Cause.** Every area-versus-truth comparison summed all pixels the map called
water, while truth could only be summed where a hand label exists. Predictions
falling on no-data label pixels therefore inflated the map side of the
comparison and made the map look closer to truth than it is. On the 65 India
chips that was 3,140 ha.

**Fix.** `metrics.mapped_area_px()` counts predicted water only on labelled
ground, applied at every call site in `operating_point.py`,
`product_vs_window.py`, `change_detect.py`, `change_sweep.py` and
`mask_terrain_water.py`.

| Quantity | Superseded | Corrected |
|---|---:|---:|
| Chip-scale mapped water at −18.75 dB | 17,545 ha (−5% vs truth) | 14,405 ha (−22.1%) |
| Area-matched operating point | −18.50 dB, 18,523 ha | −17.75 dB, 18,422 ha |
| Published S1OtsuLabelHand, same chips | 15,650 ha (−15%) | 13,554 ha (−27%) |
| Single-date pooled Otsu, chip scale | 24,208 ha (+31%) | 20,097 ha (+9%) |
| Change detection vs 19 July reference | 7,399 ha | 6,161 ha |
| Change detection vs 14 April reference | 20,113 ha | 17,575 ha |
| Tuned change method, chip scale | 23,774 ha | 19,823 ha |
| Flood-only range across occurrence cuts | 11,067 to 23,423 ha | 8,893 to 19,458 ha |

No IoU, precision or recall changed, because `confusion()` already excluded
no-data. Full-scene figures are unaffected: they are pixel counts over imaged
ground with no label involved.

**Consequence for the headline.** The map under-counts labelled water by 22.1%
at the operating point the full-scene product uses. The reported 119,779 ha is
therefore more likely an underestimate of water extent than a near-unbiased
figure. Scaling by the chip-scale ratio gives 153,681 ha, but that
assumes chip error rates transfer to terrain the chips never sampled, which
finding F-08 says they should not be assumed to.

### C-02 Accuracy was reported from the most favourable split

**Cause.** The README quoted test IoU 0.680 alongside the all-chip 0.519.
Nothing in this pipeline is trained, so train, valid and test are simply three
samples of chips scored by one fixed threshold. Their spread is larger than any
method difference measured anywhere in the project.

| Split | Chips | IoU | 95% CI |
|---|---:|---:|---|
| train | 37 | 0.326 | [0.226, 0.438] |
| valid | 14 | 0.612 | [0.319, 0.750] |
| test | 14 | 0.680 | [0.504, 0.776] |
| all | 65 | 0.519 | [0.395, 0.609] |

**Fix.** The headline accuracy is now micro IoU **0.519, 95% CI [0.395,
0.609]**, with macro IoU **0.280** (sd 0.249, minimum 0.000) reported beside it.
Intervals are percentile bootstrap resampled over chips, not pixels, because
pixels within a chip are strongly autocorrelated and resampling them would give
intervals far too narrow. Produced by `accuracy_ci.py`, which also reports a
conventional confusion matrix, producer and user accuracy per class, and
quantity and allocation disagreement (Pontius and Millones 2011) instead of
kappa.

The macro figure is the important addition: at least one chip scores exactly
zero. A single micro-averaged number hid that the method fails outright on some
chips.

### C-03 `config.py` contradicted the code

`SLOPE_MAX_DEG` was declared 5.0 and `GSW_PERMANENT_MIN` 80. Neither constant
was imported anywhere; the pipeline ran 8.0 and 50. Corrected to the values in
use, and `EDGE_BUFFER_PX`, `MIN_OBJECT_PX_SCENE`, `TILE_PX`, `TILE_HALO_PX`,
`CROPLAND_CLASS`, `GEOBOUNDARIES_API` and the `RESAMPLING` table moved there
from argparse defaults and scattered module constants. `pixel_ha()` replaces a
hard-coded 0.01 that assumed 10 m. No computed number changed.

### C-04 Resampling was undeclared for three of four raster loads

`odc-loader` defaults to nearest (`odc/loader/types.py:506`). Sentinel-1 VH, the
Copernicus DEM and JRC occurrence all took that default silently, and both the
threshold and the slope mask are sensitive to it. Now declared explicitly in
`config.RESAMPLING`, set to `nearest` so the published numbers are exactly
reproduced, and overridable per run via `--resample-sar`, `--resample-dem` and
`--resample-occurrence` so alternatives can be tested against a known baseline.
The DEM tile cache key includes the resampling rule, so a test cannot silently
reuse tiles built with the default.

### C-05 Minimum mapping unit call was deprecated

`remove_small_objects(min_size=n)` is deprecated in scikit-image 0.26 and
removed in 2.0. Replaced with `max_size=n-1`, which is exactly the same
comparison (`min_size` dropped objects smaller than n; `max_size` drops objects
smaller than or equal to m). The MMU step still removes 3,052 ha.

### C-06 Dependencies

`requirements.txt` was a 200-package environment freeze including `pywinpty`,
which cannot install off Windows. Replaced with a minimal pinned direct
dependency list; the original freeze is preserved as `requirements-lock.txt`.

### C-07 Provenance

`make_manifest.py` added. It walks `data/` and `results/`, records file counts
and sizes per group, and SHA-256 digests every small text artefact, so a claim
of reproduction can be checked rather than asserted. Empty `notebooks/` and
`viewer/` directories removed; the orphaned `date_comparison.*` outputs,
superseded by the `--out` named pairs, deleted.

### C-08 Parameter sensitivity published

`sensitivity_grid.py` added. Three parameters that cannot be validated against
any labelled data set roughly 45% of the subtraction between the raw threshold
output and the reported area. The script bins every water pixel once by slope,
occurrence and distance from the swath edge, then answers all 216 combinations
from that one histogram. Across the full grid the reported flood area ranges
35,187 to 275,969 ha; within the defensible band of slope 5 to 12 degrees and
occurrence 25 to 70 percent it is 60,783 to 186,921 ha, a factor of 3.08. The
published choice sits at 122,832 ha before the MMU.

### C-09 `compare_dates.py` assumed the first map was the later one

Temporal labels inverted whenever the pair was given in the other order. It
reported the 7 to 31 August comparison as "filling, 13.2 to 1" when the flood
fell from 64,615 ha to 38,887 ha. Counts were correct throughout; the words
attached to them were not. The pair is now ordered by date, and the persistence
definition is consistently "of the earlier flood, how much was still wet later".
This changed the reported persistence for the 12 vs 7 August pair from 95.4% to
71.7%, which is the same quantity asked the right way round.

### C-10 The headline became a bracket

The reported hectare figure was computed at the operating point chosen to
maximise IoU, which recovers only 77.9% of hand-labelled water. The full scene
was therefore also produced at the area-matched threshold of −17.75 dB, and the
headline is now a range.

| | Map-optimal, −18.75 dB | Area-matched, −17.75 dB |
|---|---:|---:|
| Flood water | 119,779 ha | 170,625 ha |
| Flooded cropland | 46,943 ha | 87,127 ha |

Neither figure replaces the other and neither is withdrawn. The two thresholds
score 0.519 and 0.522 IoU on the chips, indistinguishable inside an interval of
±0.11, and differ by 42% on the reported area.

A prediction recorded here because it was wrong: the area-matched full scene was
expected near 153,000 ha, by scaling the published figure by the chip-scale
ratio of 1.28. The scene gave 1.42. Chip-scale ratios do not transfer, for the
same reason the Otsu window, the slope mask and the swath-edge artefact did not:
the 65 validation chips are floodplain, and the scene is not.

District ranking is unaffected. Nagaon, Morigaon and Sonitpur hold the top three
places at both thresholds.

### C-11 The three-date comparison was single-threshold

The recession finding was computed only at the map-optimal threshold. Both other
acquisitions were reproduced at the area-matched threshold and the comparison
re-run.

| | Map-optimal | Area-matched |
|---|---:|---:|
| Flood 7 Aug, in overlap | 64,615 ha | 90,785 ha |
| Flood 31 Aug, in overlap | 38,887 ha | 44,991 ha |
| Persistence | 56.9% | 46.1% |
| Net change | to 60.2% | to 49.6% |
| Total flood fall | 39.8% | 50.4% |
| Flooded cropland fall | 80.8% | 82.5% |

The total-flood recession is threshold-dependent and is now reported as a range.
The cropland recession is not, moving 1.7 points across a choice that shifts
total flood area by 42%, so the claim that fields drain faster than channels
stands without qualification.

A prediction that was wrong, recorded rather than dropped: relaxing the
threshold was expected to add terrain and edge noise. On 7 August 87% of what it
adds is cropland, because partially inundated fields with emergent crop sit at
intermediate backscatter. On 31 August, post-drainage, that falls to 57%.

### C-12 The cropland figure was measured on a smaller footprint than the flood

**Cause.** `district_stats.py` sums flooded cropland over geoBoundaries ADM2
polygons. On 12 August the swath reaches ground those polygons do not cover, so
the district sum accounts for 110,081 ha of the 119,779 ha of mapped flood. The
headline paired a scene-wide flood figure with a district-restricted cropland
figure and presented the second as a share of the first.

**Fix.** `cropland_scene.py` counts flooded cropland over the same raster the
flood figure uses, by windowing each WorldCover tile onto the refined water
raster rather than mosaicking. Tile windows are checked for overlap before
anything is counted, and the flood total is cross-checked against
`fullscene_stats_*.json`. Results in `results/cropland_scene.csv`.

| Quantity | Superseded | Corrected |
|---|---:|---:|
| Flooded cropland, 12 Aug, map-optimal | 43,494 ha | 46,943 ha |
| Flooded cropland, 12 Aug, area-matched | 80,923 ha | 87,127 ha |

The 7 and 31 August figures are unchanged. Those passes are on relative orbit 4
and fall entirely inside Indian district polygons, so the district sum and the
scene total agree to the hectare.

The share of mapped flood sitting on cropland moves from 39.5% to 39.2% at the
map-optimal point, so the reading does not change. The magnitude does.

One limitation the measurement exposed: the fetched WorldCover tiles cover
97.8% of the grid. The uncovered 2.2% is counted as not cropland, so every
cropland figure in this repository is a floor rather than a best estimate.

### C-13 Two numbers that were quoted for months and stored nowhere

**Cause.** `verify_all.py` section A traces every number in README.md against
`results/`. It has never looked at `docs/index.html`, and it skips decimals and
percentages. Two claims lived in that blind spot.

Macro IoU 0.280 was computed by `accuracy_ci.py`, printed to the console, and
never written to a file. The permanent-water sensitivity on the public page
read 11,067 to 23,423 ha, a pair that appears nowhere in `results/`; the
measurement in `mask_terrain_water.csv` is 8,893 to 19,458 ha. And the
swath-edge rate, 17% of area against 1.9%, had no producer at all.

**Fix.** Section A2 now traces the public page the same way section A traces
the README. `accuracy_ci.py` writes `macro_iou`, `macro_iou_sd` and
`macro_iou_min` per split. `build_docs_page.py` reads the sensitivity range
from `mask_terrain_water.csv` rather than carrying it as a literal. And
`edge_rate.py` measures the swath-edge rate from the raw and refined rasters.

| Quantity | Superseded | Measured |
|---|---:|---:|
| Permanent-water sensitivity, on chips | 11,067 to 23,423 ha | 8,893 to 19,458 ha |
| Flood called inside the 600 m buffer | 17% of area | 32.9% |
| Flood called in the interior | 1.9% of area | 3.1% |

The buffer rate was wrong by nearly a factor of two, and in the direction that
strengthens the argument for the buffer rather than weakening it: the contrast
is about eleven to one, not nine to one. The measurement is confirmed
independently, since 79,785 ha of buffer at 32.9% is 26,249 ha of flood against
the 26,223 ha `refine_figure.py` measures as moving to no data.

**What this says about the audit.** A number matching something in `results/`
is weak evidence, because with 22,516 indexed values a tolerance will land on
an unrelated value sooner or later: 11,067 matched by coincidence while its
own partner did not. The misses are the signal. The report now says so.

---

## Issue register round, October 2026

An issue register compiled against commit 614d8bb listed 27 errors and
irregularities that the records above did not. Each was checked against the
code before anything was changed. Items I-01 to I-27 below refer to that
register. No headline figure moves: 119,779 to 170,625 ha of flood and 46,943
to 87,127 ha of flooded cropland are unchanged.

### C-14 The Earth Engine cost was not split at matched recall (I-02)

The README said "at matched recall" and then quoted the precision differences
between each curve's best-on-valid points. `product_vs_window.py` defines
matched recall as each curve's row nearest the baseline recall of 0.601, and
read that way the split comes out the other way round.

| Part of the precision gap | Superseded | Corrected |
|---|---:|---:|
| RTC to the GEE product | +0.009 | +0.024 |
| Pooled to per-scene Otsu | +0.031 | +0.016 |
| Total | +0.040 | +0.040 |

The 0.012 IoU cost of the migration is unchanged; it is a difference between
best-on-valid points and is now described as one. The broader reading holds:
both parts are small against the 0.326 to 0.680 spread between splits.

### C-15 `final_method.json` stated three things that were no longer true (I-01, I-08)

`slope_mask_reason` said the slope cut "removed true water faster than shadow".
Its own figures, precision +0.008 for recall −0.003 at 20°, mean the cut
removed about 0.4% of true water and about 3.8% of false water. The method was
called "single-date pooled Otsu" though the threshold is swept against labels,
`slope_mask` was null though the scene applies 8°, and the change signal was
quoted at IoU 0.147, superseded on 9 September. All four were strings typed into
`operating_point.py`. They are now written from `mask_terrain_water.csv`,
`change_sweep.csv` and `config.py` on every run. The notes at the top of
`full_scene.py` carried the same wording and are rewritten.

### C-16 `flood_only_ha` still counted unlabelled pixels (I-06)

C-01 restricted `area_ha` to labelled ground. The `flood_only_ha` field
computed two lines later in `operating_point.py` was missed and counted every
predicted pixel. It now counts labelled ground only. No README figure uses it;
the new values are in `operating_point.csv` and `final_method.json`.

### C-17 The cross-orbit offset was called a median (I-16)

The 0.05 dB in the README is a weighted mean of the eight tile land medians,
each weighted by the tile's total pixel count, and the 0.11 dB scatter is their
sample standard deviation, while `orbit_offset.py` printed the population
figure, 0.103. The README and `verify_all.py` now name the statistics.
`orbit_offset.py` now prints the sample figure and writes each tile's land
pixel count, so a future run can weight by land pixels; that run has not been
made.

### C-18 The change-detection figure was chosen on all chips (I-20)

IoU 0.196 is the best of the sweep over all 65 chips, test split included.
Chosen on the valid split, as every other setting in the project is, the same
signal reaches 0.146. Both figures are now stated. It flatters a rejected
method, so the rejection stands.

### C-19 The external check was looser than it read (I-19)

The README said both worst-affected districts inside the study area "appear at
the top" of the 7 August cropland table. Golaghat is first and Jorhat third,
behind Lakhimpur. The 4 August map has since been traced: the International
Water Management Institute made it from ESA Sentinel-1 data and it is posted on
ReliefWeb. Its worst-affected list is credited to ASDMA figures as of 1 August,
which count people affected, and the README now says so. ASDMA's 25 July
counts, as quoted in an ACAPS briefing note of 3 August 2016, are added as a
second ranking check. Majuli was part of Jorhat until 8 September 2016, so
the README also gives Jorhat and Majuli together; the order is unchanged.

### C-20 The alignment step was said to fix a 10 px offset (I-18)

The median shift in `coregistration.csv` is 2 pixels in x and 0 in y, with the
largest at 11. The pipeline table now says so.

### C-21 The "600 m" swath-edge buffer is about 640 m (I-23)

`refine_scene.core_mask` erodes a mask decimated by 8, `round(30 / 8) = 4`
times, so the 30 pixels requested become 32, about 640 m at 20 m.
`sensitivity_grid.py` builds its buffers the same way, so no figure was
computed on a different buffer from the one described; only the description
changes. `config.applied_edge_px()` now gives the applied width, and the
README, the public page, the publication map, the three-date sheet and the
sensitivity figures in `sensitivity_grid.py` and `make_figures.py` use it.

### C-22 The README pointed to a raster that is not in the repository (I-04)

No raster is committed. The README now says which scripts produce the
area-matched raster.

### C-23 The public page claimed more of its numbers were read from files than were (I-05)

The footer said every number on the page is read from `results/` at build
time. Eleven were typed. The accuracy figures, the change-detection figures and
the district counts are now read at build time. Three stay typed because the
scripts that produce them print without storing: the all-water score 0.130,
the 99.3% of the channel below 8°, and the 97.8% WorldCover coverage. The
footer names those three and says how they are checked. Two of the three were
in results/ all along and the third is now stored, so all three are read at
build time; see M-03 and M-05 below.

### C-24 The reproduction checks could not pass on a clean copy (I-12 to I-15, I-24, I-26, I-27)

- **Manifest digests (I-14).** Digests were taken on CRLF files while git
  stores and checks out LF, so no clone could match them. `make_manifest.py`
  now normalises line endings before hashing and writes LF, and
  `preflight.py` uses the same function. `accuracy_ci.csv`, which really had
  changed, and the files C-12 and C-13 added are picked up by the rerun.
- **`preflight.py` (I-13).** It required the README to carry the superseded
  80,923 ha and now checks flooded cropland against `cropland_scene.csv`. It no
  longer lists itself as a scratch file to delete, and it skips `data/`
  entries when `data/` is absent, as it is on any clone.
- **`verify_report.txt` (I-12).** The report records a digest of the README it
  read, and `preflight.py` fails if the README has changed since.
- **Figure freshness (I-15).** `verify_all.py` section D compared file times,
  which git does not keep. It now uses each file's last commit time when the
  file is tracked and unchanged, and its file time otherwise.
- **Usable chips (I-24).** `triage_fetch.py` and `coregister.py` both wrote
  `usable_chips.txt` by different rules. `triage_fetch.py` now writes
  `triage_usable_chips.txt`, and `coregister.py` is the only writer of the list
  later steps read.
- **WorldCover year (I-26).** `district_stats.py` took the newest year the
  catalogue offered. It now defaults to `config.WORLDCOVER_YEAR = "2021"`.
- **Console-only figures (I-27).** The separability figures, the share of
  water already dark on each reference date and the change-filter deletion
  rates were printed and never stored. `product_vs_window.py`,
  `change_detect.py` and `change_sweep.py` now write
  `product_separability.csv`, `reference_wetness.csv` and
  `change_filter_rates.csv`.

### C-25 Housekeeping (I-03, I-07, I-09, I-10, I-11, I-17)

- C-07 said the empty `notebooks/` and `viewer/` folders were removed. They
  were still there, each holding a `.gitkeep`, and are now deleted (I-03).
- `operating_point.py`, `product_vs_window.py` and `mask_terrain_water.py` set
  `PIXEL_HA = 0.01`, and `operating_point.py` its own occurrence cut of 50,
  after C-03 said `pixel_ha()` had replaced the literal. All three now use
  `pixel_ha(TARGET_RES)` and `GSW_PERMANENT_MIN`. Both values are unchanged at
  10 m (I-07).
- Two comments still justified the edge buffer with the superseded 17% and
  1.9%; they now cite `edge_rate.csv` (I-09).
- Three docstrings described an earlier pipeline: `full_scene.py`,
  `district_stats.py` and `verify_all.py` (I-10).
- This round of review was headed "2016 review" here and in `config.py`; it
  took place in 2026 (I-11).
- `REVIEW.md` S-01 said nearest resampling from 10 m to 20 m discards half the
  samples. It discards three quarters; an erratum is added (I-17).

### C-26 Three README figures were older than the code that draws them

`operating_point.png`, `change_sweep.png` and `product_vs_window.png` in the
repository came from an earlier version of `make_figures.py`. Redrawn by the
current one from the same CSVs, they differ in labelling and layout only. Minus
signs are typeset, the change-detection point is labelled as the best over all
65 chips (C-18), and the two operating-point labels now sit above the curves,
where before their white halo hid part of the all-chips line. No plotted value
changed.

### C-27 Six analysis scripts drew over the README figures

`operating_point.py`, `change_sweep.py`, `product_vs_window.py`,
`sensitivity_grid.py`, `accuracy_ci.py` and `orbit_offset.py` each saved a
quick-look figure under the name `make_figures.py` uses for the README version,
so rerunning any of them replaced a README figure until `make_figures.py` ran
again (C-26 came from this). They now write `<name>_check.png`, which
`.gitignore` excludes, and `make_figures.py` is the only writer of the README's
charts. The map, the two date sheets and the terrain and water mask panel each
have their own script, and nothing else writes over them.

### Measured in this round (I-21, I-22, I-25)

`register_checks.py` measures what the register could not settle by reading.
Its readings were set before it ran, and both chip checks reproduced the
published IoU (0.5186 and 0.5221) before changing anything.

- **I-21, Lee noise term: under the bar.** Fixing the term to the median of the
  65 per-chip values (0.00193 in linear power) moved IoU by −0.0009 at both
  operating points and mapped area by −0.23% and −0.34%. The bar was 0.005 IoU
  or 1% area. Recorded as measured and small. The chips cannot show its size on
  hilly scene tiles. `results/register_check_lee.csv`.
- **I-22, `morph_clean`: over the bar on area.** With the clean-up run at the
  chips' 10 m, where its 25 pixel limit is 0.25 ha, chip mapped area falls
  2.93% at −18.75 dB and 3.36% at −17.75 dB. That was not the scene's limit,
  which is 1 ha at 20 m; N-03 below measures it.
  IoU is unchanged at the first and rises by 0.0050 at the second. The README
  now states these figures and what follows from them for the headline scaling
  and for the area-matched point. `results/register_check_clean.csv`.
- **I-25, frame lookup: the same frames.** The lookup by id with the `_rtc`
  suffix and the search by bounding box, date and orbit return the same three
  12 August frames. The `full_scene.flood_items` docstring said the id lookup
  returns nothing, which holds only for bare GRD ids, and now says that.
  `results/register_check_items.csv`.

---

## Final register round, October 2026

A second register, compiled at `7f9de52` while checking the first round's
fixes, found six issues, N-01 to N-06, and eleven minor ones, M-01 to M-11.
They keep its numbers here. None moves a headline flood or cropland figure.

### N-03 The clean-up step was measured at a quarter of the scene's ground

`morph_clean` drops water patches and fills holes under 25 pixels. On the 10 m
chips that is 0.25 ha; on the 20 m scene `full_scene.py --res 20` maps, it is
1 ha. `register_checks.py` ran it with the defaults on the chips, so I-22
measured a gentler step than the published map applies. `morph_clean` now
takes its limits as arguments, and the check runs at both: 25 pixels, as
before, and 100 pixels, the scene's 1 ha. Set before rerunning: the same bars
apply, and wherever the README describes the published map its figures come
from the 1 ha rows. Results below.

### N-01 `preflight.py` failed on a fresh clone

The skip for absent data/ tested the folder, and importing `make_manifest`
imports `config.py`, which creates an empty data/. On a clone the check then
reported five missing manifest entries. It now skips data/ entries when none of
the data/ files exists, so a partial data/ still fails. Checked on a fresh
clone with the fix in place: 46 passed, none failed.

### N-02 The freshness check failed a correct figure

`accuracy_ci.csv` gained three columns (C-13) that `accuracy_ci.png` never
draws, and was committed after the figure, which redrew byte for byte the same.
By commit time the figure was stale. Section D of `verify_all.py` now reads the
source as it was at the figure's last commit: for a CSV, if every column that
existed then holds the same values now, the figure passes; anything else must
match byte for byte. The committed report no longer carries a failure.

### N-04 "45% of the study area darkened" matched no row of its file

`change_filter_rates.csv` has no 45%; the nearest row is 46.6% at a 0.5 dB
drop, measured over labelled ground on the chips, not the study area, and its
13% is hand-labelled water with the river in it. The README now quotes that
row and says what it covers, and ties the 66% against 46% to the 3 dB drop it
comes from.

### N-05 `sensitivity_grid.csv` labelled buffers with requested widths

The file keeps `edge_buffer_px` and `edge_buffer_m` and adds
`edge_buffer_applied_px` and `edge_buffer_applied_m`, so the published row
reads 30, 600, 32 and 640. `make_figures.py` reads the applied column.

### N-06 Two files gave different "already dark" shares

`reference_wetness.csv` now carries a `references` column with Lee-filtered and
unfiltered rows, and its threshold is rounded. The filtered rows are the 45.1%
and 18.7% the README quotes, now named as their source; the unfiltered ones
explain why `dry_reference.csv`, measured on unfiltered references, reads about
ten points higher. `fetch_dry_reference.py`'s docstring says so, since
rewriting that file needs Planetary Computer.

### Minor, M-01 to M-11

- **M-01.** C-27 now says `make_figures.py` writes the README's charts and
  that the map, the date sheets and the mask panel have their own scripts.
- **M-02.** The orbit chart's subtitle reads "pixel-weighted mean of tile
  medians", as C-17 renamed it everywhere else.
- **M-03, M-05.** The public page typed three figures. The all-water score is
  the labelled water share in `change_filter_rates.csv`, the 99.3% follows
  from `refine_scene_20m.csv`, and `cropland_scene.py` now writes
  `worldcover_grid_cover_pct`. `build_docs_page.py` reads all three, and its
  footer no longer lists exceptions.
- **M-04.** "The same configuration converges on 0.130" named the wrong row.
  Every change-only configuration converges on about 0.13; the one that
  reaches 0.196 gives 0.129.
- **M-06.** The README's script table lists `register_checks.py` and
  `preflight.py`.
- **M-07.** The README is version 1.2.
- **M-08.** `district_stats.py` no longer lists a figure it does not draw.
- **M-09.** `verify_all.py` checks the map PDF the README links as well as the
  PNG.
- **M-10.** `register_checks.py` writes no negative zeros,
  `reference_wetness.csv` rounds its threshold, and `verify_all.py` prints a
  gap that rounds to nothing as +0.
- **M-11.** `orbit_offset.py` is rerun so `orbit_offset.csv` carries
  `land_pixels` and `verify_all.py` weights the land medians by land. Set
  before rerunning: if the land-weighted mean rounds to the README's 0.05 dB,
  the figure stands and the README names the new weighting; otherwise the
  README quotes the new figure.

### Measured in this round

- **N-03, clean-up at the scene's 1 ha: over the bar, and larger.** Both
  baselines reproduced 0.5186 and 0.5221, and the 0.25 ha rows reproduced the
  first measurement exactly. At 1 ha the step lowers chip mapped area by 7.91%
  at −18.75 dB and 9.88% at −17.75 dB, against 2.93% and 3.36% at 0.25 ha.
  IoU moves by −0.0049 at the first and +0.0072 at the second. By the rule set
  before rerunning, the README now quotes the 1 ha rows: on the chips the
  area-matched pipeline maps 10.2% less water than the labels, against 3.7%
  as first stated, and the map-optimal one recovers 13,266 ha of 18,483, a
  shortfall of 28.2% that scales the headline to about 166,900 ha, against
  24.3% and 158,300 ha. No published map figure changes; the bracket's upper
  end is now said to be likely low as well. `results/register_check_clean.csv`.
- **M-11, orbit offset weighted by land: the figure stands.** Over the same
  eight tiles, with the same per-tile medians, the land-weighted mean of the
  tile land medians is −0.048 dB against −0.047 dB weighted by all pixels,
  and the sample standard deviation is 0.11 dB either way. Both round to the
  README's 0.05 dB, so the figure stays and the README now names the land
  weighting. `results/orbit_offset.csv`.
- **N-06, already dark.** Filtered, 45.1% on 19 July and 18.7% on 14 April, as
  quoted; unfiltered, 55.4% and 29.4%, which is the gap to
  `dry_reference.csv`. `results/reference_wetness.csv`.
- **N-05, M-05.** `sensitivity_grid.csv` reproduces every flood area with the
  applied widths added; the published row reads 30, 600, 32, 640.
  `cropland_scene.csv` reproduces every area and records WorldCover covering
  97.84% of the grid.

### Third round, R-01 to R-05

A third register, at `081a132`, found all 17 items above fixed and five
smaller points.

- **R-01.** The public page still called the area-matched figure unbiased and
  never mentioned the clean-up step. It now says the area matches the labels
  before that step and maps less water with it, reading the shortfall from a
  new `area_vs_labels_after` column of `register_check_clean.csv`, so the
  10.2% traces to a file. The README's opening and its "anyone buying a
  hectare figure" sentence say the same.
- **R-02.** The orbit chart's subtitle gave the all-ground mean, −0.015 dB,
  beside the README's land figure of 0.05 dB. It now gives the land-pixel
  weighted mean of the tile land medians, −0.048 dB.
- **R-03.** The unfiltered shares in `reference_wetness.csv` are close to
  `dry_reference.csv`'s, not equal, since that file covers 63 chips.
- **R-04.** The N-01 check ran on a clone with the fix, not on `7f9de52`.
- **R-05.** The public page cannot be rebuilt from a clone, since it needs the
  refined rasters; the README says so and points to `verify_all.py` section
  A2, which checks the page's numbers on a clone.

### Fourth and fifth rounds, S-01 to S-05 and T-01, T-02

These S numbers belong to the register. `REVIEW.md` uses S-01 to S-05 for its
own suspicions, which are a different list. C-31 and C-37 refer to those.

A fourth register found five points left after R-01 to R-05, and a fifth, at
`2717c21`, found them still open and two slips in the comment clean-up.

- **S-01.** The printed map's note still called −17.75 dB "mapped area
  unbiased against them". It now reads "area matching them before clean-up,
  about a tenth low after it", and the map is redrawn.
- **S-02.** `verify_all.py` section A2 said it traced every number on the
  public page; it traces numbers with thousands separators. Its wording, the
  README's and `build_docs_page.py`'s now say that, and A2 now also checks the
  page's clean-up shortfall against `register_check_clean.csv`'s
  `area_vs_labels_after`.
- **S-03.** A2's docstring no longer mentions numbers named in the page
  footer, since none are.
- **S-04.** The README's operating-point table and the operating-point chart
  say "before clean-up" where they said "unbiased", and the chart is redrawn.
- **S-05.** The page's thresholds, slope cut, buffer and pixel limits are
  settings written into its text. `build_docs_page.py` and the footer now
  say every result is read from `results/`, and name the settings as written
  in.
- **T-01, T-02.** A comma splice in `threshold_analysis.py`'s docstring is a
  semicolon, and `compare_rtc.py` no longer prints two colons in one message.

### Sixth round, U-01 to U-03

A sixth register, at `3faaecb`, found the points above fixed and three
optional ones left.

- **U-01.** The public page said "every number comes from the 20 m raster",
  though its accuracy scores and the chip-level areas are measured on the
  10 m chips. It now says the scene and district areas are measured on the 20 m raster, not
  on the preview.
- **U-02.** A2's shortfall check said nothing when `register_check_clean.csv`
  or its scene-scale row was missing. It now reports a warning.
- **U-03.** A comma splice in the operating-point chart's caption is a
  semicolon, and the chart is redrawn.

---

## Independent sample of the 12 August map, October 2026

### C-28 The map now has an accuracy estimate of its own (F-01, F-02)

Until now every accuracy figure described 65 chips scored before the slope cut,
the swath-edge buffer and the clean-up, and the README said a design-based
estimate "has not been drawn". It has now. A stratified random sample of the
published 20 m map was labelled on the Sentinel-2A image of 12 August, 04:15
UTC, and `estimate_accuracy.py` and `floodplain_layer.py` turn the labels into
areas and accuracies with standard errors. No published figure changes; the map
figures stay as they were, and the README adds the estimate beside them.

- **The sample.** Seven strata read off the map, 550 points, plus 60 in
  floodplain land far from flood, where the main draw put only 7. One
  interpreter labelled them blind to the map.
- **Three draws.** The first used the scene classification alone and let
  points through at cloud edges. The second added a 100 m distance from
  classified cloud and still put P0002 inside a cloud bank the classification
  had missed. The third adds a brightness test on the image, whose cutoffs were
  chosen on the second draw by checking chips before any labelling. The two
  earlier keys, the one label made on the second draw, and a log of every draw
  are kept in `results/validation/sample/`.
- **Where it holds.** Under cloud the land strata are far higher and steeper
  than in clear sky, so the headline is the floodplain, at or below 150 m with
  2° of slope or less. There the clear and cloudy parts agree on slope.
- **What it says.** Open-water flood in the floodplain is 160,688 ± 30,796 ha,
  against 102,697 ha mapped there at −18.75 dB and 146,367 ha at −17.75 dB.
  Water seen through vegetation is reported apart, since it turns up as often
  far from flood as near it and in August includes paddies standing in water.
- **Where it lives.** Small results go to `results/validation/` and are
  committed. The Sentinel-2 classification raster and the image chips stay in
  `data/validation/`, which git ignores; `clear_sky.py` and
  `draw_sample.py --chips-only` rebuild them.

### C-29 A second reader on the hard points

C-28 rested on one interpreter. `second_label.py` took the 62 points outside
permanent water that the first reader marked as guesses, added 40 at random
and renumbered them in random order. A second person labelled them, and Claude
labelled them separately, both blind to the first labels and to the map.
`compare_labels.py` scores the agreement and recomputes the estimates with each
second reader's labels on those points.

| Quantity | First reader | Second person | Claude |
|---|---:|---:|---:|
| Open-water flood in the floodplain | 160,688 ± 30,796 ha | 130,608 ± 24,733 ha | 143,738 ± 28,605 ha |
| Kappa with the first reader, random points | | 0.856 | 0.736 |
| Kappa with the first reader, guesses | | 0.542 | 0.461 |

The headline stays at 160,688 ha and is now described as the top of what
different readers give. No other published figure changes. The key, both
sheets and the two result tables are in `results/validation/second/`. The
renumbered chips and the pack sent to the second person stay in
`data/validation/`, which git ignores. `label_tool.py` gained `--sheet` and
`--chips` so it can open a second sheet.

### C-30 Eighth register round, V-03 to V-05

The register on f6b7263 found five points. V-01, a top-up of land near flood,
and V-02, the step from clear sky to cloud, waited for the map that S-01 and
S-02 settled. The other three are fixed here.

- **V-03, the swath-edge count.** The README said 1 of 45 readable points in
  the buffer was water. The labels are 1 W and 1 V, and the register read that
  as 2. The count of 1 is right by the project's definition of flood: the W
  point, P0543, has a JRC occurrence of 90 and so is permanent water. The
  README now says so, and the page says "flood water" where it said "water".
- **V-04, what "clear" covers.** The draw takes classes 2 and 7 of the scene
  classification, dark area and unclassified, as well as the clear ones. The
  README now says points were drawn where the classification shows no cloud,
  cloud shadow or cirrus within 100 m, gives the 105 points on those two
  classes, and heads the column "Eligible ha sampled". The counts are in a
  new `accuracy_labels_by_scl.csv`.
- **V-05, two roundings of one figure.** `floodplain_layer.py` wrote stratum
  areas rounded to the hectare, and `compare_labels.py` read them back, so its
  first-reader figures came out at 160,689 and 70,660 ha against 160,688 and
  70,659 in the summary. The areas are now written to one decimal.

Ready for S-01 and S-02, with no published figure changed:

- `full_scene.py` refuses a resampling test without `--variant`. Without one
  it would have resumed from the published run's record and rewritten
  `fullscene_stats_20m.json`. `refine_scene.py` writes a DEM test under a
  `_dem-bilinear` name instead of over `refine_scene_20m.csv`.
- `score_map.py` scores any version of the map against the sample. The strata
  stay as drawn and the map class is read at each point, the estimator of
  Stehman (2014) for strata that differ from the map classes. On the published
  map it reproduces `floodplain_layer.py`, and checks that before it writes
  `map_scores.csv`.

### C-31 Resampling tested, the DEM made bilinear, the clean-up made consistent

REVIEW.md suspected two resampling rules, S-01 for the VH load and S-02 for
the DEM behind the slope cut. Both were run against the published 12 August
map and scored on the labelled sample with `score_map.py`.

- **S-01, averaged VH. Not adopted.** The raw flood went from 217,490 to
  216,370 ha. Refined with the same DEM and clean-up as the comparison run, it
  came to 119,384 ha against 119,970, 0.5% less. Five sample points changed,
  three toward their labels and two away. Nearest keeps single 10 m values,
  which is what the threshold was tuned on on the chips.
- **A prediction that failed.** Before the refined result was seen, the
  expected change was a fall of 5 to 15%, reasoning that averaging mixes water
  and land in linear power at flood edges, where land dominates. It was 0.5%.
  The likely reason is that the Lee filter already mixes linear power across
  those edges, so most of that effect was in the map before. That reason has
  not been measured.
- **S-02, bilinear DEM. Adopted.** The slope cut removes 68,958 ha against
  68,437, and the permanent channel above 8° falls from about 415 to 275 ha.
  Four sample points change and all four move toward their labels. P0085,
  P0090 and P0105 are open water marked sure, on the valley floor at 69 to
  76 m; the nearest DEM gave them slopes of 10.4 to 11.0° and the bilinear one
  6.9 to 7.6°, so they are no longer cut. P0067, not water, at 1,634 m, goes
  from 7.3° to 12.0° and is now cut. `config.RESAMPLING["dem"]` is
  `"bilinear"`, and the DEM tile cache is named by the rule, so a change of
  default cannot reuse tiles built the old way.

**A correction to C-05.** C-05 replaced `min_size=10` with `max_size=9` and
said the clean-up "still removes 3,052 ha". That was not rerun, and it was
wrong. scikit-image 0.26 passes a `min_size` argument on as `max_size`
unchanged, so the September call dropped components of 10 pixels or fewer,
where the code since C-05, and config.py, drop those under 10. The September
maps were not all refined the same way. Recounted from the raw rasters:

| Map | Removed in September, ha | 10 px or fewer | 9 px or fewer |
|---|---:|---:|---:|
| 12 Aug, map-optimal | 3,051.8 | 3,051.8 | 2,860 |
| 7 Aug, map-optimal | 454.2 | 454.2 | 426.6 |
| 31 Aug, map-optimal | 422.6 | 422.6 | 400.2 |
| 12 Aug, area-matched | 4,379.3 | 4,666 | 4,379.3 |
| 7 Aug, area-matched | 620.2 | 650 | 620.2 |
| 31 Aug, area-matched | 575.5 | 609 | 575.5 |

All six are now refined with the documented rule. On 12 August, map-optimal,
the move from 119,779 to 120,790 ha is about 191 ha from the clean-up and
820 ha from the DEM.

**The sample stays on the maps it was drawn from.** The strata were read off
the September maps, and every point's weight comes from their hectares, so
they cannot follow the published map. `clear_sky.py` now points at
`India_water_20m_dem-nearest_refined.tif` and its area-matched twin, rebuilt
with the nearest DEM, and for the first with `--min-pixels 11`, which
reproduces the September clean-up. A first rebuild without that flag came out
191 ha larger and moved the floodplain flood stratum from 102,697 to 102,737 ha
without changing a single point; `score_map.py` now stops if either map as
drawn differs from the hectares the draw recorded in `strata.csv`.
`estimate_accuracy.py` labels its maps "as drawn", and the page takes the
published map's figures from `map_scores.csv`. Open-water flood on the ground,
160,688 ± 30,796 ha, does not change, since it estimates the ground.

**Two faults caught before they wrote anything.** The bilinear tiles share a
folder with the nearest ones, and `floodplain_layer.py`, `topup_sample.py` and
`estimate_accuracy.py` matched both, which would have counted the floodplain
twice. They now read the nearest tiles only. And the DEM cache was named by
whether a rule was the default, so changing the default would have read
nearest tiles as bilinear.

Published figures:

| Quantity | Superseded | Corrected |
|---|---:|---:|
| Flood, 12 Aug, map-optimal | 119,779 ha | 120,790 ha |
| Flood, 12 Aug, area-matched | 170,625 ha | 171,683 ha |
| Flood, 7 Aug, map-optimal / area-matched | 64,704 / 90,915 ha | 65,356 / 91,670 ha |
| Flood, 31 Aug, map-optimal / area-matched | 38,887 / 44,991 ha | 39,481 / 45,648 ha |
| Flooded cropland, 12 Aug | 46,943 / 87,127 ha | 47,028 / 87,274 ha |
| Flooded cropland, 7 Aug | 30,035 / 52,882 ha | 30,109 / 52,999 ha |
| Flooded cropland, 31 Aug | 5,776 / 9,256 ha | 5,826 / 9,325 ha |
| District totals, 12 Aug, flood / cropland | 110,081 / 43,494 ha | 110,938 / 43,564 ha |
| Removed by the slope cut / the clean-up, 12 Aug | 68,437 / 3,052 ha | 68,958 / 1,519 ha |
| Sensitivity grid, published cell | 122,832 ha | 122,310 ha |
| Drained 7 to 31 Aug | 27,843 / 48,950 ha | 27,933 / 49,099 ha |
| Newly flooded 7 to 31 Aug | 2,114 / 3,157 ha | 2,147 / 3,207 ha |
| Mapped flood in the floodplain, published | 102,697 / 146,367 ha | 102,758 / 146,400 ha |
| User's / producer's accuracy, whole map, −18.75 dB | 0.740 / 0.421 | 0.755 / 0.439 |
| Headline scaled by the chip shortfall, without / with the clean-up | 153,681 / about 166,900 ha | about 155,000 / 168,300 ha |

Every district row moves by a few hectares; the ranking does not change.

The top-level README kept the September figures until C-37 brought it into
line.

### C-32 A second top-up, where the headline's uncertainty sat (V-01, V-02)

The eighth register found that land within about 1 km of flood held 624,310 ha
of the floodplain and 44 readable points, 5 of them open water, and carried
96% of the headline's variance. `topup_sample.py --second` drew 150 more there
under the same screen, as batch "topup2", P0611 to P0760, seed 20261017; 4
candidates were screened out. Every script that leaves top-ups out of
whole-stratum figures now treats any batch starting "topup" alike.

| Open water in the floodplain | Superseded | Corrected |
|---|---:|---:|
| Whole floodplain | 160,688 ± 30,796 ha | 135,505 ± 13,221 ha |
| 95% interval | 100,327 to 221,049 ha | 109,593 to 161,417 ha |
| Clear part | 70,659 ± 14,411 ha | 59,172 ± 6,204 ha |
| Floodplain ceiling at 100 m | 151,794 ha | 130,769 ha |
| Counting V as flood | 393,655 ± 47,226 ha | 400,861 ± 23,933 ha |
| Producer's accuracy, −18.75 dB / −17.75 dB | 0.46 / 0.54 | 0.55 / 0.64 |
| Second person's labels on the relabelled points | 130,608 ± 24,733 ha | 123,996 ± 12,133 ha |
| Claude's labels on the relabelled points | 143,738 ± 28,605 ha | 118,349 ± 11,708 ha |

The open-water share in that stratum fell from 5 of 44 points to 14 of 191, so
the error fell by more than the register's estimate. The new figure lies
inside the old interval. The README no longer says the −17.75 dB map is the
closer one: the first reader's figure lies nearer it, the second person's
about midway, and Claude's nearer the −18.75 dB map. The 200 m ceiling,
157,603 ha, cannot use either top-up and did not change. User's accuracy and
everything over the whole map are unchanged, since the top-ups count only in
the floodplain.

**The first reader labelled the top-up differently.** None of the 150 was
marked as a guess, against 18 of the 100 points near flood in the main sample,
and 50 were called V, against 19. She also knew every one came from near
mapped flood. `second_label.py --extend` therefore took 40 of them at random
and the 8 other points she called open water, R103 to R150, for the same
second person, who labelled them on the first reader's computer, and for
Claude. On the random 40 the second person agreed with the first on 0.875 of
the points, a kappa of 0.776, close to the 0.856 on the main sample. Of the 8
open-water calls she kept 6 and Claude 3. `compare_labels.py` now reports
every set in the key.

**A limit of the renumbering.** Each chip shows its point's original number in
the title. The R numbers hid the order and the set a point came from, but not
which point it was. Neither second reader had the first labels open, and the
first round had the same titles.

**V-02.** The README's limits now name the step from clear sky to cloud: on the
map as drawn 58.7% of the floodplain flood lay under cloud, the whole-floodplain
figure assumes the map errs there as in clear sky, the terrain check supports
that on slope more than on elevation, and the clear part is given beside it.

### C-33 The threshold tried on other floods (F-07)

F-07 said the test split, adjacent chips from the India scene, could not show
the threshold transfers. `transfer_events.py` scores the fixed −18.75 dB on the
hand-labelled chips of the other Sen1Floods11 events. Each went through India's
steps: Planetary Computer RTC read onto every chip on the event's date and
orbit, shifted onto the label grid by correlation with the dataset's own
imagery within ±5 pixels, Lee-filtered, thresholded. India, scored by the same
code, reproduces 0.519 and the script stops if it ever does not.

- **The metadata.** The dates and orbits `find_scenes.py` transcribed all
  match `Sen1Floods11_Metadata.geojson`. Its `VH_thresh` field confirms the
  −21.56 dB `config.py` gives for India as the dataset's own value, on Earth
  Engine sigma0. Across events that field runs from −25.13 to −19.56 dB.
- **What was scored.** 309 chips from nine events. Paraguay's 67 have no
  Sentinel-1 scene on Planetary Computer for 31 October 2018, orbit 68, in RTC
  or GRD; the nearest is 5 November on orbit 141. Two Sri Lanka chips never
  aligned.
- **The result.** Pooled IoU 0.493, 95% interval 0.432 to 0.551, against 0.519
  on India and 0.499 for the authors' per-chip Otsu on the same chips. By event
  it runs from 0.764 (Mekong) to 0.131 (Somalia). Pakistan and Somalia fail on
  precision, 0.205 and 0.152, and their best single thresholds reach only
  0.255 and 0.132. The best threshold per event spans −21.75 to −17.25 dB.
- **Alignment.** Ten chips aligned at the edge of the search, eight of them in
  Mekong; without those Mekong goes from 0.764 to 0.786.

No published figure changes. The README gains a section, "Other floods", and
the closing claim that the method should be checked before use in a new region,
dry ones above all. The chips and RTC reads stay in `data/`; the per-event
tables are in `results/transfer/`.

### C-34 Outside the floodplain, and the 7 and 31 August maps (F-01, F-02)

C-28 checked the floodplain of the 12 August map. This round checks the rest
of that map and both other dates. No published map figure changes; the README
gains two sections, "Outside the floodplain" and "Independent check of the 7
and 31 August maps".

- **The rest of the 12 August map.** `floodplain_layer.py` gains a cutoff of
  150 m at any slope, which splits the rest in two. `score_map.py` scores each
  part with the points in it. On low ground the DEM calls sloped, the map is
  right where it says flood and finds 0.263 ± 0.120 of the open water in the
  clear part. 16 of the 18 open-water points there sit between 57 and 81 m on
  the valley floor.
- **Above 150 m.** Only 280 ha of the 8,282 ha mapped there lay under clear
  sky, with one point in it. `topup_sample.py --third` drew 30 more there (seed
  20261022). 21 of the 30 readable are open water, a user's accuracy of 0.700 ±
  0.085, 0.778 on the published map. The open water is on flat ground at a
  median of 230 m; the false flood is in the mountains, median 1,219 m.
  `usable_topup` now checks slope as well as elevation, and every test of a
  top-up batch matches any name starting "topup".
- **What zero hits rule out.** Where a land stratum finds no open water, its
  share gets no variance, and above 150 m the producer's accuracy printed as
  1.000 ± 0.000. `score_map.py` and `date_sample.py` now give the 95% upper
  bound for every such group in `zero_hit_bounds.csv`. Above 150 m, land far
  from flood could hide up to 45,859 clear hectares.
- **The 7 and 31 August maps.** `scene_inventory.py --map-date` found no
  usable Sentinel-2 scene near either date. `landsat_clear_sky.py` measured
  Landsat clear sky over each map, and `date_sample.py` drew 300 points per
  date on Landsat 7 of 4 August and Landsat 8 of 28 August (seeds 20261023 and
  20261024), screened them, cut chips and estimated. In the floodplain, at
  −18.75 dB:

  | Map | Mapped | Open water | User's accuracy | Producer's accuracy |
  |---|---:|---:|---:|---:|
  | 7 August | 58,286 ha | 35,865 ± 4,187 ha | 0.566 ± 0.069 | 0.920 ± 0.033 |
  | 31 August | 33,768 ha | 27,717 ± 6,235 ha | 0.542 ± 0.073 | 0.660 ± 0.140 |

  The 7 August map's extra flood is mostly water standing in fields; the 31
  August map's is mostly dry ground in the river's seasonal bed. The 7 August
  producer's accuracy rests on no open water among 36 points in floodplain land
  near flood, and the bound there would take it to about 0.54. Both images are
  three days before the radar and 30 m, and only the first reader labelled.
- **The recession.** In open water the floodplain fell from 35,865 to 27,717
  ha, about one standard error of the difference. Counting water through
  vegetation it fell from 165,112 to 38,283 ha. The README's recession figures
  stand as map figures; the check says most of that fall is water leaving
  fields.
- **Tools.** `label_tool.py` gains S to skip a point in simple mode,
  `--blank-only` to visit only unlabelled points, and refuses a label on a
  point with no chip. That last one came from B0106, which was labelled before
  its chip existed; the label was cleared and the point labelled again from
  its chip.
- **Counts.** `accuracy_labels_by_scl.csv` now counts all three top-ups: 167
  points on dark area or unclassified pixels, 62 of them open water, where the
  README said 153 and 48.

### C-35 The 7 and 31 August samples: terrain check and a second reader

C-34 left two things open on the new samples. `date_checks.py` does both. No
published map figure changes.

- **Terrain.** The clear part of each stratum against the rest, on elevation
  and slope, as for 12 August. Inside the floodplain slope agrees on both dates
  (standardised differences 0.24 or less). Elevation differs by 0.23 to 0.42
  on 7 August, about as on 12 August, and by up to 1.70 on 31 August, where the
  clear part of the flood stratum lies 6 m higher than the rest. The README now
  gives the 31 August clear-part figure as the one that needs no assumption,
  and says the whole-floodplain one, and so the recession comparison, rests
  on a weak stand-in. Over the whole map the land strata under cloud are far higher and
  steeper on both dates.
- **A second reader on 7 August.** 145 points: all 105 in the map's flood and
  in "upper threshold only", and 40 at random from the rest (seed 20261025),
  renumbered SA001 onward with their chips cut again under the new numbers.
  Agreement with the first reader is 0.876, kappa 0.787, on the 105 and 0.975,
  kappa 0.847, on the 40. She kept 49 of the 56 water-through-vegetation calls.
  Open water in the floodplain moves from 35,865 to 34,776 ± 4,111 ha with her
  labels, user's accuracy from 0.566 to 0.577.
- **Code.** `date_sample.py` now reads the grid through one generator,
  `tile_pass()`, which the draw and the terrain check share, and its estimate
  is split into `prepare()` and `score_rows()` so the second reading can reuse
  it. Rerun on the 7 August files, the draw gives the same hectares and the
  same candidates, and the estimate the same figures.

### C-36 A second reader on 31 August

The same design as C-35 on the 31 August sample: 145 points, all 105 in the
map's flood and "upper threshold only" and 40 at random (seed 20261026),
renumbered SB001 onward and cut again. No published map figure changes.

- **Agreement.** 0.876, kappa 0.787, on the 105, which by coincidence matches
  7 August to three places; 0.950, kappa 0.812, on the 40. She kept 47 of the
  49 not-water calls, and called 29 of the 60 points in the map's flood not
  water, against 25.
- **Effect.** Open water in the floodplain goes from 27,717 to 22,551 ± 4,790
  ha, its clear part from 11,274 to 8,713 ± 2,403 ha, and user's accuracy from
  0.542 to 0.500.
- **The recession.** On the first reader's labels open water in the floodplain
  fell by about one standard error of the difference between 7 and 31 August;
  on the second person's, from 34,776 to 22,551 ha, by about two. The README
  now says the answer turns on the reader.

### C-37 A fix and polish list on fbc08ab

A list of eight items, none of them in the analysis. Two published figures
change on the map page only.

| Quantity | Superseded | Corrected |
|---|---:|---:|
| 12 August flood on the map page's headline tile | 120,791 ha | 120,790 ha |
| Nagaon flood on the map page | 17,281 ha | 17,280 ha |

- **The map page rounded halves up.** `build_docs_page.py` wrote the page's
  numbers with JavaScript's `Math.round`, which takes 120,790.5 to 120,791,
  where Python's round half to even, used for every README and CSV, gives
  120,790. 27 values in the page's data end in .5 on an even integer. The page
  now rounds half to even, and `verify_all.py` fails if it ever does not.
- **The top-level README** still gave the September figures, 119,779 to
  170,625 ha and 46,943 to 87,127 ha of cropland. It now gives C-31's, and its
  status cell names the one open finding. Docstrings in seven scripts that
  quoted the September figures are updated or marked as such.
- **`REVIEW.md` has a current status.** A dated box under the title, Status
  and Fixed in columns on both finding tables, and a Now column on the
  acceptance criteria. The original text is kept as written.
- **S-03 measured.** `refine_scene.py` said the clean-up ran per tile with a
  16 pixel halo. The halo feeds the DEM only; the clean-up runs on each tile's
  own pixels, so a component split by a seam is judged one side at a time. On
  12 August one pass over the whole map keeps 289 pixels more, 11.6 ha of
  120,790. The same rebuild from the raw map reproduces the published flood
  count to the pixel, which is the part of S-05 tested so far. The clean-up is
  left as it is; the docstring now says what it does.
- **F-09.** The README now names the grid as UTM zone 46N and gives its effect
  on area: an area scale of 0.9992 to 0.9995 over the flood, so the hectares are
  about 0.07% below the ground, 88 ha on the headline. `area_scale.py` measures
  it and writes `results/area_scale.csv`.
- **The 7 August figure that looked like a typo.** The recession block's 65,268
  and 91,540 ha are flood on ground both passes saw, against 65,356 and 91,670
  ha for the whole pass. The block now says "shared ground" and gives the 88
  and 130 ha left out. `compare_dates.py` writes both dates' shared-ground
  flood, so the block traces to a file.
- **Setup.** `requirements.txt` and `requirements-lock.txt` moved from the
  repository root into this folder, the README says to run from here and gives
  the macOS and Linux activation line, and `verify_report.txt` names the
  project folder instead of a local path.
- **Checks.** `verify_all.py` now exits with 1 on any failure. The README's
  headline sits between `<!-- headline -->` markers, so a check on the
  top-level README can compare against it. Rerunning `compare_dates.py` then
  showed a gap: its three figures came out byte for byte the same, so their
  last commit stayed older than the CSVs, and `verify_all.py` called them
  stale while `preflight.py`, which read only the report's README digest,
  passed. The figure check now accepts rows added to a key and value table
  when every row the figure read is unchanged, and `preflight.py` fails on any
  failure the report records. The report also printed "-0.0%" for a
  difference a hair below zero, which came out "+0.0%" on another machine; it
  now prints "+0.0%" for any difference that rounds to zero.
- **RS-02's review** said the RS-01 requirements file sat at the repository
  root. Both mentions now say where it moved.
- **A stray screenshot,** `Capture.JPG` from fd228fb, removed, and
  `.gitignore` now skips files the Windows snipping tool names that way.

### C-38 The zero-hit bound, the other way round

A review on fda900f found the C-34 bound covered only one direction. A land
stratum with no open water found got its 95% bound, but a map whose flood
points were all open water, or none of them, still printed a user's accuracy
of 1.000 ± 0.000 or 0.000 ± 0.000 with nothing to say how few points stood
behind it. No published figure changes.

- **The bound.** `score_map.py` and `date_sample.py` now write
  `user_accuracy_bounds.csv`: for every map, scope and variant where the user's
  accuracy is exactly 1 or 0, the readable points behind it and the 95%
  Clopper-Pearson bound, 0.025^(1/n) or 1 minus it, counted on the points
  without stratum weights. On 12 August, low sloped ground has 8 such points on
  the map as drawn, bound 0.631, and 11 on the published map, bound 0.715.
  Above 150 m at −17.75 dB, 7 August has 3 points and 31 August 1, none open
  water, bounds 0.708 and 0.975.
- **Counts.** Every row of `map_scores.csv` and of each date's `estimates.csv`
  now carries `n_readable` and `n_map_flood`, so a thin figure shows itself.
- **Wording.** The review's numbers, 0.78 and 0.69 for 12 and 8 points, are
  one-sided 95% bounds. These are two-sided, as the C-34 bounds are, so they
  sit lower: 0.735 and 0.631.
- **README.** "What finding nothing rules out" gains the mirror case, and the
  7 and 31 August section gives the −17.75 dB points above 150 m.

---

## Open, not fixed

- **F-01 / F-02, cloud on 31 August and the hills.** The floodplain, the rest
  of the 12 August map and both other dates now have estimates with standard
  errors, and both other dates have a second reader on the points that set
  their user's accuracy. On 31 August the clear part is a weak stand-in for the
  cloudy part of the floodplain. Outside the floodplain the zero-hit bounds
  show how loosely a few dozen points pin down missed water in the hills.
