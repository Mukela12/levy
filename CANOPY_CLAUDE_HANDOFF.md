# Canopy continuation handoff, 14 September 2026

## Outcome

The Canopy frontend port has a locally tested implementation. It is **not live**
and full visual parity has not been accepted by the user. The user requested a
further fidelity pass after the original implementation; see the refinement
section below before treating the earlier QA as completion.
Production publication stopped at Vercel's commit-author authorization control,
not at a source-code build error. See `CANOPY_RELEASE_QA.md` for test evidence,
known defects and the exact deployment blocker. Do not report this release deployed.

## Git and working directories

- Main checkout: `/Users/mukelakatnngu/levy`, clean at `54c748f` when checked.
- Integration: `/Users/mukelakatnngu/levy-canopy`, branch `codex/canopy-ui-integration`.
- Latest main was merged cleanly into the integration branch (`a0e7f62`).
- `80bc983`: Canopy production defaults, workflow fixes, assets and regression tests.
- `e3f91f1`: welcome photograph shading stacking fix, visually checked in both themes.
- Release documentation follows those commits. No main push or domain promotion done.
- Preserve existing work and use a fast-forward only after checking both checkouts.

## What changed

Canopy is now the default, with `?ui=legacy` and build-level
`NEXT_PUBLIC_UI_VARIANT=legacy` rollback options. Reused the approved Canopy assets,
Public Sans fonts, capsule styles and existing backend workflows. Normalized the
21 Lordicon assets and preserved the five onboarding illustrations. Added tour
replay from Profile and visible Skip. No shared QA password was reset.

Fixed duplicate Brief instances, maintained generated IRAC while closing/reopening,
removed the composer's full-width backing, measured its scroll clearance, fixed
mobile Study actions behind the dock, surfaced upload failures, disabled sending
during uploads, and hardened theme initialization against unavailable storage.
Shared Base UI source/gallery dialogs now manage focus and Escape. Source matching
remains an identity check, not a legal-validity or proposition-support guarantee.
Removed fictitious profile plan/role labels. Final photo shading was previously
behind the images; it now sits above them and below the content.

## QA

All 11 automated tests pass (`node --test tests/*.test.mjs` in frontend).
`npx tsc --noEmit`, `npm run lint`, `npm run build` and `git diff --check` pass.
Build generated 931 pages. Signed-in browser tests used real backend calls and
the dedicated synthetic QA account documented in the QA report. Tested chat
creation/persistence, source PDF rendering, actual PDF/Word downloads, artifact
text, IRAC retention, five-step tour/replay, Study quiz generation/grading, PDF
upload/library promotion, folder creation, Word template import and Matter notes/link.
Desktop 1440x900 and mobile 320x740 welcome checked in light/dark; earlier workflow
checks used 453x863. Browser viewport override reset afterwards.

QA chats to reopen after normal login:
- `0d6a1947-ec18-4d0c-8778-174cbe2aec8c`: checklist, PDF, citations, IRAC.
- `b202b5a5-b17f-4884-ae91-91a4c04131f7`: Study quiz and upload.

Keep credentials out of this file and git. Exclude the synthetic QA account from
analytics. Retained QA records are deliberate regression fixtures, not real clients.

## Fidelity refinement after user review

Re-read the named design task `Design Levy UI concepts` and the recovered
digest, plus the lab's v13 buttons, v15 controls and In Focus implementation.
The following is a new local refinement pass, not proof of complete visual parity:

- Shared Base UI dropdowns for Research and folder selectors, with selected checks,
  bounded menus, keyboard support and a legacy native-select fallback.
- Borderless Web control in every state; retain explicit Web on/off words on phones.
- Theme-aware Lordicon primary fills and visible Add Document icon.
- Try an example opens a question-preview dialog rather than shifting the welcome
  layout. Selection prefills, never auto-sends. In Focus hides while drafting.
- Full-width neutral old-domain banner above sidebar and content.
- Transparent scales and case artwork bundled as static Next Image imports;
  scales also replace the Brief empty-state green tile. See asset README.
- Shared workspace typography and controls, Study format segmentation, Source
  search error feedback, and narrow-screen Matters/document-row fixes.
- Bounded post-save Haiku 4.5 title service: first exchange only, 40 output tokens,
  eight-second provider timeout, no legal tools/system/history, compare-and-set
  update to preserve renamed titles. Failure retains the provisional title.
  Frontend refreshes titles quietly. Backend is NOT deployed; tests use mocks.
- Public-source question edition with explicit dates, status caveats, source
  links and expiry. Seed edition has two topics, not a complete news service.

Automation `levy-weekly-in-focus-review` is an ACTIVE local Codex heartbeat for
Monday 07:00. It reviews original public sources, updates the edition and validates
it, without publishing while release gates remain unresolved. It is NOT a Railway
background job; a changed static edition still needs a verified deployment.

Browser checks in this pass cover light/dark welcome, Research/Web controls,
example and source-detail dialogs, editable sourced prompts, 320px Documents and
Study, the Matters header and artwork, and opening the redesigned IRAC Brief.
Two mobile/contrast defects found during checks were corrected. Full page-by-page
prototype acceptance, hosted image loading and live title integration remain gates.

## Resume deployment

Vercel project is `mukelas-projects/levy`, root `frontend`, project ID
`prj_Nn5TSsBSBpTLfYgDkATSHm2Sw6vZ`. Worktree root is explicitly linked. Deploy
from that root using `vercel deploy --prod --skip-domain --yes --scope mukelas-projects`.
Do not rely on CLI "Building"; inspect the deployment API's `readyState`.
Latest candidate is blocked with `TEAM_ACCESS_REQUIRED`. Owner must resolve the
commit identity association/team permission. Do not bypass the control by changing
authors or hiding git metadata. After authorization, create a fresh candidate,
test its hosted authenticated downloads and persistence, then promote and sync main.
Live-domain smoke checks and git push remain unfinished.

## Separate follow-ups, not proven fixed by this UI release

1. Employment Code passage labels conflict with PDF pages. Corpus metadata audit required.
2. Study model leaks explanations before quiz submission. Prompt/model follow-up.
3. Documents total is limited to the first 1,000 returned rows.
4. Password recovery targets an absent reset route; untested workflow.
5. Historical harvest, integrity and weekly report tasks need their own continuation.

Recovered context and design digest remain in
`/private/tmp/claude-501/-Users-mukelakatnngu-levy/bf0d7dfb-f126-4d2d-9f21-247e9b180a89/scratchpad/`.
Read `codex_design_digest.md` and `claude_resume_handoff.md`, not the enormous
source transcripts wholesale. Three recovered Claude agents ended at the usage
limit; do not assume their unfinished tasks completed. No new harvest or corpus
mutation was performed during this frontend release work.
