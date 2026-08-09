import re
from pathlib import Path

from apps.metadata_service.schemas.runbook import RunbookSection


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNBOOK_DIRECTORY = PROJECT_ROOT / "data" / "runbooks"

RUNBOOK_HEADING_PATTERN = re.compile(
    r"^# (?P<runbook_id>RB-[A-Z]+-\d{3}): "
    r"(?P<title>.+)$"
)
SECTION_HEADING_PATTERN = re.compile(
    r"^## (?P<title>.+)$"
)


def slugify_heading(heading: str) -> str:
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        heading.lower(),
    ).strip("-")

    if not slug:
        raise ValueError(
            f"Unable to create slug from heading: {heading}"
        )

    return slug


def load_runbook(path: Path) -> list[RunbookSection]:
    path = Path(path)
    text = path.read_text(encoding="utf-8").strip()

    if not text:
        raise ValueError(f"Runbook is empty: {path}")

    lines = text.splitlines()

    heading_match = RUNBOOK_HEADING_PATTERN.fullmatch(
        lines[0].strip()
    )

    if heading_match is None:
        raise ValueError(
            f"Runbook has an invalid heading: {path}"
        )

    runbook_id = heading_match.group("runbook_id")
    runbook_title = heading_match.group("title").strip()

    section_headings: list[tuple[int, str]] = []

    for line_number, line in enumerate(lines[1:], start=1):
        section_match = SECTION_HEADING_PATTERN.fullmatch(
            line.strip()
        )

        if section_match is not None:
            section_headings.append(
                (
                    line_number,
                    section_match.group("title").strip(),
                )
            )

    if not section_headings:
        raise ValueError(
            f"Runbook contains no sections: {path}"
        )

    sections: list[RunbookSection] = []
    citation_ids: set[str] = set()

    for position, (
        line_number,
        section_title,
    ) in enumerate(section_headings):
        if position + 1 < len(section_headings):
            next_line_number = section_headings[
                position + 1
            ][0]
        else:
            next_line_number = len(lines)

        content = "\n".join(
            lines[line_number + 1 : next_line_number]
        ).strip()

        citation_id = (
            f"{runbook_id}#{slugify_heading(section_title)}"
        )

        if not content:
            raise ValueError(
                f"Runbook section is empty: {citation_id}"
            )

        if citation_id in citation_ids:
            raise ValueError(
                f"Duplicate runbook citation: {citation_id}"
            )

        citation_ids.add(citation_id)

        sections.append(
            RunbookSection(
                runbook_id=runbook_id,
                runbook_title=runbook_title,
                section_title=section_title,
                citation_id=citation_id,
                content=content,
                source_file=path.name,
            )
        )

    return sections


def load_runbooks(
    directory: Path = DEFAULT_RUNBOOK_DIRECTORY,
) -> list[RunbookSection]:
    directory = Path(directory)
    runbook_paths = sorted(directory.glob("*.md"))

    if not runbook_paths:
        raise FileNotFoundError(
            f"No runbook Markdown files found in: {directory}"
        )

    sections: list[RunbookSection] = []
    runbook_ids: set[str] = set()

    for runbook_path in runbook_paths:
        runbook_sections = load_runbook(runbook_path)
        runbook_id = runbook_sections[0].runbook_id

        if runbook_id in runbook_ids:
            raise ValueError(
                f"Duplicate runbook ID: {runbook_id}"
            )

        runbook_ids.add(runbook_id)
        sections.extend(runbook_sections)

    return sections