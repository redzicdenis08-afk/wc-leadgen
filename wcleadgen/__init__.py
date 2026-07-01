"""wcleadgen — reference pipeline for workers'-comp premium-audit lead-gen.

Score leads, gate them through a fail-closed compliance engine, and route
qualified consults to partner audit firms — pure standard library, fully
explainable, every decision auditable.
"""
from .compliance import SuppressionList, check_compliance
from .models import (
    AuditEvent,
    ComplianceCheck,
    ComplianceResult,
    Lead,
    Partner,
    PipelineResult,
    RoutingResult,
    ScoreFactor,
    ScoreResult,
)
from .pipeline import run_batch, run_pipeline
from .routing import route_lead
from .scoring import score_lead

__version__ = "0.1.0"

__all__ = [
    "AuditEvent",
    "ComplianceCheck",
    "ComplianceResult",
    "Lead",
    "Partner",
    "PipelineResult",
    "RoutingResult",
    "ScoreFactor",
    "ScoreResult",
    "SuppressionList",
    "check_compliance",
    "route_lead",
    "run_batch",
    "run_pipeline",
    "score_lead",
    "__version__",
]
