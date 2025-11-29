#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare precision by class across different simulated versions.

This script calculates precision for each class by comparing:
- Ground truth (uir_ground_truth.jsonl)
- Version 1 (uir_simulated_v1.jsonl) - ~8% errors
- Version 2 (uir_simulated_v2.jsonl) - ~15% errors
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict


def load_predictions(file_path: Path) -> Dict[str, str]:
    """Load predictions: {uid: predicted_class}"""
    predictions: Dict[str, str] = {}
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entity = data.get("entity", {})
                uid = entity.get("uid")
                predicted_class = entity.get("tier_label")
                if uid and predicted_class:
                    predictions[str(uid)] = str(predicted_class)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                continue
    return predictions


def calculate_precision_by_class(
    ground_truth: Dict[str, str],
    predictions: Dict[str, str],
    version_name: str,
) -> Dict[str, Dict[str, float]]:
    """Calculate precision, recall, and F1 for each class."""

    # Group by true class
    true_by_class = defaultdict(list)
    for uid, true_class in ground_truth.items():
        true_by_class[true_class].append(uid)

    # Group predictions by predicted class
    pred_by_class = defaultdict(list)
    for uid, pred_class in predictions.items():
        if uid in ground_truth:  # Only count entities in ground truth
            pred_by_class[pred_class].append(uid)

    results: Dict[str, Dict[str, float]] = {}
    all_classes = set(list(true_by_class.keys()) + list(pred_by_class.keys()))

    for class_name in sorted(all_classes):
        true_uids = set(true_by_class[class_name])
        pred_uids = set(pred_by_class.get(class_name, []))

        # True positives: predicted as this class AND actually this class
        tp = len(true_uids & pred_uids)

        # False positives: predicted as this class BUT not actually this class
        fp = len(pred_uids - true_uids)

        # False negatives: actually this class BUT not predicted as this class
        fn = len(true_uids - pred_uids)

        # Calculate metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        results[class_name] = {
            "precision": precision * 100,
            "recall": recall * 100,
            "f1": f1 * 100,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": len(true_uids),  # Number of true instances
        }

    return results


def print_comparison_table(results_v1: Dict, results_v2: Dict) -> None:
    """Print a comparison table."""
    print("\n" + "=" * 100)
    print("PRECISION COMPARISON BY CLASS")
    print("=" * 100)
    print(f"{'Class':<35} {'V1 Prec':<12} {'V2 Prec':<12} {'Diff':<10} {'Support':<10}")
    print("-" * 100)

    all_classes = set(list(results_v1.keys()) + list(results_v2.keys()))

    for class_name in sorted(all_classes):
        v1 = results_v1.get(class_name, {})
        v2 = results_v2.get(class_name, {})

        v1_prec = v1.get("precision", 0.0)
        v2_prec = v2.get("precision", 0.0)
        diff = v2_prec - v1_prec
        support = v1.get("support", v2.get("support", 0))

        # Only show classes with support > 0
        if support > 0:
            print(f"{class_name:<35} {v1_prec:>10.2f}% {v2_prec:>10.2f}% {diff:>+9.2f}% {support:>9}")

    print("=" * 100)

    # Summary statistics
    v1_avg = sum(r.get("precision", 0) for r in results_v1.values()) / len(results_v1) if results_v1 else 0
    v2_avg = sum(r.get("precision", 0) for r in results_v2.values()) / len(results_v2) if results_v2 else 0

    print(f"\nAverage Precision:")
    print(f"  Version 1: {v1_avg:.2f}%")
    print(f"  Version 2: {v2_avg:.2f}%")
    print(f"  Difference: {v2_avg - v1_avg:+.2f}%")


def main() -> None:
    # Input directory (where JSONL files live)
    project_dir = Path(__file__).resolve().parent.parent
    input_dir = project_dir / "input"

    gt_file = input_dir / "uir_ground_truth.jsonl"
    v1_file = input_dir / "uir_simulated_v1.jsonl"
    v2_file = input_dir / "uir_simulated_v2.jsonl"

    print("Loading files...")
    ground_truth = load_predictions(gt_file)
    predictions_v1 = load_predictions(v1_file)
    predictions_v2 = load_predictions(v2_file)

    print(f"Ground truth: {len(ground_truth)} entities")
    print(f"Version 1: {len(predictions_v1)} entities")
    print(f"Version 2: {len(predictions_v2)} entities")

    # Ground truth vs. itself (conceptual upper bound)
    print("\nCalculating metrics for Ground Truth (self-comparison)...")
    results_gt = calculate_precision_by_class(ground_truth, ground_truth, "Ground Truth")

    print("\nCalculating metrics for Version 1...")
    results_v1 = calculate_precision_by_class(ground_truth, predictions_v1, "Version 1")

    print("Calculating metrics for Version 2...")
    results_v2 = calculate_precision_by_class(ground_truth, predictions_v2, "Version 2")

    print_comparison_table(results_v1, results_v2)

    # Save detailed results to JSON (including ground truth baseline)
    output_file = input_dir / "precision_comparison.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(
            {"ground_truth": results_gt, "version_1": results_v1, "version_2": results_v2},
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()


