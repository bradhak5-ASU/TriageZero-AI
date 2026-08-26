"""Human-reviewed resolution input.

Closed schema, same as every other request model: a reviewer supplies
conclusions, not free-form structure.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.ai.schemas import Classification, ReleaseRisk, Severity


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, populate_by_name=True
    )

    classification: Classification
    severity: Severity
    release_risk: ReleaseRisk
    resolution_summary: str = Field(min_length=1, max_length=2000)
    responsible_component: str = Field(default="", max_length=120)
    resolver: str = Field(default="local-operator", max_length=120)
