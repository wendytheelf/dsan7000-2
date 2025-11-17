#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute success metrics for the IFC → Canonical pipeline.

Usage:
    python compute_success_metrics.py --outdir output_llama3

Output (printed as JSON):
    {
      "outdir": "output_llama3",
      "tier1_mapping_rate_%": ...,
      "unit_normalization_rate_%": ...,
      "manual_accuracy_%": ... or null,
      "uncertainty_rate_%": ... or null,
      "flag_precision_%": ... or null,
      "n_assets": ...,
      "n_props": ...,
      "n_flags": ...,
      "n_review_rows": ...,
      "n_reviewed": ...,
      "n_uncertain": ...
    }
"""

import os
import json
import argparse
from typing import List, Dict, Any, Optional

import pandas as pd
import yaml

CLASS_MAP_PATH = "rules/class_maps.yaml"


# -----------------------------
# Helpers
# -----------------------------
def load_allowed_classes() -> List[str]:
    """Read the allowed_classes list from class_maps.yaml (if present)."""
    try:
        with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
            m = yaml.safe_load(f) or {}
        allowed = m.get("allowed_classes") or list(
            set((m.get("ifc_to_canonical") or {}).values())
        )
        return [a for a in allowed if a]
    except Exception:
        return []


def compute_mapping_rate(assets_df: pd.DataFrame, allowed_classes: List[str]) -> float:
    """Compute the Tier-1 class mapping success rate (auto metric)."""
    if assets_df.empty:
        return 0.0

    def is_tier1(row: pd.Series) -> bool:
        cc = str(row.get("canonical_class") or "").strip()
        if not cc:
            return False
        if allowed_classes:
            return cc in allowed_classes
        return True

    rate = assets_df.apply(is_tier1, axis=1).mean() * 100.0
    return float(rate)


def compute_unit_normalization_rate(props_df: pd.DataFrame) -> float:
    """Compute the success rate of unit normalization (auto metric)."""
    if props_df.empty:
        return 0.0

    den_mask = props_df["value_raw"].notna()
    den = props_df[den_mask]
    if den.empty:
        return 0.0

    num_mask = den_mask & props_df["value_norm"].notna() & (
        props_df["unit_norm"].fillna("") != ""
    )
    num = props_df[num_mask]

    rate = (len(num) / len(den)) * 100.0 if len(den) > 0 else 0.0
    return float(rate)


# -----------------------------
# Manual review–based metrics
# -----------------------------
def compute_manual_accuracy(review_df: pd.DataFrame) -> Optional[float]:
    """
    Manual accuracy = (correct predictions / total reviewed) × 100
    Reviewed rows are those with review_status == 'REVIEWED' and non-empty true_class.
    """
    if review_df.empty:
        return None

    df = review_df.copy()
    # normalize columns
    for col in ["canonical_class", "true_class", "review_status"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    mask_reviewed = (df["review_status"].str.upper() == "REVIEWED") & (
        df["true_class"].str.strip() != ""
    )
    reviewed = df[mask_reviewed]
    if reviewed.empty:
        return None

    correct = reviewed["canonical_class"].str.strip() == reviewed["true_class"].str.strip()
    acc = correct.mean() * 100.0
    return float(acc)


def compute_uncertainty_rate(review_df: pd.DataFrame) -> Optional[float]:
    """
    Uncertainty rate = (uncertain cases / total reviewed) × 100

    Where:
      - uncertain cases: review_status == 'UNCERTAIN'
      - total reviewed: rows with review_status in {'REVIEWED', 'UNCERTAIN'}
                        (true_class may be empty for UNCERTAIN rows)
    """
    if review_df.empty:
        return None

    df = review_df.copy()
    if "review_status" not in df.columns:
        return None

    df["review_status"] = df["review_status"].fillna("").astype(str).str.upper()

    mask_uncertain = df["review_status"] == "UNCERTAIN"
    mask_reviewed_any = df["review_status"].isin(["REVIEWED", "UNCERTAIN"])

    n_uncertain = int(mask_uncertain.sum())
    n_reviewed_any = int(mask_reviewed_any.sum())

    if n_reviewed_any == 0:
        return None

    rate = n_uncertain / n_reviewed_any * 100.0
    return float(rate)


def compute_flag_precision(
    flags_df: pd.DataFrame,
    review_df: pd.DataFrame,
) -> Optional[float]:
    """
    Flag precision ≈ (useful flagged assets / total flagged assets) × 100.

    Definition here:
      - total flagged assets: number of distinct asset_id that have at least one flag.
      - useful flagged assets:
            asset has at least one flag AND
            (review_status == 'UNCERTAIN' OR
             (review_status == 'REVIEWED' AND canonical_class != true_class))

    This treats "flags that lead a reviewer to find an error or uncertainty"
    as useful. It is an approximation consistent with the project guide.
    """
    if flags_df.empty or review_df.empty:
        return None
    if "asset_id" not in flags_df.columns:
        return None

    # Normalize review frame
    df_r = review_df.copy()
    for col in ["asset_id", "canonical_class", "true_class", "review_status"]:
        if col in df_r.columns:
            df_r[col] = df_r[col].fillna("").astype(str)

    df_r["review_status"] = df_r["review_status"].str.upper()

    # One row per asset in review
    review_by_asset = (
        df_r.groupby("asset_id")
        .agg(
            canonical_class=("canonical_class", "first"),
            true_class=("true_class", "first"),
            review_status=("review_status", "first"),
        )
        .reset_index()
    )

    flagged_assets = sorted(flags_df["asset_id"].dropna().astype(str).unique())
    if not flagged_assets:
        return None

    review_by_asset = review_by_asset.set_index("asset_id")
    useful = 0
    total = 0

    for aid in flagged_assets:
        total += 1
        if aid not in review_by_asset.index:
            continue
        row = review_by_asset.loc[aid]
        rs = str(row.get("review_status") or "").upper()
        cc = str(row.get("canonical_class") or "").strip()
        tc = str(row.get("true_class") or "").strip()

        # UNCERTAIN → useful
        if rs == "UNCERTAIN":
            useful += 1
        # REVIEWED but wrong class → useful
        elif rs == "REVIEWED" and tc and (cc != tc):
            useful += 1
        # REVIEWED & correct & not uncertain → not useful

    if total == 0:
        return None
    return float(useful / total * 100.0)


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Compute success metrics for IFC → Canonical pipeline."
    )
    ap.add_argument(
        "--outdir",
        type=str,
        default="output",
        help="Directory containing assets.csv, asset_props.csv, asset_flags.csv, review_queue.csv",
    )
    ap.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Optional: create a small sample of review_queue in <outdir>/review/manual_class_check.csv",
    )
    args = ap.parse_args()

    outdir = args.outdir
    assets_path = os.path.join(outdir, "assets.csv")
    props_path = os.path.join(outdir, "asset_props.csv")
    flags_path = os.path.join(outdir, "asset_flags.csv")
    review_queue_path = os.path.join(outdir, "review_queue.csv")

    # Check existence
    missing = [
        p for p in [assets_path, props_path, flags_path, review_queue_path] if not os.path.exists(p)
    ]
    if missing:
        print(
            json.dumps(
                {
                    "error": "Missing required files",
                    "missing": missing,
                    "hint": "Make sure ifc_to_canonical.py has been run with this outdir.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    # Load data
    assets = pd.read_csv(assets_path)
    props = pd.read_csv(props_path)
    flags = pd.read_csv(flags_path)
    review = pd.read_csv(review_queue_path)

    allowed = load_allowed_classes()

    # Auto metrics
    mapping_rate = compute_mapping_rate(assets, allowed)
    unit_norm_rate = compute_unit_normalization_rate(props)

    # Manual-review based metrics
    manual_acc = compute_manual_accuracy(review)
    uncertainty_rate = compute_uncertainty_rate(review)
    flag_prec = compute_flag_precision(flags, review)

    # Optional: small sample for manual labeling (TOP-N from review_queue)
    sample_file = None
    if args.sample_size > 0 and not review.empty:
        os.makedirs(os.path.join(outdir, "review"), exist_ok=True)
        sample_n = min(args.sample_size, len(review))
        sample = review.head(sample_n).copy()
        sample_file = os.path.join(outdir, "review", "manual_class_check.csv")
        sample.to_csv(sample_file, index=False)

    # Count stats
    n_assets = int(len(assets))
    n_props = int(len(props))
    n_flags = int(len(flags))
    n_review_rows = int(len(review))

    # Reviewed counts for context
    if "review_status" in review.columns:
        rs = review["review_status"].fillna("").astype(str).str.upper()
        n_uncertain = int((rs == "UNCERTAIN").sum())
        n_reviewed_rows = int(rs.isin(["REVIEWED", "UNCERTAIN"]).sum())
    else:
        n_uncertain = 0
        n_reviewed_rows = 0

    result: Dict[str, Any] = {
        "outdir": outdir,
        "tier1_mapping_rate_%": round(float(mapping_rate), 2),
        "unit_normalization_rate_%": round(float(unit_norm_rate), 2),
        "manual_accuracy_%": round(manual_acc, 2) if manual_acc is not None else None,
        "uncertainty_rate_%": round(uncertainty_rate, 2) if uncertainty_rate is not None else None,
        "flag_precision_%": round(flag_prec, 2) if flag_prec is not None else None,
        "n_assets": n_assets,
        "n_props": n_props,
        "n_flags": n_flags,
        "n_review_rows": n_review_rows,
        "n_reviewed": n_reviewed_rows,
        "n_uncertain": n_uncertain,
        "manual_sample_file": sample_file,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
