from evaluation.metrics import evaluate


def test_evaluate_separates_core_value_completeness_and_source_correctness():
    ground_truth = {
        "document_id": "sample",
        "document_title": "Sample",
        "fields": [
            {
                "field_id": "production_nominal_energy",
                "field_name": "Production nominal energy",
                "value": 5.12,
                "unit": "kWh",
                "authoritative_source": {"section_id": "3.2", "section_title": "Rated Energy and Capacity"},
            },
            {
                "field_id": "minimum_isolation_resistance",
                "field_name": "Minimum isolation resistance",
                "value": {"minimum_resistance": 500, "test_voltage": 500},
                "authoritative_source": {"section_id": "6.2", "section_title": "Electrical Isolation"},
            },
            {
                "field_id": "cycle_life_acceptance_criterion",
                "field_name": "Cycle-life acceptance criterion",
                "value": {"minimum_equivalent_full_cycles": 2000, "minimum_retained_capacity_percent": 80},
                "authoritative_source": {"section_id": "8.5", "section_title": "Cycle-Life Acceptance"},
            },
        ],
    }
    inference = {
        "run_id": "sample-run",
        "latency_seconds": 2.5,
        "model_latency_seconds": 2.0,
        "analysis": {
            "fields": [
                {
                    "field_id": "production_nominal_energy",
                    "value": "5.12 kWh",
                    "unit": "kWh",
                    "qualifier": "nominal",
                    "conditions": ["Revision C production configuration"],
                    "source_section": {"section_id": "3.2", "section_title": "Rated Energy and Capacity"},
                },
                {
                    "field_id": "minimum_isolation_resistance",
                    "value": "500 Ω/V",
                    "unit": "Ω/V",
                    "source_section": {"section_id": "6.3", "section_title": "Isolation Test"},
                },
                {
                    "field_id": "cycle_life_acceptance_criterion",
                    "value": "at least 2,000 equivalent full cycles",
                    "unit": "EFC",
                    "source_section": {"section_id": "8.5", "section_title": "Cycle-Life Acceptance"},
                },
            ],
            "summary": "Summary",
        },
    }

    report = evaluate(ground_truth, inference)

    assert report["metrics"]["extraction_accuracy"]["score"] == 1.0
    assert report["metrics"]["source_correctness"]["correct_source_references"] == 2
    assert report["metrics"]["completeness"]["status_counts"] == {
        "complete": 1,
        "partially_complete": 0,
        "incomplete": 2,
    }
    assert report["fields"][1]["completeness_status"] == "incomplete"
    assert report["fields"][1]["missing_context"] == ["specified DC test voltage"]
    assert report["metrics"]["latency"]["end_to_end_seconds"] == 2.5


def test_completeness_uses_partial_status_when_only_supporting_context_is_missing():
    ground_truth = {
        "document_id": "sample",
        "document_title": "Sample",
        "fields": [
            {
                "field_id": "maximum_cell_to_cell_temperature_spread",
                "field_name": "Maximum cell-to-cell temperature spread",
                "value": 8,
                "authoritative_source": {
                    "section_id": "4.4",
                    "section_title": "Temperature Uniformity Requirement",
                },
            }
        ],
    }
    inference = {
        "run_id": "sample-run",
        "latency_seconds": 1.0,
        "analysis": {
            "fields": [
                {
                    "field_id": "maximum_cell_to_cell_temperature_spread",
                    "value": "8 °C",
                    "unit": "°C",
                    "source_section": {
                        "section_id": "4.4",
                        "section_title": "Temperature Uniformity Requirement",
                    },
                }
            ]
        },
    }

    report = evaluate(ground_truth, inference)

    assert report["metrics"]["extraction_accuracy"]["score"] == 1.0
    assert report["metrics"]["completeness"]["score"] == 0.5
    assert report["fields"][0]["completeness_status"] == "partially_complete"
