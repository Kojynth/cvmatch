"""
Section Validation Report
-------------------------

Generates a detailed, section-by-section validation report for extraction results.

Features
- Runs the enhanced extraction pipeline on N CV files (text files recommended)
- Computes per-section precision/recall vs a provided baseline (or creates one)
- Includes Overfitting Monitor indicators (pattern diversity, enforcement action)
- Produces a JSON report and console summary dashboard

Usage
  python scripts/section_validation_report.py \
      --input CV/ --limit 5 \
      --baseline baseline_report.json \
      --output validation_report.json

Notes
- If --baseline is not provided, a new baseline is generated from the current run and saved.
- If no files are found under --input, the script falls back to synthetic scenarios from
  scripts/validate_hardened_extraction_metrics.py to still produce a report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set

from app.utils.enhanced_extraction_pipeline import EnhancedExtractionPipeline


def _collect_cv_files(input_dir: Path, limit: int) -> List[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        return []
    exts = {".txt", ".md"}  # pipeline loader is simplified; prefer text inputs
    files = [p for p in sorted(input_dir.iterdir()) if p.suffix.lower() in exts]
    return files[:limit]


def _fallback_scenarios() -> List[Tuple[str, List[str]]]:
    try:
        # reuse existing synthetic scenarios
        from scripts.validate_hardened_extraction_metrics import create_test_cv_scenarios
        return create_test_cv_scenarios()
    except Exception:
        return [("fallback_one", ["Experience", "2020 - 2022", "Dev chez ACME", "API, React"])]


def _normalize_str(x: Any) -> str:
    return " ".join(str(x or "").strip().split())


def _section_sets_from_result(result: Dict[str, Any]) -> Dict[str, Set[str]]:
    # Build comparable sets per section from pipeline result
    sections: Dict[str, Set[str]] = {
        "experiences": set(),
        "education": set(),
        "skills": set(),
        "languages": set(),
        "certifications": set(),
        "projects": set(),
    }

    for exp in result.get("experiences", []) or []:
        # prefer title + org if present
        key = _normalize_str(f"{exp.get('title','')}|{exp.get('organization','')}")
        if key.strip("|"):
            sections["experiences"].add(key)

    for edu in result.get("education", []) or []:
        key = _normalize_str(f"{edu.get('degree','')}|{edu.get('institution','')}")
        if key.strip("|"):
            sections["education"].add(key)

    for sk in result.get("skills", []) or []:
        name = _normalize_str(sk.get("name", ""))
        if name:
            sections["skills"].add(name)

    for lang in result.get("languages", []) or []:
        name = _normalize_str(lang.get("language", lang.get("name", "")))
        if name:
            sections["languages"].add(name)

    for cert in result.get("certifications", []) or []:
        name = _normalize_str(cert.get("name", ""))
        if name:
            sections["certifications"].add(name)

    for prj in result.get("projects", []) or []:
        name = _normalize_str(prj.get("name", ""))
        if name:
            sections["projects"].add(name)

    return sections


def _prf(current: Set[str], baseline: Set[str]) -> Dict[str, float]:
    inter = current.intersection(baseline)
    p = (len(inter) / len(current)) if current else 1.0
    r = (len(inter) / len(baseline)) if baseline else 1.0
    f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    j = (len(inter) / len(current.union(baseline))) if (current or baseline) else 1.0
    return {"precision": p, "recall": r, "f1": f1, "jaccard": j, "tp": len(inter), "cur": len(current), "base": len(baseline)}


def _extract_with_pipeline(pipeline: EnhancedExtractionPipeline, path: Path) -> Dict[str, Any]:
    return pipeline.extract_cv_enhanced(str(path))


def _extract_from_lines(pipeline: EnhancedExtractionPipeline, name: str, lines: List[str]) -> Dict[str, Any]:
    # Write to temp file to reuse the same pipeline path
    tmp = Path(name + "_tmp.txt")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    try:
        return _extract_with_pipeline(pipeline, tmp)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def run(input_dir: Path, limit: int, baseline_path: Path | None, output_path: Path) -> int:
    pipeline = EnhancedExtractionPipeline()

    files = _collect_cv_files(input_dir, limit)
    used_scenarios = False

    if not files:
        scenarios = _fallback_scenarios()[:limit]
        used_scenarios = True
    else:
        scenarios = []

    current_results: Dict[str, Any] = {}

    if used_scenarios:
        for name, lines in scenarios:
            res = _extract_from_lines(pipeline, name, lines)
            current_results[name] = res
    else:
        for p in files:
            res = _extract_with_pipeline(pipeline, p)
            current_results[p.name] = res

    # Prepare or load baseline
    if baseline_path and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_results = baseline.get("results", {})
    else:
        baseline_results = current_results
        # Save generated baseline for future comparisons
        if baseline_path:
            baseline_path.write_text(json.dumps({"results": baseline_results}, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build per-section sets and compute metrics
    report: Dict[str, Any] = {
        "documents": {},
        "summary": {},
    }

    per_section_scores: Dict[str, List[float]] = {s: [] for s in ["experiences", "education", "skills", "languages", "certifications", "projects"]}

    for doc_name, cur in current_results.items():
        base = baseline_results.get(doc_name, {})
        cur_sets = _section_sets_from_result(cur)
        base_sets = _section_sets_from_result(base)

        section_metrics = {}
        for section in cur_sets.keys():
            m = _prf(cur_sets[section], base_sets.get(section, set()))
            section_metrics[section] = m
            per_section_scores[section].append(m["f1"])  # track F1 for summary

        # Overfitting monitor / diversity signals (from validation in pipeline result)
        validation = cur.get("validation", {})
        diversity = validation.get("pattern_diversity", 0.0)
        enforcement = validation.get("enforcement_result", {})

        report["documents"][doc_name] = {
            "section_metrics": section_metrics,
            "diversity": diversity,
            "enforcement": enforcement,
            "success": cur.get("success", False),
        }

    # Summary dashboard
    summary = {}
    for section, f1s in per_section_scores.items():
        if f1s:
            summary[section] = {
                "avg_f1": sum(f1s) / len(f1s),
                "docs": len(f1s)
            }
        else:
            summary[section] = {"avg_f1": 1.0, "docs": 0}
    report["summary"] = summary

    # Save report
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console dashboard
    print("\n=== Section Validation Summary ===")
    for section in ["experiences", "education", "skills", "languages", "certifications", "projects"]:
        s = report["summary"].get(section, {})
        print(f"- {section:14} F1(avg)={s.get('avg_f1', 0.0):.3f} over {s.get('docs', 0)} docs")

    # Overfitting monitor signals
    print("\n=== Overfitting Monitor Signals ===")
    for doc, data in report["documents"].items():
        action = data.get("enforcement", {}).get("action", "unknown")
        diversity = data.get("diversity", 0.0)
        print(f"- {doc:20} diversity={diversity:.3f} enforcement={action}")

    return 0


def main():
    ap = argparse.ArgumentParser(description="Generate section-wise validation report (regression vs baseline)")
    ap.add_argument("--input", type=str, default="CV",
                    help="Folder with CV text files (defaults to ./CV)")
    ap.add_argument("--limit", type=int, default=5, help="Max files to process")
    ap.add_argument("--baseline", type=str, default="", help="Path to baseline JSON to compare against")
    ap.add_argument("--output", type=str, default="section_validation_report.json", help="Output JSON report path")
    args = ap.parse_args()

    input_dir = Path(args.input)
    baseline_path = Path(args.baseline) if args.baseline else None
    output_path = Path(args.output)

    return run(input_dir, args.limit, baseline_path, output_path)


if __name__ == "__main__":
    raise SystemExit(main())

