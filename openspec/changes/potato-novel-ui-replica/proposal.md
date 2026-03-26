## Why

The current Potato Novel frontend delivers the interactive fiction flow, but its visual language and interaction details still feel like a functional prototype rather than the immersive paper-textured reading product shown in the UI/UX draft. We need a spec-first change that locks down the landing page, bookshelf, interactive play view, and read-only review presentation before implementation so the frontend rewrite can target a consistent pixel-faithful experience.

## What Changes

- Define a paper-textured visual system for Potato Novel, including parchment background colors, ink text colors, amber accent colors, serif/sans typography roles, mobile frame constraints, and reusable shadows.
- Define the landing/login screen presentation, including textured background, blurred decorative glows, tilted potato icon card, serif branding, and large tactile login button.
- Define the bookshelf dashboard presentation, including sticky header, horizontally scrollable "我的宇宙" book shelf, free-creation card, and vertically stacked opening template cards.
- Define the interactive co-creation page presentation, including frosted header, serif story flow, right-aligned user action bubbles, bottom glass input dock, recommendation buttons, and animated reveal/loading behavior.
- Define the read-only review page presentation so user actions become centered divider labels instead of chat bubbles while preserving the same literary reading atmosphere.
- Define motion and feedback requirements for typing dots, chunk-in transitions, slide-up footer behavior, hidden scrollbars, and pressed-state scaling across clickable surfaces.

## Capabilities

### New Capabilities
- `paper-story-design-system`: Covers shared color, typography, container, texture, and motion primitives used across the Potato Novel frontend.
- `potato-login-experience`: Covers the landing/login page layout, decorative treatment, branding hierarchy, and login CTA behavior.
- `bookshelf-dashboard-experience`: Covers the bookshelf home header, horizontal book shelf cards, free-creation composer, and opening template list presentation.
- `interactive-story-reading-experience`: Covers the co-creation page header, story text layout, user action bubble styling, recommended action area, custom input dock, and loading/reveal transitions.
- `story-review-reading-experience`: Covers the read-only review page layout and centered divider treatment for previously chosen user actions.

### Modified Capabilities

## Impact

- Affects shared frontend styling and theme setup in [frontend/src/styles.css](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/styles.css), [frontend/index.html](/Users/pipilu/Documents/Projects/potato-novel/frontend/index.html), and frontend build configuration such as Tailwind or equivalent theme wiring if introduced.
- Affects page-level Vue views including [frontend/src/views/HomePage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/HomePage.vue), [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue), [frontend/src/views/StoryResultPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryResultPage.vue), and [frontend/src/views/StoryHistoryPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/StoryHistoryPage.vue).
- May require minor frontend data-shape normalization so existing session, template, and saved-story content can render within the new page structures without changing the backend interaction model.
