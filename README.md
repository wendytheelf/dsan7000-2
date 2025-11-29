# Trustworthy BIM — LLM-assisted Canonicalization & Validation Pipeline
Author : Li Wen (Wendy) Hu

This repository implements an end-to-end pipeline for mapping IFC building information to canonical classes and validating them through a hybrid LLM + rule-based system.  
The goal is to improve trustworthiness, consistency, and efficiency in BIM data processing.

---

## Project Structure

trustworthy_bim/
├── compute_success_metrics.py # Evaluates model outputs (precision, recall, F1, validation coverage)
├── config.yaml # Configuration for input/output paths, thresholds, and model parameters
├── ifc_to_canonical.py # Maps IFC entities to canonical class representations
├── llm_runner.py # Handles prompt construction, API calls, and response parsing for LLM
├── models.py # Defines data schemas and helper classes (Asset, Property, ValidationRecord)
├── unit_normalizer.py # Normalizes physical units (e.g., "5 m" → 5.0, "200mm" → 0.2)
├── validators.py # Implements rule-based and statistical validation of canonicalized data
│
├── input/ # Input IFC-derived data or preprocessed assets
├── output/ # Generated canonical assets, property mappings, and validation results
│ ├── assets.csv
│ ├── asset_props.csv
│ └── logs/
│
├── prompt_templates/ # Prompt templates for different LLM tasks (mapping, property inference, etc.)
├── rules/ # Rule definitions and class mapping configurations
│   ├── class_maps.yaml # Canonical class mappings, keyword overrides, and keyword validation
│   ├── neighbor_rules.yaml # Relationship rules with minimum count requirements
│   ├── validation_rules.yaml # Validation incoherences and error detection rules
│   ├── required_props.yaml # Required properties per class
│   ├── ranges.yaml # Property value ranges (min/max)
│   └── units_override.yaml # Unit conversion overrides
├── results/ # Visualizations and summary metrics (created by scripts)
└── logs/ # System and evaluation logs

## How to run

```
python ifc_to_canonical.py run \
  --in input/uir_enriched.jsonl \
  --outdir output \
  --config config.yaml \
  --tolerant
```
This maps IFC entities into canonical class representations, output a json showing the validation results and the property mappings

```
python compute_success_metrics.py

```
Running the `compute_success_metrics.py` shows the mapping rate and the normalization rate

---

## Pipeline Overview

1. **Input Parsing**  
   IFC elements are extracted and preprocessed into structured tabular data.

2. **Canonicalization (LLM Stage)**  
   `llm_runner.py` sends IFC entity descriptions to an LLM using templates in `prompt_templates/`.  
   The LLM predicts canonical class and missing properties.

3. **Normalization & Rule-based Validation**  
   - `unit_normalizer.py` ensures consistent units.  
   - `validators.py` applies logical and numerical checks using rules in `rules/`.

4. **Evaluation & Metrics**  
   - `compute_success_metrics.py` calculates precision, recall, F1-score, validation coverage, and confidence reliability.  
   - Outputs are logged in `output/` and summarized for review.

---

## Rules System

The validation pipeline uses a comprehensive rule-based system defined in YAML files under `rules/`. These rules ensure consistency, detect errors, and validate relationships in BIM models.

### Rule Files Overview

#### 1. `class_maps.yaml`
**Purpose**: Defines canonical class mappings and keyword-based classification rules.

**Sections**:
- **`allowed_classes`**: List of all valid canonical class names (e.g., "Foundation_Slab", "Columns (Concrete)")
- **`ifc_to_canonical`**: Basic IFC class to canonical class mappings (e.g., `IfcSlab` → `Slabs`)
- **`keyword_overrides`**: Keyword-based classification that overrides basic mappings. Used for:
  - Distinguishing external vs internal walls
  - Identifying foundation slabs vs regular slabs
  - Classifying concrete vs steel columns/beams
  - MEP component classification
- **`keyword_validation`**: Consistency checking rules that validate entity names/properties match expected keywords
  - Format: `{class: {any: [required_keywords], none: [forbidden_keywords]}}`
  - Example: Pump must contain "pump" and must not contain "valve" or "radiator"

#### 2. `neighbor_rules.yaml`
**Purpose**: Defines relationship requirements between entities (structural and MEP).

**Format**: Each class specifies required relationships with `min_count` requirements:
```yaml
Foundation_Slab:
  relations:
    supports:
      min_count: 1  # Must support at least 1 Column or Wall
    restsOn:
      min_count: 1  # Must rest on IfcSite (Terrain)
```

**Covers**:
- Structural elements: Foundation_Slab, Slabs, Columns, Beams, Walls, Doors, Windows, Roof, Ceilings, Floors
- MEP elements: Pump, Valve, Fan, Motor, Duct, Pipe, Boiler, Chiller, AHU, etc.

**Validation**: Flags entities as `INCONSISTENT_NEIGHBOR` if relationship requirements are not met.

#### 3. `validation_rules.yaml`
**Purpose**: Defines validation incoherences and error detection rules for Tier1 structural classes.

**Structure**: Each class contains:
- **`definition`**: Class description
- **`incoherences`**: List of validation rules with:
  - `description`: What to check
  - `severity`: `error`, `warning`, or `info`
  - `hint`: Guidance for edge cases
  - `exception`: Valid exceptions to the rule

**Example Rules**:
- **Foundation_Slab**: Floating (must contact terrain), Clash (overlap with Piles)
- **Columns**: Floating/Gap (must touch something above/below), Transfer Columns (valid if on Transfer Beam)
- **Beam**: Clash (must not intersect Windows/Doors), Cantilevers (valid if one end fixed)
- **External walls**: Gaps (perimeter must be closed), Curtain Walls (valid exceptions)
- **Doors/Windows**: Orphan (must have wall), Clash (must not intersect Columns)

**Edge Cases**: Includes valid exceptions like:
- Cantilevers (beams with one free end)
- Transfer Columns (columns starting mid-air on Transfer Beams)
- Juliet Balconies (external doors above floor level)
- Floor-to-Ceiling windows (storefronts)

#### 4. `required_props.yaml`
**Purpose**: Defines required properties for each canonical class.

**Format**: Simple list of property names per class:
```yaml
Slabs:
  - NetArea
  - NetVolume

External walls (façade):
  - NetSideArea
  - Width
```

**Validation**: Flags entities as `MISSING_REQUIRED_PROPERTY` if required properties are absent.

#### 5. `ranges.yaml`
**Purpose**: Defines valid value ranges (min/max) for properties.

**Structure**:
- **Global ranges**: Apply to all classes unless overridden
- **Class-specific ranges**: Override global ranges for specific classes

**Example**:
```yaml
# Global
flow_rate:
  min: 0.01  # L/s
  max: 500.0  # L/s

# Class-specific
Pump:
  flow_rate:
    min: 0.1  # L/s
    max: 500.0  # L/s
```

**Validation**: Flags values as `OUT_OF_RANGE` if outside specified min/max.

#### 6. `units_override.yaml`
**Purpose**: Defines unit conversion overrides for geometric dimensions.

**Default units**: Typically `mm` for geometric dimensions (common in IFC Qto_* properties).

**Usage**: Used by `unit_normalizer.py` to ensure consistent unit representation before validation.

### Rule Validation Flow

1. **Class Mapping**: `class_maps.yaml` maps IFC classes to canonical classes
2. **Keyword Validation**: `keyword_validation` section checks name/property consistency
3. **Property Validation**: `required_props.yaml` and `ranges.yaml` validate properties
4. **Relationship Validation**: `neighbor_rules.yaml` checks entity relationships
5. **Incoherence Detection**: `validation_rules.yaml` detects geometric and logical errors

### Adding New Rules

To add rules for a new class:
1. Add to `allowed_classes` in `class_maps.yaml`
2. Add IFC mapping in `ifc_to_canonical` section
3. Add keyword overrides if needed
4. Add required properties in `required_props.yaml`
5. Add value ranges in `ranges.yaml` (if applicable)
6. Add relationship rules in `neighbor_rules.yaml`
7. Add validation rules in `validation_rules.yaml` (for structural elements)

---

## Simulation & Evaluation Scripts

The project includes a small set of Python utilities (in addition to `ifc_to_canonical.py`) for **simulating errors** and **evaluating the rule-based validator** without relying on a real LLM:

### 1. `trustworthy_bim/input/generate_simulated_errors.py`
**Purpose**: Create two simulated datasets with injected errors starting from `uir_ground_truth.jsonl`.

**Outputs**:
- `uir_simulated_v1.jsonl` (~8% errors)
- `uir_simulated_v2.jsonl` (~15% errors)

**Error types injected**:
- `wrong_class`: change `entity['tier_label']`
- `out_of_range`: multiply selected numeric Beam properties by 1000×
- `negative`: flip selected numeric Beam properties to negative values
- `missing_prop`: delete selected Beam properties

Each line also gets a `sim_error` field recording:
- `has_error`, `error_type`, `field`, `original_value`, `true_class`

### 2. Running the pipeline on simulated data

Use the same canonicalization pipeline on ground truth and both simulated files:

```bash
cd /home/wendy/dsan7000-2

python trustworthy_bim/ifc_to_canonical.py run \
  --in trustworthy_bim/input/uir_ground_truth.jsonl \
  --outdir trustworthy_bim/output_ground_truth \
  --tolerant

python trustworthy_bim/ifc_to_canonical.py run \
  --in trustworthy_bim/input/uir_simulated_v1.jsonl \
  --outdir trustworthy_bim/output_simulated_v1 \
  --tolerant

python trustworthy_bim/ifc_to_canonical.py run \
  --in trustworthy_bim/input/uir_simulated_v2.jsonl \
  --outdir trustworthy_bim/output_simulated_v2 \
  --tolerant
```

This produces (per output dir): `assets.csv`, `asset_props.csv`, `asset_relations.csv`, `asset_flags.csv`, and `review_queue.csv`.

### 3. `trustworthy_bim/input/compare_precision_by_class.py`
**Purpose**: Compare **per-class precision/recall/F1** between:
- Ground truth (`uir_ground_truth.jsonl`)
- Simulated V1 (`uir_simulated_v1.jsonl`)
- Simulated V2 (`uir_simulated_v2.jsonl`)

**Output**:
- Prints per-class precision table (V1 vs V2)
- Writes `precision_comparison.json` for downstream plotting

### 4. `trustworthy_bim/input/visualize_precision_comparison.py`
**Purpose**: Plot **per-class precision** comparison for:
- Ground truth (ideal, 100%)
- Simulated V1 (~8% noise)
- Simulated V2 (~15% noise)

**Output**:
- `results/visualizations/A_mapping_accuracy_comparison.png`

### 5. `trustworthy_bim/input/evaluate_validator.py`
**Purpose**: Evaluate how well the **rule-based validator** catches the injected errors (no LLM needed).

For each simulated dataset, it:
- Reads `sim_error` from the simulated JSONL
- Reads `assets.csv` and `asset_flags.csv` from the corresponding outdir
- Computes, per error type (`out_of_range`, `negative`, `missing_prop`):
  - Injected count (ground-truth positives)
  - Caught count (matching rule-based flags)
  - TP / FP / FN / TN
  - Precision / Recall / F1
- Builds a row-normalized confusion matrix of `true_class` vs `canonical_class`

**Usage**:

```bash
cd trustworthy_bim/input

python evaluate_validator.py \
  --sim_jsonl uir_simulated_v1.jsonl \
  --outdir ../output_simulated_v1

python evaluate_validator.py \
  --sim_jsonl uir_simulated_v2.jsonl \
  --outdir ../output_simulated_v2
```

This creates:
- `uir_simulated_v1.validator_eval.json`
- `uir_simulated_v2.validator_eval.json`

### 6. `trustworthy_bim/input/plot_validator_metrics.py`
**Purpose**: Visualize validator performance and class confusion using the `*.validator_eval.json` files.

**Outputs** (in `results/visualizations/`):
- `E_validator_recall_by_error_type.png`
  - Bar chart of **recall (%) by error type** for each simulated dataset
- `E_validator_class_confusion_simulated_v1.png`
- `E_validator_class_confusion_simulated_v2.png`
  - Heatmaps of **true_class vs predicted_class** (row-normalized, %)

**Usage**:

```bash
cd trustworthy_bim/input
python plot_validator_metrics.py
```

---

## 📊 Current Progress

- Implemented core modules: canonicalizer, validator, and metric computation  
- Configured YAML-based rule system (`rules/class_maps.yaml`)  
- Generated and validated sample `assets.csv` and `asset_props.csv`  
- Ongoing: Confidence–correctness correlation analysis  
- Next: Reliability calibration & visualization dashboard

---

## Next Steps

1. **Add visualization of reliability curve (ECE, Brier score)**  
2. **Refine prompt templates for improved property completion**  
3. **Integrate manual review feedback loop into `review/` pipeline**  
4. **Automate runtime tracking and optimization analysis**

---
