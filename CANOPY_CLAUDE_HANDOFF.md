# Canopy continuation handoff, 14 September 2026

## Outcome

### Fourth pass, 14 September: remaining account screens

Compared the prototype's actual Profile/Auth implementations before porting.
Canopy auth now uses the split artwork/form layout, mobile single column,
labelled autofill fields, password reveal and real Supabase login/signup. Email
confirmation required by Supabase no longer produces a false signed-in screen.
The legacy login/signup presentation remains available through the UI boundary.
Added `/auth/reset-password` and recovery entry; authenticated password update
is wired, but email delivery, redirect allowlisting and a real recovery-link
round trip have NOT been verified. No password was changed in QA.

Profile now has the account banner, editable name (real metadata persistence),
read-only email, appearance, password recovery and tour replay. No fabricated
role/plan or unsupported email editor was copied from the prototype.
Matter detail forms now wrap on narrow screens, have 44px actions, accessible
add/remove controls and a save retry button. Updates check Supabase errors and
zero-row writes; party/date changes are reflected only after successful saves.
This is a functional refinement, not a claim that the prototype's every tab was
replicated. Onboarding retains all five approved assets and fixes button contrast.

Browser evidence: QA sign-in succeeds; profile save returns confirmation; all
five tour steps and Done work; fictional party `Fictional QA Party` / `QA fixture`
in matter `82bfe06c-9783-4256-9924-bb69e5afb28e` survives reload. Auth checked on
desktop and narrow preview, signup in light/dark; recovery entry and reset route
render. No new signup, recovery email or password mutation performed. The retained
fictional party is a QA fixture, not a real user record.

Vercel API recheck still reports BLOCKED / TEAM_ACCESS_REQUIRED for candidate
`dpl_7msfLL6771MVt4GBuJ1bVFuQUiJb`. Asked owner to fix commit identity association.
Railway login was corrected by the user and integration/backend explicitly linked
to the real levy-api project, production, service `10e39a27-a7a1-4c94-8360-7f7fd935ec31`.
Verified previous backend deployment uses main `54c748f` and rootDirectory backend.
Uploaded naming-only backend diff from REPO ROOT, deployment
`cdb9236d-10fb-4ef5-a4f3-846f2f198770`; see latest QA evidence for final status.

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

### Second screenshot-led refinement, 14 September

User supplied three screenshots at 08:47, 08:51 and 09:01 and corrected the
welcome interaction explicitly. Their newest directions override old prototype
choices: no topbar avatar, jurisdiction/live dot, or Add Document welcome pill.

- Topbar is now a quiet section label/theme control in the same inset content
  column as the welcome surface. Desktop no longer shows a duplicate menu button.
  Sidebar account access remains. Removed duplicate mobile IRAC topbar action;
  the conversation heading still opens the Brief.
- In Focus appears by default. Its close action reveals only Show a question and
  Try an example. They are mutually exclusive with the card. Both disappear while
  drafting. The card no longer inherits capsule backdrops, eliminating dark text
  patches. Closing returns keyboard focus to the restore action.
- Removed redundant attachment prop/pill; composer attachment flow stays intact.
- Mobile disclaimer hidden, composer sits lower, latest-response button anchored
  at `bottom: calc(100% + 10px)` rather than an overlapping negative top offset.
- Mobile scene footer now uses normal flow instead of a 200px spacer.
- Replaced the hand-drawn menu SVG with Lucide Menu/X. No new generated SVGs.
- Study uses the existing approved book asset, distinct format cards, one subject
  selector and an optional topic. Cards stack only at 360px and below. Existing
  lesson/quiz/cheat-sheet prompts are unchanged.
- Matters gained real client-side search and honest workspace count, wrapping
  card titles. No simulated archive, draft or linked-chat counts were copied.
- Legislation now uses Canopy shell without an auth gate, preserving `/acts` and
  detail URLs, metadata and server-rendered Act links. New searchable directory
  uses real names/numbers/years, without invented categories or legal-status badges.
- Supporting-screen muted copy contrast and source-search input sizing improved.

Started the original prototype with its normal Vite command at
`http://127.0.0.1:4317/canopy/#/study`. Compared running Study, Documents, Templates,
Matters, source-search and legislation screens, plus the named design task.
Main app checked at 1440x900, 390x844 and 320x740, with focused light/dark checks.
At 390px, measured latest button bottom 616, composer top 626/bottom 754 and dock
top 766: 10px above and 12px below. Disclaimer computed display is none. These
are emulated browser measurements, not a real iOS keyboard test.

Remaining parity: Documents/Templates still use folder-first pages rather than
the prototype's combined shelf/file list and view switch. Source search uses real
semantic-search results, not the prototype's sample browse/filter dataset. Matter
detail/forms, Profile, auth and onboarding need a final whole-screen parity pass.
Do not copy sample data/features merely to match screenshots. Employment Code
directory and detail counts disagreed (200 vs 133), and extracted headings contain
OCR artifacts; new directory omits section counts, but corpus repair is NOT done.

Four structural regression guards supplement the thirteen earlier tests. They
do not replace browser checks. Backend behavior and deployment are unchanged in
this second refinement. Vercel authorization gate remains unresolved.

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

### Third refinement: compact starter, libraries and live naming QA (14 September)

- Confirmed no IRAC action in topbar. Chat heading art is now 28px and inline
  action art 24px; the button remains a separate interactive target.
- In focus is smaller and quieter: shorter metadata, compact padding and question
  typography, an explicit Discuss action, hover/focus feedback and Another topic.
  Browser checks in light/dark confirmed source-aware draft selection without sending.
- Documents/Templates now keep the folder shelf and file list together, with real
  all-files/folder selection and list/grid controls. This supersedes the folder-first
  limitation above. Canopy dialogs replace the custom modal overlays in these pages.
  Fixed duplicate mobile Template Upload, aligned Upload styling, labelled editor
  fields, enlarged Edit/Delete targets, distinguished no search matches from an empty
  library, and surfaced action failures instead of swallowing them.
- `scripts/qa_chat_titles_live.py --run-live` tested real Haiku and Supabase, using
  only a synthetic QA-owned first exchange. Generated and persisted title:
  `Initial Client Meeting Document Organization`. Subsequent manual title was
  preserved. Fixture session `7a94cdc6-2024-48a9-9e4c-572c797603be` is retained and
  must be excluded from user analytics. This tests the service, not the full HTTP
  route trigger or deployed backend. No production naming release was made.
- The weekly source-review automation remains local; the current two-topic edition
  expires September 21. It is not a production-autonomous current-news pipeline.
  Do not label older Acts as new news. Additional search results were not ingested.

Still not complete: whole-screen prototype acceptance for Profile/auth/onboarding
and Matter detail/forms, hosted workflow QA and release. Existing folder artwork
is retained, not claimed as exact prototype parity. Prior Vercel authorization
block has not been revalidated or bypassed. This pass does not repair the separate
backend/corpus/password-recovery issues below.

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
