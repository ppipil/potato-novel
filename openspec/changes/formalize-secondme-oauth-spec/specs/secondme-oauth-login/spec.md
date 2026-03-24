## ADDED Requirements

### Requirement: User can start SecondMe OAuth login from the demo frontend
The system SHALL let an unauthenticated user start the SecondMe OAuth flow from the frontend, and the backend SHALL create and store an OAuth state value before redirecting the browser to SecondMe.

#### Scenario: Login begins from the home page
- **WHEN** an unauthenticated user clicks the SecondMe login action on the home page
- **THEN** the browser is redirected to the backend login endpoint and then to the SecondMe authorization URL with `client_id`, `redirect_uri`, `response_type=code`, `scope`, and `state`

#### Scenario: Backend stores state before redirecting
- **WHEN** the backend handles a login request
- **THEN** it sets an `oauth_state` cookie before returning the redirect response to SecondMe

### Requirement: Frontend callback completes authentication through the backend
The system SHALL accept the OAuth callback on the frontend callback route, and the frontend SHALL send the returned `code` and `state` values to the backend exchange endpoint so the backend can complete token exchange and session creation.

#### Scenario: Frontend callback exchanges a valid authorization code
- **WHEN** the frontend callback route receives valid `code` and `state` query parameters from SecondMe
- **THEN** the frontend calls the backend `/api/auth/exchange` endpoint with those values and redirects the user to the bookshelf after the backend reports success

#### Scenario: Callback rejects missing or failed authorization data
- **WHEN** the frontend callback route receives an OAuth error or lacks `code` or `state`
- **THEN** the callback page shows an error state instead of continuing to the bookshelf

#### Scenario: Backend rejects state mismatches
- **WHEN** the backend exchange endpoint receives a `state` value that does not match the stored `oauth_state` cookie
- **THEN** it rejects the request and does not create a session

### Requirement: Successful exchange creates an authenticated session
The backend SHALL exchange the authorization code with SecondMe, retrieve user information, and create a signed session cookie that the frontend can use to determine whether the user is authenticated.

#### Scenario: Successful exchange sets a session cookie
- **WHEN** the backend exchange endpoint receives a valid code and the token and user info requests succeed
- **THEN** it returns a successful response, sets a signed `session` cookie, and clears the `oauth_state` cookie

#### Scenario: Session-backed identity is available to the frontend
- **WHEN** the frontend calls `/api/me` with a valid session cookie
- **THEN** the backend returns `authenticated: true` together with the current user's profile data

#### Scenario: Invalid session is treated as anonymous
- **WHEN** `/api/me` is called without a valid signed session cookie
- **THEN** the backend returns `authenticated: false`

### Requirement: Bookshelf access requires an authenticated session
The frontend SHALL treat the bookshelf as an authenticated area and SHALL redirect unauthenticated users away from it.

#### Scenario: Authenticated user enters the bookshelf
- **WHEN** the bookshelf page loads and `/api/me` returns `authenticated: true`
- **THEN** the bookshelf page renders the user identity, story-opening choices, and role choices

#### Scenario: Unauthenticated user is redirected out of the bookshelf
- **WHEN** the bookshelf page loads and `/api/me` returns `authenticated: false`
- **THEN** the frontend redirects the user back to the home page

### Requirement: User can log out and clear the demo session
The system SHALL let an authenticated user end the local demo session without requiring direct interaction with SecondMe.

#### Scenario: Logout clears the session cookie
- **WHEN** the user triggers logout from the bookshelf
- **THEN** the frontend calls the backend logout endpoint and the backend clears the `session` cookie

#### Scenario: Logged out user loses authenticated access
- **WHEN** a user logs out and then reloads the app
- **THEN** `/api/me` reports `authenticated: false` and the user must start login again to re-enter the bookshelf
