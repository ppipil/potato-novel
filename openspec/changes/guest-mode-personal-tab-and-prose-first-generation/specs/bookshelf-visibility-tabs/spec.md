## ADDED Requirements

### Requirement: Bookshelf SHALL provide Public and Mine tabs
The bookshelf dashboard SHALL provide two top-level tabs: `公共` and `我的`, and the active tab SHALL control which story collection is visible.

#### Scenario: User opens bookshelf
- **WHEN** a user enters the bookshelf page
- **THEN** the UI shows a `公共` tab and a `我的` tab
- **AND** only one tab collection is visible at a time

### Requirement: Public tab SHALL show shared stories only
The `公共` tab SHALL show stories intended for all users, such as shared library templates, and SHALL NOT include private user-generated stories.

#### Scenario: Viewing public tab
- **WHEN** a user switches to `公共`
- **THEN** the list contains only shared/public story items
- **AND** private stories from any user are excluded

### Requirement: Mine tab SHALL be user-scoped and private
The `我的` tab SHALL show only stories visible to the current viewer context.

#### Scenario: Authenticated user views mine tab
- **WHEN** an authenticated user switches to `我的`
- **THEN** the list includes only that user's private generated stories (plus local unsynced drafts if present)
- **AND** stories from other users are not visible

#### Scenario: Guest user views mine tab
- **WHEN** a guest user switches to `我的`
- **THEN** the list includes only locally stored guest stories for the current browser context
- **AND** no other user's stories are visible

### Requirement: Free-created stories SHALL appear in Mine tab
Any story created from freeform custom opening SHALL be categorized as a personal story and displayed in `我的`.

#### Scenario: Authenticated user creates a freeform story
- **WHEN** an authenticated user completes freeform generation
- **THEN** the new story appears in `我的`
- **AND** it does not appear in `公共` by default

#### Scenario: Guest user creates a freeform story
- **WHEN** a guest user completes freeform generation
- **THEN** the new local story appears in `我的`
- **AND** it is not visible to other users
