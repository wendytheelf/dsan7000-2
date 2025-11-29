#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Count class distributions in UIR JSONL files.

Usage:
    python3 trustworthy_bim/scripts/count_class_distribution.py \
        --file trustworthy_bim/input/uir_ground_truth.jsonl \
        --field tier_label

Fields you can count:
    - tier_label   (canonical / Tier-1 class, recommended)
    - ifc_class    (original IFC class)
    - any other key inside entity (e.g., attributes.type)
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict


def get_nested(d: Dict[str, Any], path: str, default=None):
    """
    Safely get nested value from dict using dot-separated path, e.g.:
        get_nested(entity, "attributes.type")
    """
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part, default)
        if cur is default:
            break
    return cur


def count_classes(file_path: Path, field: str) -> Counter:
    """
    Count occurrences of a given field inside entity.
    - field examples: "tier_label", "ifc_class", "attributes.type"
    """
    counter: Counter = Counter()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entity = data.get("entity", {}) or {}
                value = get_nested(entity, field)
                if value is None:
                    value = "<MISSING>"
                counter[str(value)] += 1
            except Exception as e:
                print(f"[WARN] Error parsing line: {e}")
                continue

    return counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Count class distributions in UIR JSONL file.")
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to JSONL file, e.g., trustworthy_bim/input/uir_ground_truth.jsonl",
    )
    parser.add_argument(
        "--field",
        type=str,
        default="tier_label",
        help="Field inside entity to count (default: tier_label). Examples: tier_label, ifc_class, attributes.type",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="Show only top-N classes (0 = show all).",
    )

    args = parser.parse_args()
    file_path = Path(args.file)

    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return

    print(f"Counting distribution for '{args.field}' in: {file_path}")
    counts = count_classes(file_path, args.field)

    total = sum(counts.values())
    print(f"\nTotal records: {total}")
    print(f"Unique values: {len(counts)}\n")

    items = counts.most_common(args.top or None)

    print(f"{'Value':<40} {'Count':>8} {'Percent':>9}")
    print("-" * 60)
    for value, cnt in items:
        pct = (cnt / total * 100.0) if total > 0 else 0.0
        print(f"{value:<40} {cnt:>8} {pct:>8.2f}%")


if __name__ == "__main__":
    main()


