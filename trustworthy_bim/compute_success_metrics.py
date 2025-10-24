#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute success metrics for IFC → Canonical pipeline.
Author: Wendy + ChatGPT assistant
Usage:
    python compute_success_metrics.py
Output:
    JSON summary of tier1 mapping rate, unit normalization rate, and sample file for manual labeling.
"""

import pandas as pd
import os
import yaml
import json
import random

# 路徑設定
ASSETS_PATH = "output/assets.csv"
PROPS_PATH = "output/asset_props.csv"
CLASS_MAP_PATH = "rules/class_maps.yaml"
REVIEW_DIR = "review"
SAMPLE_FILE = os.path.join(REVIEW_DIR, "manual_class_check.csv")


def load_allowed_classes():
    """讀取 class_maps.yaml 內的 allowed_classes 清單"""
    allowed = []
    try:
        with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
            m = yaml.safe_load(f)
        allowed = m.get("allowed_classes") or list(set((m.get("ifc_to_canonical") or {}).values()))
    except Exception:
        pass
    return [a for a in allowed if a]


def compute_mapping_rate(assets_df, allowed_classes):
    """計算 Tier-1 class mapping 成功率"""
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
    """計算單位正規化成功率"""
    if props_df.empty:
        return 0.0

    den = props_df["value_raw"].notna()
    num = den & props_df["value_norm"].notna() & (props_df["unit_norm"].fillna("") != "")
    rate = (props_df[num].shape[0] / props_df[den].shape[0] * 100.0) if props_df[den].shape[0] else 0.0
    return rate


def create_manual_label_sample(assets_df):
    """輸出 50 筆隨機樣本供人工標註"""
    os.makedirs(REVIEW_DIR, exist_ok=True)
    sample_n = min(50, len(assets_df))
    sample = assets_df.sample(sample_n, random_state=42)[["asset_id", "ifc_class", "canonical_class"]].copy()
    sample["true_class"] = ""  # 人工填寫欄位
    sample.to_csv(SAMPLE_FILE, index=False)

    with open(os.path.join(REVIEW_DIR, "README.txt"), "w", encoding="utf-8") as f:
        f.write(
"""如何標註：
1) 打開 review/manual_class_check.csv，針對每列填入 true_class（你認為的正解 canonical 類別）。
2) 存檔後執行第二段指令，會自動計算 top-1 accuracy。

備註：
- 若有 allowed_classes 名單，請以該名單為準。
- 若你希望人工用 Uniclass 或更細項，請先在 class_maps.yaml 定義口徑。
"""
        )


def main():
    # 檢查檔案存在
    if not os.path.exists(ASSETS_PATH) or not os.path.exists(PROPS_PATH):
        print("❌ 找不到 output/assets.csv 或 output/asset_props.csv，請先執行 ifc_to_canonical.py")
        return

    # 讀資料
    assets = pd.read_csv(ASSETS_PATH)
    props = pd.read_csv(PROPS_PATH)
    allowed = load_allowed_classes()

    # 計算指標
    mapping_rate = compute_mapping_rate(assets, allowed)
    unit_norm_rate = compute_unit_normalization_rate(props)

    # 產出人工標註樣本
    create_manual_label_sample(assets)

    # 輸出結果
    result = {
        "tier1_mapping_rate_%": round(mapping_rate, 2),
        "unit_normalization_rate_%": round(unit_norm_rate, 2),
        "manual_label_file": SAMPLE_FILE,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
