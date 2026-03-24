## 1. Confirm And Align Auth Requirements

- [ ] 1.1 Review the proposal, design, and spec against the current repository docs and keep the current frontend-callback flow as the confirmed baseline.
- [ ] 1.2 Resolve whether the preferred backend-callback architecture should remain a follow-up change rather than being mixed into this one.

## 2. Align Implementation With The Spec

- [ ] 2.1 Verify backend login, exchange, session, `/api/me`, and logout behavior against the `secondme-oauth-login` requirements.
- [ ] 2.2 Verify frontend home, callback, and bookshelf flows against the `secondme-oauth-login` requirements, including error handling and redirect behavior.

## 3. Validate The Demo Flow

- [ ] 3.1 Run a local OAuth smoke test from login through bookshelf access using real SecondMe credentials in local environment variables.
- [ ] 3.2 Capture any requirement gaps discovered during smoke testing as either spec edits to this change or a follow-up change.
