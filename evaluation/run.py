"""Generate a JSON evaluation record and concise Markdown summary."""

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.metrics import evaluate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GROUND_TRUTH = PROJECT_ROOT / "data/ground_truth/fictional_battery_module_spec_validation.json"
DEFAULT_RESULT = PROJECT_ROOT / (
    "data/results/"
    "battery-module-technical-specification-validation-report_"
    "20261005T090211Z_bdc39d95_validated.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/results/evaluation"


def _percent(score: float) -> str:
    """Format a ratio as a one-decimal percentage."""
    return f"{score * 100:.1f}%"


def _main_errors(report: dict[str, Any]) -> list[str]:
    """Summarize incorrect values, missing context, and source mismatches."""
    errors = []
    for item in report["fields"]:
        if not item["value_correct"]:
            errors.append(f"{item['field_name']}: core value differs from the expected value.")
        if item["missing_context"]:
            details = ", ".join(item["missing_context"])
            errors.append(f"{item['field_name']}: missing context: {details}.")
        if not item["source_correct"]:
            expected = item["expected_source"]["section_id"]
            actual = item["model_source"] or {}
            actual_id = actual.get("section_id", "not provided")
            errors.append(f"{item['field_name']}: cited section {actual_id}; expected {expected}.")
    return errors


def render_summary(report: dict[str, Any]) -> str:
    """Render the evaluated metrics and field-level issues in Markdown."""
    metrics = report["metrics"]
    accuracy = metrics["extraction_accuracy"]
    completeness = metrics["completeness"]
    sources = metrics["source_correctness"]
    latency = metrics["latency"]
    counts = completeness["status_counts"]
    errors = _main_errors(report)

    lines = [
        f"# Evaluation Summary: {report['document_title']}",
        "",
        f"- **Inference run:** `{report['run_id']}`",
        f"- **Fields evaluated:** {report['total_fields']}",
        f"- **Extraction Accuracy:** {accuracy['correct_core_values']}/{accuracy['total_fields']} ({_percent(accuracy['score'])})",
        f"- **Completeness:** {_percent(completeness['score'])} "
        f"(complete {counts['complete']}, partially complete {counts['partially_complete']}, incomplete {counts['incomplete']})",
        f"- **Source Correctness:** {sources['correct_source_references']}/{sources['total_fields']} ({_percent(sources['score'])})",
        f"- **End-to-End Latency:** {latency['end_to_end_seconds']:.2f} seconds",
        "- **Model Request Latency:** "
        + (
            f"{latency['model_request_seconds']:.2f} seconds"
            if latency["model_request_seconds"] is not None
            else "not recorded"
        ),
        "",
        "## Main Errors and Missing Details",
        "",
    ]
    lines.extend([f"- {error}" for error in errors] if errors else ["- None detected."])
    lines.extend(
        [
            "",
            "## Scoring Assumptions",
            "",
            f"- Completeness scoring: {completeness['score_method']}",
            "- Completeness checks the model's value, unit, qualifier, and conditions; field labels and citations do not count as answer context.",
            "- Source correctness requires both the section ID and case-insensitive section title to match the Ground Truth.",
            "- Core-value accuracy is scored independently from qualifiers and source references.",
            "",
        ]
    )
    return "\n".join(lines)


def run_evaluation(
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH,
    result_path: Path = DEFAULT_RESULT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path, dict[str, Any]]:
    """Load the two existing JSON files, score them, and save both reports."""
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    inference = json.loads(result_path.read_text(encoding="utf-8"))
    report = evaluate(ground_truth, inference)

    timestamp = inference["run_id"].split("_", maxsplit=1)[0]
    base_name = f"battery-module-evaluation_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{base_name}.json"
    markdown_path = output_dir / f"{base_name}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_summary(report), encoding="utf-8")
    return json_path, markdown_path, report


def main() -> None:
    """Run evaluation using the existing project artifacts by default."""
    parser = argparse.ArgumentParser(description="Score a validated inference result against Ground Truth.")
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    json_path, markdown_path, report = run_evaluation(args.ground_truth, args.result, args.output_dir)
    metrics = report["metrics"]
    print(f"Detailed report: {json_path}")
    print(f"Summary: {markdown_path}")
    print(f"Extraction Accuracy: {_percent(metrics['extraction_accuracy']['score'])}")
    print(f"Completeness: {_percent(metrics['completeness']['score'])}")
    print(f"Source Correctness: {_percent(metrics['source_correctness']['score'])}")


if __name__ == "__main__":
    main()
