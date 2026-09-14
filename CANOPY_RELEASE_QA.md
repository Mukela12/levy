# Canopy release QA, 14 September 2026

Status: implementation and verification in progress. Not yet deployed.

## Test identity

The owner explicitly authorized creating a dedicated QA account. Created
`levy-qa-canopy-20260914@levylegal.ai` with display name `Levy Canopy QA`
and `user_metadata.is_qa = true`. Exclude this account, the existing
`levy-qa-probe@levylegal.ai`, and the owner's account from product analytics.
No shared probe password was reset. No credentials belong in this file.

## Verified so far

- Local Canopy sign-in through the normal browser login form succeeds.
- Authenticated welcome screen exposes uploads, library attachments and review mode.
- First question creates a saved chat and navigates to its persistent URL.
- Real backend tool activity reaches the saved conversation.
- Saved conversations and generated document cards survive navigation and reload.
- Citation badge opens its explanation and the Employment Code Act PDF renders (79 pages).
- Generated QA PDF and Word exports saved to Downloads as valid PDF/OOXML files.
- Authenticated artifact text loads and is readable.
- IRAC generation completes; closing and reopening retains the generated analysis.
- Five-step illustrated tour progresses through all steps, finishes, and replays from Profile.
- Welcome starters prefill an editable question without starting a billed run.
- Study launcher seeds the correct quiz prompt; real quiz generation and grading work (1/1, 100%).
- Synthetic PDF upload completes, attachment chip appears, and Save to library succeeds.
- Fictional Matter creation and saving notes survive a full page reload.
- Eleven automated source-model and UI-boot regressions pass.
- Full lint and typecheck pass with zero errors or warnings after cleanup.
- Production build passes with 931 generated pages (rerun after final release edits).
- Current production LLM health check reports Sonnet healthy.
- Typecheck and targeted lint passed after initial layout fixes (one existing warning).

## Changes under test

- Removed the duplicate legacy Brief aside from the new Canopy chat route.
- Removed the full-width backing behind the floating composer.
- Fixed nested paragraph markup in the composer disclaimer.
- Stream following no longer repeatedly starts smooth scrolling.
- Upload errors are visible; send waits for the attachment to finish.
- Theme boot survives unavailable local storage; theme updates stay consistent.
- Explicit UI switching updates the query override as well as storage.
- Fixed existing application lint errors; excluded the vendored PDF worker from lint.
- Fixed mobile dock covering Study actions and added measured composer clearance.
- Unified source/gallery dialog focus handling and retained the responsive Brief instance.
- Removed hard-coded professional plan/role claims from Profile.

## Release configuration

Canopy is the default UI. `?ui=legacy` remains a browser-level escape hatch;
`NEXT_PUBLIC_UI_VARIANT=legacy` remains a build-level rollback option.
The exact Vercel project was verified after the owner signed in again:
`mukelas-projects/levy`, project `prj_Nn5TSsBSBpTLfYgDkATSHm2Sw6vZ`, root `frontend`.
Vercel's deployment dry run excludes both local environment files.
Latest main (`54c748f`) was merged into the integration branch without discarding changes.

## Separate pre-existing data/behavior findings

- Employment Code retrieval labels include `Section 8 · Part XI · p.70–71`,
  but the original PDF page 70 displays the First Schedule. PDF rendering and
  authority identity matching work; passage metadata requires a corpus audit.
- Study's model response revealed revision explanations before quiz submission.
  The interactive grading itself worked. This is prompt/model behavior, not a
  successful assessment of the legal correctness of its answer.
- Documents currently labels the returned first 1,000 records as the global
  library count. Do not use that number as a complete corpus analytics total.

These findings prevent claiming that all legal answers or corpus metadata are verified.

## Remaining release gates

- Complete signed-in chat, reload/persistence, citations and PDF/download tests.
- Verify Study Mode, documents, templates, matters, search and profile.
- Complete visual comparison against the recovered Canopy design digest,
  including onboarding, desktop/mobile, both themes and keyboard accessibility.
- Run fresh full lint, typecheck and production build after final edits.
- Reconcile current main changes without losing the existing worktree edits.
- Verify deployment project, publish, then smoke-test the deployed release.
- Write the final Claude handoff with actual results and remaining limitations.

Historical results are not evidence that the current release passed these gates.
