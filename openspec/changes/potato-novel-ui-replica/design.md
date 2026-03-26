## Context

The repository already has a working Vue 3 frontend, a FastAPI backend, SecondMe OAuth login, an authenticated bookshelf route, an interactive story session page, and a saved-story history view. What is missing is a coherent product-grade presentation layer: current screens use prototype styling, desktop-first spacing, and generic cards that do not match the provided parchment-style UI draft or the intended "interactive literary companion" tone.

This change is primarily a frontend presentation redesign, but it is cross-cutting because it affects shared tokens, page structure, component reuse, transitions, and how existing content is arranged inside the current authenticated flow. The backend session and OAuth boundaries should remain intact; the redesign should wrap the existing story/session data model rather than invent a new interaction contract unless a small frontend normalization layer is needed.

## Goals / Non-Goals

**Goals:**
- Establish a reusable paper-textured design system with explicit color, typography, shadow, radius, and animation tokens.
- Rebuild the four user-facing screens so they visually match the supplied UI/UX draft: login, bookshelf dashboard, interactive co-creation view, and read-only review view.
- Preserve the current SecondMe login flow, bookshelf entry flow, story session flow, and saved-story reading flow while changing presentation and interaction affordances.
- Enforce a mobile-first frame with centered desktop presentation, hidden scrollbars, safe-area padding, and tactile pressed states.
- Keep animation behavior intentional and lightweight, especially for story chunk reveal, loading dots, and bottom input dock transitions.

**Non-Goals:**
- Changing the backend authentication protocol, token exchange, or session ownership model.
- Redesigning the narrative generation contract, choice semantics, or multi-turn session lifecycle already covered by `interactive-fiction-mvp`.
- Building a reusable design system package outside this repository.
- Introducing a fully bespoke illustration pipeline or image asset management system for book covers in this change.

## Decisions

### Adopt Tailwind theme tokens plus CSS variables for textured and animated details
The implementation should introduce Tailwind theme extensions for the documented paper and accent palette, serif/sans font roles, max-width shell, radii, and shared shadows. CSS variables and a small global stylesheet should still own paper grain, blurred glow layers, hidden scrollbars, safe-area utilities, and keyframe animations because those effects are awkward to express only through utility classes.

Alternative considered: keep the current plain CSS approach and manually restyle each page. We are not choosing that because the design language is repeated across all screens, and Tailwind tokens make the eventual implementation more consistent with the user's requested frontend stack.

### Keep the current route and API structure, but remap each route to a dedicated mobile-frame page composition
The existing page routes already map well to the desired experience: `HomePage` becomes the landing/login screen, `BookshelfPage` becomes the home dashboard, `StoryResultPage` becomes the core interactive co-creation screen, and `StoryHistoryPage` becomes the read-only reading/review view. We should preserve those route responsibilities and rebuild their internal layout around a shared centered mobile shell.

Alternative considered: add new routes and keep the current pages as legacy flows. We are not choosing that because it would duplicate behavior and complicate navigation without changing the underlying user journey.

### Preserve OAuth and story-session contracts, and solve UI-fit issues with a frontend view-model layer
SecondMe login, story session start/continue/finalize, and saved story retrieval should keep their current backend contracts. If the new layouts require data shaping such as deriving display labels, turning transcript entries into visual reading blocks, or generating placeholder cover tints, that work should happen in the frontend view layer or helper functions instead of changing backend payload semantics.

Alternative considered: extend backend responses purely to serve presentation details. We are not choosing that for this change because the redesign target is visual fidelity, and the backend already provides the content needed to assemble the new views.

### Use a single shared "paper device" shell with page-specific overlays and sticky regions
All four pages should render inside the same max-width mobile frame with a warm paper background, subtle border, and desktop rounding to mimic a physical reading device or framed page. Decorative glow placement, sticky headers, and bottom glass docks should vary by page, but the base shell should be shared so the experience feels like one product instead of separate demo screens.

Alternative considered: let each page define its own container and background treatment. We are not choosing that because it would drift visually and make spacing inconsistencies likely.

### Treat story text as literary content first and interaction chrome second
In the interactive and review pages, serif body text, paragraph spacing, indentation, and generous line height should take priority over card-heavy UI chrome. User actions, save controls, and recommendation buttons should remain readable, but story prose should feel like the main object on screen rather than content inside generic widgets.

Alternative considered: keep the existing two-column dashboard-like story layout. We are not choosing that because the provided reference clearly favors a reading-first vertical composition.

### Differentiate active co-creation view from read-only review through action rendering, not a separate visual language
The review screen should inherit the same paper reading atmosphere and typographic system as the interactive screen, but past user actions should render as centered divider labels with dashed lines instead of right-aligned speech bubbles. This preserves continuity between "playing" and "reading back" while clearly signaling that the session is no longer awaiting input.

Alternative considered: build the history reader as a standard detail card with raw story text only. We are not choosing that because it discards the co-creation timeline structure and does not match the supplied reading-review concept.

## Risks / Trade-offs

- [Adding Tailwind to a currently CSS-driven frontend may create overlapping styling systems] -> Mitigation: define shared tokens once, migrate page-by-page, and keep global CSS limited to primitives Tailwind cannot express cleanly.
- [Pixel-faithful recreation may expose gaps between current content shapes and the screenshot layout] -> Mitigation: allow lightweight frontend-derived view models for labels, cover tints, and empty states without changing backend contracts.
- [Heavy blur, texture, and shadows could hurt low-end mobile performance] -> Mitigation: use static layered backgrounds, limit animated blur regions, and keep transitions to opacity/transform where possible.
- [A bottom glass input dock can obscure story content on short screens] -> Mitigation: require large bottom padding in the story flow and safe-area-aware footer spacing.
- [The saved-story payload may not yet preserve user actions separately enough for divider-style review rendering] -> Mitigation: document this dependency clearly and, if needed during implementation, derive readable action separators from transcript/history metadata before considering backend changes.

## Migration Plan

1. Add the visual foundation first: Tailwind/theme wiring, font loading, paper tokens, shared shell, motion primitives, and utility classes such as hidden scrollbars.
2. Rebuild the login and bookshelf pages on top of the shared shell so the authenticated entry flow matches the new brand language.
3. Rebuild the interactive story page with reading-first layout, sticky/frosted header, and bottom action dock while keeping the current continuation logic intact.
4. Rebuild the saved-story review page using the same reading shell but with centered action dividers and no editable footer.
5. Verify login, story creation, multi-turn continuation, save, and story review flows end to end after the visual rewrite.

## Open Questions

- During implementation, should the bookshelf's template cards use static local cover color blocks, generated gradients, or future real thumbnails as the default visual placeholder?
- Does the saved-story history currently retain enough per-turn structure to render user-action divider labels directly, or will the first implementation need to reconstruct that structure from transcript metadata?
- Should the "保存书架" affordance on the interactive page save immediately every time it is tapped, or remain gated by the current minimum-turn save rule and visually explain disabled state?
