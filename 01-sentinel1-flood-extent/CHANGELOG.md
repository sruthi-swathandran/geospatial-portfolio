# Changelog

Every entry gives the superseded value, the corrected value, and why the first
one was wrong. Nothing is silently overwritten. Where a number appeared in an
earlier version of `README.md` or `docs/index.html`, it is listed here so a
reader who saw it can find out what happened to it.

---

## 2016 review round (methodological audit)

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
figure. Scaling by the chip-scale ratio gives roughly 153,800 ha, but that
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
occurrence 25 to 70 percent it is 61,522 to 173,395 ha, a factor of 2.8. The
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
| Flooded cropland | 43,494 ha | 80,923 ha |

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
| Total flood fall | 39.9% | 50.5% |
| Flooded cropland fall | 80.8% | 82.5% |

The total-flood recession is threshold-dependent and is now reported as a range.
The cropland recession is not, moving 1.7 points across a choice that shifts
total flood area by 42%, so the claim that fields drain faster than channels
stands without qualification.

A prediction that was wrong, recorded rather than dropped: relaxing the
threshold was expected to add terrain and edge noise. On 7 August 87% of what it
adds is cropland, because partially inundated fields with emergent crop sit at
intermediate backscatter. On 31 August, post-drainage, that falls to 57%.

---

## Open, not fixed

- **F-01 / F-02.** The reported product has never been validated. All accuracy
  figures describe the chip-scale threshold output at 10 m, before the slope
  mask, edge buffer and MMU exist. A design-based area estimate with a standard
  error requires a probability sample of the mapped area that has not been
  drawn. Documented in README limitations with the direction and rough size of
  the bias.
- **F-07.** The Sen1Floods11 splits for one event are spatially adjacent chips
  from a single scene. The test split checks that the threshold was not fitted
  to the valid split. It is not evidence of transfer.
- **S-01 / S-02.** Whether nearest resampling of VH and of the DEM biases the
  threshold and the slope mask. Machinery to test it is in place; the runs have
  not been made.
