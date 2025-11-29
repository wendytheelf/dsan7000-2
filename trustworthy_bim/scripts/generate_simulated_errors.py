#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate two simulated JSONL files with controlled errors for robustness testing.

- Version 1 (uir_simulated_v1.jsonl): ~8% error rate, mix of easier errors
- Version 2 (uir_simulated_v2.jsonl): ~15% error rate, more & slightly harder errors

Error types:
- wrong_class: change entity['tier_label']
- out_of_range: make numeric properties extremely large
- negative: flip numeric properties to negative
- missing_prop: delete an existing property

We also add a "sim_error" field at the top-level to record what was injected.
"""

import json
import random
from pathlib import Path

random.seed(42)

# Project / input directory
THIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = THIS_DIR.parent
INPUT_DIR = PROJECT_DIR / "input"

ERROR_TYPES = ["wrong_class", "out_of_range", "negative", "missing_prop"]

# 妳原本的錯誤對應表，保留
ERROR_PAIRS = {
    "Slabs": ["Foundation_Slab", "Floors"],
    "Foundation_Slab": ["Slabs", "Floors"],
    "Floors": ["Slabs", "Foundation_Slab", "Ceilings"],
    "External walls (façade)": ["Internal walls", "Curtain Panels"],
    "Internal walls": ["External walls (façade)"],
    "Roof": ["Slabs"],
    "Ceilings": ["Floors"],
    "Columns (Concrete)": ["Column (Steel)"],
    "Beam (Concrete)": ["Beam (Steel)"],
    "Piping": ["Piping fittings"],
    "Piping fittings": ["Piping"],
    "Cable Tray": ["Cable Tray fittings"],
    "Cable Tray fittings": ["Cable Tray"],
    "Doors": ["Windows"],
    "Windows": ["Doors"],
}

# 目前針對 Beam 幾何欄位做測試（因為 rules 裡有 required / range）
TARGET_BEAM_CLASSES = {"Beam (Concrete)", "Beam (Steel)"}

NUMERIC_PROP_CANDIDATES = [
    ("Qto_BeamBaseQuantities", "Length"),
    ("Qto_BeamBaseQuantities", "NetVolume"),
    ("Qto_BeamBaseQuantities", "NetSurfaceArea"),
]

MISSING_PROP_CANDIDATES = NUMERIC_PROP_CANDIDATES[:]


def inject_wrong_class(entity):
    true_class = entity.get("tier_label")
    if not true_class:
        return None, None, None

    if true_class in ERROR_PAIRS:
        wrong_class = random.choice(ERROR_PAIRS[true_class])
    else:
        # 如果不在表裡，隨便換一個已知 class
        all_classes = list(ERROR_PAIRS.keys())
        if not all_classes:
            return None, None, None
        wrong_class = random.choice(all_classes)

    entity["tier_label"] = wrong_class
    return "wrong_class", "tier_label", true_class


def find_numeric_field(entity):
    """在 properties 裡找一個可用的 numeric field。"""
    true_class = entity.get("tier_label")
    if true_class not in TARGET_BEAM_CLASSES:
        return None, None, None

    props = entity.get("properties", {})
    for pset_name, field in NUMERIC_PROP_CANDIDATES:
        pset = props.get(pset_name)
        if isinstance(pset, dict) and field in pset:
            val = pset[field]
            if isinstance(val, (int, float)):
                return pset_name, field, val
    return None, None, None


def inject_out_of_range(entity):
    pset_name, field, val = find_numeric_field(entity)
    if pset_name is None:
        return None, None, None

    props = entity.get("properties", {})
    # 直接放大 1000 倍，製造極端值
    props[pset_name][field] = val * 1000.0
    entity["properties"] = props
    return "out_of_range", f"{pset_name}.{field}", val


def inject_negative(entity):
    pset_name, field, val = find_numeric_field(entity)
    if pset_name is None:
        return None, None, None

    props = entity.get("properties", {})
    props[pset_name][field] = -abs(val)
    entity["properties"] = props
    return "negative", f"{pset_name}.{field}", val


def inject_missing_prop(entity):
    true_class = entity.get("tier_label")
    if true_class not in TARGET_BEAM_CLASSES:
        return None, None, None

    props = entity.get("properties", {})
    # 找一個目前有存在的欄位，刪掉它
    candidates = []
    for pset_name, field in MISSING_PROP_CANDIDATES:
        pset = props.get(pset_name)
        if isinstance(pset, dict) and field in pset:
            candidates.append((pset_name, field))

    if not candidates:
        return None, None, None

    pset_name, field = random.choice(candidates)
    old_val = props[pset_name].pop(field)
    entity["properties"] = props
    return "missing_prop", f"{pset_name}.{field}", old_val


def apply_error(entity, error_type):
    if error_type == "wrong_class":
        return inject_wrong_class(entity)
    elif error_type == "out_of_range":
        return inject_out_of_range(entity)
    elif error_type == "negative":
        return inject_negative(entity)
    elif error_type == "missing_prop":
        return inject_missing_prop(entity)
    else:
        return None, None, None


def generate_version(input_file: Path, output_file: Path,
                     error_rate: float, version_name: str):
    errors_by_class = {}
    errors_by_type = {}
    total_errors = 0
    total_count = 0

    with input_file.open("r", encoding="utf-8") as inf, \
         output_file.open("w", encoding="utf-8") as outf:

        for line in inf:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except Exception as e:
                print(f"Error parsing line: {e}")
                continue

            entity = data.get("entity", {})
            true_class = entity.get("tier_label")
            total_count += 1

            should_error = random.random() < error_rate
            sim_info = {"has_error": False}

            if should_error:
                chosen_error_type = random.choice(ERROR_TYPES)
                etype, field_name, original_val = apply_error(entity, chosen_error_type)

                if etype is not None:
                    total_errors += 1
                    errors_by_type[etype] = errors_by_type.get(etype, 0) + 1
                    if true_class:
                        errors_by_class[true_class] = errors_by_class.get(true_class, 0) + 1

                    sim_info = {
                        "has_error": True,
                        "error_type": etype,
                        "field": field_name,
                        "original_value": original_val,
                        "true_class": true_class,
                    }

            data["entity"] = entity
            data["sim_error"] = sim_info

            outf.write(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"\n{version_name} generated: {output_file}")
    print(f"  Total entities: {total_count}")
    print(f"  Total injected errors: {total_errors} ({total_errors/total_count*100:.2f}%)")
    print(f"  Errors by type: {errors_by_type}")
    print(f"  Top classes with errors: {dict(sorted(errors_by_class.items(), key=lambda x: -x[1])[:10])}")

    return total_errors, total_count


def main():
    input_file = INPUT_DIR / "uir_ground_truth.jsonl"

    if not input_file.exists():
        print(f"Error: {input_file} not found!")
        return

    # Version 1: 8% error rate
    v1_file = INPUT_DIR / "uir_simulated_v1.jsonl"
    print("Generating Version 1 (minor errors, ~8% error rate)...")
    generate_version(input_file, v1_file, error_rate=0.08, version_name="Version 1")

    # Version 2: 15% error rate
    v2_file = INPUT_DIR / "uir_simulated_v2.jsonl"
    print("\nGenerating Version 2 (more errors, ~15% error rate)...")
    generate_version(input_file, v2_file, error_rate=0.15, version_name="Version 2")

    print("\n" + "=" * 60)
    print("Files generated successfully!")
    print("=" * 60)
    print(f"Ground truth: {input_file}")
    print(f"Version 1 (minor errors): {v1_file}")
    print(f"Version 2 (more errors): {v2_file}")


if __name__ == "__main__":
    main()


