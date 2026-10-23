"""
RS-02. Fine-tune FTW v3 B7 on Indian chips, on a free Kaggle GPU.

Why
---
FTW v3 with an EfficientNet-B7 encoder is the best public checkpoint in this
project. It finds 12.9% of labelled Indian test parcels and 33.1% of
Slovenian ones. It has already seen India: FTW's release config lists India
among its training countries, and the checkpoint records ignore_index 3, so
its loss skipped every unlabelled Indian pixel. Indian masks hold no
background at all, only interior (1), boundary (2) and unknown (3). This asks
whether more weight on India, starting from v3, finds more Indian parcels.

Two arms, from the same starting weights
----------------------------------------
  india            India's train split only
  india_slovenia   India's train split, plus as many Slovenian train chips
                   as India has, drawn afresh each epoch, which carry real
                   background labels
Indian chips with no labelled pixel are left out, since they add nothing to
the loss.

The recipe, fixed before training
---------------------------------
  start      prue_efnet7_checkpoint.ckpt, v3 full B7, its sha256 checked
  network    smp U-Net, EfficientNet-B7, 8 channels in, 3 classes, as stored
  loss       log-cosh Dice over the three classes with class weights 0.05,
             0.2 and 0.75 and unknown pixels (3) ignored, which are v3's own
             settings; the loss is copied from ftw-tools (MIT licence)
  optimiser  AdamW at a learning rate of 0.0001, a tenth of v3's, held
             constant
  epochs     20, each one pass over India's labelled train chips
  batch      8, in mixed precision
  input      window_b then window_a, B04 B03 B02 B08 each
  augment    each sample divided by a random number from 1500 to 4500, with
             its two windows swapped half the time, as the PRUE recipe
             trains; then a random quarter turn and random flips. FTW's
             random sharpness is left out.
  selection  after every epoch, object recall on India's val chips, scored
             the way the project scores: objects are 4-connected runs of
             class 1 of 500 m2 or more, and a parcel counts as found at IoU
             0.5 against its interior with the boundary ring given back. The
             epoch with the highest India val recall, from 1 to 20, is kept,
             the earlier one on a tie. Epoch 0, v3 untouched, is measured for
             reference and cannot be chosen.
  seed       20261026. GPU kernels are not bit-exact, so a rerun lands near
             the same numbers and not exactly on them.

The test chips, 399 Indian and 228 Slovenian, are never read here. They are
scored on the author's machine by src/finetune_score.py, whose readings were
set in its own docstring before this ran.

Running it on Kaggle
--------------------
  1. A private Kaggle dataset holding india.zip, slovenia.zip and
     prue_efnet7_checkpoint.ckpt. Kaggle may unpack the zips; either works.
  2. A notebook with that dataset added, a GPU accelerator and internet on.
  3. This file in one cell. With SMOKE = True it runs one short epoch per arm
     on 32 chips, to check that everything loads and to time a step. With
     SMOKE = False, run it through Save Version, Save and Run All, so it
     keeps going with the browser closed.

Outputs, in /kaggle/working/finetune/<arm>/:
  v3b7_ft_<arm>.ckpt   the chosen epoch, in the layout newer_checkpoints.py
                       loads, with the fine-tuning recorded in its
                       hyper_parameters
  log.csv              loss and val recall per epoch, epoch 0 included
  done.json            the chosen epoch, its val recall and the sha256
An arm that already has a done.json is skipped, so a run that stops can be
started again.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from importlib import metadata
from pathlib import Path

import numpy as np

SMOKE = True                 # set False for the real run

SEED = 20261026
EPOCHS = 20
BATCH = 8
LR = 1e-4
ARMS = {"india": ["india"], "india_slovenia": ["india", "slovenia"]}
# 500 m2 over each country's mean pixel area, 36.81 and 24.81 m2, as
# ftw_common.grid_pixel_area_m2() gives them
MIN_PX = {"india": 14, "slovenia": 20}
MAX_RING_DIST = 3.0
IGNORE = 3
BASE_FILE = "prue_efnet7_checkpoint.ckpt"
BASE_SHA = ("2b1b34a17b85b8f70da6ff737529743b"
            "6bc6049e987bce5a1fcdd7279eb3b120")
SMP_VERSION = "0.5.0"        # the version pinned in requirements-lock.txt
INPUT = Path("/kaggle/input")
UNPACK = Path("/tmp/ftw")
OUT = Path("/kaggle/working/finetune_smoke" if SMOKE
           else "/kaggle/working/finetune")
RULE = "=" * 78


def need(dist: str, version: str | None = None) -> None:
    """Install a package unless the right version is already there."""
    try:
        have = metadata.version(dist)
        if version is None or have == version:
            return
    except metadata.PackageNotFoundError:
        pass
    spec = f"{dist}=={version}" if version else dist
    print(f"  installing {spec}", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec],
                   check=True)


need("segmentation_models_pytorch", SMP_VERSION)
need("rasterio")

import pandas as pd                                           # noqa: E402
import rasterio                                               # noqa: E402
import segmentation_models_pytorch as smp                     # noqa: E402
import torch                                                  # noqa: E402
from scipy.ndimage import distance_transform_edt              # noqa: E402
from scipy.ndimage import label as cc_label                   # noqa: E402
from segmentation_models_pytorch.losses import DiceLoss       # noqa: E402


# ---------------------------------------------------------------------------
# loss, copied from ftw-tools (MIT)
# ---------------------------------------------------------------------------

class LogCoshDice(DiceLoss):
    """ftw-tools' logCoshDice: smp's Dice per class, weighted, then log cosh.

    ftw-tools passes classes=3, which smp's to_tensor turns into None, so
    every class is kept. Passing None here does the same thing.
    """

    def __init__(self, class_weights, **kwargs):
        super().__init__(**kwargs)
        self.class_weights = torch.tensor(class_weights, dtype=torch.float32)

    def aggregate_loss(self, loss: torch.Tensor) -> torch.Tensor:
        w = self.class_weights.to(loss.device)
        loss = (loss * w) / w.sum()
        return torch.log(torch.cosh(loss.mean()))


# ---------------------------------------------------------------------------
# scoring, as in ftw_common, compare_segmenters and seg_score
# ---------------------------------------------------------------------------

def full_fields(inst: np.ndarray, c3: np.ndarray) -> np.ndarray:
    """Parcels with the eroded boundary ring given back to the nearest one."""
    ring = c3 == 2
    if inst.max() == 0 or not ring.any():
        return inst.copy()
    dist, idx = distance_transform_edt(inst == 0, return_indices=True)
    claim = ring & (dist <= MAX_RING_DIST)
    full = inst.copy()
    full[claim] = inst[tuple(idx)][claim]
    return full


def drop_small(seg: np.ndarray, min_px: int) -> np.ndarray:
    counts = np.bincount(seg.ravel())
    small = np.flatnonzero(counts < min_px)
    small = small[small > 0]
    if small.size:
        seg = seg.copy()
        seg[np.isin(seg, small)] = 0
    return seg


def object_count(seg: np.ndarray) -> int:
    counts = np.bincount(seg.ravel())
    return int((counts[1:] > 0).sum()) if counts.size > 1 else 0


def parcel_ious(truth: np.ndarray, seg: np.ndarray) -> list:
    seg = seg.astype(np.int64, copy=False)
    n_seg = int(seg.max())
    sizes = np.bincount(seg.ravel(), minlength=n_seg + 1)
    out = []
    for pid in np.unique(truth[truth > 0]):
        t = truth == pid
        ov = np.bincount(seg[t].ravel(), minlength=n_seg + 1)
        ov[0] = 0
        j = int(ov.argmax())
        inter = int(ov[j])
        union = int(t.sum()) + int(sizes[j]) - inter
        out.append(inter / union if union else 0.0)
    return out


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def find_country(country: str) -> Path:
    hit = sorted(INPUT.rglob(f"chips_{country}.parquet"))
    if hit:
        return hit[0].parent
    z = sorted(INPUT.rglob(f"{country}.zip"))
    if not z:
        sys.exit(f"neither chips_{country}.parquet nor {country}.zip is "
                 f"under {INPUT}. Add the dataset to the notebook.")
    dest = UNPACK / country
    if not (dest / f"chips_{country}.parquet").exists():
        print(f"  unpacking {z[0].name}", flush=True)
        zipfile.ZipFile(z[0]).extractall(dest)
    return dest


def read(path: Path) -> np.ndarray:
    with rasterio.open(path) as s:
        return s.read()


class Country:
    DIRS = ("s2_images/window_b", "s2_images/window_a",
            "label_masks/semantic_3class", "label_masks/instance")

    def __init__(self, name: str):
        self.name = name
        self.root = find_country(name)
        self.meta = pd.read_parquet(self.root / f"chips_{name}.parquet")

    def ids(self, split: str) -> list:
        ids = sorted(self.meta.loc[self.meta["split"] == split, "aoi_id"])
        return [i for i in ids
                if all((self.root / d / f"{i}.tif").exists()
                       for d in self.DIRS)]

    def image(self, i: str) -> np.ndarray:
        b = read(self.root / "s2_images/window_b" / f"{i}.tif")
        a = read(self.root / "s2_images/window_a" / f"{i}.tif")
        img = np.concatenate([b, a])
        if img.shape != (8, 256, 256):
            sys.exit(f"{self.name} {i}: image is {img.shape}, not 8x256x256")
        return img

    def c3(self, i: str) -> np.ndarray:
        return read(self.root / "label_masks/semantic_3class" / f"{i}.tif")[0]

    def truth(self, i: str) -> np.ndarray:
        inst = read(self.root / "label_masks/instance" / f"{i}.tif")[0]
        return full_fields(inst.astype(np.int32), self.c3(i))


def load_train(c: Country, limit: int) -> dict:
    ids = c.ids("train")
    xs, ys, kept = [], [], []
    for i in ids:
        y = c.c3(i)
        if not (y != IGNORE).any():
            continue
        xs.append(c.image(i))
        ys.append(y)
        kept.append(i)
        if limit and len(kept) >= limit:
            break
    print(f"  {c.name} train: {len(kept)} of {len(ids)} chips have labelled "
          f"pixels", flush=True)
    return {"x": np.stack(xs), "y": np.stack(ys), "ids": kept}


def load_val(c: Country, limit: int) -> dict:
    ids = c.ids("val")
    if limit:
        ids = ids[:limit]
    xs, ts = [], []
    for i in ids:
        xs.append(c.image(i))
        ts.append(c.truth(i))
    print(f"  {c.name} val: {len(ids)} chips", flush=True)
    return {"x": np.stack(xs), "truth": ts, "ids": ids}


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

def load_base(path: Path) -> tuple:
    try:
        ck = torch.load(path, map_location="cpu", weights_only=False)
    except ModuleNotFoundError:
        need("lightning")
        ck = torch.load(path, map_location="cpu", weights_only=False)
    hp = dict(ck["hyper_parameters"])
    state = {k[len("model."):]: v for k, v in ck["state_dict"].items()
             if k.startswith("model.")}
    return hp, state


def build(hp: dict):
    return smp.Unet(encoder_name=hp["backbone"], encoder_weights=None,
                    in_channels=hp["in_channels"], classes=hp["num_classes"],
                    **(hp.get("model_kwargs") or {}))


def augment(x: torch.Tensor, y: torch.Tensor, rng) -> tuple:
    """Raw counts in, scaled and moved samples out, one sample at a time."""
    xs, ys = [], []
    for k in range(x.shape[0]):
        xi, yi = x[k], y[k]
        if rng.random() < 0.5:
            xi = torch.cat([xi[4:], xi[:4]])
        q = int(rng.integers(4))
        xi, yi = torch.rot90(xi, q, (1, 2)), torch.rot90(yi, q, (0, 1))
        if rng.random() < 0.5:
            xi, yi = xi.flip(2), yi.flip(1)
        if rng.random() < 0.5:
            xi, yi = xi.flip(1), yi.flip(0)
        xs.append(xi / float(rng.uniform(1500, 4500)))
        ys.append(yi)
    return torch.stack(xs), torch.stack(ys)


@torch.no_grad()
def val_recall(net, v: dict, country: str) -> dict:
    net.eval()
    hits = parcels = objs = chips = 0
    for s in range(0, len(v["ids"]), 16):
        xb = torch.from_numpy(v["x"][s:s + 16].astype(np.float32)).cuda()
        with torch.autocast("cuda", dtype=torch.float16):
            pred = net(xb / 3000).argmax(1).cpu().numpy()
        for k, p in enumerate(pred):
            truth = v["truth"][s + k]
            if truth.max() == 0:
                continue
            lab, _ = cc_label(p == 1)
            seg = drop_small(lab.astype(np.int32), MIN_PX[country])
            ious = parcel_ious(truth, seg)
            hits += sum(x >= 0.5 for x in ious)
            parcels += len(ious)
            objs += object_count(seg)
            chips += 1
    net.train()
    return {"recall": hits / max(parcels, 1), "parcels": parcels,
            "objects": objs / max(chips, 1)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# one arm
# ---------------------------------------------------------------------------

def train_arm(arm: str, train: dict, val: dict, hp: dict, base: dict) -> None:
    out = OUT / arm
    out.mkdir(parents=True, exist_ok=True)
    if (out / "done.json").exists():
        print(f"\n  {arm}: done.json exists, skipped")
        return
    print("\n" + RULE)
    print(f"ARM {arm}: {', '.join(ARMS[arm])}")
    print(RULE, flush=True)

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    net = build(hp)
    net.load_state_dict(base, strict=True)
    net.cuda().train()
    loss_fn = LogCoshDice(class_weights=hp["class_weights"],
                          mode="multiclass", ignore_index=IGNORE)
    opt = torch.optim.AdamW(net.parameters(), lr=LR)
    scaler = torch.amp.GradScaler("cuda")
    epochs = 1 if SMOKE else EPOCHS

    log = []

    def evaluate(epoch: int, loss: float, secs: float) -> dict:
        row = {"arm": arm, "epoch": epoch, "train_loss": round(loss, 5)}
        for c, v in val.items():
            r = val_recall(net, v, c)
            row[f"{c}_val_recall"] = round(r["recall"], 4)
            row[f"{c}_val_objects"] = round(r["objects"], 1)
        row["secs"] = round(secs)
        log.append(row)
        with (out / "log.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row))
            w.writeheader()
            w.writerows(log)
        print("  " + "  ".join(f"{k} {v}" for k, v in row.items()
                               if k != "arm"), flush=True)
        return row

    evaluate(0, float("nan"), 0)
    best, best_epoch = -1.0, 0
    n_in = len(train["india"]["ids"])
    for epoch in range(1, epochs + 1):
        tic = time.time()
        order = [("india", int(i)) for i in rng.permutation(n_in)]
        if "slovenia" in ARMS[arm]:
            n_sl = len(train["slovenia"]["ids"])
            pick = rng.choice(n_sl, size=min(n_in, n_sl), replace=False)
            order += [("slovenia", int(i)) for i in pick]
            order = [order[j] for j in rng.permutation(len(order))]
        total, steps = 0.0, 0
        for b in range(0, len(order), BATCH):
            items = order[b:b + BATCH]
            x = torch.from_numpy(np.stack(
                [train[c]["x"][i] for c, i in items]).astype(np.float32))
            y = torch.from_numpy(np.stack(
                [train[c]["y"][i] for c, i in items]).astype(np.int64))
            x, y = augment(x.cuda(), y.cuda(), rng)
            with torch.autocast("cuda", dtype=torch.float16):
                logits = net(x)
            loss = loss_fn(logits.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            total += float(loss)
            steps += 1
            if epoch == 1 and steps == 20:
                rate = (time.time() - tic) / steps
                print(f"  {rate:.2f} s a step, {len(order) // BATCH} steps "
                      f"an epoch", flush=True)
        row = evaluate(epoch, total / max(steps, 1), time.time() - tic)
        if row["india_val_recall"] > best:
            best, best_epoch = row["india_val_recall"], epoch
            torch.save(net.state_dict(), out / "best_state.pt")

    state = torch.load(out / "best_state.pt", map_location="cpu")
    hp2 = dict(hp)
    hp2["lr"] = LR
    hp2["fine_tune"] = {
        "script": "kaggle/finetune_v3.py", "base": BASE_FILE,
        "base_sha256": BASE_SHA, "arm": arm, "countries": ARMS[arm],
        "epochs": epochs, "best_epoch": best_epoch, "seed": SEED,
        "india_val_recall_epoch0": log[0]["india_val_recall"],
        "india_val_recall_best": best, "smoke": SMOKE}
    ckpt = out / f"v3b7_ft_{arm}.ckpt"
    torch.save({"hyper_parameters": hp2,
                "state_dict": {"model." + k: v for k, v in state.items()}},
               ckpt)
    (out / "best_state.pt").unlink()
    done = {"arm": arm, "best_epoch": best_epoch,
            "india_val_recall_epoch0": log[0]["india_val_recall"],
            "india_val_recall_best": best, "checkpoint": ckpt.name,
            "sha256": sha256(ckpt), "smoke": SMOKE}
    (out / "done.json").write_text(json.dumps(done, indent=2))
    print(f"  kept epoch {best_epoch}, India val recall "
          f"{log[0]['india_val_recall']:.4f} at epoch 0, {best:.4f} kept")
    print(f"  wrote {ckpt}")
    del net
    torch.cuda.empty_cache()


def main() -> None:
    print(RULE)
    print("FINE-TUNING FTW v3 B7 ON INDIA" + (", SMOKE TEST" if SMOKE else ""))
    print(RULE)
    if not torch.cuda.is_available():
        sys.exit("no GPU. Set the notebook's accelerator to a GPU.")
    print(f"  {torch.cuda.get_device_name(0)}, torch {torch.__version__}, "
          f"smp {smp.__version__}")
    hits = sorted(INPUT.rglob(BASE_FILE))
    if not hits:
        sys.exit(f"{BASE_FILE} is not under {INPUT}")
    got = sha256(hits[0])
    if got != BASE_SHA:
        sys.exit(f"{BASE_FILE} has sha256 {got}, not the release's")
    print(f"  {BASE_FILE} matches the release")
    hp, base = load_base(hits[0])
    print(f"  {hp['backbone']}, loss {hp['loss']}, class weights "
          f"{hp['class_weights']}, ignore_index {hp['ignore_index']}")

    limit = 32 if SMOKE else 0
    countries = {c: Country(c) for c in ("india", "slovenia")}
    train = {c: load_train(countries[c], limit) for c in countries}
    val = {c: load_val(countries[c], limit) for c in countries}
    for arm in ARMS:
        train_arm(arm, train, val, hp, base)
    print("\n" + RULE)
    print(f"Done. Download {OUT} from the notebook's output.")
    print(RULE)


if __name__ == "__main__":
    main()
