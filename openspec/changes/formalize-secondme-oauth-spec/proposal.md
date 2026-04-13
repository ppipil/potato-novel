## Why

SecondMe OAuth requirements for this project are currently spread across the README, setup notes, and implementation guidance. We need a single OpenSpec change that captures the confirmed login behavior so Codex can implement and evolve the demo without drifting from the documented flow.

## What Changes

- Define a first-class spec for the current SecondMe OAuth login flow used by the Potato Novel demo.
- Document the callback contract where the frontend receives `code` and `state`, then calls the backend exchange endpoint to finish authentication.
- Document the session-backed bookshelf access and logout behavior that the frontend and backend must preserve.
- Record the current scope boundaries so future work such as MCP or a backend-owned callback can be proposed separately.

## Capabilities

### New Capabilities
- `secondme-oauth-login`: Covers login initiation, callback handling, token exchange, session establishment, bookshelf access, and logout for the current demo flow.

### Modified Capabilities

## Impact

- Affects [README.md](/Users/pipilu/Documents/Projects/potato-novel/README.md) and [docs/integrations/secondme.md](/Users/pipilu/Documents/Projects/potato-novel/docs/integrations/secondme.md) as the source documents for confirmed requirements.
- Affects backend auth endpoints in [backend/app/main.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/main.py) and session signing helpers in [backend/app/security.py](/Users/pipilu/Documents/Projects/potato-novel/backend/app/security.py).
- Affects frontend routes and auth interactions in [frontend/src/routes.js](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/routes.js), [frontend/src/views/CallbackPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/CallbackPage.vue), [frontend/src/views/HomePage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/HomePage.vue), and [frontend/src/views/BookshelfPage.vue](/Users/pipilu/Documents/Projects/potato-novel/frontend/src/views/BookshelfPage.vue).
