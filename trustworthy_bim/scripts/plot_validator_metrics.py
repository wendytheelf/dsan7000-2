#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot validator metrics from *.validator_eval.json files.

This script visualizes:
  1. Error-type detection (recall) per dataset (e.g., simulated_v1 vs simulated_v2)
  2. Class mapping confusion matrix heatmap (per dataset)

Usage:
    cd /home/wendy/dsan7000-2
    python trustworthy_bim/scripts/plot_validator_metrics.py
    # (Assumes *.validator_eval.json are under trustworthy_bim/input)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

import matplotlib.pyplot as plt
import numpy as np

try:
    import seaborn as sns

    HAS_SEABORN = True
    sns.set_style("whitegrid")
except Exception:
    HAS_SEABORN = False


def load_eval(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plot_error_type_recall(eval_files: Dict[str, Path], output_path: Path) -> None:
    """
    Bar chart: error_type vs recall for multiple datasets (v1, v2, ...).
    """
    # Collect union of error types
    error_types: List[str] = []
    for _, p in eval_files.items():
        data = load_eval(p)
        mets = data.get("error_type_metrics", {})
        for et in mets.keys():
            if et not in error_types:
                error_types.append(et)

    if not error_types:
        print("No error_type_metrics found in any eval files.")
        return

    datasets = list(eval_files.keys())
    x = np.arange(len(error_types))
    width = 0.8 / max(len(datasets), 1)

    plt.figure(figsize=(10, 5))
    ax = plt.gca()

    colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336"]

    for i, (name, path) in enumerate(eval_files.items()):
        data = load_eval(path)
        mets = data.get("error_type_metrics", {})
        recalls = [mets.get(et, {}).get("recall_%", 0.0) for et in error_types]
        bars = ax.bar(
            x + (i - (len(datasets) - 1) / 2) * width,
            recalls,
            width,
            label=name,
            color=colors[i % len(colors)],
            alpha=0.8,
            edgecolor="black",
            linewidth=1,
        )
        for b in bars:
            h = b.get_height()
            if h > 0:
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    h,
                    f"{h:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(error_types, rotation=45, ha="right")
    ax.set_ylabel("Recall (%)", fontsize=12, fontweight="bold")
    ax.set_title("Validator Recall by Error Type", fontsize=14, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.legend(title="Dataset")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def plot_confusion_heatmap(eval_file: Path, name: str, output_path: Path) -> None:
    """
    Plot class confusion matrix heatmap for a single dataset.
    Expects eval JSON to have 'class_confusion_%' dict (row-normalized).
    """
    data = load_eval(eval_file)
    cm_dict = data.get("class_confusion_%") or {}
    if not cm_dict:
        print(f"No class_confusion_% found in {eval_file}, skipping heatmap.")
        return

    # cm_dict is nested: {true_class: {pred_class: value}}
    import pandas as pd

    cm = pd.DataFrame.from_dict(cm_dict, orient="index").fillna(0.0)

    plt.figure(figsize=(max(8, 0.6 * cm.shape[1] + 4), max(6, 0.6 * cm.shape[0] + 3)))
    ax = plt.gca()

    if HAS_SEABORN:
        sns.heatmap(
            cm,
            annot=False,
            cmap="Blues",
            cbar_kws={"label": "Row-normalized accuracy (%)"},
            ax=ax,
        )
    else:
        im = ax.imshow(cm.values, cmap="Blues", aspect="auto")
        plt.colorbar(im, ax=ax, label="Row-normalized accuracy (%)")

    ax.set_title(f"Class Mapping Confusion – {name}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Predicted Class", fontsize=12, fontweight="bold")
    ax.set_ylabel("True Class", fontsize=12, fontweight="bold")
    ax.set_xticks(np.arange(len(cm.columns)))
    ax.set_xticklabels(cm.columns, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(cm.index)))
    ax.set_yticklabels(cm.index)
    ax.grid(False)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def main() -> None:
    project_dir = Path(__file__).resolve().parent.parent
    input_dir = project_dir / "input"

    # Look for known eval files
    eval_files: Dict[str, Path] = {}
    v1 = input_dir / "uir_simulated_v1.validator_eval.json"
    v2 = input_dir / "uir_simulated_v2.validator_eval.json"
    if v1.exists():
        eval_files["simulated_v1"] = v1
    if v2.exists():
        eval_files["simulated_v2"] = v2

    if not eval_files:
        print("No *.validator_eval.json files found in input/. Run evaluate_validator.py first.")
        return

    results_dir = project_dir.parent / "results" / "visualizations"

    # 1) Error-type recall comparison
    plot_error_type_recall(
        eval_files,
        results_dir / "E_validator_recall_by_error_type.png",
    )

    # 2) Confusion heatmaps per dataset
    for name, path in eval_files.items():
        out = results_dir / f"E_validator_class_confusion_{name}.png"
        plot_confusion_heatmap(path, name, out)


if __name__ == "__main__":
    main()



