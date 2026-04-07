## 1. Bootstrap and Route Split

- [ ] 1.1 Create `backend/app/routes/` and move existing auth, library, stories, sessions, and MCP endpoints into dedicated route modules.
- [ ] 1.2 Update `backend/app/main.py` so it only initializes FastAPI, registers middleware, and mounts routers from the new route modules.
- [ ] 1.3 Verify all existing backend API paths and response contracts remain unchanged after route extraction.

## 2. Runtime and Domain Extraction

- [ ] 2.1 Create `backend/app/services/story_runtime_service.py` and move runtime initialization, choice progression, and completed-run assembly logic out of `main.py`.
- [ ] 2.2 Create `backend/app/domain/session_models.py` and `backend/app/domain/story_package.py` for shared session/package normalization and validation helpers.
- [ ] 2.3 Update session-related route handlers to call runtime/domain helpers instead of inline business logic.

## 3. Provider and Generation Boundaries

- [ ] 3.1 Create or finalize `backend/app/providers/volcengine.py`, `backend/app/providers/secondme.py`, `backend/app/providers/prompts.py`, and `backend/app/providers/parsers.py` with clear module boundaries.
- [ ] 3.2 Create `backend/app/services/story_generation_service.py` and move two-stage generation and hydrate orchestration behind service interfaces.
- [ ] 3.3 Update generation-related routes and services so provider transport, prompt construction, and parser behavior are no longer implemented inside `main.py`.

## 4. Repository and Library Seed Extraction

- [ ] 4.1 Create `backend/app/repositories/stories_repo.py` and `backend/app/repositories/sessions_repo.py` to unify JSON-file and database persistence access.
- [ ] 4.2 Create `backend/app/services/library_seed_service.py` and move seed loading, generation, waiting, locking, and reuse logic out of `main.py`.
- [ ] 4.3 Update library story and session flows to use repository and library-seed service APIs rather than direct storage helpers.

## 5. Documentation Standards and Validation

- [ ] 5.1 Add a concise Chinese file-purpose description to each backend module created or migrated in this refactor.
- [ ] 5.2 Add Chinese docstrings to public functions and complex private helpers touched by this refactor, while keeping inline comments limited to non-obvious intent.
- [ ] 5.3 Run backend and frontend validation for critical flows, including OAuth exchange, library seed start, custom story generation, session progression, finalize/save, and related build or compile checks.
