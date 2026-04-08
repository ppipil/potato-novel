## 1. Bootstrap and Route Split

- [x] 1.1 Create `backend/app/routes/` and move existing auth, library, stories, sessions, and MCP endpoints into dedicated route modules.
- [x] 1.2 Update `backend/app/main.py` so it only initializes FastAPI, registers middleware, and mounts routers from the new route modules.
- [x] 1.3 Verify all existing backend API paths and response contracts remain unchanged after route extraction.

## 2. Runtime and Domain Extraction

- [x] 2.1 Create `backend/app/services/story_runtime_service.py` and move runtime initialization, choice progression, and completed-run assembly logic out of `main.py`.
- [x] 2.2 Create `backend/app/domain/session_models.py` and `backend/app/domain/story_package.py` for shared session/package normalization and validation helpers.
- [x] 2.3 Update session-related route handlers to call runtime/domain helpers instead of inline business logic.

## 3. Provider and Generation Boundaries

- [x] 3.1 Create or finalize `backend/app/providers/volcengine.py`, `backend/app/providers/secondme.py`, `backend/app/providers/prompts.py`, and `backend/app/providers/parsers.py` with clear module boundaries.
- [x] 3.2 Create `backend/app/services/story_generation_service.py` and move two-stage generation and hydrate orchestration behind service interfaces.
- [x] 3.3 Update generation-related routes and services so provider transport, prompt construction, and parser behavior are no longer implemented inside `main.py`.
- [x] 3.4 Split oversized generation orchestration functions into smaller named steps so top-level service functions describe workflow rather than embedding all details inline.
- [x] 3.5 Remove the unused partial-node hydrate mode from the two-stage generation path and keep only the full-materialization flow used by active entry points.

## 4. Repository and Library Seed Extraction

- [x] 4.1 Create `backend/app/repositories/stories_repo.py` and `backend/app/repositories/sessions_repo.py` to unify JSON-file and database persistence access.
- [x] 4.2 Create `backend/app/services/library_seed_service.py` and move seed loading, generation, waiting, locking, and reuse logic out of `main.py`.
- [x] 4.3 Update library story and session flows to use repository and library-seed service APIs rather than direct storage helpers.
- [x] 4.4 Split oversized library-seed and session orchestration functions when they still mix process control, storage mutation, and rollback logic in one body.

## 5. Documentation Standards and Validation

- [x] 5.1 Add a concise Chinese file-purpose description to each backend module created or migrated in this refactor.
- [x] 5.2 Add Chinese docstrings to public functions and complex private helpers touched by this refactor, while keeping inline comments limited to non-obvious intent.
- [x] 5.3 Run backend and frontend validation for critical flows, including OAuth exchange, library seed start, custom story generation, session progression, finalize/save, and related build or compile checks.
