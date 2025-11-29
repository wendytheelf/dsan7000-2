#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualize precision comparison for:
- Ground truth (self-comparison, ideal upper bound)
- Simulated Version 1 (uir_simulated_v1.jsonl)
- Simulated Version 2 (uir_simulated_v2.jsonl)

Output:
- A bar chart PNG comparing precision by class for the three versions.
"""

import json
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np


def load_precision(path: Path) -> Dict[str, Dict]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    project_dir = Path(__file__).resolve().parent.parent
    input_dir = project_dir / "input"
    precision_path = input_dir / "precision_comparison.json"

    if not precision_path.exists():
        print(f"Error: {precision_path} not found. Run compare_precision_by_class.py first.")
        return

    data = load_precision(precision_path)
    gt = data.get("ground_truth", {})
    v1 = data.get("version_1", {})
    v2 = data.get("version_2", {})

    # Use classes that exist in ground truth (to avoid zero-support noise)
    classes = sorted(gt.keys())

    precisions_gt = [gt[c]["precision"] for c in classes]
    precisions_v1 = [v1.get(c, {}).get("precision", 0.0) for c in classes]
    precisions_v2 = [v2.get(c, {}).get("precision", 0.0) for c in classes]
    supports = [gt[c]["support"] for c in classes]

    # Optionally filter to classes with reasonable support
    filtered = [
        (c, pg, p1, p2, s)
        for c, pg, p1, p2, s in zip(classes, precisions_gt, precisions_v1, precisions_v2, supports)
        if s > 5
    ]
    if not filtered:
        print("No classes with sufficient support to plot.")
        return

    classes, precisions_gt, precisions_v1, precisions_v2, supports = zip(*filtered)

    x = np.arange(len(classes))
    width = 0.25

    plt.figure(figsize=(14, 6))
    ax = plt.gca()

    ax.bar(
        x - width,
        precisions_gt,
        width,
        label="Ground Truth (ideal)",
        color="#4CAF50",
        alpha=0.8,
        edgecolor="black",
        linewidth=1,
    )
    bars_v1 = ax.bar(
        x,
        precisions_v1,
        width,
        label="Simulated V1 (~8% errors)",
        color="#2196F3",
        alpha=0.8,
        edgecolor="black",
        linewidth=1,
    )
    bars_v2 = ax.bar(
        x + width,
        precisions_v2,
        width,
        label="Simulated V2 (~15% errors)",
        color="#FF9800",
        alpha=0.8,
        edgecolor="black",
        linewidth=1,
    )

    ax.set_ylabel("Precision (%)", fontsize=12, fontweight="bold")
    ax.set_title("Per-class Precision Comparison (Ground Truth vs Simulated Versions)", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(classes, rotation=45, ha="right")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.legend()

    # Add value labels for V1 and V2 (GT is 100% for all)
    for bars in (bars_v1, bars_v2):
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{height:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    rotation=90,
                )

    plt.tight_layout()

    # Save to results/visualizations
    results_dir = project_dir.parent / "results" / "visualizations"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / "A_mapping_accuracy_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"✓ Saved visualization to: {output_path}")


if __name__ == "__main__":
    main()


