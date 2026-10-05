"""Small, transparent scoring functions for one inference result."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any


# Each item is (label, alternative token groups, critical). Every token in a
# group must appear; a missing critical item makes the field incomplete.
COMPLETENESS_RULES: dict[str, list[tuple[str, tuple[tuple[str, ...], ...], bool]]] = {
    "production_nominal_energy": [
        ("nominal rating", (("nominal",),), True),
        ("Revision C production scope", (("revision c",), ("production configuration",)), False),
    ],
    "production_nominal_voltage": [
        ("nominal rating", (("nominal",),), True),
        ("DC terminal context", (("dc", "terminal"),), False),
    ],
    "continuous_discharge_current": [
        ("continuous limit", (("continuous",),), True),
        ("BMS and thermal conditions", (("bms",), ("thermal",)), False),
    ],
    "maximum_charge_current": [
        ("maximum continuous charge limit", (("maximum", "continuous"),), True),
        ("below-zero charging restriction", (("below 0",), ("below-freezing",)), False),
    ],
    "usable_soc_window": [
        ("inclusive controller endpoints", (("inclusive", "endpoints"),), False),
        ("normal module window", (("normal", "window"), ("usable", "module")), False),
    ],
    "operating_temperature": [
        ("ambient operating condition", (("ambient",),), True),
        ("derating at range endpoints", (("derating",), ("derated",)), False),
    ],
    "storage_temperature": [
        ("storage-specific condition", (("storage",),), True),
        ("module isolated condition", (("module", "isolated"),), False),
    ],
    "maximum_cell_temperature_during_operation": [
        ("maximum permitted cell temperature", (("maximum", "cell"),), True),
        ("during-operation condition", (("during operation",), ("operating",)), False),
    ],
    "maximum_cell_to_cell_temperature_spread": [
        ("steady-load condition", (("steady", "load"),), False),
        ("coolant condition", (("coolant",),), False),
    ],
    "module_mass": [
        ("maximum mass limit", (("maximum",), ("not more than",)), True),
        ("dry-state condition", (("dry state",), ("dry",)), False),
    ],
    "enclosure_ingress_protection": [
        ("assembled module is correctly sealed", (("assembled module", "seal"), ("correctly sealed",)), True),
    ],
    "minimum_isolation_resistance": [
        ("specified DC test voltage", (("500 v dc",), ("test voltage", "500")), True),
    ],
    "vibration_validation_profile": [
        ("frequency range", (("10", "500", "hz"),), True),
        ("vibration severity", (("3.0", "g rms"),), True),
        ("duration and axes", (("8", "hour", "axis"),), True),
    ],
    "cycle_life_acceptance_criterion": [
        ("retained-capacity endpoint", (("80%",), ("80", "retained capacity")), True),
    ],
    "known_issue_soc_indication_lag": [
        ("rapid-load-change trigger", (("rapid load change",), ("rapid", "load")), True),
        ("protection impact", (("protection", "not affected"), ("protection", "no impact")), False),
    ],
}

NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")


def _numbers(value: Any) -> list[Decimal]:
    """Extract ordered numeric components from a scalar or compound value."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float, Decimal)):
        try:
            return [Decimal(str(value))]
        except InvalidOperation:
            return []
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _numbers(item)]
    if isinstance(value, str):
        found = []
        for token in NUMBER_PATTERN.findall(value.replace(",", "")):
            try:
                found.append(Decimal(token))
            except InvalidOperation:
                continue
        return found
    return []


def _expected_core_numbers(field_id: str, expected: Any) -> list[Decimal]:
    """Select the core numeric answer, excluding separate completeness details."""
    if field_id == "minimum_isolation_resistance":
        return _numbers(expected["minimum_resistance"])
    if field_id == "cycle_life_acceptance_criterion":
        return _numbers(expected["minimum_equivalent_full_cycles"])
    return _numbers(expected)


def _searchable_text(field: dict[str, Any]) -> str:
    """Join answer context while excluding the prompt-provided field label/citation."""
    parts = [field.get("value"), field.get("unit"), field.get("qualifier"), field.get("conditions", [])]

    def collect(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value.casefold()]
        if isinstance(value, dict):
            return [item for child in value.values() for item in collect(child)]
        if isinstance(value, (list, tuple)):
            return [item for child in value for item in collect(child)]
        return []

    return " ".join(item for part in parts for item in collect(part))


def _detail_present(text: str, alternatives: tuple[tuple[str, ...], ...]) -> bool:
    """Match a required phrase, allowing one of several concise formulations."""
    return any(all(term.casefold() in text for term in group) for group in alternatives)


def _completeness(field_id: str, model_field: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Score whether required qualifiers and conditions accompany an answer."""
    text = _searchable_text(model_field)
    rules = COMPLETENESS_RULES[field_id]
    present = [label for label, alternatives, _ in rules if _detail_present(text, alternatives)]
    missing = [label for label, alternatives, _ in rules if not _detail_present(text, alternatives)]
    missing_critical = [
        label for label, alternatives, critical in rules
        if critical and not _detail_present(text, alternatives)
    ]
    if missing_critical:
        status = "incomplete"
    elif missing:
        status = "partially_complete"
    else:
        status = "complete"
    return status, present, missing


def _value_is_correct(field_id: str, expected: Any, model_value: Any) -> bool:
    """Compare the core value while leaving qualifiers to the completeness score."""
    expected_numbers = _expected_core_numbers(field_id, expected)
    if expected_numbers:
        return _numbers(model_value) == expected_numbers
    if isinstance(expected, str):
        expected_key = re.sub(r"[^a-z0-9]", "", expected.casefold())
        model_key = re.sub(r"[^a-z0-9]", "", str(model_value).casefold())
        return expected_key in model_key
    return expected == model_value


def evaluate(ground_truth: dict[str, Any], inference: dict[str, Any]) -> dict[str, Any]:
    """Compare one validated inference result with its Ground Truth record.

    Core-value, required-context, and source checks are kept independent so a
    right value with missing conditions or a wrong citation remains visible.
    """
    expected_fields = {item["field_id"]: item for item in ground_truth["fields"]}
    model_fields = {
        item["field_id"]: item
        for item in inference["analysis"]["fields"]
    }
    if set(expected_fields) != set(model_fields):
        raise ValueError("Ground Truth and inference must contain the same field IDs.")

    details = []
    for field_id, expected in expected_fields.items():
        model_field = model_fields[field_id]
        expected_source = expected["authoritative_source"]
        model_source = model_field.get("source_section")
        value_correct = _value_is_correct(field_id, expected["value"], model_field.get("value"))
        status, present_context, missing_context = _completeness(field_id, model_field)
        source_correct = bool(
            model_source
            and model_source.get("section_id") == expected_source["section_id"]
            and " ".join(model_source.get("section_title", "").casefold().split())
            == " ".join(expected_source["section_title"].casefold().split())
        )
        details.append(
            {
                "field_id": field_id,
                "field_name": expected["field_name"],
                "expected_value": expected["value"],
                "model_value": model_field.get("value"),
                "value_correct": value_correct,
                "completeness_status": status,
                "present_context": present_context,
                "missing_context": missing_context,
                "expected_source": expected_source,
                "model_source": model_source,
                "source_correct": source_correct,
            }
        )

    total = len(details)
    completeness_weights = {"complete": 1.0, "partially_complete": 0.5, "incomplete": 0.0}
    completeness_points = sum(completeness_weights[item["completeness_status"]] for item in details)
    status_counts = {
        status: sum(item["completeness_status"] == status for item in details)
        for status in completeness_weights
    }
    correct_values = sum(item["value_correct"] for item in details)
    correct_sources = sum(item["source_correct"] for item in details)

    return {
        "document_id": ground_truth["document_id"],
        "document_title": ground_truth["document_title"],
        "run_id": inference["run_id"],
        "total_fields": total,
        "metrics": {
            "extraction_accuracy": {
                "correct_core_values": correct_values,
                "total_fields": total,
                "score": correct_values / total if total else 0.0,
            },
            "completeness": {
                "score": completeness_points / total if total else 0.0,
                "score_method": "complete=1, partially_complete=0.5, incomplete=0; mean across fields",
                "status_counts": status_counts,
            },
            "source_correctness": {
                "correct_source_references": correct_sources,
                "total_fields": total,
                "score": correct_sources / total if total else 0.0,
                "comparison": "section ID and case-insensitive section title must both match",
            },
            "latency": {
                "end_to_end_seconds": inference["latency_seconds"],
                "model_request_seconds": inference.get("model_latency_seconds"),
            },
        },
        "fields": details,
        "assumptions": [
            "Core-value scoring compares numeric components or the exact classification; units and qualifiers are scored separately under completeness.",
            "Completeness checks only model value, unit, qualifier, and conditions. It does not count field names, IDs, or citations as answer context.",
            "A critical missing context item makes a field incomplete; if all critical items are present but supporting context is missing, it is partially complete.",
            "Source correctness requires both the authoritative section ID and normalized title to match.",
        ],
    }
