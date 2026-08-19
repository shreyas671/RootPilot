from sqlalchemy import Enum

from apps.metadata_service.models import (
    Base,
    InvestigationReviewEvent,
)


def test_investigation_review_event_table_metadata() -> None:
    table = InvestigationReviewEvent.__table__

    assert table.name == "investigation_review_events"
    assert (
        Base.metadata.tables[
            "investigation_review_events"
        ]
        is table
    )
    assert set(table.columns.keys()) == {
        "id",
        "report_id",
        "previous_status",
        "new_status",
        "reviewed_by",
        "reviewer_feedback",
        "created_at",
    }
    assert table.c.id.primary_key
    assert not table.c.report_id.nullable
    assert not table.c.reviewed_by.nullable
    assert table.c.reviewer_feedback.nullable

    foreign_key = next(
        iter(table.c.report_id.foreign_keys)
    )

    assert (
        foreign_key.target_fullname
        == "investigation_reports.id"
    )
    assert foreign_key.ondelete == "CASCADE"

    for column_name in (
        "previous_status",
        "new_status",
    ):
        status_type = table.c[column_name].type

        assert isinstance(status_type, Enum)
        assert set(status_type.enums) == {
            "pending_review",
            "approved",
            "rejected",
        }
