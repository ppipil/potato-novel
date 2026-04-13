## ADDED Requirements

### Requirement: Story-generation-adjacent modules SHALL live under typed backend layers
Backend modules that directly support story generation SHALL be organized under typed directories such as `core`、`domain`、`providers`、`services`, rather than remaining as unscoped root modules beside the application entrypoint.

#### Scenario: Generation support modules are no longer introduced as root files
- **WHEN** a new or migrated module supports prompt construction, model invocation, opening presets, integration metadata, or text normalization for story generation
- **THEN** that module SHALL be placed in the appropriate typed layer directory
- **AND** the change SHALL not introduce another generation-specific root file under `backend/app`

#### Scenario: Existing generation root modules are moved toward typed layers
- **WHEN** the team refactors currently exposed generation root modules such as prompt, provider, opening, or text-normalization helpers
- **THEN** those modules SHALL be migrated into the typed layer that matches their responsibility
- **AND** import boundaries SHALL continue to keep `main.py` focused on app wiring rather than business orchestration

### Requirement: The application entrypoint SHALL remain thin during generation feature growth
As story-generation features evolve, the application entrypoint MUST continue to act primarily as an app assembly and dependency wiring module, with new business behavior delegated to services, providers, or domain modules.

#### Scenario: New style-tag behavior avoids growing main.py
- **WHEN** style-tag generation support is added
- **THEN** new branching logic, mappings, or prompt composition behavior SHALL be implemented outside `main.py`
- **AND** the entrypoint SHALL only retain minimal parameter plumbing required to invoke the delegated logic
