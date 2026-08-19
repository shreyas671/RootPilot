# RootPilot

RootPilot is an in-progress, evidence-grounded incident investigation backend. It is being built to turn structured production evidence—symptoms, metrics, logs, and recent changes—into a reviewable root-cause analysis supported by operational runbook citations.

The project currently implements the pre-evaluation MVP workflow:

- A FastAPI metadata service with job and investigation-report APIs
- A PostgreSQL-backed job, report, and review lifecycle
- Strictly validated incident evidence loaded from JSON
- Markdown runbook loading and deterministic section-level chunking
- OpenAI embeddings behind a replaceable provider interface
- In-memory semantic retrieval using cosine similarity
- Stable citation identifiers for every retrieved runbook section
- A typed LangGraph investigation workflow with a low-relevance guard
- Structured OpenAI root-cause generation through the Responses API
- Citation validation that rejects unsupported model output
- A CLI path that can persist a validated assessment against a pending job
- A deterministic unit-test suite that does not call live OpenAI or PostgreSQL services

RootPilot now reaches the evaluation handoff: the complete retrieval, generation, validation, persistence, and basic review path exists. Retrieval/LLM evaluation datasets, an audit-event history, automated PostgreSQL integration tests, and production delivery capabilities remain future work. This README separates implemented behavior from planned behavior so that it remains an accurate learning guide.

## Table of contents

- [What RootPilot is trying to solve](#what-rootpilot-is-trying-to-solve)
- [Current project status](#current-project-status)
- [Technology stack](#technology-stack)
- [Core concepts](#core-concepts)
- [Architecture overview](#architecture-overview)
- [Detailed component architecture](#detailed-component-architecture)
- [Current execution flows](#current-execution-flows)
- [Data contracts](#data-contracts)
- [Runbook chunking and citations](#runbook-chunking-and-citations)
- [Semantic retrieval in detail](#semantic-retrieval-in-detail)
- [Job lifecycle and API](#job-lifecycle-and-api)
- [Repository structure](#repository-structure)
- [Local setup](#local-setup)
- [Running the application](#running-the-application)
- [Running semantic retrieval](#running-semantic-retrieval)
- [Running grounded investigations](#running-grounded-investigations)
- [Troubleshooting](#troubleshooting)
- [Testing strategy](#testing-strategy)
- [Important design decisions](#important-design-decisions)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Suggested learning path](#suggested-learning-path)
- [Architecture invariants](#architecture-invariants)
- [Glossary](#glossary)

## What RootPilot is trying to solve

Production incidents produce a large amount of fragmented evidence:

- Alerts describe symptoms but not causes.
- Metrics show that something changed but rarely explain why.
- Logs contain useful clues mixed with noise.
- Recent deployments may be related or coincidental.
- Runbooks contain operational knowledge, but responders must find the relevant section quickly.

RootPilot’s intended workflow is:

1. Receive a structured incident containing observable evidence.
2. Validate that evidence before it enters the investigation pipeline.
3. Search operational runbooks for the most relevant sections.
4. Give the incident and retrieved evidence to a controlled investigation graph.
5. Generate a structured root-cause assessment containing citations.
6. Persist that assessment as pending human review.
7. Allow an operator to approve or reject the assessment.

The goal is not to let an AI system make unreviewed production changes. The goal is to reduce investigation time while keeping the result grounded, traceable, and reviewable.

## Current project status

The following table describes the repository as it exists today.

| Capability | Status | Notes |
|---|---|---|
| FastAPI service | Implemented | Health, readiness, job, report retrieval, and report review endpoints exist. |
| PostgreSQL integration | Implemented | Async SQLAlchemy, asyncpg, Docker Compose, and Alembic are configured. |
| Job lifecycle | Implemented | Supports `pending → processing → completed/failed`. |
| Incident evidence models | Implemented | Pydantic validates nested JSON evidence and rejects unknown fields. |
| Incident fixtures and loader | Implemented | Two prepared incident scenarios are included. |
| Runbook loader | Implemented | Markdown is split structurally at level-two headings. |
| Stable citations | Implemented | Every runbook section receives a deterministic citation ID. |
| Embedding abstraction | Implemented | Retrieval depends on an `EmbeddingProvider` protocol. |
| OpenAI embedding adapter | Implemented | Uses the asynchronous OpenAI embeddings API. |
| Similarity search | Implemented | Brute-force, in-memory cosine similarity with top-K ranking. |
| Vector database | Not implemented | Vectors are not persisted and no ANN index is used. |
| LangGraph investigation | Implemented | Retrieval, structured generation, citation validation, and low-relevance rejection are connected. |
| LLM root-cause generation | Implemented | The OpenAI Responses API returns a validated `IncidentAssessment`. |
| Persisted investigation report | Implemented | One report per job stores RCA fields, confidence, citations, and review state. |
| Human approval/rejection | Implemented (basic) | Pending reports can be approved or rejected once with reviewer identity and feedback. |
| RAG and LLM evaluation | Not implemented | Deterministic retrieval unit tests exist, but no evaluation suite yet. |
| End-to-end integration tests | Not implemented | Current API database tests use fake sessions. |
| Authentication and authorization | Deferred | Outside the reduced MVP. |
| Worker queue and Redis | Deferred | Outside the reduced MVP. |
| User interface | Deferred | The current interfaces are HTTP and CLI. |

### What “RAG” means for the current repository

RAG stands for **retrieval-augmented generation**. It has two major halves:

1. **Retrieval:** find relevant source material.
2. **Generation:** ask a model to create an answer grounded in that material.

RootPilot implements both halves. It embeds an incident, ranks runbook chunks, removes results below the configured relevance threshold, and sends the surviving evidence to a structured analyst. The returned assessment is accepted only if its incident ID matches and every citation came from the retrieved context.

## Technology stack

| Technology | Role in RootPilot |
|---|---|
| Python 3.12+ | Application language and type system. |
| FastAPI | Async HTTP API, request validation integration, and OpenAPI documentation. |
| Pydantic | Runtime validation and serialization of jobs, incidents, chunks, assessments, reports, and review requests. |
| pydantic-settings | Typed loading of PostgreSQL and OpenAI configuration. |
| SQLAlchemy 2 | Async object-relational mapping and transaction handling. |
| asyncpg | Async PostgreSQL driver used by SQLAlchemy. |
| PostgreSQL 18 | Durable job, investigation-report, and review-state storage. |
| Alembic | Version-controlled database schema migrations. |
| OpenAI Python SDK | Asynchronous access to embeddings and structured Responses API output. |
| `text-embedding-3-small` | Default model used to vectorize incident and runbook text. |
| `gpt-5.6-sol` | Default structured incident-analysis model. |
| LangGraph | Typed retrieval, analysis, and validation orchestration. |
| pytest | Unit-test framework. |
| AnyIO pytest plugin | Executes async tests using the asyncio backend. |
| uv | Python version, virtual environment, dependency, lockfile, and command management. |
| Docker Compose | Runs PostgreSQL for local development. |

## Core concepts

### Incident evidence

An incident is represented as structured JSON instead of an unstructured prompt. It contains:

- Identity: incident ID, title, service, and start time
- A concise summary
- Human-readable symptoms
- Named metrics with numeric values and units
- Timestamped log records
- Timestamped recent changes

This structure lets validation happen before retrieval or analysis begins.

### Runbook

A runbook is an operational Markdown document describing signals, diagnosis steps, likely causes, remediation, and verification procedures for a known class of incident.

### Chunk

Embedding an entire long runbook as one document makes retrieval imprecise. RootPilot therefore divides each runbook into meaningful sections. Each `##` section becomes one chunk.

### Citation

A citation is a stable identifier pointing to one runbook section, for example:

```text
RB-DB-001#diagnosis
```

The part before `#` identifies the runbook. The slug after `#` identifies the section. Generated RCA output uses these IDs to show which operational source supports a claim.

### Embedding

An embedding is a list of floating-point numbers representing the semantic meaning of a piece of text. Texts with related meanings usually receive vectors that point in similar directions.

### Cosine similarity

Cosine similarity measures the angle between two vectors. RootPilot uses it to compare the incident embedding with each runbook-section embedding.

### Job

A job is a persisted lifecycle record. It tracks an input path, current status, error information, and timestamps. The persisted CLI claims a pending job, closes that transaction, performs network work, then opens a new short transaction to store a report and complete the job. Failures similarly use a short transaction to mark the job failed.

## Architecture overview

There are three connected runtime surfaces:

1. The **metadata API**, which creates jobs and reads or reviews reports.
2. The **retrieval CLI**, which demonstrates semantic runbook search without persistence.
3. The **investigation CLI**, which can run ephemerally or claim a pending job and persist the validated assessment.

```mermaid
flowchart TD
    subgraph Interfaces[Interfaces]
        HTTP[HTTP client]
        RCLI[Retrieval CLI]
        ICLI[Investigation CLI]
    end

    subgraph Metadata[Metadata and review API]
        API[FastAPI application]
        JOBAPI[Job routes]
        REPORTAPI[Report and review routes]
        ORM[SQLAlchemy job and report models]
        DB[(PostgreSQL)]
        MIG[Alembic migrations]
    end

    subgraph Evidence[Evidence and retrieval]
        IFIX[(Incident JSON files)]
        RFILES[(Runbook Markdown files)]
        ILOAD[Incident loader]
        RLOAD[Runbook chunker]
        TEXT[Retrieval text builders]
        EMBED[OpenAI embedding provider]
        MEMORY[(In-memory section vectors)]
        COS[Cosine top-K plus minimum score]
    end

    subgraph Investigation[Grounded investigation]
        GRAPH[LangGraph]
        ANALYST[Structured OpenAI analyst]
        VALIDATE[Incident ID and citation validation]
        EXEC[Execution coordinator]
        REPORT[Pending-review report]
    end

    HTTP --> API
    API --> JOBAPI
    API --> REPORTAPI
    JOBAPI --> ORM
    REPORTAPI --> ORM
    ORM --> DB
    MIG --> DB

    RCLI --> ILOAD
    RCLI --> RLOAD
    ICLI --> ILOAD
    ICLI --> RLOAD
    IFIX --> ILOAD
    RFILES --> RLOAD
    ILOAD --> TEXT
    RLOAD --> TEXT
    TEXT --> EMBED
    EMBED --> MEMORY
    MEMORY --> COS
    COS --> GRAPH
    GRAPH --> ANALYST
    ANALYST --> VALIDATE
    VALIDATE --> EXEC
    ICLI --> EXEC
    EXEC --> REPORT
    REPORT --> ORM
```

### Persisted execution boundary

The most important runtime boundary is the absence of a long-lived database transaction around model calls:

```mermaid
sequenceDiagram
    participant CLI as Investigation CLI
    participant DB as PostgreSQL
    participant G as LangGraph
    participant OAI as OpenAI

    CLI->>DB: Lock pending job; mark processing; commit
    Note over CLI,DB: Database session closes
    CLI->>G: Run investigation
    G->>OAI: Embed runbooks and incident
    OAI-->>G: Vectors
    G->>OAI: Generate structured assessment
    OAI-->>G: IncidentAssessment
    G->>G: Validate incident ID and citations
    alt success
        CLI->>DB: Lock processing job; insert report; mark completed; commit
    else graph or validation failure
        CLI->>DB: Lock processing job; mark failed; commit
    end
```

## Detailed component architecture

### 1. Interface layer

| Component | Location | Responsibility |
|---|---|---|
| FastAPI application | `apps/metadata_service/main.py` | Creates the HTTP application, registers routes, and exposes health/readiness checks. |
| Job router | `apps/metadata_service/api/jobs.py` | Creates jobs, retrieves jobs, and enforces job status transitions. |
| Report router | `apps/metadata_service/api/investigation_reports.py` | Retrieves reports and applies one-time approve/reject decisions. |
| Retrieval command | `apps/metadata_service/commands/retrieve_runbooks.py` | Wires configuration, loaders, OpenAI embeddings, and the retriever into a runnable CLI. |
| Investigation command | `apps/metadata_service/commands/investigate_incident.py` | Composes retrieval, LangGraph, structured analysis, optional job execution, and report persistence. |

The interface layer performs wiring and transport work. Retrieval mathematics and file parsing remain in service modules so they can be tested independently.

### 2. Schema and validation layer

| Component | Location | Responsibility |
|---|---|---|
| Job schemas | `schemas/job.py` | Validate API requests and serialize ORM jobs. |
| Incident schemas | `schemas/incident.py` | Validate incident identity and nested evidence. |
| Runbook schema | `schemas/runbook.py` | Represent one independently retrievable runbook section. |
| Retrieval schema | `schemas/retrieval.py` | Pair a section with a bounded similarity score. |
| Assessment schema | `schemas/assessment.py` | Validate the generated RCA, confidence, action lists, and citations. |
| Investigation state | `schemas/investigation.py` | Define the typed state exchanged by LangGraph nodes. |
| Report schemas | `schemas/investigation_report.py` | Validate report creation, API serialization, and review decisions. |

Pydantic models form trust boundaries. Invalid or unexpected data should fail near ingestion instead of failing later inside retrieval or model prompting.

### 3. Loader and transformation layer

| Component | Location | Responsibility |
|---|---|---|
| Incident loader | `services/incident_loader.py` | Read JSON, parse it, validate it, detect duplicate incident IDs, and return typed models. |
| Runbook loader | `services/runbook_loader.py` | Parse Markdown headings, create section chunks, generate citations, and detect malformed runbooks. |
| Retrieval text builder | `services/retrieval_text.py` | Convert typed incidents and runbook sections into consistent embedding input. |
| Analysis text builder | `services/analysis_text.py` | Serialize the incident and retrieved evidence into the grounded analyst input. |

The original models are kept separate from the text sent for embedding. This makes retrieval formatting explicit and independently testable.

### 4. Embedding and retrieval layer

| Component | Location | Responsibility |
|---|---|---|
| `EmbeddingProvider` | `services/embedding.py` | Defines the asynchronous interface needed by retrieval. |
| `OpenAIEmbeddingProvider` | `services/openai_embedding.py` | Adapts the OpenAI embeddings API to the internal interface. |
| `InMemoryRunbookRetriever` | `services/retriever.py` | Builds section vectors, embeds incident queries, calculates similarity, sorts results, and returns top-K sections. |

The retriever depends on the protocol, not directly on the OpenAI implementation. Tests can therefore inject a deterministic fake embedding provider and avoid network calls, API charges, rate limits, and nondeterminism.

### 5. Investigation and grounding layer

| Component | Location | Responsibility |
|---|---|---|
| `IncidentAnalyst` | `services/analyst.py` | Defines the structured analysis capability required by the graph. |
| OpenAI analyst | `services/openai_analyst.py` | Calls the Responses API and parses output directly into `IncidentAssessment`. |
| Investigation graph | `services/investigation_graph.py` | Retrieves evidence, applies the relevance threshold, generates an assessment, and validates grounding. |
| Execution coordinator | `services/investigation_execution.py` | Claims a pending job, runs network work without an open DB session, then records success or failure. |

The graph refuses to call the analyst when no retrieved section reaches the configured minimum score. After analysis, it rejects an incident-ID mismatch and any citation that was not present in the retrieved context.

### 6. Persistence layer

| Component | Location | Responsibility |
|---|---|---|
| SQLAlchemy base | `models/base.py` | Defines shared metadata and deterministic database constraint names. |
| Job model | `models/job.py` | Maps the job lifecycle record to the `jobs` table. |
| Report model | `models/investigation_report.py` | Stores one structured assessment per job plus pending/approved/rejected review state. |
| Report service | `services/investigation_reports.py` | Performs locked lifecycle transitions, report creation, failure recording, lookup, and one-time review. |
| Database module | `database.py` | Builds the async database URL, engine, session factory, and FastAPI session dependency. |
| Alembic environment | `migrations/env.py` | Runs online or offline migrations using application metadata. |
| Migrations | `migrations/versions/` | Create job/report enums, tables, constraints, indexes, and the one-report-per-job foreign key. |

### 7. Configuration layer

`apps/metadata_service/config.py` uses `pydantic-settings` to load configuration from environment variables and `.env`. `SecretStr` prevents the API key from being casually displayed when a settings object is printed. It is display protection, not encryption or a secrets manager.

`get_settings()`, the database URL, engine, and session factory are cached. They are application-wide objects that should not be recreated on every request.

### 8. Test layer

The tests are deliberately isolated:

- API tests replace the real database dependency with a fake asynchronous session.
- Embedding tests replace the OpenAI client with an async mock.
- Retriever tests inject a deterministic keyword-based embedding provider.
- Loader tests use prepared fixtures and temporary malformed files.
- Graph and analyst tests use fake retrievers, analysts, and OpenAI responses.
- Execution tests assert that database sessions close before network work begins.
- Report tests exercise lifecycle, serialization, review, rollback, and row-lock behavior.

This allows the complete unit suite to run without PostgreSQL connectivity or OpenAI credits.

## Current execution flows

### Metadata-service request flow

```mermaid
sequenceDiagram
    participant C as HTTP client
    participant F as FastAPI
    participant P as Pydantic schema
    participant J as Job route logic
    participant S as Async SQLAlchemy session
    participant D as PostgreSQL

    C->>F: POST /jobs
    F->>P: Validate request body
    P-->>F: JobCreate
    F->>J: create_job(...)
    J->>S: add, flush, refresh
    S->>D: INSERT job
    D-->>S: Generated/default fields
    J->>P: JobResponse.model_validate(job)
    J->>S: commit
    J-->>C: 201 Created + JobResponse
```

If a SQLAlchemy operation fails, the route rolls back the transaction and returns a controlled HTTP 500 response.

### Readiness flow

`GET /ready` obtains an async database session and executes `SELECT 1`.

- Success returns HTTP 200 with `database: connected`.
- `OSError` or `SQLAlchemyError` returns HTTP 503.

`GET /health` does not contact PostgreSQL. It only confirms that the web process can answer requests.

### Runbook indexing flow

“Indexing” currently means constructing an in-memory list of embeddings. Nothing is written to PostgreSQL or a vector database.

```mermaid
sequenceDiagram
    participant CLI as Retrieval CLI
    participant RL as Runbook loader
    participant TB as Search-text builder
    participant EP as Embedding provider
    participant OAI as OpenAI embeddings API
    participant R as In-memory retriever

    CLI->>RL: load_runbooks()
    RL-->>CLI: 10 validated RunbookSection objects
    CLI->>R: InMemoryRunbookRetriever.create(...)
    loop Each section
        R->>TB: build_runbook_search_text(section)
        TB-->>R: Title + section title + content
    end
    R->>EP: embed_texts(all section texts)
    EP->>OAI: One batched embedding request
    OAI-->>EP: Indexed embedding records
    EP-->>R: Vectors restored to input order
    R->>R: Store sections and vectors in memory
```

### Incident retrieval flow

```mermaid
sequenceDiagram
    participant CLI as Retrieval CLI
    participant IL as Incident loader
    participant TB as Query-text builder
    participant EP as Embedding provider
    participant R as In-memory retriever

    CLI->>IL: load_incidents()
    IL-->>CLI: IncidentEvidence by incident ID
    CLI->>R: retrieve(incident, limit)
    R->>TB: build_incident_query(incident)
    TB-->>R: Searchable incident text
    R->>EP: embed_texts([query])
    EP-->>R: One query vector
    loop Every stored section vector
        R->>R: cosine_similarity(query, section)
    end
    R->>R: Sort by score descending
    R->>R: Break ties by citation ID
    R-->>CLI: Top-K RetrievedRunbookSection objects
```

### Grounded investigation flow

```mermaid
sequenceDiagram
    participant C as Investigation CLI
    participant R as Runbook retriever
    participant G as LangGraph
    participant A as OpenAI analyst
    participant V as Validation node

    C->>G: IncidentEvidence
    G->>R: retrieve(incident, limit)
    R-->>G: Ranked sections with scores
    G->>G: Keep scores >= minimum threshold
    alt no relevant context
        G-->>C: NoRelevantRunbookContextError
    else grounded context exists
        G->>A: Incident plus retrieved sections
        A-->>G: Parsed IncidentAssessment
        G->>V: Assessment plus retrieved context
        V->>V: Check incident ID and citation subset
        V-->>C: Validated state
    end
```

The analyst receives the incident and full retrieved-section content, including citation IDs. Structured Outputs validate the field shape; the final graph node separately validates semantic provenance by requiring every generated citation to be a subset of retrieved citations.

### Report review flow

Reports are created with `pending_review`. `PATCH /investigation-reports/{report_id}/review` locks the row and allows exactly one transition to `approved` or `rejected`. Rejection requires non-empty reviewer feedback. A second decision returns HTTP `409`.

## Data contracts

### Incident evidence

All incident-related models inherit from `EvidenceModel`, which sets:

```python
model_config = ConfigDict(extra="forbid")
```

This means an incident containing an unexpected key is rejected rather than silently accepted. It catches spelling mistakes and protects the downstream pipeline from an ambiguous schema.

#### `IncidentEvidence`

| Field | Type | Validation or meaning |
|---|---|---|
| `incident_id` | `str` | Must follow `INC-<CATEGORY>-<3 digits>`, such as `INC-DB-001`. |
| `title` | `str` | Non-empty incident title. |
| `service` | `str` | Non-empty affected-service name. |
| `started_at` | `datetime` | Parsed from an ISO 8601 timestamp. |
| `summary` | `str` | Non-empty situation summary. |
| `symptoms` | `list[str]` | At least one symptom. |
| `metrics` | `list[IncidentMetric]` | At least one numeric measurement. |
| `logs` | `list[IncidentLog]` | At least one timestamped log record. |
| `recent_changes` | `list[IncidentChange]` | Required list; it may be empty. |

Nested evidence types:

- `IncidentMetric`: name, numeric value, and unit
- `IncidentLog`: timestamp, level, and message
- `IncidentChange`: timestamp and description

### Runbook section

Each parsed Markdown section becomes a `RunbookSection`:

| Field | Meaning |
|---|---|
| `runbook_id` | Stable ID parsed from the top-level heading. |
| `runbook_title` | Human-readable title from the top-level heading. |
| `section_title` | Text from the `##` heading. |
| `citation_id` | Stable `<runbook-id>#<section-slug>` reference. |
| `content` | Markdown content underneath that section heading. |
| `source_file` | Original Markdown filename. |

### Retrieval result

`RetrievedRunbookSection` contains:

- `section`: the complete `RunbookSection`
- `score`: cosine similarity constrained to the range `[-1.0, 1.0]`

### Job record

| Field | Database type/behavior | Meaning |
|---|---|---|
| `id` | UUID primary key | Stable job identifier. |
| `input_path` | `VARCHAR(1024)` | Reference to the input artifact; currently stored but not processed. |
| `status` | PostgreSQL enum, indexed | `pending`, `processing`, `completed`, or `failed`. |
| `error_message` | Nullable text | Required by API validation only for a transition to `failed`. |
| `started_at` | Nullable timezone-aware datetime | Set when processing begins. |
| `completed_at` | Nullable timezone-aware datetime | Set on completion or failure. |
| `created_at` | Server-default timestamp | Creation time. |
| `updated_at` | Server default with SQLAlchemy `onupdate` | Updated automatically for ORM-managed updates; no database trigger currently exists. |

### Incident assessment

`IncidentAssessment` is the structured contract returned by the analyst:

| Field | Validation or meaning |
|---|---|
| `incident_id` | Must match the investigated incident. |
| `root_cause` | Non-empty diagnosis text. |
| `supporting_evidence` | At least one concrete evidence item. |
| `recommended_actions` | At least one remediation action. |
| `verification_steps` | At least one measurable verification step. |
| `confidence` | Float in `[0.0, 1.0]`. |
| `citation_ids` | Unique, valid runbook-section IDs; every value must have been retrieved. |

### Investigation report

The `investigation_reports` table stores the assessment fields directly. `job_id` is a unique foreign key, so one job can produce at most one report. The status enum is `pending_review`, `approved`, or `rejected`. Reviewer identity, feedback, and timestamp remain null until a decision is recorded. A database check constraint independently enforces the confidence range.

## Runbook chunking and citations

### Required Markdown format

A runbook must begin with exactly this kind of top-level heading:

```markdown
# RB-DB-001: Database Connection-Pool Exhaustion
```

Its chunks are defined by level-two headings:

```markdown
## Signals

Content describing observable signals.

## Diagnosis

Content describing diagnostic steps.
```

The loader rejects:

- Empty files
- Invalid top-level headings
- Runbooks with no `##` sections
- Empty sections
- Duplicate citation IDs within one runbook
- Duplicate runbook IDs across files in the loaded directory

### Why structural chunking is used

The current runbooks are intentionally organized by operational purpose. Splitting on `##` headings preserves that meaning:

- A “Signals” result tells the investigator why the runbook matched.
- A “Diagnosis” result supplies confirmation steps.
- A “Remediation” result supplies recovery actions.
- A “Verification” result supplies success criteria.

Fixed-size token windows would be useful for large, irregular documents, but they could split a procedure in the middle. Structural chunks are simpler and more interpretable for the current curated corpus.

### Citation generation

The loader lowercases a section title, replaces non-alphanumeric sequences with hyphens, and removes leading/trailing hyphens.

Examples:

| Runbook ID | Section heading | Citation ID |
|---|---|---|
| `RB-DB-001` | `Signals` | `RB-DB-001#signals` |
| `RB-DB-001` | `Likely causes` | `RB-DB-001#likely-causes` |
| `RB-KAFKA-001` | `Verification` | `RB-KAFKA-001#verification` |

The ID is deterministic: the same runbook ID and heading produce the same citation every time. It is not immutable—renaming a section heading changes its generated citation ID.

### Included corpus

The repository currently contains two runbooks, each with five sections:

- `RB-DB-001`: database connection-pool exhaustion
- `RB-KAFKA-001`: Kafka consumer lag and poison events

Together they produce ten retrievable chunks.

## Semantic retrieval in detail

### Step 1: Build searchable text

Raw objects are converted into deliberate text representations before embedding.

For an incident, `build_incident_query()` includes:

- Title
- Service
- Summary
- Symptoms
- Metric names, values, and units
- Log levels and messages
- Recent-change descriptions when present

For a runbook chunk, `build_runbook_search_text()` includes:

- Runbook title
- Section title
- Section content

Metadata such as the source filename and citation ID is kept on the object but is not currently embedded.

### Step 2: Generate embeddings

The internal contract is intentionally small:

```python
class EmbeddingProvider(Protocol):
    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...
```

Any object with this asynchronous method can be used by the retriever. `OpenAIEmbeddingProvider` is the live OpenAI adapter currently included.

It sends:

```python
await client.embeddings.create(
    model=model_name,
    input=texts,
    encoding_format="float",
)
```

The adapter sorts returned records by their `index` and verifies that every expected index exists. This protects the association between input text and output vector.

### Step 3: Build the in-memory index

`InMemoryRunbookRetriever.create()`:

1. Requires at least one section.
2. Builds embedding text for every section.
3. Embeds the section texts as one batch.
4. Verifies that the provider returned exactly one vector per section.
5. Stores the section list and parallel vector list on the retriever object.

This is called an in-memory index for convenience, but it is a simple list rather than a specialized nearest-neighbor data structure.

### Step 4: Embed the incident query

`retrieve()` builds one incident query and requests exactly one query embedding. It rejects a provider response containing zero or multiple query embeddings.

### Step 5: Calculate cosine similarity

For query vector `q` and runbook vector `r`, cosine similarity is:

```text
cosine_similarity(q, r) = dot(q, r) / (length(q) × length(r))
```

Expanded:

```text
dot(q, r) = q₁r₁ + q₂r₂ + ... + qₙrₙ

length(q) = √(q₁² + q₂² + ... + qₙ²)
```

Interpretation:

- Near `1.0`: vectors point in very similar directions.
- Near `0.0`: vectors are largely unrelated in direction.
- Near `-1.0`: vectors point in opposite directions.

The function rejects empty vectors, vectors with different dimensions, and zero-length vectors. A calculated score is clamped to `[-1.0, 1.0]` to remove tiny floating-point overshoots.

### Step 6: Rank and select top-K

Every section is scored. Results are ordered by:

1. Similarity score descending
2. Citation ID ascending as a deterministic tie-breaker

The first `limit` results are returned. The default limit is three.

Conceptually:

```python
for section_vector in all_section_vectors:
    score = cosine_similarity(query_vector, section_vector)
    results.append((section, score))

results.sort(by="highest score, then citation ID")
return results[:limit]
```

### Complexity

For `N` chunks with embedding dimension `D`, one retrieval performs approximately `O(N × D)` similarity work and stores `O(N × D)` floating-point values.

This is appropriate for ten chunks. As the corpus grows, persistent vector storage becomes valuable. Sufficiently large or latency-sensitive collections may also benefit from an approximate-nearest-neighbor index, such as PostgreSQL with `pgvector` or a dedicated vector database.

### What is and is not stored

Currently stored in PostgreSQL:

- Job metadata and lifecycle timestamps
- Structured incident assessments
- Confidence and citation IDs
- Report review status, reviewer identity, feedback, and timestamps

Currently stored only in process memory:

- Runbook-section embeddings
- Incident query embedding
- Ranked retrieval results

Currently stored as repository files:

- Incident fixtures
- Runbook Markdown files

Because vectors are not persisted, starting the CLI again embeds all ten runbook chunks again before embedding the incident query.

## Job lifecycle and API

### State machine

```mermaid
stateDiagram-v2
    [*] --> pending: Create job
    pending --> processing: Start work
    processing --> completed: Work succeeds
    processing --> failed: Work fails with error_message
    completed --> [*]
    failed --> [*]
```

No other transitions are allowed. For example:

- `pending → completed` is rejected.
- `completed → processing` is rejected.
- `failed → processing` is rejected.

Status updates retrieve the row using `SELECT ... FOR UPDATE` semantics through `with_for_update=True`. With PostgreSQL, this serializes concurrent updates to the same job row so that two requests cannot both apply transitions based on the same stale status.

The unit suite verifies that route code requests `with_for_update=True`. Actual concurrent behavior still needs to be proven by a PostgreSQL integration test.

### Endpoints

| Method | Path | Typical responses | Purpose |
|---|---|---|---|
| `GET` | `/health` | `200` | Process-level liveness check. |
| `GET` | `/ready` | `200` or `503` | Database readiness check. |
| `POST` | `/jobs` | `201` | Create a pending job. |
| `GET` | `/jobs/{job_id}` | `200` or `404` | Retrieve one job. |
| `PATCH` | `/jobs/{job_id}/status` | `200`, `404`, or `409` | Apply an allowed lifecycle transition. |
| `GET` | `/investigation-reports/{report_id}` | `200` or `404` | Retrieve a persisted assessment and review state. |
| `PATCH` | `/investigation-reports/{report_id}/review` | `200`, `404`, `409`, or `422` | Approve or reject a pending report. |

### Create a job

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"input_path":"data/incidents/database_pool_exhaustion.json"}'
```

Example response shape:

```json
{
  "id": "5fa77a07-7d39-414f-a6f1-0b3a54d21e86",
  "input_path": "data/incidents/database_pool_exhaustion.json",
  "status": "pending",
  "error_message": null,
  "started_at": null,
  "completed_at": null,
  "created_at": "2026-08-15T12:00:00Z",
  "updated_at": "2026-08-15T12:00:00Z"
}
```

The UUID and timestamps are examples; actual values are generated at runtime.

### Retrieve a job

```bash
curl http://127.0.0.1:8000/jobs/<job-id>
```

### Start processing

The persisted investigation CLI performs this transition automatically when given a pending job. It can also be performed directly through the lifecycle API:

```bash
curl -X PATCH http://127.0.0.1:8000/jobs/<job-id>/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"processing"}'
```

### Mark a job completed

```bash
curl -X PATCH http://127.0.0.1:8000/jobs/<job-id>/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"completed"}'
```

### Mark a job failed

```bash
curl -X PATCH http://127.0.0.1:8000/jobs/<job-id>/status \
  -H 'Content-Type: application/json' \
  -d '{
    "status":"failed",
    "error_message":"Investigation failed"
  }'
```

An error message is required for `failed` and forbidden for every other requested status.

### Retrieve and review a report

```bash
curl http://127.0.0.1:8000/investigation-reports/<report-id>
```

Approve a pending report:

```bash
curl -X PATCH \
  http://127.0.0.1:8000/investigation-reports/<report-id>/review \
  -H 'Content-Type: application/json' \
  -d '{
    "status":"approved",
    "reviewed_by":"operator@example.com"
  }'
```

Rejecting uses `"status":"rejected"` and requires a non-empty `reviewer_feedback`. Review decisions are terminal in the current MVP.

## Repository structure

```text
rootpilot/
├── apps/
│   └── metadata_service/
│       ├── api/
│       │   ├── investigation_reports.py # Report lookup and review endpoints
│       │   └── jobs.py                  # Job HTTP endpoints and transitions
│       ├── commands/
│       │   ├── investigate_incident.py  # RAG/LLM CLI with optional persistence
│       │   └── retrieve_runbooks.py     # Live semantic-retrieval CLI
│       ├── models/
│       │   ├── base.py                  # SQLAlchemy declarative base
│       │   ├── investigation_report.py  # Report ORM model and review status
│       │   └── job.py                   # Job ORM model and status enum
│       ├── schemas/
│       │   ├── assessment.py            # Structured RCA contract
│       │   ├── incident.py              # Incident evidence contracts
│       │   ├── investigation.py         # Typed LangGraph state
│       │   ├── investigation_report.py  # Persistence/review contracts
│       │   ├── job.py                   # Job API contracts
│       │   ├── retrieval.py             # Ranked retrieval result
│       │   └── runbook.py               # Runbook-section contract
│       ├── services/
│       │   ├── analyst.py               # Analyst protocol
│       │   ├── embedding.py             # Embedding protocol
│       │   ├── investigation_execution.py # Job/graph/report coordination
│       │   ├── investigation_graph.py   # LangGraph workflow and grounding
│       │   ├── investigation_reports.py # Persistence and lifecycle service
│       │   ├── openai_analyst.py        # Structured Responses API adapter
│       │   ├── openai_embedding.py      # Embeddings adapter
│       │   ├── retriever.py             # Cosine search and ranking
│       │   └── ...                      # Loaders and text builders
│       ├── config.py                     # Environment-based settings
│       ├── database.py                   # Async engine and sessions
│       └── main.py                       # FastAPI application
├── data/
│   ├── incidents/                       # Prepared incident JSON
│   └── runbooks/                        # Curated Markdown runbooks
├── migrations/
│   ├── versions/                        # Alembic schema revisions
│   └── env.py                           # Async migration environment
├── tests/
│   ├── integration/                     # Reserved for PostgreSQL tests
│   └── unit/                            # Deterministic application tests
├── compose.yaml                         # PostgreSQL 18 development service
├── alembic.ini                          # Migration configuration
├── pyproject.toml                       # Project metadata and dependencies
└── uv.lock                              # Reproducible dependency lockfile
```

## Local setup

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for dependency and environment management
- Docker with Docker Compose for local PostgreSQL
- An `OPENAI_API_KEY` configuration value, currently required whenever the shared settings model is loaded

The unit tests do not require OpenAI credits or a running database. Because PostgreSQL and OpenAI settings currently share one required model, migrations and `/ready` also need `OPENAI_API_KEY` to be present. Only the live retrieval CLI needs it to be a valid, funded API key.

### 1. Clone the repository

```bash
git clone https://github.com/shreyas671/RootPilot.git
cd RootPilot
```

### 2. Install dependencies

```bash
uv sync
```

`uv sync` creates or updates `.venv` and installs the exact versions resolved in `uv.lock`.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Set these values in `.env`:

```dotenv
POSTGRES_USER=rootpilot
POSTGRES_PASSWORD=choose_a_local_password
POSTGRES_DB=rootpilot
POSTGRES_PORT=5432
POSTGRES_HOST=localhost
OPENAI_API_KEY=replace_with_your_api_key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_ANALYSIS_MODEL=gpt-5.6-sol
```

When the Python application runs directly on the host and PostgreSQL runs through Compose, `POSTGRES_HOST=localhost` is appropriate.

### 4. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

Compose maps the configured host port to PostgreSQL’s container port `5432` and stores database files in the named `postgres_data` volume.

### 5. Apply migrations

```bash
uv run alembic upgrade head
```

Useful migration commands:

```bash
uv run alembic current
uv run alembic history
```

## Running the application

Start the FastAPI development server:

```bash
uv run uvicorn apps.metadata_service.main:app --reload
```

Then open:

- API documentation: <http://127.0.0.1:8000/docs>
- Alternative API documentation: <http://127.0.0.1:8000/redoc>
- Health check: <http://127.0.0.1:8000/health>
- Readiness check: <http://127.0.0.1:8000/ready>

Stop the PostgreSQL container without deleting its volume:

```bash
docker compose down
```

## Running semantic retrieval

Retrieve the three most relevant chunks for the database incident:

```bash
uv run python -m \
  apps.metadata_service.commands.retrieve_runbooks \
  INC-DB-001
```

Retrieve chunks for the Kafka incident:

```bash
uv run python -m \
  apps.metadata_service.commands.retrieve_runbooks \
  INC-KAFKA-001
```

Change the number of results:

```bash
uv run python -m \
  apps.metadata_service.commands.retrieve_runbooks \
  INC-DB-001 \
  --limit 5
```

Output has this shape:

```text
Incident: INC-DB-001
Embedding model: text-embedding-3-small
Retrieved sections:
1. RB-DB-001#<section> score=<similarity>
   Database Connection-Pool Exhaustion — <Section title>
...
```

Exact scores and ordering can change when embedding models change. Citation IDs remain stable as long as runbook IDs and section headings remain stable.

Each CLI process currently makes one batched embedding request for all runbook sections and another request for the selected incident. Repeated CLI runs therefore repeat embedding work.

## Running grounded investigations

Run retrieval, structured analysis, and citation validation without persistence:

```bash
uv run python -m \
  apps.metadata_service.commands.investigate_incident \
  INC-DB-001 \
  --limit 3 \
  --minimum-score 0.0
```

`--minimum-score` must be between `-1.0` and `1.0`. If every retrieved section scores below the threshold, the graph stops before calling the analyst.

To persist an investigation, first create a pending job:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"input_path":"data/incidents/database_pool_exhaustion.json"}'
```

Copy the returned job UUID and run:

```bash
uv run python -m \
  apps.metadata_service.commands.investigate_incident \
  INC-DB-001 \
  --job-id <job-id> \
  --limit 3 \
  --minimum-score 0.0
```

The job must still be `pending`; do not manually move it to `processing`. The execution coordinator locks and claims it, closes the database session, runs the graph, and finally stores a `pending_review` report while marking the job `completed`. A graph or validation exception marks the job `failed`. The command prints the report UUID needed by the report API.

## Troubleshooting

### OpenAI returns HTTP 429 with `credit_balance_exhausted`

This means the request reached the OpenAI API, but the API organization or project associated with the key has no usable credits. It is a billing/quota failure, not a failure in chunking or cosine similarity.

Check the API project’s billing status, ensure the key belongs to the intended funded project, and retry after billing changes have taken effect. ChatGPT subscriptions and API billing are separate.

### OpenAI returns an authentication error

Confirm that:

- `OPENAI_API_KEY` exists in `.env`.
- The process is running from the project directory where `.env` can be found.
- The key has not been revoked.
- The key belongs to a project permitted to use the requested embedding model.

Do not place a real key in `.env.example` or commit one to Git.

### `/ready` returns HTTP 503

`/ready` executes a real `SELECT 1`, so verify:

```bash
docker compose ps
docker compose logs postgres
uv run alembic current
```

Also verify that `POSTGRES_HOST`, `POSTGRES_PORT`, the database name, and credentials in `.env` match the Compose service.

### Settings validation says a field is missing

The current `Settings` class requires all PostgreSQL fields plus `OPENAI_API_KEY`. This applies even when the operation only needs database configuration. Add every documented variable to `.env`; separating database and OpenAI settings is a roadmap cleanup.

### The retrieval command reports an unknown incident ID

The CLI only accepts incidents loaded from `data/incidents/*.json`. Current IDs are:

```text
INC-DB-001
INC-KAFKA-001
```

Add a valid JSON fixture or use one of those identifiers.

### `--limit` fails

The retrieval limit must be at least one:

```bash
uv run python -m \
  apps.metadata_service.commands.retrieve_runbooks \
  INC-DB-001 \
  --limit 1
```

### Investigation reports no relevant runbook context

The graph applies `--minimum-score` after top-K retrieval. Lower the threshold only when the value is justified by retrieval evaluation; using a very low threshold makes it easier for unrelated context to reach the analyst.

### Persisted investigation rejects the job

`--job-id` claims a job using a locked `pending → processing` transition. Verify that the UUID exists and the job is still `pending`. Completed and failed jobs are terminal, and a job can have at most one report.

### Retrieval order differs from an earlier run

Scores and order can change when the embedding model, model version, incident text, or runbook content changes. The unit test does not assert live OpenAI scores; it uses deterministic keyword vectors to verify the ranking algorithm independently.

## Testing strategy

### Run all tests

```bash
uv run pytest
```

Verbose output:

```bash
uv run pytest -v
```

### Run focused test groups

```bash
uv run pytest -v tests/unit/test_incident_loader.py
uv run pytest -v tests/unit/test_runbook_loader.py
uv run pytest -v tests/unit/test_retriever.py
uv run pytest -v tests/unit/test_openai_embedding.py
uv run pytest -v tests/unit/test_investigation_graph.py
uv run pytest -v tests/unit/test_investigation_execution.py
uv run pytest -v tests/unit/test_investigation_report_service.py
uv run pytest -v tests/unit/test_investigation_reports_api.py
uv run pytest -v tests/unit/test_jobs_api.py
```

### Current coverage by behavior

The 93 unit tests cover:

- Incident fixture discovery and nested model parsing
- Rejection of incomplete incident evidence
- Job table metadata
- Input trimming, length validation, and response serialization
- Error-message rules for job failures
- Job creation, retrieval, missing jobs, and invalid IDs
- Every legal job transition and representative illegal transitions
- Row-lock use during status updates
- Transaction commit/rollback behavior
- Health and database readiness responses
- OpenAI embedding request construction and response ordering
- Rejection of empty embedding batches
- Incident and runbook retrieval-text construction
- Cosine similarity behavior
- Correct database/Kafka runbook ranking using fake embeddings
- Runbook parsing, citation construction, and malformed-file rejection
- Structured assessment constraints and unique citation validation
- Grounded analysis-text construction and OpenAI parsing behavior
- LangGraph node ordering, incident-ID validation, and citation-subset enforcement
- Low-relevance/no-match behavior that stops before analysis
- Pending-job claim, success persistence, and failure recording
- The absence of an open database session during graph network work
- Report table constraints and one-report-per-job mapping
- Report creation, lookup, serialization, approval, and rejection
- Terminal review conflict handling and reviewer-feedback requirements
- Persisted and non-persisted investigation CLI formatting and wiring

### Why tests use fakes

Unit tests must be fast and repeatable. Live systems introduce unrelated failure modes:

- OpenAI calls require credentials, credits, and network availability.
- Embedding output can change across model versions.
- PostgreSQL requires container and migration setup.

The fake keyword embedding provider converts database-related words and Kafka-related words into a two-dimensional test vector. It is not used in production; it makes the expected ranking deterministic.

The fake database session imitates only the SQLAlchemy operations required by the routes. This verifies application behavior but does not prove that the migration and endpoints work together against real PostgreSQL. That gap belongs to future integration tests.

### Pre-commit verification

```bash
uv run pytest
git diff --check
git status --short
```

`git diff --check` detects whitespace errors such as trailing spaces.

## Important design decisions

### Strict Pydantic evidence models

Evidence models reject extra fields. The cost is that schema additions require code changes; the benefit is that malformed evidence cannot quietly influence an investigation.

### Protocol-based embedding dependency

The retriever needs the capability “embed these texts,” not knowledge of a specific SDK. The protocol makes provider replacement and deterministic testing straightforward.

### Async network and database boundaries

The OpenAI client and SQLAlchemy sessions are asynchronous. Persisted execution uses three separate phases: claim the job and commit, run retrieval/analysis with no database session open, then open a short success or failure transaction. This avoids holding a connection or row lock while waiting on external APIs.

### Structural runbook chunks

Operational headings already encode meaning. Using them as boundaries produces chunks that are easier to retrieve, cite, inspect, and explain.

### In-memory retrieval before vector infrastructure

With ten chunks, a vector database would add operational complexity without improving meaningful performance. The current list scan keeps the algorithm visible while preserving a clear migration path to persistent vector search.

### Deterministic citations and tie-breaking

Stable citations are essential for grounding and evaluation. Sorting equal scores by citation ID also prevents unstable result ordering.

### Row locking for lifecycle transitions

Checking a status and updating it are one logical operation. Locking the selected job row prevents concurrent requests from independently approving conflicting transitions.

### Small, verified milestones

The repository has been built in narrow slices: schema, loader, chunking, text construction, provider abstraction, retrieval, graph orchestration, structured analysis, persistence, review, and CLI integration. Each slice adds focused tests before the next architectural layer is introduced.

## Known limitations

These are deliberate boundaries of the current implementation, not hidden features:

1. **No RAG/LLM evaluation suite:** thresholds, recall, ranking quality, answer quality, and grounding rates have not been measured against a labeled dataset.
2. **No vector persistence:** all embeddings disappear when the process exits.
3. **Repeated embedding cost:** each CLI invocation re-embeds every runbook section.
4. **Linear search:** every query is compared with every stored vector.
5. **Uncalibrated relevance threshold:** the guard exists, but its default has not been selected from evaluation data.
6. **Section-only top-K:** high-ranked signal sections can crowd out remediation or verification sections from the same runbook.
7. **No persisted retrieval trace:** reports store citation IDs, but not the exact retrieved scores, chunk text, prompt version, or model versions used for that run.
8. **Basic review only:** approve/reject is terminal and row-locked, but there is no immutable audit-event history, reassignment, reopening, or multi-reviewer policy.
9. **No authentication or authorization:** job and review endpoints are development-only, so reviewer identity is asserted by the caller.
10. **No background worker:** the CLI executes investigations; creating a job through HTTP alone does not enqueue work.
11. **No application-level resilience policy:** SDK failures are recorded on persisted jobs, but RootPilot does not yet define its own timeouts, retry budget, backoff, or error taxonomy.
12. **Configuration coupling:** database-only commands still load the shared settings model containing OpenAI configuration.
13. **Input-path trust boundary unfinished:** `input_path` is metadata; the investigation CLI selects a prepared incident by ID rather than reading an arbitrary job path.
14. **Database tests are mocked:** the migration round trip has been exercised locally, but PostgreSQL integration tests are not automated.
15. **No production observability:** structured logging, tracing, metrics, alerting, and audit events are not implemented.
16. **No deployment workflow:** CI, containerized application deployment, and environment promotion are still pending.

## Roadmap

### Completed foundation

- [x] Bootstrap Python 3.12 project with uv
- [x] Add FastAPI health endpoint
- [x] Add PostgreSQL configuration and readiness check
- [x] Add async SQLAlchemy and Alembic migration support
- [x] Add persisted job model and lifecycle API
- [x] Add prepared incident and runbook fixtures
- [x] Add strict incident evidence schemas and loaders
- [x] Add structural runbook chunking and citation IDs
- [x] Add retrieval-specific text construction
- [x] Add replaceable embedding-provider interface
- [x] Add OpenAI embedding adapter
- [x] Add in-memory cosine-similarity retrieval
- [x] Add CLI retrieval demonstration

### Completed investigation graph

- [x] Add LangGraph
- [x] Define typed investigation state
- [x] Add a retrieval node using the existing retriever
- [x] Define a structured incident-assessment schema
- [x] Add an analyst/provider interface that can be faked in tests
- [x] Add a structured OpenAI analysis node
- [x] Validate incident IDs and generated citations
- [x] Add a configurable low-relevance/no-match path

The intended graph shape is:

```text
START
  → retrieve_runbook_context
  → generate_structured_assessment
  → validate_assessment_and_citations
  → END
```

### Completed persistence and basic review

- [x] Add investigation-report persistence
- [x] Store diagnosis, remediation, verification, confidence, and citations
- [x] Connect a job to one investigation report
- [x] Execute network work outside long-lived database transactions
- [x] Record execution failures on jobs
- [x] Mark generated reports as pending review
- [x] Add one-time approve/reject operations and reviewer feedback
- [ ] Record an audit trail

### Next handoff: evaluation and human-review hardening

- [ ] Build retrieval evaluation cases with expected citation sets
- [ ] Measure top-K recall and ranking quality
- [ ] Calibrate the minimum relevance threshold
- [ ] Evaluate structured RCA fields and citation validity
- [ ] Persist retrieval/model/prompt provenance for repeatability
- [ ] Add an immutable review audit trail
- [ ] Define reviewer authorization and reassessment policy
- [ ] Add PostgreSQL integration tests
- [ ] Add end-to-end investigation tests
- [ ] Add error-handling and retry tests
- [ ] Complete demo documentation
- [ ] Add deployment and CI workflows

### Deferred production capabilities

- Durable background queue and workers
- Redis or another queue backend
- Persistent vector index such as pgvector
- Authentication and role-based access control
- Web user interface
- Production metrics, dashboards, and tracing
- Cloud deployment and autoscaling

## Suggested learning path

If you are studying this project, read it in the following order.

### 1. Learn the validated domain shapes

Start with:

- `schemas/incident.py`
- `schemas/runbook.py`
- `schemas/retrieval.py`

Questions to answer:

- Which fields are required?
- What happens when an extra field appears?
- Why is a retrieved section returned together with its score?
- Which IDs are intended to remain stable?

### 2. Follow data ingestion

Read:

- `services/incident_loader.py`
- `services/runbook_loader.py`
- `data/incidents/`
- `data/runbooks/`

Trace how bytes from a file become validated Python objects. Pay particular attention to duplicate-ID checks and citation creation.

### 3. Follow retrieval text construction

Read `services/retrieval_text.py`.

Compare the original incident model with the generated query. Notice that formatting is separate from validation and that timestamps are currently excluded from embedding text.

### 4. Understand dependency inversion

Read `services/embedding.py`, then `services/openai_embedding.py`.

The protocol defines what the application needs. The adapter defines how one external provider fulfills that need. Then compare the real adapter with `KeywordEmbeddingProvider` in `tests/unit/test_retriever.py`.

### 5. Work through the retrieval algorithm

Read `services/retriever.py` in this order:

1. `cosine_similarity()`
2. `InMemoryRunbookRetriever.create()`
3. `InMemoryRunbookRetriever.retrieve()`

Write down the parallel relationship between `self._sections[i]` and `self._section_embeddings[i]`.

### 6. See composition at the CLI boundary

Read `commands/retrieve_runbooks.py`, then `commands/investigate_incident.py`.

The first is the composition root for retrieval. The second adds the analyst, LangGraph, relevance threshold, optional job execution, and persistence session factory.

### 7. Follow the grounded graph

Read:

- `services/analysis_text.py`
- `services/analyst.py`
- `services/openai_analyst.py`
- `services/investigation_graph.py`

Trace how retrieved sections enter the model prompt, how Structured Outputs create an `IncidentAssessment`, and why schema validation alone is not enough without the citation-subset check.

### 8. Study persistence and transaction boundaries

Read:

- `models/job.py`
- `models/investigation_report.py`
- `schemas/job.py`
- `schemas/investigation_report.py`
- `database.py`
- `api/jobs.py`
- `api/investigation_reports.py`
- `services/investigation_reports.py`
- `services/investigation_execution.py`
- both Alembic migrations

Follow a pending job through claim, network execution, report creation, completion, and review. Confirm that the execution tests observe a closed session before the workflow begins.

### 9. Use tests as executable documentation

For every module above, read its corresponding test. Tests state the behavior more precisely than comments and make edge cases visible.

## Architecture invariants

The current code attempts to preserve these rules:

- Incident IDs match `INC-<CATEGORY>-<3 digits>`.
- Runbook IDs match `RB-<CATEGORY>-<3 digits>`.
- Citation IDs identify exactly one section within a loaded runbook.
- Incident evidence does not silently accept unknown fields.
- A retriever is never created without at least one section.
- Every embedded section must receive exactly one vector.
- Query retrieval must receive exactly one query vector.
- Compared vectors must be non-empty, non-zero, and dimensionally equal.
- Retrieval scores remain inside `[-1.0, 1.0]`.
- Ranking is deterministic for equal scores.
- The analyst is not called when no section meets the minimum relevance score.
- Generated assessments preserve the investigated incident ID.
- Every generated citation is a member of the retrieved citation set.
- Assessment confidence remains inside `[0.0, 1.0]` in both Pydantic and PostgreSQL.
- A job can only follow the declared lifecycle transitions.
- A failed-job request contains an error message; other transitions do not.
- Status transitions lock the selected job row.
- Persisted execution closes the job-claim session before calling the graph.
- One job can create at most one investigation report.
- New reports begin in `pending_review`.
- A report can receive only one terminal approve/reject decision.
- Rejection requires non-empty reviewer feedback.
- Caught SQLAlchemy failures in job routes explicitly roll back the session before returning HTTP 500.

These invariants treat nondeterministic model output as untrusted data. Pydantic validates its structure, and the graph adds provenance checks that cannot be expressed by field types alone.

## Glossary

| Term | Meaning in RootPilot |
|---|---|
| **ANN** | Approximate nearest-neighbor search, commonly used for large vector collections; not currently implemented. |
| **Citation** | Stable ID linking an investigation claim to one runbook section. |
| **Chunk** | One independently embedded and retrievable runbook section. |
| **Cosine similarity** | Direction-based vector similarity measure used for ranking chunks. |
| **Embedding** | Numeric representation of text meaning. |
| **Evidence grounding** | Constraining analysis to observable incident data and retrieved operational sources. |
| **Human in the loop** | Requiring a person to review an AI-generated assessment before accepting it. |
| **RAG** | Retrieval-augmented generation: retrieve sources, then generate an answer using those sources. |
| **RCA** | Root-cause analysis. |
| **Runbook** | Operational instructions for diagnosing and resolving a known incident class. |
| **Top-K** | The highest-ranked `K` retrieval results. |
| **Vector database** | Persistent storage optimized for similarity search; not currently used. |

---

RootPilot has reached the evaluation and human-review-hardening handoff. The next work should measure retrieval and assessment quality, calibrate the relevance threshold, persist provenance, and strengthen reviewer auditability before expanding deployment scope.
