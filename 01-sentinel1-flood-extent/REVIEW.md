# Technical review: RS-01 Sentinel-1 flood extent

Reviewed as (a) an operational EO product for methodological defensibility and
(b) a submission for reproducibility and provenance. Findings below are against
the repository at `01-sentinel1-flood-extent`, commit `fc951f1` plus 65
uncommitted files.

**Verdict on the editorial test: NO.** An independent analyst with only this
repository cannot reproduce the reported numbers. Blockers are listed in F-01,
F-02 and F-11.

**Verdict on the scientific claim:** the headline figure of 119,779 ha is a map
pixel count carrying no uncertainty, produced by a pipeline whose final three
processing steps have never been validated against anything. The number may well
be approximately right. Nothing in the repository establishes that it is.

---

## Scope note: what of the protocol applies

| Protocol section | Applies | Why |
|---|---|---|
| Geometry and projection | Yes | |
| SAR preprocessing | Partly | RTC is a provider-level product; orbit, thermal noise, calibration and terrain correction are Microsoft's, not ours |
| Optical preprocessing | No | No optical data used |
| Temporal stack | Partly | Three single dates, no compositing |
| Sample design, hyperparameters, tuning | Mostly no | Threshold method, no classifier, no training. The one tuned parameter was selected on the valid split |
| Accuracy reporting | Yes, and failing | |
| Area estimation | Yes, and failing | |
| MMU | Yes, passing | |
| Determinism and seeds | Yes | No RNG in the pipeline |
| Reproducibility | Yes, and failing | |

---

## Phase 1 — Inventory

### Repository state

| Item | Value |
|---|---|
| Commits | 2 (`eb2ac8c`, `fc951f1`) |
| Remote | none configured |
| Modified tracked files | 3 |
| Untracked files | 62, including `README.md`, all of `docs/`, and every `results/` artefact produced after the chip stage |
| Empty or orphaned directories | `notebooks/`, `viewer/` |

**Every number in the README comes from a file that is not in version control.**

### Source files

29 Python files in `src/`, 3 of them shared modules (`config.py`, `chips.py`,
`metrics.py`). Execution graph is intact: `config` → fetch scripts → chip
analysis → `operating_point.py` → `final_method.json` → `full_scene.py` →
`refine_scene.py` → `district_stats.py`, with `compare_dates.py` terminal. No
break found. `find_scenes.py`, `compare_rtc.py`, `triage_fetch.py` and
`agreement_check.py` are diagnostic dead ends by design, and nothing downstream
reads them.

### Dependencies

`requirements.txt` is a full `pip freeze` of 200+ packages, fully pinned. It
includes `jupyterlab`, `notebook`, `scikit-learn` and `stackstac`, none of which
the pipeline imports, and `pywinpty==3.0.5`, which is Windows-only and will fail
to install on Linux or macOS. There is no declared minimal dependency set.

### Hard-coded values outside `config.py`

| Value | File | Note |
|---|---|---|
| `OCCURRENCE_CUT = 50` | `full_scene.py:101`, `refine_scene.py`, `district_stats.py` | Declared three times independently |
| `TILE = 2048`, `HALO = 16` | `full_scene.py:99-100`, `compare_dates.py:70`, `district_stats.py:76` | Four independent declarations |
| `--slope` default `8.0` | `refine_scene.py` argparse | The single largest subtraction in the pipeline lives in a CLI default |
| `--edge-buffer` default `30` | `refine_scene.py` argparse | Same |
| `--min-pixels` default `10` | `refine_scene.py` argparse | Same |
| `CROPLAND = 40` | `district_stats.py:78` | |
| `GB_API` URL | `district_stats.py:80` | |
| `PIXEL_HA = 0.01` | `change_detect.py:59`, `change_sweep.py:69` | Assumes 10 m; silently wrong if those scripts are ever run on the 20 m products |
| `SIGN_TTL`, `RETRIES` | `full_scene.py:102-103` | Benign |

### Config contradicts the code

`config.py` declares:

```python
SLOPE_MAX_DEG = 5.0            # above this, radar shadow/layover dominates
GSW_PERMANENT_MIN = 80         # JRC occurrence % counted as permanent water
```

Neither value is used anywhere. The pipeline runs at **8.0°** and **50%**. The
file that exists to be the single source of truth states two parameters
incorrectly, and a reader auditing the method from `config.py` would compute
different numbers.

### What I could not verify

- I did not run the pipeline from a clean checkout, so end-to-end
  reproducibility is asserted from the execution graph, not demonstrated.
- I did not confirm bit-identical reruns by hashing outputs.
- I did not confirm the installed `odc-stac 0.5.3` default resampling mode by
  reading its source. F-06 is written as "not declared", which is verifiable
  from our code, rather than as a claim about what the default is.
- No data manifest exists, so I cannot state how many files a clean fetch should
  produce or how large they should be.

---

## Phase 2 — Methodological audit, selected results

**Geometry.** All processing is in EPSG:32646 (UTM 46N) at a fixed pixel size,
so areas are computed in projected metres rather than degrees. UTM is conformal,
not equal-area. The AOI spans 92.15–94.16°E against a central meridian of 93°E,
so the scale factor stays within roughly 0.9996–1.0002 and the areal error is
under about 0.1%, on the order of 120 ha on the headline figure. Acceptable, and
currently unstated.

**Resampling.** Declared in exactly one place: `district_stats.py:132`, where
WorldCover uses `mode`, which is correct for a categorical layer. Every other
load takes the library default: Sentinel-1 VH (`full_scene.py:223`), the DEM
(`refine_scene.py:105`, `fetch_dem.py:110`) and JRC occurrence
(`full_scene.py:232`). Three of those are resampled from a finer or coarser
native grid onto the 20 m target, and the choice affects both the speckle
statistics that the threshold acts on and the slope surface that the 8° mask
acts on.

**SAR chain.** Orbit correction, thermal noise removal, calibration and terrain
correction are Microsoft's RTC processing, not ours. Our steps are: linear power
to dB, Lee 5×5 applied in linear power and returned in dB (`chips.py:58-70`,
verified correct), then a global threshold. Correct order, and correctly
described in the README.

**Accuracy.** Reported as single-valued IoU, precision and recall, micro-averaged
across 65 chips. No confidence intervals, no per-split sample sizes, no
per-class producer and user accuracy in the conventional form, no quantity and
allocation disagreement.

**Area.** Pixel count of the map. No stratified or bias-adjusted estimator, no
standard error. This is the central finding, F-01.

**MMU.** 10 pixels at 20 m, so 0.4 ha, applied before area is computed. Reported
area respects it. Passing.

**Determinism.** No random number generation anywhere. Otsu, thresholds,
morphology and the fixed-stride subsamples (`[::7]`, `[::13]`, `[::17]`) are all
deterministic. Reruns should be bit-identical; not verified.

---

## Phase 3 — Findings

### Confirmed

| ID | Severity | Component | Finding | Evidence | Effect on reported area | Required action |
|---|---|---|---|---|---|---|
| F-01 | **Blocking** | Area estimation | The reported product has never been validated. All accuracy figures come from 65 chips at 10 m, scored **before** the slope mask, edge buffer and MMU exist. Those three steps remove 45% of the raw area. The validated product and the reported product are different products. | `operating_point.py` scores chips; `refine_scene.py` produces the reported raster; no script scores the latter | Unknown, and currently unquantifiable | State it in Results, not only in narrative. Report the chip-scale accuracy as applying to the chip-scale product only |
| F-02 | **Blocking** | Area estimation | 119,779 ha is a pixel count with no uncertainty. Good practice (Olofsson et al. 2014, *Remote Sensing of Environment*) requires a design-based estimator with a standard error. At the chosen operating point recall is 0.608, so the map systematically omits water. | `full_scene.py` totals; `results/final_method.json` | Direction: under-detection at the map level, partly offset by commission. At chip scale the tuned point gave −5% against truth | Either produce a bias-adjusted estimate with CI, or label the figure explicitly as an uncorrected map pixel count and quote the chip-scale bias as the only available guide |
| F-03 | Major | Accuracy reporting | No confidence intervals on any accuracy figure. n = 65 chips, micro-averaged, which weights by pixel count and hides chip-level variance. | README accuracy table; `metrics.py` | None directly | Bootstrap over chips; report IoU, P and R with 95% CI, and report macro alongside micro |
| F-04 | Major | Parameter provenance | Three of the four decisions that set the final number (slope 8°, occurrence 50%, edge buffer 30 px) were chosen by inspecting full-scene distributions with no held-out data, and cannot be validated because no labels exist outside the chips. They live in argparse defaults. | `refine_scene.py` argparse | They remove 45% of the raw area between them | Move to config; publish the final area across a grid of all three, not only at the chosen point |
| F-05 | Major | Config integrity | `config.py` declares `SLOPE_MAX_DEG = 5.0` and `GSW_PERMANENT_MIN = 80`; the pipeline runs 8.0 and 50. The stated source of truth is wrong. | `config.py`; `refine_scene.py`; `full_scene.py:101` | None to the computed number; total loss of auditability | Single source of truth, imported everywhere |
| F-06 | Major | Resampling | Resampling is declared for WorldCover only. S1 VH, DEM and GSW take the library default, undeclared and unjustified, and both the threshold and the slope mask are sensitive to it. | `full_scene.py:223,232`, `refine_scene.py:105` vs `district_stats.py:132` | Unquantified | Declare explicitly for every load with a one-line justification per variable |
| F-07 | Major | Validation design | The Sen1Floods11 splits for a single event are spatially adjacent chips from one scene sharing radiometry, terrain and flood state. "Test IoU 0.680" implies a transferability it does not support. | Official split CSVs; `chips.py:split_lookup` | None | Describe the test split as a within-scene check on threshold overfitting, not as evidence of generalisation |
| F-08 | Major | Representativeness | Quoted accuracy applies to floodplain chips; the area figure is computed over 6.26 M ha including hills and upland the chips never sampled. The three artefact retractions already prove the domains differ. | README "Three times a conclusion did not survive" | None directly; bounds the meaning of every accuracy figure | One sentence in Results, adjacent to the accuracy table |
| F-09 | Minor | Projection | Areas computed in UTM 46N, a conformal projection. Distortion under ~0.1% over this AOI, about 120 ha. Unstated. | `config.py` `TARGET_CRS` | ~120 ha, negligible | State the CRS and the bound in the README |
| F-10 | Minor | Dependencies | `requirements.txt` is a 200-package environment freeze including `pywinpty`, which does not install off Windows. No minimal dependency set. | `requirements.txt` | None | Ship a minimal pinned `requirements.txt`; keep the freeze as `requirements-lock.txt` |
| F-11 | **Blocking** | Provenance | 62 untracked files including the README, `docs/`, and every result the README cites. No remote. The committed repository contains only the chip-stage pipeline. | `git status` | None | Commit and push before any claim of reproducibility |
| F-12 | Minor | Hard-coding | `TILE`, `HALO`, `OCCURRENCE_CUT` and `PIXEL_HA` each declared independently in three or four files. `PIXEL_HA = 0.01` assumes 10 m and is wrong if those scripts touch the 20 m products. | table above | None today; latent | Centralise; derive `PIXEL_HA` from resolution |
| F-13 | Minor | Repo hygiene | `notebooks/` and `viewer/` empty. `date_comparison.csv` orphaned by the later `--out` naming. | file tree | None | Remove or populate |
| F-14 | Editorial | Documentation | No data manifest, so "clean state" reproduction cannot be checked. | absent | None | Add expected file counts and sizes per fetch script |

### Suspected, with the test that would settle each

| ID | Severity if confirmed | Suspicion | Test |
|---|---|---|---|
| S-01 | Major | Nearest-neighbour resampling of 10 m VH onto the 20 m grid discards half the samples and inflates speckle variance, which shifts the optimum threshold and therefore the area. | Re-run `full_scene.py --res 20` with `resampling="average"` on the VH load and compare flood area and the slope histogram. One run, ~30 min |
| S-02 | Major | DEM resampled from 30 m to 20 m by nearest produces a stepped surface and biases computed slope, which sets the 8° cut removing 68,437 ha. | Recompute slope from a bilinear-resampled DEM and re-run `refine_scene.py`; compare the removed area |
| S-03 | Moderate | MMU applied per padded tile could split a connected flood object across a tile seam. With a 16 px halo and a 10 px MMU the object must be under 10 px on both sides, so the effect should be near zero. | Count components touching tile boundaries and compare against a single-pass run on a subset |
| S-04 | Moderate | The residual scattered water in the north-west may be genuine wetland rather than artefact. | Cross-tabulate residual flood against JRC seasonality and WorldCover wetland classes |
| S-05 | Minor | Reruns may not be bit-identical if any load path is order-dependent. | Hash `India_water_20m.tif` across two clean runs |

---

## Phase 4 — Remediation, proposed

Per the protocol I am not changing anything that alters a reported number
without asking. Ordered by value:

1. **Commit and push** (F-11). No method change. Nothing else is meaningful
   until the results are under version control.
2. **Config integrity and centralisation** (F-05, F-04, F-12). No method change,
   no number changes. Fix the two wrong constants, move the three refinement
   parameters into `config.py`, derive `PIXEL_HA` from resolution.
3. **Accuracy with intervals** (F-03). New numbers, no change to existing ones:
   bootstrap over chips, report macro alongside micro.
4. **Parameter sensitivity grid** (F-04). Report the final area across slope ×
   occurrence × buffer rather than at one point. This does not change the
   headline; it puts a range around it, which is what the project already does
   for its other four sensitivities.
5. **Bias-adjusted area** (F-02). This one **will change the headline number**.
   The honest version requires a probability sample of the mapped area, which
   does not exist and would need to be drawn and labelled. The achievable
   version is to state the figure as an uncorrected pixel count with the
   chip-scale bias quoted. I recommend the achievable version plus an explicit
   statement of what a defensible estimate would require.
6. **Resampling declared** (F-06, S-01, S-02). May change the headline. Two runs
   to measure, then a decision.
7. **Minimal requirements** (F-10), **data manifest** (F-14), **repo hygiene**
   (F-13).

## Phase 5 — README

The current README is closer to a methods section than to marketing, but against
this protocol it fails on: accuracy without intervals, area without an
estimator or standard error, no confusion matrix, no per-file directory table,
no citation block, no licence, no changelog, and no expected runtimes or row
counts for reproduction. Items 1 to 4 above would have to land first, since the
README should not claim more rigour than the repository holds.

## Phase 6 — Map

Not attempted. The current `docs/index.html` is a working web deliverable but is
not a publication map: no scale bar, no north arrow, no graticule, no inset
locator, no stated CRS on the face, no per-class area table with uncertainty,
and a palette chosen for screen rather than for colour-blind safety. Building
one is straightforward once F-02 is settled, because the area table needs the
uncertainty column that does not yet exist.

---

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Pipeline runs end to end from clean state using only repository contents | **FAIL** | 62 untracked files; no data manifest |
| 2 | Reported areas reproduce within a stated tolerance | **FAIL** | No tolerance stated; determinism unverified |
| 3 | No Blocking or Major finding open, or each documented with quantified effect | **FAIL** | F-01, F-02, F-11 blocking; six Major open |
| 4 | Every README number traces to a generated artefact | **PASS with exception** | All trace to `results/*.csv` or `*.json`, but those files are untracked (F-11) |
| 5 | Map carries all required cartographic elements | **FAIL** | See Phase 6 |
| 6 | No hard-coded credentials, paths or asset IDs outside config | **PARTIAL** | No credentials anywhere (PASS). Paths and parameters scattered (F-12) |

Nothing here says the flood map is wrong. It says the repository does not
currently let anyone else establish that it is right, and that the single most
quoted number carries no uncertainty and describes a product that was never
scored.
