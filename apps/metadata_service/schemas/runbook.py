from pydantic import BaseModel, ConfigDict, Field


class RunbookSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runbook_id: str = Field(
        pattern=r"^RB-[A-Z]+-\d{3}$",
    )
    runbook_title: str = Field(min_length=1)
    section_title: str = Field(min_length=1)
    citation_id: str = Field(
        pattern=r"^RB-[A-Z]+-\d{3}#[a-z0-9-]+$",
    )
    content: str = Field(min_length=1)
    source_file: str = Field(min_length=1)