## MODIFIED Requirements

### Requirement: Bookshelf access supports guest mode and authenticated mode
The frontend SHALL treat the bookshelf as accessible in two modes: guest mode for unauthenticated users and authenticated mode for users with valid session cookies.

#### Scenario: Authenticated user enters bookshelf
- **WHEN** the bookshelf page loads and `/api/me` returns `authenticated: true`
- **THEN** the bookshelf page renders authenticated identity and user-synced personal stories
- **AND** authenticated-only actions remain available

#### Scenario: Unauthenticated user enters bookshelf in guest mode
- **WHEN** the bookshelf page loads and `/api/me` returns `authenticated: false`
- **THEN** the bookshelf page remains accessible in guest mode
- **AND** the UI limits capabilities to guest-safe actions instead of redirecting to the home page
