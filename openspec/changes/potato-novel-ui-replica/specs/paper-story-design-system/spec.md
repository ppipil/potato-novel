## ADDED Requirements

### Requirement: The frontend SHALL provide a shared paper-textured visual system
The frontend SHALL define a reusable design system for Potato Novel that includes the documented paper background colors, ink text colors, amber accent colors, serif/sans font roles, shared radii, and shared shadow tokens so all primary pages render within the same visual language.

#### Scenario: Shared tokens are available to all primary pages
- **WHEN** the login, bookshelf, interactive reading, and review pages render
- **THEN** each page uses the same named paper, ink, and accent tokens rather than page-specific ad hoc color values

#### Scenario: Typography roles remain consistent
- **WHEN** headings, story prose, system labels, and action controls are rendered
- **THEN** literary titles and narrative text use the serif role and system controls or metadata use the sans-serif role

### Requirement: The application SHALL render inside a mobile-first framed reading shell
The frontend SHALL present the application inside a centered mobile-first shell with a maximum width equivalent to `max-w-md`, and SHALL apply large desktop rounding plus a light outer border to simulate a physical device or framed page on larger screens.

#### Scenario: Mobile layout fills the viewport naturally
- **WHEN** the application is opened on a narrow viewport
- **THEN** the page content fills the available width with mobile-first spacing and no desktop-only framing assumptions

#### Scenario: Desktop layout preserves the mobile reading frame
- **WHEN** the application is opened on a wider viewport
- **THEN** the content is centered inside a bounded shell with rounded outer corners and a light border

### Requirement: The frontend SHALL include shared paper texture, hidden scrollbar, and safe-area utilities
The frontend SHALL provide global utilities for subtle paper texture, decorative blurred glows, hidden scrollbars, and `env(safe-area-inset-bottom)` padding so page-specific implementations do not recreate those primitives inconsistently.

#### Scenario: Scroll containers hide platform scrollbars
- **WHEN** a horizontally or vertically scrollable region such as the bookshelf shelf is rendered
- **THEN** the container remains scrollable while its visible scrollbar chrome is hidden

#### Scenario: Footer regions respect device safe areas
- **WHEN** a bottom-aligned input or action region is rendered on a device with a bottom safe area
- **THEN** the region includes safe-area padding so controls are not clipped against the viewport edge

### Requirement: Shared animation primitives SHALL be available for story interaction states
The frontend SHALL define reusable animation primitives for typing dots, chunk-in reveal, slide-up footer appearance, and pressed-state scaling so interactions feel tactile and consistent across the product.

#### Scenario: New story content enters with chunk-in motion
- **WHEN** newly generated story paragraphs or recommended actions appear
- **THEN** they animate upward from a small vertical offset while fading from transparent to opaque

#### Scenario: Clickable surfaces provide tactile feedback
- **WHEN** a user presses a button, card, or selectable action
- **THEN** the surface visually compresses through an active-state scale effect
