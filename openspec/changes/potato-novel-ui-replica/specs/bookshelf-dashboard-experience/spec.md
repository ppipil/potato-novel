## ADDED Requirements

### Requirement: The bookshelf dashboard SHALL use a reading-first mobile home layout
The authenticated bookshelf page SHALL render as a vertically stacked mobile dashboard with a sticky top region, generous paper spacing, and section groupings that match the supplied "我的宇宙" and "开启新篇章" composition.

#### Scenario: Bookshelf opens into the dashboard home
- **WHEN** an authenticated user enters the bookshelf route
- **THEN** the page shows a welcome header, the personal universe shelf, and the story-start area in one vertically scrollable reading layout

#### Scenario: Top identity remains available while browsing
- **WHEN** the user scrolls the bookshelf page
- **THEN** the header region remains visually anchored at the top of the page

### Requirement: The dashboard SHALL render the "我的宇宙" section as a horizontal book shelf
The bookshelf dashboard SHALL display saved or resumable story items as horizontally scrollable book cards with a 2:3 ratio, simulated book spine, lower title mask, round-count badge, and hidden scrollbar.

#### Scenario: Shelf items appear as book-like cards
- **WHEN** one or more story items are available for the personal universe section
- **THEN** each item renders as a vertical book card with cover tint, spine line, bottom title area, and turn-count badge

#### Scenario: Shelf remains usable on mobile
- **WHEN** the personal universe row overflows the viewport width
- **THEN** the user can scroll the row horizontally without seeing native scrollbar chrome

### Requirement: The dashboard SHALL provide a free-creation composer card
The bookshelf dashboard SHALL include a prominent free-creation card with serif-forward copy, a large textarea on a paper-toned inset surface, decorative glow detail, and a clear entry action for starting a story from custom text.

#### Scenario: User starts from a custom opening
- **WHEN** the user enters a custom opening in the free-creation card and activates the entry action
- **THEN** the existing story-session start flow uses that custom opening

#### Scenario: Composer placeholder supports literary prompting
- **WHEN** the custom opening textarea is empty
- **THEN** it displays a story-like placeholder that encourages the user to describe identity and opening situation in literary language

### Requirement: The dashboard SHALL render recommended openings as stacked template cards
The bookshelf dashboard SHALL show recommended story openings as vertically stacked cards with a category tag, serif title, line-clamped hook text, and a colored identification strip or block that distinguishes card variants.

#### Scenario: Template cards preserve quick scanning
- **WHEN** multiple recommended openings are shown
- **THEN** each card exposes its genre label, title, and short hook without requiring the user to expand the full description

#### Scenario: Template selection starts the existing story flow
- **WHEN** the user selects a recommended opening card and proceeds
- **THEN** the chosen opening is used to start the interactive story session
