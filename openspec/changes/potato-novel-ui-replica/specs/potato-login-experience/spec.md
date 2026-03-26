## ADDED Requirements

### Requirement: The landing page SHALL present Potato Novel as an immersive parchment-branded login experience
The unauthenticated landing page SHALL use the shared paper shell, parchment background treatment, decorative blurred light pools, and a centered visual hierarchy that matches the supplied UI draft rather than a generic product demo hero.

#### Scenario: Unauthenticated users see the branded landing composition
- **WHEN** an unauthenticated user opens the root route
- **THEN** the page shows the potato icon block, product name, literary slogan, and the primary login call to action inside the paper-textured composition

#### Scenario: Authenticated users can continue into the bookshelf flow
- **WHEN** an already authenticated user opens the root route
- **THEN** the page preserves the same branded shell while offering a direct path into the bookshelf experience

### Requirement: The landing page SHALL include a tilted icon card and serif-first branding hierarchy
The landing page SHALL render the potato icon inside a floating white card with pronounced rounding and slight tilt, and SHALL render the product title and supporting slogan with a serif-led hierarchy that emphasizes literary tone over technical framing.

#### Scenario: Icon treatment matches the immersive brand direction
- **WHEN** the landing page is displayed
- **THEN** the icon appears inside a floating rounded card with subtle lift and slight rotation rather than as a flat inline emoji or badge

#### Scenario: Brand copy prioritizes title and slogan
- **WHEN** the landing page text is displayed
- **THEN** the main title is visually dominant and the supporting slogan appears as softer, spaced secondary text

### Requirement: The landing page SHALL provide a single large tactile login call to action
The login page SHALL present the main action as a full-width, dark-ink, large-radius button with pressed-state feedback and SHALL keep the current SecondMe OAuth initiation behavior behind that button.

#### Scenario: User starts login from the primary action
- **WHEN** an unauthenticated user taps the main login button
- **THEN** the frontend initiates the existing SecondMe login flow

#### Scenario: Login action remains visually prominent
- **WHEN** the landing page is rendered
- **THEN** no secondary action visually competes with the primary login button for the default unauthenticated path
