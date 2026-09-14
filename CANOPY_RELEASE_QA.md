# Canopy release QA, 14 September 2026

Status: local implementation and core workflow QA complete; production deployment blocked by Vercel commit-author permissions. Live domain unchanged.

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
- Fictional Matter links to the saved QA conversation.
- Document folder creation and Word template import succeed; the imported card is visible.
- Eleven automated source-model and UI-boot regressions pass.
- Full lint and typecheck pass with zero errors or warnings after cleanup.
- Final production build passes with 931 generated pages after the release edits.
- Current production LLM health check reports Sonnet healthy.
- Final welcome scene checked at desktop 1440x900 and mobile 320x740 in both themes.
- Background and citation dialogs open from keyboard and close with Escape; gallery returns focus to its opener.

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
- Fixed the photo shading layer being painted behind the background images.

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
- Password-reset redirect points to `/auth/reset-password`, which is absent from
  the build routes. Password recovery has not been verified and needs separate repair.

These findings prevent claiming that all legal answers or corpus metadata are verified.

## Deployment blocker

Candidate for code commit `e3f91f1`:
`https://levy-27eg5wjve-mukelas-projects.vercel.app`
Deployment ID: `dpl_7msfLL6771MVt4GBuJ1bVFuQUiJb`.
Vercel API reports `BLOCKED`, seat block `TEAM_ACCESS_REQUIRED`, with reason:
"The deployment was blocked because the commit author doesn’t have permission to create deployments for this project."

CLI login is `mukela12`. Commit author email is `mukela.j.katungu@gmail.com`;
the Vercel account primary email is `mukelathegreat@gmail.com`. This difference
is a diagnostic clue, not proof of the missing link: GitHub verified email access
is unavailable to the current gh token. The owner should verify GitHub `Mukela12`
is connected to Vercel and the commit email is recognized by that identity.
Do not rewrite authors or strip git metadata to bypass this control.

The initial candidate `dpl_FGHQksGV6CyxSqSPxzLoQ8uz3ga5` was also blocked.
Neither candidate was promoted. The CLI's "Building" output did not mean a build
was running: the read-only deployment API exposed the actual blocked state.

## Remaining release gates

- Owner resolves Vercel commit identity/team authorization; redeploy candidate.
- Verify hosted sign-in, saved QA chat, citation viewer and actual PDF/Word downloads.
- Finish hosted search, legislation, anonymous path and responsive smoke checks.
- Promote only a ready, verified candidate; fast-forward clean main and push the verified release.
- Confirm live domain serves Canopy and update the handoff with deployment evidence.

Historical results are not evidence that the current release passed these gates.
