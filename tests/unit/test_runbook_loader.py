from pathlib import Path

import pytest

from apps.metadata_service.services.runbook_loader import (
    load_runbook,
    load_runbooks,
)


def test_load_runbooks_returns_all_sections() -> None:
    sections = load_runbooks()

    assert len(sections) == 25

    assert {section.runbook_id for section in sections} == {
        "RB-CACHE-001",
        "RB-DB-001",
        "RB-KAFKA-001",
        "RB-MEMORY-001",
        "RB-TLS-001",
    }

    assert {
        section.citation_id
        for section in sections
    } >= {
        "RB-DB-001#signals",
        "RB-DB-001#diagnosis",
        "RB-DB-001#remediation",
        "RB-KAFKA-001#signals",
        "RB-KAFKA-001#diagnosis",
        "RB-KAFKA-001#remediation",
    }


def test_load_runbook_preserves_section_content() -> None:
    sections = load_runbooks()

    diagnosis = next(
        section
        for section in sections
        if section.citation_id == "RB-DB-001#diagnosis"
    )

    assert diagnosis.section_title == "Diagnosis"
    assert diagnosis.source_file == (
        "database_connection_pool.md"
    )
    assert "database health check succeeds" in (
        diagnosis.content
    )


def test_load_runbook_rejects_invalid_heading(
    tmp_path: Path,
) -> None:
    runbook_path = tmp_path / "invalid.md"
    runbook_path.write_text(
        "# Invalid heading\n\n"
        "## Signals\n\n"
        "Example signal.",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="invalid heading",
    ):
        load_runbook(runbook_path)


def test_load_runbook_rejects_empty_section(
    tmp_path: Path,
) -> None:
    runbook_path = tmp_path / "empty_section.md"
    runbook_path.write_text(
        "# RB-TEST-001: Test Runbook\n\n"
        "## Signals\n\n"
        "## Diagnosis\n\n"
        "Example diagnosis.",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="section is empty",
    ):
        load_runbook(runbook_path)
