"""Validated data contracts shared by document processing and the API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


EXPECTED_FIELD_IDS = (
    "production_nominal_energy",
    "production_nominal_voltage",
    "continuous_discharge_current",
    "maximum_charge_current",
    "usable_soc_window",
    "operating_temperature",
    "storage_temperature",
    "maximum_cell_temperature_during_operation",
    "maximum_cell_to_cell_temperature_spread",
    "module_mass",
    "enclosure_ingress_protection",
    "minimum_isolation_resistance",
    "vibration_validation_profile",
    "cycle_life_acceptance_criterion",
    "known_issue_soc_indication_lag",
)


class ExtractedPage(BaseModel):
    """Text extracted from a PDF page with its best-known section heading."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    section_heading: str | None = None
    text: str


class SourceSection(BaseModel):
    """A document section cited as evidence for an extracted field."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str


class ExtractedField(BaseModel):
    """One requested value and the context needed to interpret and trace it."""

    model_config = ConfigDict(extra="forbid")

    field_id: str
    field_name: str
    value: Any
    unit: str | None = None
    qualifier: str | None = None
    conditions: list[str] = Field(default_factory=list)
    source_section: SourceSection | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty: str | None = None


class AnalysisContent(BaseModel):
    """The field extractions and concise document-level summary."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ExtractedField] = Field(min_length=len(EXPECTED_FIELD_IDS), max_length=len(EXPECTED_FIELD_IDS))
    summary: str

    @model_validator(mode="after")
    def validate_requested_fields(self) -> "AnalysisContent":
        """Require one result for each requested field, with no duplicates."""
        actual = [item.field_id for item in self.fields]
        if len(actual) != len(EXPECTED_FIELD_IDS) or set(actual) != set(EXPECTED_FIELD_IDS):
            missing = sorted(set(EXPECTED_FIELD_IDS) - set(actual))
            unexpected = sorted(set(actual) - set(EXPECTED_FIELD_IDS))
            duplicates = sorted({field_id for field_id in actual if actual.count(field_id) > 1})
            raise ValueError(
                "Analysis must contain each requested field exactly once "
                f"(missing={missing}, unexpected={unexpected}, duplicates={duplicates})."
            )
        return self


def model_output_json_schema() -> dict[str, Any]:
    """Return the model's JSON schema with the fixed evaluation field IDs."""
    schema = ModelAnalysis.model_json_schema()
    analysis_schema = schema["$defs"]["AnalysisContent"]
    field_schema = schema["$defs"]["ExtractedField"]
    analysis_schema["properties"]["fields"]["minItems"] = len(EXPECTED_FIELD_IDS)
    analysis_schema["properties"]["fields"]["maxItems"] = len(EXPECTED_FIELD_IDS)
    field_schema["properties"]["field_id"]["enum"] = list(EXPECTED_FIELD_IDS)
    return schema


class ModelAnalysis(BaseModel):
    """Document metadata and analysis returned by the local model."""

    model_config = ConfigDict(extra="forbid")

    document_title: str
    document_revision: str | None = None
    configuration_scope: str | None = None
    analysis: AnalysisContent


class AnalysisResponse(BaseModel):
    """Validated API result and references to its saved run artifacts."""

    document_id: str
    document_title: str
    document_revision: str | None = None
    configuration_scope: str | None = None
    analysis: AnalysisContent
    latency_seconds: float = Field(ge=0.0)
    model_latency_seconds: float = Field(ge=0.0)
    run_id: str
    raw_output_file: str
    validated_output_file: str
