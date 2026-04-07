## 1. Backend Template Structure

- [x] 1.1 Add a backend story-template builder that returns a fixed high-drama package skeleton for a given opening and role.
- [x] 1.2 Define template-level node beats, ending types, and state-routing metadata so package validation no longer depends on runtime skeleton generation.
- [x] 1.3 Keep the generated package compatible with the current local playback contract used by the frontend.

## 2. Split Generation Providers

- [x] 2.1 Refactor story package generation so SecondMe `act/stream` only receives node-level choice-generation prompts.
- [x] 2.2 Add a separate prose-generation provider configuration for the Volcano model, including local env loading and deployment-friendly env names.
- [x] 2.3 Implement node hydration with the new prose provider while preserving the current node normalization and fallback behavior.

## 3. Dramatic Runtime Output

- [x] 3.1 Update choice-generation prompts and post-processing so each node returns three visibly different dramatic strategies.
- [x] 3.2 Update prose-generation prompts and normalization so node text stays inside the backend-defined beat and reads more like a dramatic or comedic interactive-novel scene.
- [x] 3.3 Verify state progression and ending routing still work correctly with the new template-driven package flow.

## 4. Validation And Developer Workflow

- [x] 4.1 Add a local test script or equivalent developer workflow for validating the separate prose provider without committing secrets into the repo.
- [x] 4.2 Document the new env-variable requirements and branch-local testing workflow for the split generation setup.
- [x] 4.3 Run `openspec validate template-driven-story-generation --strict` and resolve any schema or spec-format issues.
