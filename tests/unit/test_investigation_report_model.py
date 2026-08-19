from sqlalchemy import CheckConstraint, Enum
from sqlalchemy.dialects.postgresql import JSONB

from apps.metadata_service.models import (
    Base,
    InvestigationReport,
    InvestigationReportStatus,
)


def test_investigation_report_table_metadata() -> None:
    table = InvestigationReport.__table__

    assert table.name == "investigation_reports"
    assert (
        Base.metadata.tables["investigation_reports"]
        is table
    )

    assert set(table.columns.keys()) == {
        "id",
        "job_id",
        "incident_id",
        "root_cause",
        "supporting_evidence",
        "recommended_actions",
        "verification_steps",
        "confidence",
        "citation_ids",
        "status",
        "reviewed_by",
        "reviewer_feedback",
        "reviewed_at",
        "created_at",
        "updated_at",
    }

    assert table.c.id.primary_key
    assert not table.c.job_id.nullable
    assert table.c.job_id.unique
    assert not table.c.incident_id.nullable
    assert not table.c.root_cause.nullable
    assert table.c.reviewed_by.nullable
    assert table.c.reviewer_feedback.nullable
    assert table.c.reviewed_at.nullable

    foreign_key = next(
        iter(table.c.job_id.foreign_keys)
    )

    assert foreign_key.target_fullname == "jobs.id"
    assert foreign_key.ondelete == "CASCADE"

    assert isinstance(
        table.c.supporting_evidence.type,
        JSONB,
    )
    assert isinstance(
        table.c.recommended_actions.type,
        JSONB,
    )
    assert isinstance(
        table.c.verification_steps.type,
        JSONB,
    )
    assert isinstance(
        table.c.citation_ids.type,
        JSONB,
    )

    status_type = table.c.status.type

    assert isinstance(status_type, Enum)
    assert set(status_type.enums) == {
        "pending_review",
        "approved",
        "rejected",
    }

    assert table.c.status.default is not None
    assert (
        table.c.status.default.arg
        == InvestigationReportStatus.PENDING_REVIEW
    )
    assert table.c.status.server_default is not None

    confidence_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert len(confidence_constraints) == 1
    assert (
        confidence_constraints[0].name
        == "ck_investigation_reports_confidence_range"
    )