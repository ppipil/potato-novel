## ADDED Requirements

### Requirement: Backend entry module remains thin
The backend SHALL keep `backend/app/main.py` focused on application bootstrap responsibilities, including app creation, middleware registration, and router mounting, and MUST NOT keep domain-specific story orchestration logic in that file once migration is complete.

#### Scenario: App bootstrap only wires routers
- **WHEN** the backend initializes FastAPI
- **THEN** `backend/app/main.py` SHALL configure the app and attach route modules without re-implementing library seed, story runtime, or repository logic inline

#### Scenario: Domain logic moves out of main
- **WHEN** a maintainer updates story runtime, library seed, or story generation behavior
- **THEN** the change SHALL be applied in service, repository, provider, or domain modules rather than adding new business helpers to `backend/app/main.py`

### Requirement: Route modules own HTTP concerns
The backend SHALL organize HTTP endpoints into route modules grouped by API concern, and each route module MUST be responsible only for request parsing, response shaping, and invoking the appropriate service layer.

#### Scenario: Auth routes are isolated
- **WHEN** a maintainer edits OAuth login, callback, exchange, or logout behavior
- **THEN** the corresponding FastAPI endpoints SHALL live in an auth-focused route module rather than being mixed with story session logic

#### Scenario: Session routes call services
- **WHEN** a session read, choose, hydrate, or finalize endpoint is handled
- **THEN** the route module SHALL delegate runtime progression and persistence behavior to service or repository modules instead of duplicating business rules in the route body

### Requirement: Service layer owns story orchestration
The backend SHALL expose dedicated services for story generation, story runtime progression, and library seed orchestration, and these services MUST be the primary place for cross-module workflow decisions.

#### Scenario: Library seed flow is centralized
- **WHEN** the system loads, generates, waits for, or reuses a library seed package
- **THEN** the orchestration SHALL be implemented behind a dedicated library seed service boundary

#### Scenario: Runtime progression is centralized
- **WHEN** the system initializes runtime, advances a choice, or builds a completed run payload
- **THEN** the orchestration SHALL be implemented behind a dedicated story runtime service boundary

### Requirement: Repository layer abstracts session and story persistence
The backend SHALL provide repositories for story and session persistence, and business services MUST use these repositories instead of directly manipulating storage-specific helpers.

#### Scenario: Storage mode is hidden from services
- **WHEN** a service loads or saves sessions or stories
- **THEN** the service SHALL call repository APIs without needing to know whether the underlying storage is JSON file based or database based

#### Scenario: Session updates are centralized
- **WHEN** session records are inserted, updated, or removed
- **THEN** those mutations SHALL be performed through repository-owned helpers rather than ad hoc storage writes spread across route modules

### Requirement: Provider integration is isolated from route and runtime modules
The backend SHALL isolate external model provider calls, prompt construction, and response parsing into provider-focused modules so that story workflows can depend on stable provider interfaces.

#### Scenario: Provider transport is isolated
- **WHEN** the system calls Volcengine or SecondMe
- **THEN** the HTTP transport and provider-specific error handling SHALL live in provider modules rather than route modules

#### Scenario: Prompt and parser logic is isolated
- **WHEN** a maintainer updates prompt wording or model output parsing
- **THEN** the change SHALL be made in prompt or parser modules without requiring direct edits to route registration code
