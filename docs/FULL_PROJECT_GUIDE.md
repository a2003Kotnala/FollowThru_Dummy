# FollowThru Full Project Guide

## 1. What This Project Is

FollowThru is a FastAPI backend that helps turn messy meeting inputs into structured execution output.

At a high level, it does four jobs:

1. It accepts meeting content from APIs, Slack slash commands, Slack DMs, Slack app mentions, and now Zoom recording links.
2. It extracts structured intelligence such as summary, action items, decisions, risks, and open questions.
3. It turns that intelligence into Slack Canvas markdown.
4. It stores workflow state in a relational database and optionally publishes the result back to Slack.

So the real product idea is:

- Input: notes, transcript, voice-command transcript, uploaded transcript file, or recording link.
- Processing: parse, summarize, extract execution intelligence.
- Output: a draft, a preview, chat guidance, or a published Slack Canvas.

## 2. Architectural Style

The codebase is organized in layered form:

- `app/api`: HTTP entry points.
- `app/slack`: Slack-specific entry points and handlers.
- `app/domain`: business logic and schemas.
- `app/integrations`: wrappers around external systems like Slack and OpenAI.
- `app/db`: persistence models, engine, sessions, and migrations.
- `app/workers`: background-processing components for Celery tasks.

This layout is useful because it separates:

- transport logic from business logic,
- pure workflow code from vendor APIs,
- sync request handling from async background jobs,
- data schemas from persistence schemas.

## 3. Full Directory Structure

### Root

- `.editorconfig`
  Controls basic formatting consistency across editors.
- `.gitignore`
  Tells Git which files to ignore.
- `.pre-commit-config.yaml`
  Defines code quality hooks for local development.
- `alembic.ini`
  Alembic configuration for database migrations.
- `compose.yml`
  Docker Compose setup for local PostgreSQL.
- `fix_db.py`
  Utility script for database-related manual fixes.
- `pyproject.toml`
  Python project metadata and tool configuration.
- `README.md`
  Project introduction and quick start.
- `requirements.txt`
  Python dependency list for runtime and development.

### `app/`

- `config.py`
  Central settings model. Reads environment variables and provides resolved config values.
- `dependencies.py`
  FastAPI dependency helpers, currently DB session injection.
- `logger.py`
  Logging setup.
- `main.py`
  FastAPI app bootstrap and router registration.

### `app/api/`

- `routes/followthru.py`
  Chat, capabilities, and voice-command API routes.
- `routes/health.py`
  Liveness and database health endpoints.
- `routes/slack_commands.py`
  FastAPI bridge for Slack slash commands.
- `routes/slack_interactions.py`
  FastAPI bridge for Slack interactivity payloads.
- `routes/workflows.py`
  Direct API routes for previewing and processing text workflows.

### `app/db/`

- `base.py`
  SQLAlchemy engine and declarative base.
- `session.py`
  SQLAlchemy session factory.
- `migrations/`
  Alembic migration files and migration environment.
- `models/`
  SQLAlchemy ORM models for the app’s persisted state.

### `app/domain/`

- `schemas/`
  Pydantic request/response and structured data models.
- `services/`
  Business logic for extraction, drafting, chat orchestration, dynamic extraction, and transcription.

### `app/integrations/`

- `openai_client.py`
  Wrapper for OpenAI-compatible chat/extraction calls used by the synchronous workflow.
- `slack_client.py`
  Wrapper around Slack Web API operations like canvases, files, and messages.

### `app/slack/`

- `bolt_app.py`
  Slack Bolt bootstrap and listener registration.
- `handlers/commands.py`
  Slash command, app mention, and DM event behavior.
- `handlers/interactions.py`
  Modal submission handling for the async video workflow.
- `services/source_resolver.py`
  Slack-aware source discovery and source persistence.
- `services/dm_ingestion_service.py`
  Alternate ingestion-oriented DM workflow scaffold.
- `services/dm_response_builder.py`
  DM response helper surface.
- `views/canvas_modal.py`
  Slack modal builder for selecting what to extract from a recording.

### `app/workers/`

- `celery_app.py`
  Celery app configuration.
- `media_processor.py`
  FFmpeg-based audio extraction and chunking.
- `tasks.py`
  Background orchestration task for meeting recordings.

### `docs/`

- `PROJECT_STRUCTURE.md`
  High-level structure summary.
- `RUNNING.md`
  Local run instructions.
- `LAUNCH_CHECKLIST.md`
  Release or launch checklist.
- `followthru_architecture_diagrams.md`
  Mermaid-based architecture docs.
- `FULL_PROJECT_GUIDE.md`
  This full explanation document.

### `diagrams/`

- `generate_architecture_diagrams_pdf.py`
  Generates a PDF version of the architecture diagrams without external PDF libraries.
- image files
  Diagram exports.

### `scripts/`

- `dev.py`
  Starts the FastAPI server in reload mode.
- `seed.py`
  Prints sample meeting text for manual testing.

### `tests/unit/`

Unit tests for routes, services, Slack behavior, source resolution, canvas generation, and ingestion workflows.

## 4. Main Runtime Flows

### 4.1 API Chat Flow

The route `POST /api/v1/followthru/chat` calls `handle_followthru_chat`.

That service:

1. Normalizes and parses the request.
2. Detects the mode: help, chat, preview, draft, or publish.
3. Creates or loads a chat session.
4. Stores the user message.
5. Either:
   - generates a chat response, or
   - runs extraction plus canvas workflow.
6. Stores the assistant reply.
7. Returns a structured `FollowThruResponse`.

### 4.2 Voice Command Flow

The route `POST /api/v1/followthru/voice-command` is similar to chat, but it treats the input as a speech-to-text transcript and can persist that source with `source_type=voice`.

### 4.3 Workflow Preview Flow

The route `POST /api/v1/workflows/preview`:

1. accepts raw meeting text,
2. extracts structured intelligence,
3. renders canvas markdown,
4. returns the extraction plus draft markdown without storing a draft.

This is useful for dry runs.

### 4.4 Workflow Process Text Flow

The route `POST /api/v1/workflows/process-text`:

1. stores the text as a source,
2. extracts structured data,
3. creates a draft record,
4. optionally publishes the result to Slack.

### 4.5 Slack Channel Slash Command Flow

The route `POST /slack/commands` forwards to Slack Bolt.

The command handler supports channel usage like:

- `/followthru`
- `/followthru publish`
- `/followthru help`
- `/followthru process <zoom-link>`

For channel preview/publish:

1. FollowThru resolves the latest huddle notes canvas or transcript.
2. It extracts structured meeting intelligence.
3. It returns an ephemeral preview or publishes to the channel canvas.

### 4.6 Slack DM Flow

In DMs, the bot can:

- reply with help,
- clear chat state,
- stop active ingestion jobs,
- accept pasted transcript text,
- accept uploaded transcript files,
- generate draft/preview/publish outputs.

The DM handler is more flexible than the channel handler because it supports direct raw content.

### 4.7 Async Video Processing Flow

The new recording flow works like this:

1. User runs `/followthru process <Zoom-recording-link>`.
2. FollowThru opens a modal with extraction choices.
3. User submits the modal.
4. Slack interaction handler immediately acknowledges the modal.
5. The handler posts a status message and enqueues `process_meeting_task`.
6. Celery downloads the recording.
7. FFmpeg extracts and chunks audio.
8. Whisper transcribes the audio chunks in parallel.
9. GPT-4o extracts only the user-selected fields using a dynamic schema.
10. Canvas markdown is created and uploaded to Slack.
11. A completion message is posted with the canvas ID.

This is the most asynchronous and media-heavy workflow in the repo.

## 5. What Each Important File Does

### `app/main.py`

This is the application entry point.

Responsibilities:

- initializes logging,
- creates the FastAPI app,
- adds middleware for request ID and processing time,
- registers the routers.

Why it matters:

- it is the main composition root for the HTTP layer.

### `app/config.py`

This defines a Pydantic `Settings` class.

Responsibilities:

- load environment variables,
- normalize optional values,
- provide defaults,
- derive resolved values such as database URL and LLM model,
- expose `redis_url` for the worker pipeline.

Why it matters:

- every integration and service reads config from here.

### `app/logger.py`

Simple logging bootstrap.

Responsibilities:

- configure Python logging level and format,
- expose `logger`.

### `app/dependencies.py`

Provides reusable FastAPI dependencies.

Current role:

- DB session dependency using `SessionLocal`.

### `app/api/routes/health.py`

Health endpoints:

- `/`
- `/health`
- `/db-health`

Purpose:

- check if the app is alive,
- check if database connectivity works,
- expose basic runtime configuration state.

### `app/api/routes/followthru.py`

Public API surface for FollowThru features.

Purpose:

- expose capabilities,
- expose chat,
- expose voice-command transcript processing.

### `app/api/routes/workflows.py`

Direct non-Slack workflow endpoints.

Purpose:

- preview extracted output quickly,
- process raw text into stored draft/canvas output.

### `app/api/routes/slack_commands.py`

Thin bridge from FastAPI to Slack Bolt for slash commands.

### `app/api/routes/slack_interactions.py`

Thin bridge from FastAPI to Slack Bolt for interactive events and modal submissions.

### `app/db/base.py`

Creates the SQLAlchemy engine and `Base`.

Purpose:

- central DB connectivity,
- engine pooling config,
- DB-type-specific options.

### `app/db/session.py`

Builds the SQLAlchemy session factory.

Purpose:

- every DB-using service relies on this.

### `app/db/models/user.py`

Stores a user identity.

Key fields:

- `id`
- `slack_user_id`
- `name`
- `email`
- `created_at`

### `app/db/models/source.py`

Stores raw input sources.

Examples:

- huddle notes,
- transcript text,
- voice transcript.

Why important:

- it preserves where a draft came from.

### `app/db/models/draft.py`

Stores metadata for a generated draft or published canvas.

Key fields:

- owner,
- source,
- Slack canvas ID,
- title,
- status,
- timestamps.

### `app/db/models/extracted_item.py`

Stores normalized extracted items linked to a draft.

Examples:

- summary,
- decision,
- action item,
- blocker,
- due date,
- question.

### `app/db/models/chat_session.py`

Stores a logical FollowThru conversation.

Useful for:

- context continuity,
- history persistence,
- multi-turn chat.

### `app/db/models/chat_message.py`

Stores each message in a chat session.

Roles:

- system,
- user,
- assistant.

### `app/domain/schemas/extraction.py`

Defines the structured extraction contract.

Important because:

- it standardizes the format expected by canvas generation and draft persistence.

### `app/domain/schemas/followthru.py`

Defines request and response types for chat and voice-command flows.

### `app/domain/schemas/workflow.py`

Defines request and response models for the direct preview/process-text API routes.

### `app/domain/services/extraction_service.py`

This is the core structured extraction engine for sync note-based workflows.

Responsibilities:

- normalize input,
- compress overly large transcripts,
- call LLM extraction when configured,
- otherwise fall back to deterministic rule-based parsing.

Why the fallback exists:

- it allows the app to remain useful even without an LLM key.

### `app/domain/services/followthru_service.py`

This is the main orchestration brain for the synchronous FollowThru product behavior.

Responsibilities:

- parse user intent,
- decide mode,
- manage sessions and chat history,
- resolve sources,
- run extraction,
- call draft creation,
- generate final `FollowThruResponse`.

This is one of the most important files in the repo.

### `app/domain/services/draft_service.py`

Takes extraction output and converts it into persisted draft state plus optional Slack publication.

Responsibilities:

- build canvas title,
- generate canvas markdown,
- optionally upload to Slack,
- insert `Draft`,
- insert `ExtractedItem` rows.

### `app/domain/services/canvas_composer.py`

Responsible for converting structured extraction output into Slack Canvas markdown.

It now supports two output styles:

- fixed schema canvas from `ExtractionResult`,
- dynamic schema canvas from the new async video pipeline.

### `app/domain/services/parallel_whisper.py`

Async transcription layer for audio chunks.

Responsibilities:

- call `AsyncOpenAI`,
- send chunk transcriptions in parallel,
- include the Hinglish prompt,
- pass tail context between chunks to reduce boundary hallucination,
- reassemble the transcript in order.

### `app/domain/services/dynamic_extraction.py`

Dynamic GPT-4o extraction layer for the async recording flow.

Responsibilities:

- build a Pydantic response model at runtime from user-selected fields,
- call GPT-4o,
- return only the sections requested in the Slack modal.

Why this matters:

- the extraction contract is no longer fixed.

### `app/integrations/openai_client.py`

Current synchronous OpenAI-compatible integration.

Responsibilities:

- extract structured meeting data,
- generate general FollowThru chat replies.

Why the app uses an “OpenAI-compatible” wrapper:

- it can work with OpenAI-compatible providers, not just one vendor.

### `app/integrations/slack_client.py`

Central wrapper around Slack Web API operations.

Responsibilities:

- message update/delete,
- file list/info/download/upload,
- canvas create/edit/delete,
- channel history lookup.

Why a wrapper is useful:

- keeps Slack SDK code in one place,
- makes handlers simpler,
- improves testability.

### `app/slack/bolt_app.py`

Bootstrap for Slack Bolt.

Responsibilities:

- initialize Bolt app only when Slack is configured,
- register command listeners,
- register interaction listeners,
- expose `handle_slack_request`.

### `app/slack/handlers/commands.py`

This is the main Slack behavior file.

Responsibilities:

- slash command handling,
- app mention handling,
- DM handling,
- DM file parsing,
- clear/stop flows,
- opening the async processing modal.

This file is large because it owns several Slack-facing user journeys.

### `app/slack/handlers/interactions.py`

Handles modal submission for the async recording pipeline.

Responsibilities:

- `ack()` the modal,
- read selected checkboxes and custom focus,
- post immediate status to Slack,
- enqueue the Celery task.

### `app/slack/views/canvas_modal.py`

Builds the Slack modal JSON.

Purpose:

- keep UI shape separate from handler logic.

### `app/slack/services/source_resolver.py`

This service knows how to find the best Slack source content.

Responsibilities:

- inspect channel files,
- find canvases,
- find transcript candidates,
- score likely transcript files,
- fetch canvas/transcript content,
- persist a `Source`.

This is important because Slack channels do not always contain one neat canonical source.

### `app/slack/services/dm_ingestion_service.py`

This appears to be an ingestion-oriented DM service path intended for job-based processing.

Important note:

- in the current workspace, this file references ingestion modules that are not present in `app/domain/schemas` and `app/domain/services`.
- that means it looks like partial or future-facing scaffolding rather than the currently active primary path.

### `app/workers/celery_app.py`

Defines the Celery worker app.

Responsibilities:

- broker/backend configuration using Redis,
- JSON task serialization,
- worker cleanup hooks,
- SQLAlchemy engine disposal after tasks.

### `app/workers/media_processor.py`

Runs FFmpeg.

Responsibilities:

- extract audio from media,
- convert to mono 16kHz MP3,
- segment into 10-minute chunks.

### `app/workers/tasks.py`

Main async background task orchestration.

Responsibilities:

- download media,
- call FFmpeg chunking,
- call parallel Whisper transcription,
- call dynamic GPT-4o extraction,
- build markdown,
- upload canvas to Slack,
- notify success or failure,
- clean temporary files.

### `scripts/dev.py`

Convenience script for local development.

Purpose:

- starts Uvicorn with reload enabled.

### `scripts/seed.py`

Prints a sample meeting note payload for ad hoc testing.

## 6. Database Model Relationships

The core persisted relationships are:

- one `User` can create many `Source` records,
- one `User` can own many `ChatSession` records,
- one `ChatSession` can contain many `ChatMessage` records,
- one `Source` can produce many `Draft` records,
- one `Draft` can contain many `ExtractedItem` records.

This structure is useful because it cleanly separates:

- raw input from generated output,
- chat memory from workflow drafts,
- persisted entity rows from rendered canvas content.

## 7. Full Tech Stack And Why It Is Used

### FastAPI

Used for:

- HTTP APIs,
- Slack endpoints,
- health checks,
- JSON request/response handling.

Why this stack choice is good:

- easy Pydantic integration,
- strong typing,
- fast development speed,
- lightweight and good for API-first backends.

### Slack Bolt + Slack SDK

Used for:

- slash commands,
- app mentions,
- modal handling,
- event handling,
- Slack Web API access.

Why:

- Slack Bolt is the standard event/listener framework for Slack apps.
- Slack SDK provides the lower-level Web API methods needed for canvases, files, and messaging.

### Pydantic

Used for:

- app config,
- request/response schemas,
- extracted intelligence schemas,
- dynamic schema generation.

Why:

- runtime validation,
- clean type hints,
- easy serialization/deserialization,
- perfect fit with FastAPI.

### SQLAlchemy

Used for:

- ORM models,
- database sessions,
- persistence logic.

Why:

- mature Python ORM,
- works well with PostgreSQL and SQLite,
- flexible enough for both simple and evolving schemas.

### Alembic

Used for:

- schema migrations.

Why:

- standard migration tool for SQLAlchemy projects.

### PostgreSQL

Used for:

- primary relational persistence in production/local Docker flow.

Why:

- reliable transactional database,
- better production fit than SQLite for multi-user workflow state,
- good support for structured app data.

### Redis

Used for:

- Celery broker,
- Celery result backend.

Why:

- fast in-memory queue backend,
- common and proven Celery pairing,
- good enough for transient job coordination.

### Celery

Used for:

- background task execution for long-running video-processing jobs.

Why:

- the recording workflow is too slow for a synchronous Slack request cycle,
- Celery is a standard Python background job framework,
- Redis + Celery is a familiar and maintainable async processing stack.

### FFmpeg

Used for:

- audio extraction from recordings,
- audio normalization,
- chunking audio into 10-minute MP3 segments.

Why:

- industry-standard media processing tool,
- very reliable for format conversion and segmentation.

### OpenAI / OpenAI-Compatible APIs

Used for:

- synchronous structured extraction,
- FollowThru chat responses,
- Whisper transcription in the async media workflow,
- GPT-4o dynamic extraction.

Why:

- LLMs are strong at semantic extraction,
- Whisper is strong at transcription,
- GPT-4o is strong at structured intelligence extraction from transcripts.

### httpx

Used for:

- calling external HTTP APIs,
- downloading remote files,
- posting chat-completions requests.

Why:

- modern Python HTTP client,
- clean sync and async support.

### aiofiles

Used for:

- async file reads in the parallel Whisper pipeline.

Why:

- allows non-blocking file access inside async transcription tasks.

### pytest

Used for:

- unit test suite.

Why:

- standard Python testing framework,
- readable and flexible tests.

## 8. Why This Particular Overall Stack Makes Sense

This project is fundamentally an integration-heavy workflow backend.

The stack fits that kind of product because:

- FastAPI + Pydantic are excellent for typed APIs.
- Slack Bolt is the natural tool for Slack interactivity.
- SQLAlchemy + PostgreSQL handle durable workflow state well.
- Celery + Redis handle slow background work cleanly.
- FFmpeg solves media preprocessing without reinventing media tooling.
- OpenAI APIs solve the hard semantic/transcription tasks.

In other words:

- relational DB for durable state,
- queue for long-running work,
- specialized media tool for audio preprocessing,
- LLMs for unstructured language understanding,
- Slack SDK/Bolt for the product surface,
- FastAPI as the glue.

That is why this stack is practical rather than trendy.

## 9. Request Lifecycle Summary

### Sync notes-based workflow

- user provides text,
- system extracts structure,
- system creates markdown,
- system stores draft,
- optionally system publishes to Slack.

### Sync chat workflow

- user asks FollowThru something,
- system loads recent history,
- system either replies with LLM chat or deterministic fallback,
- system persists the exchange.

### Async recording workflow

- user provides recording link,
- user chooses desired outputs,
- system enqueues background job,
- worker downloads and processes media,
- worker transcribes audio,
- worker extracts structured output,
- worker publishes canvas,
- worker posts completion message.

## 10. Testing Strategy

The repo mainly uses unit tests.

The tests cover:

- route correctness,
- settings behavior,
- extraction logic,
- canvas composition,
- Slack command behavior,
- source resolution,
- ingestion service behavior.

This is useful because the product has many branches of orchestration logic and many external integrations that are easier to mock than to run end-to-end in every test.

## 11. Important Strengths Of This Codebase

- clear separation between API, domain, integrations, DB, and Slack surfaces,
- typed schemas throughout,
- deterministic fallback when LLM is unavailable,
- durable storage of chat and workflow state,
- async recording pipeline now separated from request-response logic,
- reusable Slack wrapper and OpenAI wrapper,
- existing unit test coverage for major sync flows.

## 12. Important Caveats

- some docs in the repo describe alternate or older ingestion/transcription setups, so the code should be treated as the source of truth.
- `app/slack/services/dm_ingestion_service.py` references ingestion modules not currently present in the visible workspace, so that path looks incomplete or staged for future work.
- the current worker pipeline depends on external runtime software:
  - Redis server,
  - FFmpeg,
  - database,
  - Slack credentials,
  - OpenAI API key.

## 13. What To Learn First If You Are New

If you want to understand the project quickly, read in this order:

1. `README.md`
2. `app/main.py`
3. `app/config.py`
4. `app/domain/services/followthru_service.py`
5. `app/domain/services/extraction_service.py`
6. `app/domain/services/draft_service.py`
7. `app/domain/services/canvas_composer.py`
8. `app/slack/handlers/commands.py`
9. `app/slack/services/source_resolver.py`
10. `app/workers/tasks.py`

That reading order gives you:

- entry point,
- config,
- main orchestration,
- extraction,
- draft persistence,
- canvas generation,
- Slack behavior,
- source resolution,
- background media flow.

## 14. Short Plain-English Summary

FollowThru is an execution intelligence backend.

It listens to Slack and API inputs, turns raw meeting content into structured deliverables, stores the workflow state in PostgreSQL, and publishes the result as Slack canvases. The synchronous path handles notes, chat, and transcript text. The asynchronous path handles recording links using Redis, Celery, FFmpeg, Whisper, and GPT-4o.
