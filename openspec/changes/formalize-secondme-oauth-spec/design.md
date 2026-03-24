## Context

The repository already contains a working SecondMe OAuth demo implemented with a Vue 3 frontend and a FastAPI backend. The current confirmed flow is:

1. The frontend sends the user to the backend login endpoint.
2. The backend redirects the browser to SecondMe and stores an `oauth_state` cookie.
3. SecondMe redirects back to the frontend callback route at `/api/auth/callback`.
4. The frontend callback page POSTs `code` and `state` to the backend `/api/auth/exchange` endpoint.
5. The backend validates `state`, exchanges the authorization code for a token, fetches user info, and writes a signed session cookie.
6. The frontend uses `/api/me` to gate access to the bookshelf and uses `/api/auth/logout` to clear the session.

Repository docs also describe a preferred long-term architecture where the backend receives the OAuth callback directly, but that is not the current behavior in code.

## Goals / Non-Goals

**Goals:**
- Capture the current OAuth demo behavior as a stable capability.
- Make backend security boundaries explicit, especially around `Client Secret`, state validation, and signed session cookies.
- Give future Codex runs a clear contract for implementation and validation.

**Non-Goals:**
- Migrating the callback from the frontend to the backend.
- Defining MCP, integration review, or release workflows.
- Redesigning the bookshelf or story-generation experience beyond its auth dependency.

## Decisions

### Preserve the current frontend callback flow
The spec will treat the current frontend callback route as the source of truth because it matches the repository code and the README. This avoids forcing a partially implemented architecture shift into the first OpenSpec change.

Alternative considered: specify the backend callback flow immediately. We are not choosing that here because it would conflict with the running demo and mix requirement capture with an architectural migration.

### Keep sensitive OAuth operations on the backend
The backend remains responsible for `Client Secret` usage, authorization-code exchange, user info retrieval, and session creation. The frontend may receive public query parameters from SecondMe, but it must not perform token exchange itself.

Alternative considered: exchanging tokens directly from the browser. We are not choosing that because it would expose backend-only credentials and weaken the current security model.

### Model authentication as a session-backed capability
The spec will define successful authentication in terms of a valid backend-signed session cookie and an authenticated `/api/me` response. This aligns with the current bookshelf guard and gives future UI work a stable integration point.

Alternative considered: specifying direct token use by the frontend. We are not choosing that because the current code already uses an opaque session cookie and the demo does not require frontend token management.

## Risks / Trade-offs

- [Current callback split across frontend and backend] -> Mitigation: document the exact handoff contract now and isolate a future callback migration into its own change.
- [Platform settings may later favor a backend callback URI] -> Mitigation: keep the current flow explicit in the spec and treat callback relocation as follow-up work, not an unspoken assumption.
- [Docs contain both current and preferred callback architectures] -> Mitigation: mark this change as formalizing the current confirmed implementation, while leaving long-term improvements out of scope.
