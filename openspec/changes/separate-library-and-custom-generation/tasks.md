## 1. Source Modeling

- [x] 1.1 Add or clarify a `source_type` marker so sessions can distinguish `library` and `custom`.
- [x] 1.2 Define the storage model for prebuilt library story packages.
- [x] 1.3 Define how custom story sessions persist their generated package payload.

## 2. Library Story Flow

- [x] 2.1 Add a backend read path for library story packages that does not invoke runtime generation.
- [x] 2.2 Add a start/resume session path for library stories that creates progress without regenerating content.
- [x] 2.3 Remove template-story dependence on `preload`, `regenerate`, and `hydrate` semantics during normal play.
- [x] 2.4 Update bookshelf wording so library cards express enter/continue semantics instead of download/cache semantics.

## 3. Custom Story Flow

- [x] 3.1 Add a dedicated custom story creation path separate from library story entry.
- [x] 3.2 Define a Doubao-only generation contract for custom stories.
- [x] 3.3 Split custom generation into two Doubao-backed steps: skeleton generation and prose/choices completion.
- [x] 3.4 Ensure a generated custom story enters reading as a ready-to-play package, not as a hydrate-driven partial package.
- [x] 3.5 Update custom-story UI wording to reflect generation rather than loading.

## 4. Unified Session Playback

- [x] 4.1 Define a unified session read contract for both library and custom stories.
- [x] 4.2 Define a unified `choose` progression contract that advances current node, path, and state without runtime generation in the template path.
- [x] 4.3 Preserve finalize/save/ending-analysis behavior across both story sources.

## 5. Cleanup and Validation

- [x] 5.1 Verify library stories no longer call model generation during normal entry or normal node progression.
- [x] 5.2 Verify custom stories only call Doubao during story creation, not during normal node progression.
- [x] 5.3 Verify story refresh, resume, back navigation, and completion remain understandable across both sources.
- [x] 5.4 Remove or deprecate obsolete UI and backend assumptions that every template story needs runtime hydration.
