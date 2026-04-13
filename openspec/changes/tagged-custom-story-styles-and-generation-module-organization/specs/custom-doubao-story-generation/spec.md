## CHANGED Requirements

### Requirement: Custom story generation SHALL treat styleTag as the primary creative control
The custom-story pipeline SHALL accept a required `styleTag` and MUST use it as the main driver for structure, prose, and option tone instead of treating style as an incidental note embedded in the opening text.

#### Scenario: Style tag is submitted as a first-class generation field
- **WHEN** a user submits a custom story request
- **THEN** the frontend SHALL send `styleTag` as a dedicated field
- **AND** the backend SHALL propagate that field through skeleton selection, node prose prompt construction, and node choice prompt construction

#### Scenario: Different tags produce materially different story shapes
- **WHEN** two custom stories share a similar opening but use different tags such as `悬疑` and `搞笑`
- **THEN** the generated package SHALL differ in conflict framing, prose tone, and ending affordances
- **AND** the result SHALL not be limited to superficial vocabulary substitutions

### Requirement: Custom story generation SHALL keep supplemental note as secondary guidance
Any freeform note supplied with the request SHALL act as a localized creative adjustment, but it MUST NOT override the primary style classification contract represented by `styleTag`.

#### Scenario: Note refines but does not replace style tag
- **WHEN** a user selects `恐怖` and adds an optional note about setting or relationship details
- **THEN** the generated story SHALL still read as a horror-oriented experience first
- **AND** the note SHALL only refine setting, imagery, boundaries, or desired motifs within that style
