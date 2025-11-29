#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate rule-based validator and class mapping on simulated data (no LLM needed).

Inputs (per dataset, e.g. simulated_v1):
  - sim_jsonl: uir_simulated_v1.jsonl (from generate_simulated_errors.py)
      * contains entity.uid and sim_error metadata:
          - has_error: bool
          - error_type: one of {wrong_class, out_of_range, negative, missing_prop}
          - true_class: original tier_label before corruption
  - outdir: output_simulated_v1 (from ifc_to_canonical.py)
      * assets.csv       (canonical_class, asset_id, local_id[=uid], ...)
      * asset_flags.csv  (asset_id, flag)

What this script computes:
  1) Error-type level metrics (per error_type):
       - Injected (ground-truth positives)
       - Caught   (validator flags present)
       - TP / FP / FN / TN
       - Precision / Recall / F1
  2) Class-mapping confusion matrix:
       - true_class (from sim_error.true_class or original tier_label)
       - predicted_class (assets.csv.canonical_class)

Usage:
  python trustworthy_bim/scripts/evaluate_validator.py \
    --sim_jsonl trustworthy_bim/input/uir_simulated_v1.jsonl \
    --outdir trustworthy_bim/output_simulated_v1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, Set, Tuple

import pandas as pd

# Map simulation error types to expected validator flags
ERROR_TYPE_TO_FLAG: Dict[str, str] = {
    "out_of_range": "OUT_OF_RANGE",
    "negative": "NEGATIVE_VALUE",
    "missing_prop": "MISSING_REQUIRED_PROPERTY",
    # "wrong_class" currently has no direct rule-based flag
}


def load_assets(outdir: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load assets.csv and return:
      - uid_to_asset_id: local_id (uid) -> asset_id
      - uid_to_pred_class: local_id (uid) -> canonical_class
    """
    assets_csv = outdir / "assets.csv"
    if not assets_csv.exists():
        raise FileNotFoundError(f"assets.csv not found at {assets_csv}")

    df = pd.read_csv(assets_csv)
    required_cols = {"local_id", "asset_id", "canonical_class"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"assets.csv must contain columns: {required_cols}")

    uid_to_asset: Dict[str, str] = {}
    uid_to_pred_class: Dict[str, str] = {}
    for _, row in df.iterrows():
        uid = str(row["local_id"])
        uid_to_asset[uid] = str(row["asset_id"])
        uid_to_pred_class[uid] = str(row.get("canonical_class") or "")

    return uid_to_asset, uid_to_pred_class


def load_flags(outdir: Path) -> Dict[str, Set[str]]:
    """Load asset_flags.csv and build mapping asset_id -> set(flags)."""
    flags_csv = outdir / "asset_flags.csv"
    if not flags_csv.exists():
        raise FileNotFoundError(f"asset_flags.csv not found at {flags_csv}")

    df = pd.read_csv(flags_csv)
    required_cols = {"asset_id", "flag"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"asset_flags.csv must contain columns: {required_cols}")

    by_asset: Dict[str, Set[str]] = {}
    for _, row in df.iterrows():
        aid = str(row["asset_id"])
        flg = str(row["flag"])
        by_asset.setdefault(aid, set()).add(flg)
    return by_asset


def load_sim_ground_truth(sim_jsonl: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load simulated JSONL and return mapping:
      uid -> {
        "true_class": str,
        "true_error_type": str  # one of {NONE, wrong_class, out_of_range, negative, missing_prop}
      }
    """
    uid_info: Dict[str, Dict[str, Any]] = {}
    with sim_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            ent = data.get("entity") or {}
            uid = ent.get("uid")
            if not uid:
                continue
            uid = str(uid)

            sim_err = data.get("sim_error") or {}
            has_err = bool(sim_err.get("has_error"))
            err_type = str(sim_err.get("error_type") or "NONE")
            if not has_err:
                err_type = "NONE"

            # Prefer original class from sim_error.true_class; fallback to current tier_label
            true_cls = sim_err.get("true_class") or ent.get("tier_label") or ""
            true_cls = str(true_cls)

            uid_info[uid] = {
                "true_class": true_cls,
                "true_error_type": err_type,
            }
    return uid_info


def compute_error_type_metrics(
    uid_info: Dict[str, Dict[str, Any]],
    uid_to_asset: Dict[str, str],
    flags_by_asset: Dict[str, Set[str]],
) -> Dict[str, Dict[str, Any]]:
    """
    For each error_type in ERROR_TYPE_TO_FLAG, compute TP/FP/FN/TN, precision, recall, f1.
    """
    metrics: Dict[str, Dict[str, Any]] = {}

    all_uids = set(uid_info.keys())

    for etype, expected_flag in ERROR_TYPE_TO_FLAG.items():
        tp = fp = fn = tn = 0
        injected = 0
        caught = 0

        for uid in all_uids:
            info = uid_info[uid]
            gt_type = info.get("true_error_type", "NONE")
            gt_pos = gt_type == etype

            aid = uid_to_asset.get(uid)
            flgs = flags_by_asset.get(aid, set()) if aid else set()
            pred_pos = expected_flag in flgs

            if gt_pos:
                injected += 1
            if gt_pos and pred_pos:
                tp += 1
                caught += 1
            elif gt_pos and not pred_pos:
                fn += 1
            elif (not gt_pos) and pred_pos:
                fp += 1
            else:
                tn += 1

        precision = tp / (tp + fp) * 100.0 if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[etype] = {
            "injected": injected,
            "caught": caught,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision_%": precision,
            "recall_%": recall,
            "f1_%": f1,
        }

    return metrics


def compute_class_confusion(
    uid_info: Dict[str, Dict[str, Any]],
    uid_to_pred_class: Dict[str, str],
) -> pd.DataFrame:
    """
    Build confusion matrix: true_class vs predicted_class (canonical_class).
    Uses all uids present in both uid_info and uid_to_pred_class.
    """
    rows = []
    for uid, info in uid_info.items():
        if uid not in uid_to_pred_class:
            continue
        true_cls = info.get("true_class") or ""
        pred_cls = uid_to_pred_class.get(uid) or ""
        rows.append((true_cls, pred_cls))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["true_class", "predicted_class"])
    cm = pd.crosstab(df["true_class"], df["predicted_class"], normalize="index") * 100.0
    return cm


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate rule-based validator and class mapping on simulated data.")
    ap.add_argument(
        "--sim_jsonl",
        type=str,
        required=True,
        help="Path to simulated JSONL file (e.g., trustworthy_bim/input/uir_simulated_v1.jsonl)",
    )
    ap.add_argument(
        "--outdir",
        type=str,
        required=True,
        help="Output dir from ifc_to_canonical.py (contains assets.csv, asset_flags.csv)",
    )

    args = ap.parse_args()
    sim_jsonl = Path(args.sim_jsonl)
    outdir = Path(args.outdir)

    if not sim_jsonl.exists():
        print(f"[ERROR] sim_jsonl not found: {sim_jsonl}")
        return

    # Load data
    uid_info = load_sim_ground_truth(sim_jsonl)
    uid_to_asset, uid_to_pred_class = load_assets(outdir)
    flags_by_asset = load_flags(outdir)

    # 1) Error-type metrics
    metrics = compute_error_type_metrics(uid_info, uid_to_asset, flags_by_asset)

    print("\n=== Validator Metrics by Error Type ===")
    print(f"{'Error Type':<15} {'Inj':>6} {'Caught':>7} {'Prec%':>8} {'Rec%':>8} {'F1%':>8}")
    print("-" * 60)
    for etype, m in metrics.items():
        print(
            f"{etype:<15} "
            f"{m['injected']:>6} "
            f"{m['caught']:>7} "
            f"{m['precision_%']:>7.2f} "
            f"{m['recall_%']:>7.2f} "
            f"{m['f1_%']:>7.2f}"
        )

    # 2) Class confusion matrix
    cm = compute_class_confusion(uid_info, uid_to_pred_class)
    if not cm.empty:
        print("\n=== Class Mapping Confusion (row-normalized, %) ===")
        print(cm.round(2).to_string())

    # 3) Save detailed results
    out_json = sim_jsonl.with_suffix(".validator_eval.json")
    payload = {
        "sim_jsonl": str(sim_jsonl),
        "outdir": str(outdir),
        "error_type_metrics": metrics,
        "class_confusion_%": cm.round(4).to_dict() if not cm.empty else {},
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Detailed evaluation saved to: {out_json}")


if __name__ == "__main__":
    main()



