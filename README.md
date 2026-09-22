# Geospatial portfolio

Two remote sensing projects built on open data, each one asking how much of
its answer comes from the imagery and how much comes from choices nobody
usually declares.

That question is the point of this repository. Producing a flood map or a field
boundary layer is a solved exercise. Knowing which of its numbers would survive
someone checking them is the part that decides whether anyone should act on the
result, so every project here is built to be checked and then checked.

| | project | the question | state |
|---|---|---|---|
| **RS-01** | [Sentinel-1 flood extent](01-sentinel1-flood-extent/) | How much does a flood map move when you change one defensible decision? | Complete, three review findings open |
| **RS-02** | [Field boundaries for smallholdings](02-field-boundaries-smallholder/) | Does the published model fail on Indian fields because of the imagery or because of the model? | Stage 2b complete, stage 3 in progress |

---

## What each one found

**RS-01, flood extent on the Brahmaputra.** Between 119,779 and 170,625 hectares
of flood water on 12 August 2016, of which between 46,943 and 87,127 hectares
was cropland. The range is not measurement noise. It is the distance between two
operating points that both have an argument behind them and that differ by one
decibel. Every figure in that project is reported with the decision that moves
it and the amount it moves by. There is an
[interactive map](https://sruthi-swathandran.github.io/geospatial-portfolio/01-sentinel1-flood-extent/docs/)
of the three acquisitions and the recession between them.

**RS-02, field boundaries for Indian smallholdings.** The released state of the
art recovers 2.7% of Indian smallholdings and 22.2% of Slovenian parcels. Read
at the same object budget that model spends, a foundation model which has never
seen a field boundary recovers 15.3% of the Indian parcels and an untrained
watershed recovers 10.7%. Three draws in 200 of randomly scattered cells, with
the imagery never opened, beat the trained model outright. The failure belongs
to the method rather than to a shortage of signal, and the project also shows
that the remaining failure below three native pixels is not explained by parcel
width either.

---

## How these are built

The conventions are the same across projects and they are the reason to read
one.

**Open data only.** Every input is publicly retrievable and licensed for reuse,
listed with its terms in each project's README. Nothing here comes from any
private, client or internal source.

**Every number traces to a generated file.** Tables in the write-ups are written
by scripts from the result CSVs. In RS-02 a checker pulls every number out of
every table and fails if one of them appears in no generated table, which exists
because three numbers once drifted from their artefacts and a reviewer caught it
rather than the workflow.

**Each project carries a written review of itself.** `REVIEW.md` reads the work
twice over, once as a remote sensing scientist would read it before a programme
board and once as a journal editor would read a submission. Findings are listed
with severity and evidence, including the ones still open. The reviews are
adversarial on purpose and neither project passed its own acceptance criteria on
first reading.

**Corrections are logged, not quietly fixed.** Every number that changed is
recorded with its superseded value and the reason it was wrong. RS-01 keeps
these in `CHANGELOG.md`, RS-02 as corrections B-01 to B-12 in `COMPARISON.md`.
Among them: a control that rewarded methods for cutting a scene into more
pieces, a scorer that measured two different objects and disagreed with itself
by a factor of two, and a claim about resolution that the project's own data
contradicted.

**Controls before conclusions.** A method that beats nothing is a method that
has not been tested. RS-02 pairs every measurement with a null model at matched
object count and reads every method at a matched object budget, because the
metric otherwise pays for volume. RS-01 brackets its headline between two
operating points rather than picking one.

**Everything runs on a CPU.** No GPU appears anywhere in this repository. The
longest single job is about sixteen hours and it resumes if interrupted.

---

## Reading order

Start with the project README, which opens with the result and the decision
behind it. `REVIEW.md` is the fastest way to see how far the work has been
pushed and where it stops. The staged write-ups underneath hold the measurements
themselves.

Numbers in this repository are stated with their uncertainty and with the thing
that would change them. Where something is a bound rather than a measurement, it
says so.

---

## Who wrote this

Sruthi Swathandran. PhD in applied geology, specialising in remote sensing,
with three peer-reviewed publications and an INSPIRE fellowship from India's
Department of Science and Technology. Currently leading remote sensing and GIS
work on agricultural monitoring across Indian states, and studying for an MSc in
artificial intelligence and machine learning.

This repository is the public half of that: satellite work carried to the point
where the uncertainty is quantified rather than assumed, which is the standard
agricultural decisions actually need.

Contact and issues: please open a GitHub issue.

---

## Licence

Code is released under the MIT Licence. Data carries its own terms, listed per
project. Sentinel derivatives contain modified Copernicus data.
