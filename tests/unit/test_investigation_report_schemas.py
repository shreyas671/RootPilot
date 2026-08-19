from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.metadata_service.models.investigation_report import (
    InvestigationReportStatus,
)
from apps.metadata_service.schemas.assessment import (
    IncidentAssessment,
)
from apps.metadata_service.schemas.investigation_report import (
    InvestigationReportCreate,
    InvestigationReportResponse,
    InvestigationReportReview,
    InvestigationReviewEventResponse,
)


def build_assessment() -> IncidentAssessment:
    return IncidentAssessment(
        incident_id="INC-DB-001",
        root_cause="Database connection exhaustion",
        supporting_evidence=[
            "Connection usage reached the configured limit",
        ],
        recommended_actions=[
            "Reduce idle database connections",
        ],
        verification_steps=[
            "Verify connection usage returns to normal",
        ],
        confidence=0.92,
        citation_ids=[
            "RB-DB-001#connection-exhaustion",
        ],
    )


def test_investigation_report_create() -> None:
    job_id = uuid4()
    assessment = build_assessment()

    report = InvestigationReportCreate(
        job_id=job_id,
        assessment=assessment,
    )

    assert report.job_id == job_id
    assert report.assessment == assessment


def test_review_allows_approval_without_feedback() -> None:
    review = InvestigationReportReview(
        status=InvestigationReportStatus.APPROVED,
        reviewed_by="  operator@example.com  ",
    )

    assert (
        review.status
        is InvestigationReportStatus.APPROVED
    )
    assert review.reviewed_by == "operator@example.com"
    assert review.reviewer_feedback is None


def test_review_allows_rejection_with_feedback() -> None:
    review = InvestigationReportReview(
        status=InvestigationReportStatus.REJECTED,
        reviewed_by="operator@example.com",
        reviewer_feedback="Evidence is insufficient.",
    )

    assert (
        review.status
        is InvestigationReportStatus.REJECTED
    )
    assert review.reviewer_feedback == (
        "Evidence is insufficient."
    )


def test_review_rejects_pending_status() -> None:
    with pytest.raises(
        ValidationError,
        match="review status must be approved or rejected",
    ):
        InvestigationReportReview(
            status=(
                InvestigationReportStatus.PENDING_REVIEW
            ),
            reviewed_by="operator@example.com",
        )


def test_rejection_requires_feedback() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            "reviewer_feedback is required when "
            "rejecting a report"
        ),
    ):
        InvestigationReportReview(
            status=InvestigationReportStatus.REJECTED,
            reviewed_by="operator@example.com",
        )


def test_report_response_reads_model_attributes() -> None:
    assessment = build_assessment()
    now = datetime.now(UTC)

    record = SimpleNamespace(
        id=uuid4(),
        job_id=uuid4(),
        incident_id=assessment.incident_id,
        root_cause=assessment.root_cause,
        supporting_evidence=(
            assessment.supporting_evidence
        ),
        recommended_actions=(
            assessment.recommended_actions
        ),
        verification_steps=(
            assessment.verification_steps
        ),
        confidence=assessment.confidence,
        citation_ids=assessment.citation_ids,
        embedding_model="embedding-test",
        analysis_model="analysis-test",
        prompt_version="incident-analyst-v1",
        retrieval_backend="postgres",
        retrieval_limit=3,
        minimum_relevance_score=0.2,
        retrieved_sections=[],
        status=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        reviewed_by=None,
        reviewer_feedback=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )

    response = InvestigationReportResponse.model_validate(
        record
    )

    assert response.incident_id == "INC-DB-001"
    assert response.status is (
        InvestigationReportStatus.PENDING_REVIEW
    )
    assert response.citation_ids == [
        "RB-DB-001#connection-exhaustion"
    ]


def test_review_event_response_reads_model_attributes() -> None:
    event_id = uuid4()
    report_id = uuid4()
    now = datetime.now(UTC)
    record = SimpleNamespace(
        id=event_id,
        report_id=report_id,
        previous_status=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        new_status=InvestigationReportStatus.APPROVED,
        reviewed_by="operator@example.com",
        reviewer_feedback=None,
        created_at=now,
    )

    response = (
        InvestigationReviewEventResponse.model_validate(
            record
        )
    )

    assert response.id == event_id
    assert response.report_id == report_id
    assert response.previous_status is (
        InvestigationReportStatus.PENDING_REVIEW
    )
    assert response.new_status is (
        InvestigationReportStatus.APPROVED
    )
