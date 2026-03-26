## 1. Backend Story Package Contract

- [x] 1.1 Define the persisted interactive story package schema, including nodes, choices, choice impacts, next-node links, ending nodes, and package status metadata
- [x] 1.2 Implement backend generation and normalization for a 4-6 turn story package created from opening, role, and authenticated user context
- [x] 1.3 Add backend validation that rejects packages missing exact three-choice playable nodes, valid node links, or at least one reachable ending
- [x] 1.4 Add backend endpoints for preloading, fetching, and explicitly regenerating a story package

## 2. Frontend Bookshelf Preload Flow

- [x] 2.1 Update the bookshelf entry flow to request package preloading once the user has a usable opening and role
- [x] 2.2 Show package readiness and regeneration states on the bookshelf so users can tell whether entry should be instant
- [x] 2.3 Reuse a ready package when the user opens a story and route to the active story page with that package context

## 3. Frontend Local Playback Flow

- [x] 3.1 Refactor the active story page to read a story package and advance nodes locally instead of calling per-turn continuation APIs
- [x] 3.2 Apply per-choice relationship/persona deltas locally and reflect the resulting state during the run
- [x] 3.3 Remove custom free-text action input from active play and keep the UI constrained to the three packaged choices
- [x] 3.4 Compile a completed local path into a finalized story artifact that can be saved and reopened from history

## 4. Ending Analysis and Cleanup

- [x] 4.1 Update the ending-analysis request contract to use the completed package path and final state after a local ending
- [x] 4.2 Render normalized ending analysis fields, including potato persona labels and next-universe recommendation, in active and history views
- [x] 4.3 De-emphasize or remove legacy per-turn continuation usage once the preload package flow is working end to end
