from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.metadata_service.models.base import Base


class InvestigationReportStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


def investigation_report_status_values(
    enum_class: type[InvestigationReportStatus],
) -> list[str]:
    return [status.value for status in enum_class]


class InvestigationReport(Base):
    __tablename__ = "investigation_reports"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )
    incident_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    root_cause: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    supporting_evidence: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    recommended_actions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    verification_steps: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    citation_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[InvestigationReportStatus] = mapped_column(
        Enum(
            InvestigationReportStatus,
            name="investigation_report_status",
            values_callable=(
                investigation_report_status_values
            ),
        ),
        default=(
            InvestigationReportStatus.PENDING_REVIEW
        ),
        server_default=(
            InvestigationReportStatus.PENDING_REVIEW.value
        ),
        nullable=False,
        index=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    reviewer_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )