#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute success metrics for the IFC → Canonical pipeline.
Author: Wendy

Usage:
    python compute_success_metrics.py

Inputs (expected):
    output/assets.csv
    output/asset_props.csv
    output/asset_flags.csv
    output/review_queue.csv   (annotated by reviewers)

Outputs (printed as JSON):
    - tier1_mapping_rate_%            (automatic)
    - unit_normalization_rate_%       (automatic)
    - manual_accuracy_%               (needed after manual annotation)
    - flag_precision_%                (needed after manual annotation)
    - uncertainty_rate_%              (needed after manual annotation)
    - manual_metrics_available        (bool)
"""

import os
import json
import yaml
import pandas as pd

# Paths
ASSETS_PATH = "output/assets.csv"
PROPS_PATH = "output/asset_props.csv"
FLAGS_PATH = "output/asset_flags.csv"
REVIEW_QUEUE_PATH = "output/review_queue.csv"
CLASS_MAP_PATH = "rules/class_maps.yaml"


def load_allowed_classes():
    """Read the allowed_classes list from class_maps.yaml."""
    allowed = []
    try:
        with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
            m = yaml.safe_load(f)
        allowed = m.get("allowed_classes") or list(set((m.get("ifc_to_canonical") or {}).values()))
    except Exception:
        pass
    return [a for a in allowed if a]


def compute_mapping_rate(assets_df, allowed_classes):
    """Compute the Tier-1 class mapping success rate (purely automatic)."""
    if assets_df.empty:
        return 0.0

    def is_tier1(row):
        cc = str(row.get("canonical_class") or "").strip()
        if not cc:
            return False
        if allowed_classes:
            return cc in allowed_classes
        return True

    rate = assets_df.apply(is_tier1, axis=1).mean() * 100.0
    return rate


def compute_unit_normalization_rate(props_df):
    """Compute the success rate of unit normalization (value_norm + unit_norm present when value_raw exists)."""
    if props_df.empty:
        return 0.0

    den = props_df["value_raw"].notna()
    num = den & props_df["value_norm"].notna() & (props_df["unit_norm"].fillna("") != "")
    if props_df[den].shape[0] == 0:
        return 0.0
    rate = props_df[num].shape[0] / props_df[den].shape[0] * 100.0
    return rate


def compute_manual_metrics(review_df: pd.DataFrame, flags_df: pd.DataFrame):
    """
    Compute manual-review-based metrics using review_queue.csv + asset_flags.csv.

    Definitions:

    - Reviewed set:
        rows where review_status in {"REVIEWED", "UNCERTAIN"}
        AND true_class is non-empty.

    - Accuracy:
        correct predictions / total reviewed
        where 'correct' means canonical_class == true_class.

    - Uncertainty rate:
        (# rows with review_status == "UNCERTAIN") / total reviewed

    - Flag precision (our operational definition):
        total_flags = number of flags on reviewed assets.
        useful_flags = flags where the asset is either:
            * incorrect (canonical_class != true_class), OR
            * marked UNCERTAIN.
        flag_precision = useful_flags / total_flags
    """
    if review_df.empty:
        return None

    # Normalize column names (defensive)
    for col in ["review_status", "true_class", "canonical_class"]:
        if col not in review_df.columns:
            return None

    # Determine reviewed rows
    df = review_df.copy()
    df["review_status"] = df["review_status"].fillna("").astype(str)
    df["true_class"] = df["true_class"].fillna("").astype(str)
    df["canonical_class"] = df["canonical_class"].fillna("").astype(str)

    reviewed = df[
        df["review_status"].isin(["REVIEWED", "UNCERTAIN"])
        & (df["true_class"].str.strip() != "")
    ].copy()

    if reviewed.empty:
        # No manual labels yet
        return None

    # Accuracy
    reviewed["is_correct"] = reviewed["canonical_class"].str.strip() == reviewed["true_class"].str.strip()
    accuracy = reviewed["is_correct"].mean() * 100.0

    # Uncertainty rate
    reviewed["is_uncertain"] = reviewed["review_status"] == "UNCERTAIN"
    uncertainty_rate = reviewed["is_uncertain"].mean() * 100.0

    # Flag precision
    if flags_df is None or flags_df.empty or "asset_id" not in flags_df.columns:
        flag_precision = None
    else:
        reviewed_asset_ids = set(reviewed["asset_id"].astype(str))

        # Subset flags to reviewed assets
        flags_sub = flags_df.copy()
        flags_sub["asset_id"] = flags_sub["asset_id"].astype(str)
        flags_sub = flags_sub[flags_sub["asset_id"].isin(reviewed_asset_ids)]

        total_flags = len(flags_sub)
        if total_flags == 0:
            flag_precision = None
        else:
            # Build map asset_id -> (is_correct, is_uncertain)
            meta = reviewed.set_index("asset_id")[["is_correct", "is_uncertain"]].to_dict(orient="index")

            def is_flag_useful(aid: str):
                info = meta.get(aid)
                if not info:
                    return False
                # Useful if asset is wrong OR marked uncertain
                return (not info["is_correct"]) or info["is_uncertain"]

            flags_sub["is_useful"] = flags_sub["asset_id"].apply(is_flag_useful)
            useful_flags = flags_sub["is_useful"].sum()
            flag_precision = useful_flags / total_flags * 100.0

    return {
        "manual_accuracy_%": round(accuracy, 2),
        "uncertainty_rate_%": round(uncertainty_rate, 2),
        "flag_precision_%": round(flag_precision, 2) if flag_precision is not None else None,
        "manual_reviewed_count": int(len(reviewed)),
    }


def main():
    # Basic file checks
    if not os.path.exists(ASSETS_PATH) or not os.path.exists(PROPS_PATH):
        print("Missing output/assets.csv or output/asset_props.csv. Please run ifc_to_canonical.py first.")
        return

    # Load core data
    assets = pd.read_csv(ASSETS_PATH)
    props = pd.read_csv(PROPS_PATH)
    allowed = load_allowed_classes()

    # Automatic metrics
    mapping_rate = compute_mapping_rate(assets, allowed)
    unit_norm_rate = compute_unit_normalization_rate(props)

    # Manual-review-based metrics
    manual_metrics = None
    if os.path.exists(REVIEW_QUEUE_PATH) and os.path.exists(FLAGS_PATH):
        review_df = pd.read_csv(REVIEW_QUEUE_PATH)
        flags_df = pd.read_csv(FLAGS_PATH)
        manual_metrics = compute_manual_metrics(review_df, flags_df)
    else:
        review_df = None
        flags_df = None

    result = {
        "tier1_mapping_rate_%": round(mapping_rate, 2),
        "unit_normalization_rate_%": round(unit_norm_rate, 2),
        "manual_metrics_available": manual_metrics is not None,
    }

    if manual_metrics is not None:
        result.update(manual_metrics)
    else:
        # 給一點提示方便你 debug / 跟 mentor 說明
        result["manual_metrics_note"] = (
            "Manual-review metrics require output/review_queue.csv with "
            "true_class + review_status filled, and output/asset_flags.csv present."
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
