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

## Refinement pass following design feedback

The user did not accept the earlier port as visually complete. The new local
pass is documented in `CANOPY_CLAUDE_HANDOFF.md`; do not call full parity done.

Confirmed during this pass:

- Research menu selected state and keyboard interaction; borderless Web states.
- Full-width neutral banner at 1440px; readable wrapping at 320px.
- Example modal selection and sourced-question detail/selection without sending.
- Source question disappears while typing; selected question receives input focus.
- Study format and subject selection; existing Study flow remains in place.
- Document folder dropdown, selected check and Escape at 320px.
- Fixed document title/actions collision and Upload contrast found in browser QA.
- Brief opens from the new scales action; scales and case optimized images render.
- Five mocked backend naming tests pass: validation, first exchange, manual title
  protection, later-turn exclusion and provider-failure fallback.
- Thirteen frontend tests pass, including source/date validation and RGBA assets.
- Lint and typecheck pass. Production build generated 931 pages.

Test command is `node --test tests/*.test.mjs`, not `npm test` (no script exists).
The attempted npm-test command failed before running tests, then the actual test
runner was invoked successfully. Naming tests do not prove live provider or
production integration. Source-date tests are structural, not legal verification.

New assets are inside `frontend/public/assets/canopy-actions/`; no developer-cache
URLs are referenced. Missing static imports fail the build. Hosted optimized image
requests must still be checked after Vercel authorization is resolved.

## Remaining release gates

Second screenshot-led pass: topbar account/status removal, default mutually
exclusive In Focus/actions, mobile disclaimer removal, 10px latest-response
clearance, Study selector layout, Matter search, and Canopy legislation shell.
See handoff for exact viewport measurements and remaining screen differences.
Legislation filtering returns one Employment Code result and its detail link
opens in the same shell. An unauthenticated HTTP check confirms server-rendered
Act names/links and canonical URL still appear in HTML. Profile remains reachable
through navigation. No real-device keyboard or production-hosted test is claimed.
Final lint, typecheck, all 17 frontend tests and the 931-page production build pass.
The empty Matter-filter state and clearing it were checked with synthetic QA data.
At 320px, In Focus button backgrounds/backdrop filters are none and the page has
no horizontal overflow. Closing the card focuses Show a question; examples open
and dismiss with Escape. No backend/corpus writes were performed in this pass.

- Owner resolves Vercel commit identity/team authorization; redeploy candidate.
- Finish screen-by-screen prototype acceptance, especially supporting-screen
  structure beyond the shared typography/control pass.
- Deploy and smoke-test backend chat naming separately; it is not a frontend feature alone.
- Verify hosted sign-in, saved QA chat, citation viewer and actual PDF/Word downloads.
- Finish hosted search, legislation, anonymous path and responsive smoke checks.
- Promote only a ready, verified candidate; fast-forward clean main and push the verified release.
- Confirm live domain serves Canopy and update the handoff with deployment evidence.

Historical results are not evidence that the current release passed these gates.

## Third refinement evidence (14 September)

Real Haiku naming plus Supabase persistence and manual-rename preservation passed
through the opt-in `scripts/qa_chat_titles_live.py` fixture. No real user's content
was submitted in that test. This is not a deployed HTTP-route end-to-end test.

Current browser checks: light/dark compact welcome, topic selection fills but does
not send, no topbar IRAC/profile/status, Documents new-folder dialog, Templates
list/grid switch, single Upload action, editor open/cancel and accessible field
labels, and accurate no-matching-templates state. These latest checks used the
native narrow preview; prior 320/390/1440 results are historical, not a fresh full
breakpoint sweep. No new hosted or physical-device checks are claimed.

The combined shelf/file layout is now implemented for Documents and Templates.
Upload/move/edit handlers are retained and errors surfaced; every mutation path
has not been exercised again in this pass. Production release remains gated.

Final current-tree verification passed: `git diff --check`, lint, TypeScript,
all 17 frontend tests, and the production build (931 generated pages).

## Fourth pass and deployment evidence

Account/auth/Matter changes at `1dc64d2`: lint, typecheck, all 20 frontend tests,
5 backend naming unit tests and production build (932 pages) passed. New tests
are structural guards, not substitutes for browser interaction.
Browser: real QA login; profile metadata save; all five onboarding steps/Done;
fictional Matter party persists after reload; mobile forms, light/dark signup,
desktop sign-in artwork, recovery entry and reset page. Recovery email delivery,
new account creation and password mutation were deliberately not exercised.

Railway deployment `cdb9236d-10fb-4ef5-a4f3-846f2f198770` SUCCESS. Live backend
HTTP chat fixture `12ca1518-d409-4d51-805a-c66411267446` generated its answer and
automatically persisted `Meeting notes organization guidance`; browser title
updated without reload. Exclude this synthetic fixture from usage analytics.

GitHub push succeeded with the existing author unchanged. GitHub-triggered Vercel
preview `dpl_8q9QVkwNegcs6greih9rtyrfq5j1` has no identity/seat block. Compilation
and TypeScript passed, but page generation failed: `supabaseUrl is required`.
Vercel environment inventory confirms the public Supabase URL/anon key are only
in Production/Development, not Preview. Asked owner to configure Preview using
the same public values. No secret was copied, no empty corpus workaround added,
no main push or production-frontend promotion made. The earlier CLI identity
block is not evidence that the Git email must be changed.
