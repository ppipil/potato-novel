## ADDED Requirements

### Requirement: Guest users SHALL access bookshelf without OAuth login
The system SHALL allow unauthenticated users to enter the bookshelf experience in guest mode and browse public story cards without completing SecondMe OAuth.

#### Scenario: Guest enters bookshelf directly
- **WHEN** a user opens the bookshelf route without a valid authenticated session cookie
- **THEN** the frontend renders bookshelf in guest mode
- **AND** the user is not redirected to the login landing page

#### Scenario: Authenticated user still enters bookshelf normally
- **WHEN** a user opens the bookshelf route with a valid authenticated session
- **THEN** the frontend renders bookshelf in authenticated mode
- **AND** authenticated-only capabilities remain available

### Requirement: Guest custom generation SHALL stay local-only
The system SHALL allow guest users to generate and play custom stories, but guest stories MUST remain local-only and MUST NOT be persisted to shared backend storage.

#### Scenario: Guest generates a custom story
- **WHEN** a guest user submits a custom opening
- **THEN** the system returns a playable story session
- **AND** the generated story is stored only in local client storage

#### Scenario: Guest views personal stories
- **WHEN** a guest user opens the personal shelf area
- **THEN** the system shows only locally stored guest stories
- **AND** no cloud-synced stories are fetched for that guest

### Requirement: Guest mode SHALL hide and block ending-signature generation
The system SHALL disable ending-signature generation for guest mode in both UI and API layers.

#### Scenario: Guest reaches an ending node
- **WHEN** a guest user completes a story
- **THEN** the story page does not render the ending-signature trigger action

#### Scenario: Guest calls ending analysis API directly
- **WHEN** a guest request reaches the ending analysis endpoint without authenticated token context
- **THEN** the backend rejects the request
- **AND** no SecondMe ending-analysis request is sent
