## 1. Reading Rhythm And Text Segmentation

- [x] 1.1 Refactor the story reading state flow so final-paragraph reveal and choice-dock appearance happen in two explicit steps.
- [x] 1.2 Update story auto-scroll triggers to wait until prose reveal completes before anchoring to the option dock.
- [x] 1.3 Replace sentence-period fallback splitting with a more conservative paragraph parser that preserves explicit line breaks and quoted dialogue integrity.

## 2. Custom Creation Input And Failure Feedback

- [x] 2.1 Add an optional style/direction input to the bookshelf free-creation composer without breaking the current quick-start flow.
- [x] 2.2 Extend custom generation request payloads and backend prompt construction so style guidance participates in story generation.
- [x] 2.3 Normalize timeout, network, and backend-failure messages for custom generation and show actionable retry feedback in the bookshelf UI.

## 3. Save Idempotency And Bookshelf Sync Feedback

- [x] 3.1 Update the story result save action to expose stable saving, saved, and local-only fallback states for completed sessions.
- [x] 3.2 Add duplicate-submit protection on the frontend so the same completed session cannot be saved repeatedly from the result page.
- [x] 3.3 If needed, enforce completed-session save idempotency in story save service/repository code rather than adding new business logic to `backend/app/main.py`.

## 4. Code Boundary And Documentation Cleanup

- [x] 4.1 Keep all backend changes in route/service/provider/parser modules and avoid expanding `backend/app/main.py`.
- [x] 4.2 Add missing Chinese module headers or function docstrings in backend files touched by this change where they do not yet meet the existing documentation standard.

## 5. Validation

- [ ] 5.1 Validate that long multi-paragraph turns no longer skip the last paragraph before options appear.
- [ ] 5.2 Validate that quoted dialogue and narrative beats are not awkwardly split into micro-paragraphs.
- [ ] 5.3 Validate custom generation pending/failure states under slow and interrupted network conditions.
- [ ] 5.4 Validate that repeated save attempts for the same completed session do not create duplicate bookshelf entries.
