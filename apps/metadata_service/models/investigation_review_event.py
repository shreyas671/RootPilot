from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.metadata_service.models.base import Base
from apps.metadata_service.models.investigation_report import (
    InvestigationReportStatus,
    investigation_report_status_values,
)


class InvestigationReviewEvent(Base):
    __tablename__ = "investigation_review_events"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "investigation_reports.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[
        InvestigationReportStatus
    ] = mapped_column(
        Enum(
            InvestigationReportStatus,
            name="investigation_report_status",
            values_callable=(
                investigation_report_status_values
            ),
        ),
        nullable=False,
    )
    new_status: Mapped[
        InvestigationReportStatus
    ] = mapped_column(
        Enum(
            InvestigationReportStatus,
            name="investigation_report_status",
            values_callable=(
                investigation_report_status_values
            ),
        ),
        nullable=False,
    )
    reviewed_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    reviewer_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
