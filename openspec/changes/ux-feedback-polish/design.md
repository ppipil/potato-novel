## Context

The current UX baseline already implements a paper-style reading shell and local package progression, but user feedback highlights a second-phase polish need: density, pacing, and reliability under real waiting conditions. The product should preserve the existing architecture (Vue + FastAPI, local package playback, session save flow) while improving ergonomic and perceptual quality.

This is primarily a frontend experience change with a small backend prompt adjustment to improve content depth.

## Goals / Non-Goals

**Goals**
- Increase information density without sacrificing readability.
- Avoid trapping users in blocking loading overlays for long generation tasks.
- Provide explicit, actionable error feedback for slow or failed generation.
- Improve top-bar legibility across scrolling content.
- Guarantee predictable auto-scroll behavior during active play.
- Keep situation notes contextual to the current node presentation.
- Extend narrative depth so story progression does not feel abrupt.

**Non-Goals**
- Replacing the story package architecture or changing session ownership models.
- Introducing streaming generation infrastructure in this pass.
- Redesigning route structure or authentication flow.

## Decisions

### Compact editorial density for active play and dashboard cards
Reduce option card padding, footer dock spacing, oversized title scale, and template-card dimensions while preserving typography contrast and tap targets.

### Non-blocking waiting experience on bookshelf generation actions
Move generation feedback from full-screen lock to in-page progress messaging with recoverable actions, allowing users to continue exploring while requests are pending.

### Explicit failure language for timeout and unstable network
Standardize user-facing error copy to distinguish timeout, network interruption, and backend failure, each with clear next actions.

### Strengthened frosted header readability
Keep translucent style but pair it with stronger blur and background opacity so overlapping text is visually separated from scroll content.

### Deterministic scroll anchoring in story flow
Use a dedicated bottom anchor and trigger scroll updates on node switch, reveal-step increment, and dock readiness changes.

### Situation note as current-turn context
Show `directorNote` as a current node context panel rather than retaining it as repeated historical blocks through the entire transcript view.

### Longer prose requirements per generated node
Relax fixed short-scene constraints and require richer node prose (more paragraph depth and stronger closure in ending nodes) to improve narrative pacing.

## Risks / Trade-offs

- More compact spacing can reduce visual breathing room if over-applied.
  - Mitigation: keep prose line height and paragraph rhythm stable while reducing card chrome first.
- Non-blocking generation can create state complexity around repeat clicks.
  - Mitigation: keep one active generation request per opening and show deterministic state labels.
- Longer prose requirements can increase generation latency.
  - Mitigation: adjust only content depth constraints, not broad model orchestration.

## Migration Plan

1. Update OpenSpec requirements for bookshelf, active reading, and custom-generation feedback.
2. Implement compact density and header readability polish in frontend views.
3. Implement deterministic auto-scroll and context-only situation note behavior.
4. Implement non-blocking loading + actionable failure UI copy.
5. Tune backend prose prompt constraints for longer narrative depth.
6. Validate end-to-end flows on mobile viewport and long-wait scenarios.
