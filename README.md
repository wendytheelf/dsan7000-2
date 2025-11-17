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
├── rules/ # Rule definitions and class mapping configurations (e.g., class_maps.yaml)
├── review/ # Manual review logs and iterative feedback for validation improvements
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
