"""
RS-02. Read the ftw-tools API before writing against it.

`ftw model test` dies on Windows with WinError 1455, the paging file being too
small. Windows spawns DataLoader workers rather than forking, so each worker
re-imports torch, lightning and kornia and needs its own gigabyte or two of
commit charge. The CLI exposes no worker count, so the fix is our own loop with
num_workers=0.

That loop should use FTW's dataset and preprocessing rather than a
reimplementation, otherwise our numbers stop being comparable to theirs. This
prints what is needed to do that correctly:

    A  the checkpoint: hyperparameters and state_dict shape
    B  ftw.datasets and ftw.datamodules, what they expose and how to call it
    C  the preprocessing, in full, because normalisation decides everything
    D  how ftw_cli.model.test builds its dataloader, including num_workers

Nothing is written and nothing is downloaded. Import only.

    python src\\inspect_ftw_api.py
    python src\\inspect_ftw_api.py --ckpt models\\3class_ccby.ckpt
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
RULE = "=" * 78


def head(title):
    print("\n" + RULE)
    print(title)
    print(RULE)


def show_source(obj, label, limit=120):
    try:
        src = inspect.getsource(obj)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {label}: source unavailable ({exc})")
        return
    lines = src.splitlines()
    print(f"  --- {label}  ({len(lines)} lines) ---")
    for line in lines[:limit]:
        print("  " + line)
    if len(lines) > limit:
        print(f"  ... {len(lines) - limit} more lines ...")


def checkpoint(path):
    head("A. THE CHECKPOINT")
    p = Path(path)
    if not p.exists():
        print(f"  {p} not found")
        return
    import torch
    ck = torch.load(p, map_location="cpu", weights_only=False)
    print(f"  {p.name}, {p.stat().st_size / 1e6:.0f} MB")
    print(f"  top-level keys: {sorted(ck.keys())}\n")

    hp = ck.get("hyper_parameters", {})
    for k in sorted(hp):
        print(f"    {k:<24}{hp[k]}")

    sd = ck.get("state_dict", {})
    print(f"\n  state_dict: {len(sd):,} tensors")
    keys = list(sd.keys())
    for k in keys[:6]:
        print(f"    {k}  {tuple(sd[k].shape)}")
    print("    ...")
    for k in keys[-4:]:
        print(f"    {k}  {tuple(sd[k].shape)}")

    prefixes = sorted({k.split(".")[0] for k in keys})
    print(f"\n  top-level prefixes in state_dict: {prefixes}")
    print("  (that prefix has to be stripped before loading into a bare "
          "segmentation model)")


def modules():
    head("B. WHAT ftw.datasets AND ftw.datamodules EXPOSE")
    for name in ("ftw.datasets", "ftw.datamodules"):
        try:
            mod = __import__(name, fromlist=["*"])
        except Exception as exc:                              # noqa: BLE001
            print(f"  {name}: import failed, {type(exc).__name__}: {exc}")
            continue
        public = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n  {name}")
        print(f"    {', '.join(public)}")
        for n in public:
            obj = getattr(mod, n)
            if not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            if getattr(obj, "__module__", "") != name:
                continue          # skip things merely imported into the module
            try:
                sig = inspect.signature(obj)
            except Exception:                                 # noqa: BLE001
                sig = "(signature unavailable)"
            print(f"\n    {n}{sig}")
            doc = inspect.getdoc(obj)
            if doc:
                for line in doc.splitlines()[:6]:
                    print(f"        {line}")


def preprocessing():
    head("C. THE PREPROCESSING, IN FULL")
    try:
        from ftw import datamodules as dm
    except Exception as exc:                                  # noqa: BLE001
        print(f"  import failed: {exc}")
        return
    fn = getattr(dm, "preprocess", None)
    if fn is None:
        print("  no preprocess found in ftw.datamodules")
        return
    show_source(fn, "ftw.datamodules.preprocess")
    print("\n  Normalisation decides everything downstream. If our loop scales")
    print("  the imagery differently from this, the model sees inputs it was")
    print("  never trained on and the result says nothing about FTW.")


def dataset_getitem():
    head("D. HOW A CHIP BECOMES A TENSOR")
    try:
        from ftw import datasets as ds
    except Exception as exc:                                  # noqa: BLE001
        print(f"  import failed: {exc}")
        return
    classes = [getattr(ds, n) for n in dir(ds)
               if inspect.isclass(getattr(ds, n))
               and getattr(getattr(ds, n), "__module__", "") == "ftw.datasets"]
    if not classes:
        print("  no dataset classes found in ftw.datasets")
        return
    for cls in classes:
        print(f"\n  class {cls.__name__}")
        try:
            print(f"    __init__{inspect.signature(cls.__init__)}")
        except Exception:                                     # noqa: BLE001
            pass
        for attr in ("__getitem__", "_load_image", "_load_target"):
            fn = getattr(cls, attr, None)
            if fn is not None:
                show_source(fn, f"{cls.__name__}.{attr}", limit=60)


def cli_test():
    head("E. HOW ftw_cli BUILDS ITS DATALOADER")
    try:
        from ftw_cli import model as m
    except Exception as exc:                                  # noqa: BLE001
        print(f"  import failed: {exc}")
        return
    fn = getattr(m, "test", None)
    if fn is None:
        print("  no test function found")
        return
    show_source(fn, "ftw_cli.model.test", limit=160)
    print("\n  Look for num_workers. That argument is why this crashes on")
    print("  Windows, and whether it is hardcoded decides if the CLI can be")
    print("  used at all here.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(PROJECT / "models" / "2class_ccby.ckpt"))
    args = ap.parse_args()

    print("Reading the ftw-tools API before writing against it.")
    checkpoint(args.ckpt)
    modules()
    preprocessing()
    dataset_getitem()
    cli_test()

    print("\n" + RULE)
    print("Sections C and D are the ones I need exactly right. A guess at the")
    print("normalisation produces a model running on inputs it never saw, and")
    print("a bad score that says nothing about FTW.")
    print(RULE)


if __name__ == "__main__":
    main()
