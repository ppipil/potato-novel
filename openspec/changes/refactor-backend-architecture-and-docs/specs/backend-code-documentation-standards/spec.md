## ADDED Requirements

### Requirement: Backend modules declare file purpose in Chinese
Each backend Python module under the application package SHALL begin with a concise Chinese description that explains the file's responsibility and boundary so maintainers can quickly understand why the file exists.

#### Scenario: New backend module includes header description
- **WHEN** a maintainer creates a new module under `backend/app/`
- **THEN** the file SHALL include a concise Chinese description near the top of the file that explains the module purpose and its primary responsibility

#### Scenario: Migrated module receives purpose description
- **WHEN** an existing backend module is touched during this refactor
- **THEN** the module SHALL be updated to include a concise Chinese purpose description if it does not already have one

### Requirement: Public functions include Chinese docstrings
Public backend functions SHALL include clear Chinese docstrings that explain the function intent, major inputs or assumptions when needed, and the responsibility boundary of the function.

#### Scenario: Route handler has Chinese docstring
- **WHEN** a FastAPI route handler is defined in the backend application package
- **THEN** the handler SHALL include a Chinese docstring that explains the endpoint's purpose in the current system

#### Scenario: Public service helper has Chinese docstring
- **WHEN** a public helper or service function is exposed for use across backend modules
- **THEN** the function SHALL include a Chinese docstring describing its purpose and expected responsibility

### Requirement: Complex private functions include Chinese docstrings
Complex private backend functions SHALL include Chinese docstrings when their behavior, constraints, or side effects are not obvious from the signature alone.

#### Scenario: Non-trivial private helper is documented
- **WHEN** a private helper coordinates runtime progression, persistence, provider calls, compatibility logic, or migration-sensitive behavior
- **THEN** the helper SHALL include a Chinese docstring that explains the non-obvious behavior or constraint

#### Scenario: Trivial helper may stay compact
- **WHEN** a private helper is a trivial getter, direct passthrough, or single-purpose obvious transformation
- **THEN** the system MAY omit a docstring as long as the code remains immediately understandable

### Requirement: Inline comments explain intent instead of restating code
Inline comments in backend modules MUST be used sparingly and SHALL explain design intent, compatibility constraints, or non-obvious decisions rather than repeating literal code behavior.

#### Scenario: Comment explains why
- **WHEN** a maintainer adds an inline comment to backend code
- **THEN** the comment SHALL describe the intent, trade-off, or constraint that is not obvious from the code itself

#### Scenario: Redundant comments are avoided
- **WHEN** a line of code is self-explanatory from naming and structure
- **THEN** the maintainer SHALL avoid adding an inline comment that only restates the same operation
