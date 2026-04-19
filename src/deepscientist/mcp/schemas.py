from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricEntryPayload(BaseModel):
    """Per-metric entry inside `metric_contract.metrics`."""

    model_config = ConfigDict(extra="allow")

    metric_id: str = Field(
        ...,
        description="Canonical paper-facing metric id, e.g. `accuracy`, `f1`, `rouge_l`.",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable definition of what the metric measures. Required for the baseline gate.",
    )
    derivation: str | None = Field(
        default=None,
        description=(
            "How the metric is derived (formula, aggregation, or processing steps). "
            "Required unless `origin_path` is provided."
        ),
    )
    origin_path: str | None = Field(
        default=None,
        description=(
            "Dot- or slash-delimited path into `metrics_summary` where the canonical numeric value lives. "
            "Accepted in place of `derivation`."
        ),
    )
    source_ref: str | None = Field(
        default=None,
        description=(
            "Canonical source reference (paper section, leaderboard URL, repo path, or commit ref). "
            "Required for the baseline gate."
        ),
    )
    direction: str | None = Field(
        default=None,
        description="`higher_is_better` or `lower_is_better`.",
    )
    label: str | None = Field(default=None, description="Display label; defaults to `metric_id`.")
    unit: str | None = Field(default=None, description="Unit, e.g. `%` or `ms`.")
    decimals: int | None = Field(default=None, description="Preferred decimal places for display.")
    chart_group: str | None = Field(default=None, description="Optional chart grouping key.")
    required: bool | None = Field(
        default=None,
        description="Whether downstream experiments must cover this metric. Defaults to true.",
    )


class PrimaryMetricPayload(BaseModel):
    """Headline gate / scoreboard metric."""

    model_config = ConfigDict(extra="allow")

    metric_id: str = Field(
        ...,
        description="Metric id; must match one of the entries in `metric_contract.metrics`.",
    )
    value: float | None = Field(default=None, description="Numeric baseline value for the headline metric.")
    direction: str | None = Field(default=None, description="`higher_is_better` or `lower_is_better`.")


class MetricContractPayload(BaseModel):
    """Canonical comparison contract submitted with `confirm_baseline`."""

    model_config = ConfigDict(extra="allow")

    primary_metric_id: str | None = Field(
        default=None,
        description="Id of the headline metric; must match one of the entries in `metrics`.",
    )
    contract_id: str | None = Field(
        default=None,
        description="Stable contract identifier; defaults to the baseline id.",
    )
    metrics: list[MetricEntryPayload] = Field(
        default_factory=list,
        description=(
            "Per-metric entries with `description`, `derivation` or `origin_path`, and `source_ref`. "
            "Descriptions nested inside `metrics_summary`, `primary_metric`, or "
            "`json/metric_contract.json` are not honored."
        ),
    )
    evaluation_protocol: dict[str, Any] | None = Field(
        default=None,
        description="Optional canonical evaluation protocol (scope_id, code_paths, code_hashes, ...).",
    )
