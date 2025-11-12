#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute success metrics for the IFC → Canonical pipeline.
Author: Wendy

Usage:
    python compute_success_metrics.py

Output:
    JSON summary including:
      - Tier-1 mapping rate
      - Unit normalization rate
      - A random sample file for manual labeling.
"""

import pandas as pd
import os
import yaml
import json
import random

# Setup paths
ASSETS_PATH = "output/assets.csv"
PROPS_PATH = "output/asset_props.csv"
CLASS_MAP_PATH = "rules/class_maps.yaml"
REVIEW_DIR = "review"
SAMPLE_FILE = os.path.join(REVIEW_DIR, "manual_class_check.csv")


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
    """Compute the Tier-1 class mapping success rate."""
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
    """Compute the success rate of unit normalization."""
    if props_df.empty:
        return 0.0

    den = props_df["value_raw"].notna()
    num = den & props_df["value_norm"].notna() & (props_df["unit_norm"].fillna("") != "")
    rate = (props_df[num].shape[0] / props_df[den].shape[0] * 100.0) if props_df[den].shape[0] else 0.0
    return rate


def create_manual_label_sample(assets_df):
    """Export a 50-row random sample for manual review."""
    os.makedirs(REVIEW_DIR, exist_ok=True)
    sample_n = min(50, len(assets_df))
    sample = assets_df.sample(sample_n, random_state=42)[["asset_id", "ifc_class", "canonical_class"]].copy()
    sample["true_class"] = ""  # column for manual labeling
    sample.to_csv(SAMPLE_FILE, index=False)

    with open(os.path.join(REVIEW_DIR, "README.txt"), "w", encoding="utf-8") as f:
        f.write(
"""Instructions for Manual Labeling:
1) Open review/manual_class_check.csv and fill in the 'true_class' column for each row 
   (the correct canonical category according to your judgment).
2) Save the file and run the next script to automatically compute the top-1 accuracy.

Notes:
- If there is a predefined allowed_classes list, please label according to it.
- If you prefer to use Uniclass or a more detailed taxonomy, 
  please define it first in class_maps.yaml.
"""
        )


def main():
    # Check file existence
    if not os.path.exists(ASSETS_PATH) or not os.path.exists(PROPS_PATH):
        print("Missing output/assets.csv or output/asset_props.csv. Please run ifc_to_canonical.py first.")
        return

    # Read data
    assets = pd.read_csv(ASSETS_PATH)
    props = pd.read_csv(PROPS_PATH)
    allowed = load_allowed_classes()

    # Compute metrics
    mapping_rate = compute_mapping_rate(assets, allowed)
    unit_norm_rate = compute_unit_normalization_rate(props)

    # Generate manual labeling sample
    create_manual_label_sample(assets)

    # Output results
    result = {
        "tier1_mapping_rate_%": round(mapping_rate, 2),
        "unit_normalization_rate_%": round(unit_norm_rate, 2),
        "manual_label_file": SAMPLE_FILE,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
