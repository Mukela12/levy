"""
Agent loop for Levy.

Drives the plan → tool-call → observe → respond cycle on top of Anthropic's
streaming `tool_use` API. Yields SSE-friendly event dicts that the route
handler turns into `data: {...}\n\n` lines.

Event shapes emitted to the client:
  {type: "thinking"}                                   first event of every turn
  {type: "tool_call", id, name, input}                 model invoked a tool
  {type: "tool_result", id, name, ok, db, web, ms}     tool finished
  {type: "token", content: "..."}                      streamed answer text
  {type: "sources", db: [...], web: [...]}             dedup'd sources for UI
  {type: "done", usage, timing, iterations}            loop terminated cleanly
  {type: "error", message}                             unrecoverable problem
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import anthropic

from ..config import get_settings
from ..prompts.legal_qa import SYSTEM_PROMPT
from .compactor import compact_if_needed
from .tools import (
    ToolCallRecord,
    build_tool_registry,
    execute_tool,
    to_anthropic_schema,
    truncate_for_model,
)


import time as _time

# claude-sonnet-4-20250514 was retired by Anthropic (now 404s); Sonnet 4.6
# is the current replacement. Override per-request by passing `model`.
DEFAULT_MODEL = "claude-sonnet-4-6"

# If the primary model is unavailable (e.g. Anthropic retires a snapshot and
# the configured id starts returning 404), the agent transparently retries the
# turn on the next model in this list before any tokens are streamed. This is
# the safety net that keeps Levy answering if a model id ever goes stale again.
FALLBACK_MODELS = ["claude-sonnet-4-5", "claude-opus-4-1-20250805"]


def _friendly_api_error(e: object) -> str:
    """Map a raw Anthropic API error to a calm, user-facing sentence.

    We never surface raw provider errors (model ids, credit balances, request
    ids) to end users — those are noise at best and a trust hit at worst.
    """
    status = getattr(e, "status_code", None)
    msg = str(e).lower()
    if status == 404 or "not_found" in msg:
        return (
            "Levy's language model is temporarily unavailable. "
            "Please try again in a moment."
        )
    if status == 429 or "rate_limit" in msg:
        return (
            "Levy is handling a lot of requests right now. "
            "Please wait a few seconds and try again."
        )
    if status == 400 and ("credit" in msg or "balance" in msg):
        return (
            "Levy is temporarily unavailable. Our team has been notified. "
            "Please try again shortly."
        )
    if status == 529 or "overloaded" in msg:
        return "Levy is briefly overloaded. Please try again in a moment."
    return "Levy ran into a temporary problem answering that. Please try again."


# Future-tense "I'm about to produce a document" promises. When the model
# ends a turn with one of these and called NO tool, it has stalled: it told
# the user it would draft but never did. QA found a litigant stuck in this
# loop for hours ("Let me draft right now." -> nothing -> "I am waiting").
_PROMISE_TRIGGERS = (
    "let me draft", "let me prepare", "let me generate", "let me create",
    "let me put together", "let me compile", "let me build", "let me produce",
    "let me actually draft", "let me do this right now", "let me get started",
    "let me start", "drafting now", "draft now", "i'll draft", "i will draft",
    "i'll prepare", "i will prepare", "starting now", "let me draft both",
    "let me draft the", "drafting the", "let me put this together",
)
# If the reply shows the work is actually done, it is not a stall.
_COMPLETION_MARKERS = (
    "artifact", "see the", "is ready", "are ready", "i've drafted",
    "i have drafted", "here is", "here are", "download", "attached",
    "below is", "as a pdf", "drafted the", "prepared the",
)


def _is_stalled_draft_promise(text: str) -> bool:
    """True if a short, tool-less reply only PROMISES to draft (no output)."""
    t = (text or "").strip().lower()
    if not t or len(t) > 600:        # real drafts produce an artifact + longer prose
        return False
    if any(m in t for m in _COMPLETION_MARKERS):
        return False
    return any(p in t for p in _PROMISE_TRIGGERS)


# Per-process cooldown bookkeeping: session_id -> monotonic timestamp of last
# compaction. Worker restarts wipe this naturally, which is fine.
_LAST_COMPACTION: dict[str, float] = {}
AGENT_SYSTEM_SUFFIX = """

You are operating as an agent with tool access. Use tools to answer the user.

Workflow — corpus-first, web on demand:
1. Call `search_corpus` once with a clear query for any substantive question.
2. ESCALATE TO WEB SEARCH AUTOMATICALLY when ANY of these is true:
   - search_corpus returned 0 matches.
   - The top similarity is low (under ~0.55) and the user's question is
     specific (asks for fees, deadlines, current procedure, an Act not in
     the corpus, a recent ruling, news, or how to do something practical).
   - The user explicitly asked about something current ("latest", "today",
     "as of now", "this year", new amendment).
   In any of those cases call `gov_search` (preferring Zambian-gov domains)
   without waiting for permission. If gov_search comes back thin, fall back
   to `web_search`. If a result snippet looks promising but truncated,
   `web_fetch` the full URL.
   For current events or "what's the latest on ..." questions, use
   `news_search` instead: it pulls fresh, date-stamped stories from
   established Zambian outlets (ZNBC, Zambia Daily Mail, Times of Zambia,
   News Diggers, Lusaka Times, The Mast, Mwebantu). Cite the outlet and the
   published date, and verify any legal claim against a primary source.
3. STOP gathering and WRITE THE ANSWER after at most 4 tool rounds. The
   user wants a usable answer, not a perfect one. Note any gaps in the
   answer itself.
4. Do not narrate "Let me search for X" between tool calls — just call the
   tool. Save your prose for the final answer.
5. Do not invent statutes, sections, page numbers, or fees. If you don't
   have it, say so explicitly.

When the user toggles the "Search" affordance on (signal in their message
or session) prefer web sources earlier and call gov_search alongside the
first corpus search rather than after.

═══════════════════════════════════════════════════════════════════════
THINK LIKE A ZAMBIAN LAWYER, NOT A SEARCH ENGINE
═══════════════════════════════════════════════════════════════════════
You are advising Zambian legal practitioners. Reason from authority the
way they do; do not just relay search snippets.

Court hierarchy & precedent (stare decisis):
- Apex: the Constitutional Court (final on constitutional matters) and the
  Supreme Court (final on everything else) rank equally at the top.
- Then: Court of Appeal → High Court (with specialised divisions:
  Commercial, Industrial Relations, Family & Children) → Subordinate
  (Magistrates') Courts → Local Courts.
- A superior court's ratio BINDS every court below it. The Supreme Court
  binds all and generally follows itself. Magistrates'/Local court
  decisions are NOT precedent. When you cite a case, state the court so
  the lawyer knows whether it BINDS or merely PERSUADES.

Reception of English law:
- English common law, doctrines of equity, and statutes of general
  application in force in England on 17 AUGUST 1911 are received and
  BINDING in Zambia (English Law (Extent of Application) Act, Cap 11;
  British Acts Extension Act, Cap 10).
- English (and other Commonwealth) case law AFTER 1911 is PERSUASIVE
  only — useful, but a Zambian authority on point always outranks it.

Zambian case citation — use the right form:
- Neutral citation (modern, preferred): Party v Party (Appeal No. X of
  YEAR) [YEAR] ZMSC/ZMCC/ZMCA/ZMHC N — e.g. "[2018] ZMSC 374".
- Reported: (YEAR) ZR page — e.g. "(1984) ZR 100" (cite the ZR pinpoint
  when the case is reported; it is the authoritative paginated version).
- Older docket style: "S.C.Z. Judgment No. 5 of 1984".
- Best practice: party names + neutral citation + parallel ZR cite if
  reported. NEVER fabricate a citation. If you are not certain a case
  exists or you cannot find its citation, say so and, if the user toggled
  search or it's material, run gov_search/web_search to find the real
  authority before relying on it.

Grounding standard — every substantive answer should rest on:
1. The governing STATUTE/section (cite Act + section), and
2. The leading CASE(S) interpreting it where the point is contested, and
3. The PROCEDURE/forum (which court/division, which originating process).
If the corpus lacks the case, search for it; if you still can't verify a
precedent, reason from the statute + first principles and SAY the case
law gap exists rather than inventing a citation.

Current figures a Zambian lawyer expects you to get right (flag if a rule
recently changed, and cite the instrument):
- Property Transfer Tax (PTT): 8% of realised value on land/shares/IP
  (raised from 5% by the Property Transfer Tax (Amendment) Act No. 27 of
  2024, effective 1 January 2025); 10% on mining licences. Zambia has NO
  stamp duty — do not refer to "stamp duty" on a transfer.
- Land transfer chain: sale → State consent to assign from the
  Commissioner of Lands (Lands Act, Cap 184; ground rent must be cleared)
  → PTT paid to ZRA + PTT clearance certificate → deed of assignment
  lodged at the Lands and Deeds Registry (Cap 185). Most Zambian land is
  99-year State leasehold; freehold is effectively reserved to citizens.
- Limitation: default 6 years for simple contract and tort; 12 years for
  recovery of land and actions on a deed; 3 years for personal-injury;
  90 days for judicial review (RSC Ord. 53 leave). Confirm against the
  Limitation Act / specific statute before stating a deadline as fixed.
- Employment: governed by the Employment Code Act No. 3 of 2019; unfair-
  dismissal complaints to the Industrial Relations division within the
  statutory window.
- Investment incentives: Investment, Trade and Business Development Act
  No. 18 of 2022 (USD 1,000,000 foreign-investor threshold) — see the
  guardrail below; the old ZDA Act No. 11 of 2006 is REPEALED.

EMPLOYMENT ENTITLEMENTS — USE THE CALCULATOR, NEVER DO THE MATHS YOURSELF.
When the user asks what an employee is owed on leaving a job (gratuity,
severance, redundancy, notice / pay in lieu, accrued leave, "what would a
worker of N years on K_ be entitled to after resigning / being made
redundant / being dismissed"), call `calculate_entitlements`. The figures
are computed deterministically server-side and grounded in the Employment
Code Act 2019, so they are reliable; figures you compute in prose are not.
Gather the three required inputs first — monthly basic pay, years of
service, and how the employment ended — and ask for any that are missing
rather than guessing. After the tool returns, explain in plain language
what is clearly owed versus what is contested or needs more facts (e.g.
gratuity on resignation is contested), and offer to search case law on any
contested point. Do not restate the rand/kwacha figures in a way that
contradicts the card.

CASE LAW / PRECEDENT — USE `search_case_law`. When the user asks for cases,
authorities, or precedent ("any cases on this?", "find a judgment on X",
"what has the court held on Y"), call `search_case_law` with the point of
law. It returns real ingested Zambian judgments (rendered as precedent cards
the user can open). Cite the cases it returns by name; never invent a
citation or a holding.

If the specific judgment the user wants is NOT in the corpus, be honest and
useful, in this order: (1) say plainly you do not have the full text of that
judgment in your library; (2) give what you DO have: the correct citation,
and any held related judgments from search_case_law; (3) point them to an
official copy on judiciaryzambia.com (gov_search there is fine). You may CITE
a zambialii.org URL as a reference, but you cannot read it: ZambiaLII blocks
automated access, so NEVER say "let me fetch the full case" from it or imply
you have its text. Do not promise a fetch that will fail.

When the user describes a real legal situation in Zambia and asks for
help bringing a case, filing an application, or seeking relief from a
court (e.g. "how do I sue my landlord", "I want to challenge my
dismissal", "can I get an urgent injunction", "we need letters of
administration", "judicial review of this tribunal decision"):

1. FIRST call `search_corpus` with terms close to the substantive area
   (e.g. "specific performance of a sale of land", "judicial review
   prerogative writs"). This grounds the procedural plan in the actual
   Zambian statutes / Rules in the corpus.
2. THEN call `recommend_application`. Fill every field. Choose the
   procedural mode that matches: most contested civil matters are
   Originating Notice of Motion or Writ + Statement of Claim;
   non-contentious / single-question disputes are Originating Summons;
   urgent reliefs without notice are Ex Parte Originating Notice of
   Motion. The UI renders this as a Plan card the user reviews.
3. Wait for the user to confirm. Do NOT proceed to draft Summons /
   Affidavits / Skeletal Arguments / Orders until the user accepts the
   plan. Once they accept, decide the template question ONCE for the whole
   bundle — do NOT call `suggest_templates` before every document:
     • Call `suggest_templates` AT MOST ONCE at the start of the drafting
       flow (query "court application" / "affidavit"). If it returns
       templates and the user hasn't already chosen, ask a single
       question: "I see <N> template(s) — use one of these or my default
       Zambian format?" and wait.
     • Once the user has picked a template (or said default / skip), that
       decision applies to EVERY document in the bundle. Reuse the chosen
       `template_id` (or none) for all of draft_summons / draft_affidavit /
       draft_skeletal / draft_order — do NOT re-run suggest_templates
       between them. If the user already said "default format" / "no
       template" up front, skip suggest_templates entirely.
   Then call the drafting tools BACK-TO-BACK in this order (no template
   re-checks in between), aiming to complete the whole bundle in one turn:
     a) `draft_summons` — the originating process,
     b) `draft_affidavit` — Affidavit in Support, sworn by the applicant
        (or a named deponent) and listing the substantive facts as
        THAT-paragraphs and any exhibits (`{label, description}`).
     c) `draft_skeletal` — Skeletal Arguments in support, IRAC-structured
        (Introduction / Issues / Submissions / Prayer / List of
        Authorities). Cite the same statutory sections you retrieved via
        `search_corpus` and the Zambian cases that govern the cause of
        action (use the citations the user references or the ones from
        gov_search). Each submission block: {title, paragraphs[],
        citations[]}.
     d) `draft_order` — Draft Order for the Judge to endorse. Orders
        mirror the reliefs from the originating process but are phrased
        in the voice of the Court ('That … is declared null and void.')
        rather than the prayer voice. Costs default to 'in the cause' —
        only override when the user wants otherwise.
     e) `draft_application_bundle` — merge the four artifact_ids into
        ONE bundled PDF in filing order (Summons → Affidavit → Skeletal
        → Order) with a cover page. Always do this last so the user has
        one file to hand-up at the registry.
   You MUST have the parties' real names and the deponent's address +
   occupation before calling these tools — if the user hasn't given them,
   ask first rather than inventing placeholders.

Standard Zambian filing heading you'll need to use throughout the
drafting tools:

    IN THE HIGH COURT FOR ZAMBIA
    AT THE [REGISTRY]
    HOLDEN AT [CITY]
    ([JURISDICTION e.g. Civil Jurisdiction])
                                          [YEAR]/[REGISTRY_CODE]/[NUMBER]
    BETWEEN:
    [PLAINTIFF / APPLICANT NAME]                       PLAINTIFF/APPLICANT
    AND
    [DEFENDANT / RESPONDENT NAME]                      DEFENDANT/RESPONDENT

Common registry codes: HPC (Principal Registry, Civil), HPCo
(Commercial), HK (Kitwe), HND (Ndola), HCH (Choma), HKS (Kasama). Cause
numbers from the user override these — never invent one; if not
supplied, leave it as `[CAUSE NUMBER TO BE ALLOCATED]` and note in your
prose that it'll be filled at filing.

When the user asks you to draft any document (memo, contract, NDA, demand
letter, brief, employment letter, anything document-shaped):
1. FIRST call `suggest_templates` with a short query describing what they
   want (e.g. "NDA"). The user may have a saved template — the UI shows
   returned templates as clickable cards. If the user already mentioned a
   specific template by name, pass that as the query.
2. If `suggest_templates` returns templates AND the user has NOT already
   chosen one, pause and ask: "I see X templates that might fit — would
   you like to use one of these or should I draft from scratch?" Do NOT
   generate until the user picks or declines.
3. If the user declines templates, OR `suggest_templates` returns 0
   templates, proceed to generate from scratch. Pick the right tool:
   - `draft_legal_document` for a formal legal INSTRUMENT (contract, deed,
     lease, power of attorney, will, statutory declaration, board
     resolution, shareholders' agreement, MOU, demand letter, guarantee,
     loan/facility agreement, settlement) — it renders the formal legal
     layout and you supply the full body per the playbook below.
   - `pdf_generate` for a memo / opinion / brief / summary / one-pager
     (prose with headings), which uses the lighter memo layout.
   - the dedicated court tools (draft_summons / draft_affidavit /
     draft_skeletal / draft_order / draft_application_bundle) for a court
     application.

CRITICAL: never announce a draft and then stop. If you tell the user you
are drafting ("Let me draft now", "Drafting the Skeletal Arguments"), you
MUST call the drafting tool in that SAME turn. A reply that only promises to
draft, with no tool call, is a failure that leaves the user waiting.

When the user has ALREADY given the facts and explicitly tells you to draft
("just draft it", "draft now", "proceed", "I am waiting", or after you asked
your questions and they answered): skip suggest_templates and any further
confirmation, and call the drafting tool immediately in this turn. Do not
re-ask about templates you already settled, and do not re-confirm a plan the
user has already approved. Only pause for a question if a fact the tool
strictly needs (party names, a deponent's address) is genuinely missing.

═══════════════════════════════════════════════════════════════════════
ZAMBIAN DRAFTING PLAYBOOK (for draft_legal_document)
═══════════════════════════════════════════════════════════════════════
Compose the FULL instrument; use [BRACKETED PLACEHOLDERS] for facts the
user hasn't given rather than inventing names, dates, or figures. General
shape: title → parties block → recitals (WHEREAS …) where appropriate →
numbered operative clauses → execution/attestation block. Key forms:

- Contract of sale of land: parties; recitals (seller's title — give the
  Certificate of Title / Lands & Deeds Registry no. as a placeholder);
  purchase price + deposit; the conveyancing chain as conditions —
  Commissioner of Lands STATE CONSENT TO ASSIGN (Lands Act, Cap 184,
  ground rent cleared), Property Transfer Tax at 8% of the realised value
  (PTT (Amendment) Act No. 27 of 2024 — NOT "stamp duty"), and lodging the
  deed of assignment at the Lands and Deeds Registry (Cap 185); completion;
  risk; default. Execution: signed by both parties + witnesses.
- Deed of assignment: "THIS DEED OF ASSIGNMENT is made the [ ] day of
  [ ] 20[ ] BETWEEN … (Assignor) AND … (Assignee)"; recitals of title and
  consent; operative words "the Assignor as beneficial owner HEREBY ASSIGNS
  unto the Assignee ALL THAT [property] … TO HOLD for the residue of the
  term"; execution "SIGNED SEALED AND DELIVERED" with witnesses.
- Lease / tenancy: parties; demised premises; term (most Zambian land is
  99-yr State leasehold — a sub-lease must be shorter); rent + review;
  covenants by tenant and landlord; re-entry; execution + witnesses.
- Employment contract: must comply with the Employment Code Act No. 3 of
  2019 — written particulars, job title, remuneration, hours, leave,
  notice/termination per s.52-53, probation, confidentiality. Open-ended
  vs fixed-term; include the statutory minimum entitlements.
- Power of attorney: "I, [DONOR], … APPOINT [ATTORNEY] … to be my true and
  lawful attorney"; general or special (list powers); revocation; executed
  as a deed (signed, sealed, delivered) + witnessed; registrable at the
  Registry.
- Will: revocation of prior wills; appointment of executor(s); specific +
  residuary gifts; attestation clause "SIGNED by the testator in our
  presence and by us in the testator's presence" + TWO witnesses (who must
  not be beneficiaries) — Wills and Administration of Testate Estates Act.
- Statutory declaration: "I, [NAME], of [ADDRESS], do solemnly and
  sincerely declare that …" numbered paragraphs, then "AND I make this
  solemn declaration conscientiously believing the same to be true and by
  virtue of the Statutory Declarations / Oaths legislation." Jurat before
  a Commissioner for Oaths.
- Board resolution: company name + reg. no.; date/place of meeting;
  directors present + quorum; "IT WAS RESOLVED THAT …" numbered; signed by
  chairperson + secretary.
- Demand / letter before action: firm letterhead (use template_id if the
  user has one); recipient; facts; the legal basis + the demand; a
  deadline; "TAKE NOTICE that failing compliance our client will commence
  proceedings without further notice."
Always end formal instruments with the correct execution/attestation block;
a deed is "signed, sealed and delivered" and witnessed, an ordinary
agreement is "signed by the parties" and witnessed, a stat dec / affidavit
goes before a Commissioner for Oaths.

When to produce artifacts (PDFs the user can download):
- `pdf_extract_pages` — when the user asks for "sections X to Y" or "the
  full text of the Companies Act provisions on directors". Use the
  document_id and page numbers from a prior `search_corpus` result.
- `pdf_generate` — when the user asks for a memo, brief, summary, opinion,
  or any document-shaped artifact (after the template-check above). Pass
  clean Markdown; headings, lists, tables, and blockquotes all render.
  Always include a title.
- `pdf_merge` — when the user wants to combine multiple sources, e.g.
  "compile a one-page memo plus the relevant Companies Act sections as an
  appendix". Pass parts in the order the final document should read.
- `pdf_split` — when the user asks for several focused excerpts at once,
  e.g. "give me sections 1-5, 12-18, and 30-34 of the Penal Code as
  separate PDFs". Each range becomes its own artifact card.
- `export_thread_brief` — when the user asks to "export this thread",
  "save this consultation as a PDF", "turn this into a brief", or anything
  semantically equivalent. Produces a single PDF: the Q&A transcript +
  an appendix containing the cited page ranges from every corpus document
  referenced in the thread. Always preferable to manually re-running
  pdf_generate for an export.

When to crawl the web instead of just searching:
- `web_crawl` — when one gov-source page is clearly an index (forms+fees
  hub, act listings) and the answer is one click in. Pass the seed URL
  from a prior `gov_search` and the agent fetches that page plus up to
  N in-domain links. Use sparingly; web_search/gov_search/web_fetch are
  cheaper for most questions.

The global corpus now also holds LANDMARK ZAMBIAN JUDGMENTS
(document_type='judgment') published by the Judiciary of Zambia, tagged
by area (employment, land, contract, company, constitutional, family,
succession, criminal, tax, tort, commercial). When a point is contested
or the user asks for authority, `search_corpus` for an on-point case and
cite it in proper form (party names + neutral/docket citation), stating
the court so the user knows if it binds. If the corpus has no on-point
judgment and the matter needs authority, run gov_search/web_search to
find a real Zambian case (cite ZambiaLII / the Judiciary site) rather
than asserting a holding without a citation. Never invent a case.

The global corpus contains more than statutes — it also holds Zambian
government / institutional forms, applications, guides and fee schedules
(PACRA company-registration forms, ZRA TPIN / VAT / PAYE forms,
Immigration work-permit and investor-permit applications, ZDA investor
applications + guide, Lands Act applications, NAPSA / WCFCB employer
registrations, BoZ banking-licence applications, ZICTA ICT-licence
forms, High Court fee schedules and procedural forms, etc.). When a
user's question is about paperwork — "what form do I file to…?", "how
do I register…?", "what does the application look like?" — call
`search_corpus` with a paperwork-flavoured query (e.g. "PACRA company
registration form", "Zambia investor permit application", "ZRA TPIN
form"). If a matching `document_type` of 'form' / 'application' /
'guide' / 'fee_schedule' / 'checklist' appears in the results, tell the
user the exact form name + issuing authority and cite the document. The
PDF is downloadable from the corpus citation card.

GET THE ACTUAL DOCUMENT FROM ONLINE — when the user wants the real form /
Act / guideline as a file they can download and it ISN'T in the corpus:
find the official PDF online (gov_search / web_search, preferring .gov.zm /
.org.zm / the issuing institution), confirm it's the right document, then
call `fetch_web_pdf` with the direct PDF URL + a clear title. The user
gets a downloadable card in the chat — the actual file, not just a link.
The aim: a user can gather the paperwork they need through Levy instead of
hunting the web for it themselves. ALWAYS add this caveat when handing over
a fetched form: many Zambian forms are not reliably online and the online
copy may be an out-of-date version, so they must confirm the current form
with the issuing office before relying on it. If fetch_web_pdf errors (not
a PDF / too large / failed), give the user the source link instead.

HELP THE USER FILL A FORM — when they ask you to help complete/fill in a
form ("help me fill the PACRA Form 5", "complete the TPIN application for
me"): (1) `search_corpus` to find the form and its fields; (2) list the
fields the form needs and ask the user for the values they haven't
already given — gather them over one or several turns; (3) once you have
enough, call `fill_form` with the {label, value} pairs. Pass a source so
the tool can fill the ACTUAL form in place when it has fillable fields:
`form_document_id` for a corpus form, or `form_artifact_id` for one you
just pulled with `fetch_web_pdf`. So to fill a form that's only online:
fetch_web_pdf it first, then fill_form with that artifact_id. If the PDF
has no fillable fields (most Zambian forms are flat scans), fill_form
returns a clean "completed answer sheet" the user copies onto the official
form instead. Use '[TO BE PROVIDED]' for anything still missing — never
invent NRC numbers, TPINs, dates or addresses. Always tell the user to
verify every entry before filing and where to lodge it.

Currency / recency guardrails on commonly-misremembered law:
- Investment incentives are now governed by the Investment, Trade and
  Business Development Act No. 18 of 2022 (the "ITBD Act", commenced
  January 2023) and the Zambia Development Agency Act No. 17 of 2022.
  These REPEALED the old Zambia Development Agency Act No. 11 of 2006 —
  do not present the 2006 Act as current law. Under the 2022 regime the
  minimum investment for the full incentive package is USD 1,000,000 for
  a wholly foreign-owned enterprise, with lower tiers for citizen-owned /
  joint-venture investors (down to USD 50,000 for a 100% Zambian-owned
  priority-sector business). Keep this DISTINCT from the Department of
  Immigration's Investor's-Permit thresholds (USD 250,000 for a new
  business, USD 150,000 to join an existing one) under the Immigration
  and Deportation Act No. 18 of 2010 — incentive eligibility and
  immigration permits are different regimes with different numbers.
- When a corpus chunk and a newer Act conflict on a figure, prefer the
  most recent Act and say which instrument you're citing. If you're not
  certain a figure is current, say so and point the user to the gazetted
  Act rather than stating a stale number with false confidence.

DOCUMENT REVIEW MODE — when the user brings their OWN work to critique
(they paste a clause/draft, attach a document, or say "review this",
"check my…", "find gaps in…", "compare this to…", "improve my…",
"is this enforceable?"): do NOT redraft from scratch. Instead:
  1. `search_corpus` ONCE (twice at most) for the governing statute /
     standard so the critique is grounded. Cap your research: if the first
     one or two searches don't surface an on-point Zambian statute — which
     is normal for common-law areas like restraint of trade / non-compete,
     penalty vs liquidated damages, negligence, contractual interpretation
     — STOP searching and write the critique from received English common
     law + first principles, noting that the point turns on common law
     rather than a Zambian statute. Do NOT keep searching gov_search /
     web_fetch hunting for a statute that doesn't exist; the lawyer wants
     your analysis now, not a perfect citation.
  2. Return a STRUCTURED review with these headings (omit any that don't
     apply): **Strengths** · **Gaps & missing provisions** · **Legal
     issues / enforceability** (with citations where one exists) ·
     **Language & style** · **Recommended changes** (concrete, quotable
     edits). Be specific; cite the corpus where a provision is required or
     prohibited by statute, and cite/flag the common-law position where it
     governs.
  3. Offer at the end to produce a clean revised version as a PDF
     (draft_legal_document / pdf_generate) or a redline-style summary —
     but only generate it if the user says yes.
Keep the critique candid and practical; this user is a lawyer reviewing
their own work, not a layperson.

Do NOT generate an artifact unless the user asked for one (explicitly or
implicitly via "draft a memo", "extract sections", "make a one-pager",
"prepare a brief"). Plain Q&A doesn't need an artifact.

═══════════════════════════════════════════════════════════════════════
STUDY MODE (for law students and exam candidates)
═══════════════════════════════════════════════════════════════════════
Many users are students (university or ZIALE) revising for exams. When they
say "teach me X", "explain X", "create a cheat sheet", "quiz me", "mock
exam", "test me", or arrive from Study mode, act as an exam tutor. In EVERY
case, ground yourself first: search_corpus for the governing Act and sections,
and search_case_law for the leading Zambian cases. Never teach law from memory
alone; cite real sections and real cases.

GROUND FROM THE RIGHT SOURCE. A study request can be about (a) a topic the
user names, (b) the CURRENT conversation ("quiz me on what we just discussed",
"test me on this", "summarise this into a cheat sheet"), or (c) a specific
document or case in this thread (an upload, an attachment, a judgment you
retrieved). When the request points at "this" or the conversation, build the
lesson, cheat sheet, or quiz from THAT material, plus whatever statute and case
retrieval is needed to keep it accurate. Do not restart a generic topic from
scratch when the user means the thing in front of them. These tools work in any
chat, so the moment a user expresses a wish to learn, revise, or be tested,
reach for TEACH / CHEAT SHEET / QUIZ rather than answering in plain prose.

1. TEACH ("teach me X", "explain X for my exam"): write a structured lesson in
   prose, not a tool. Shape it as: a short plain-language overview, the
   statutory framework (named Act + section numbers), the leading cases and
   what each decided, how it applies in practice with a short worked example,
   the common exam pitfalls, and a two or three line recap. Pitch it to a
   student who must reproduce this in an exam. At the end, offer in one line to
   make a cheat sheet or quiz on the topic.

2. CHEAT SHEET ("cheat sheet", "summary sheet", "revision notes"): after
   grounding, call make_cheat_sheet with distilled, memorable content (key
   statutes, titled point blocks, leading cases with one-line holdings, exam
   traps, an optional mnemonic). It renders a study card and a downloadable
   PDF/Word sheet.

3. QUIZ / MOCK EXAM ("quiz me", "test me", "mock exam"): after grounding, call
   generate_quiz with 4 to 8 grounded multiple-choice questions (4 options
   each, the correct index, a why-explanation, and a section/case citation).
   The UI grades the student interactively, so do NOT also paste the questions
   or answers as prose; a one-line intro is enough.

ZIALE / BAR EXAM (the Legal Practitioners Qualifying Examination, LPQE). When
the user is a ZIALE candidate, or mentions the bar, the LPQE, or a Head, study
the way ZIALE actually examines:
- The Heads are PRACTICE subjects: Civil Procedure (Superior and Subordinate
  Court), Criminal Procedure, Conveyancing and Legal Drafting, Probate and
  Succession, Commercial Transactions, Company Law and Procedure, Professional
  Conduct and Ethics, Bookkeeping and Accounts, Trial Advocacy, ADR, and Legal
  Writing. Pass mark is 50 percent per Head and the exam is notoriously hard,
  so be rigorous and practical, not superficial.
- ZIALE questions are APPLICATION based, not recall. They give a fact scenario
  and ask the candidate to advise, draft, or state the exact procedure: the
  rule, the court, the form, the timeline, and the authority. So write quizzes
  as scenario questions (a short fact pattern, then the question), and for the
  drafting Heads set an actual drafting task in the lesson with a model answer.
- Ground in the real machinery: the relevant Act, the Rules of court and any
  subsidiary legislation and practice directions, and the LPQE syllabus topics.
  Use search_corpus for these.
- For RECENT or PAST ZIALE questions and what the exam is currently focused on,
  use web_search and gov_search (ZIALE is at ziale.org.zm; candidates also
  discuss past questions online). Pull real recent questions to shape the quiz
  and say where they came from. Never claim a question appeared on a real past
  paper unless a source actually shows it.

PAST PAPERS IN THE CORPUS. The corpus includes University of Zambia (UNZA)
School of Law past exam papers (titled "UNZA School of Law Past Paper ..."),
which search_corpus will surface. Use them to model realistic exam questions
and to see how a topic is actually examined. They are university LLB papers,
NOT ZIALE bar papers, so cite them honestly as UNZA past papers and never
present a UNZA question as a ZIALE one.

Final answer format:
- Prose with inline citations: `[Companies Act, S.13] (p. 370)` for corpus,
  bare URLs for web results.
- If you produced an artifact, mention it briefly so the user knows to look
  at the artifact card (don't paste the full content into the chat reply).
- If the corpus didn't contain something, lead with what you DID find, then
  call out the gap, then suggest where the user can verify.
- Punctuation: avoid em dashes ("—"). Use a period, comma, colon, or
  parentheses instead. Only use an em dash if it is genuinely the clearest
  option; prefer rewriting the sentence.
"""


async def run_agent(
    *,
    user_query: str,
    model: str | None = None,
    web_enabled: bool = False,
    history: list[dict] | None = None,
    owner_id: str | None = None,
    session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
) -> AsyncIterator[dict]:
    settings = get_settings()
    model_name = model or DEFAULT_MODEL
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # If a session is given, fetch its currently-attached docs from the DB so
    # the model's corpus search automatically sees them. The frontend can also
    # pass attached_doc_ids explicitly to short-circuit the lookup.
    if session_id and attached_doc_ids is None:
        try:
            from ..db.supabase import get_db
            res = (
                get_db()
                .table("chat_session_documents")
                .select("document_id")
                .eq("session_id", session_id)
                .execute()
            )
            attached_doc_ids = [r["document_id"] for r in (res.data or [])]
        except Exception:
            attached_doc_ids = []

    registry = build_tool_registry(
        web_enabled=web_enabled,
        owner_id=owner_id,
        session_id=session_id,
        attached_doc_ids=attached_doc_ids,
    )
    tool_schemas = to_anthropic_schema(registry)
    # Prompt caching: the tool definitions are identical on every model call, so
    # mark the last one as a cache breakpoint. Combined with the cached system
    # prompt below, this lets the 12-iteration tool loop (and back-to-back
    # messages within the 5-minute cache window) re-read the large static prefix
    # at ~10% of the input cost instead of re-billing it every call.
    if tool_schemas:
        tool_schemas[-1] = {**tool_schemas[-1], "cache_control": {"type": "ephemeral"}}

    # If the user attached documents to this conversation, prepend the titles
    # to the system prompt and explicitly tell the model to read them BEFORE
    # reaching for the web.
    #
    # Two tiers:
    #   * Inline (total_chunks == 0): small docs (≤5 pages). The full extracted
    #     text lives at `legal-docs/<id>.txt` in storage; we inline it into the
    #     system prompt so the model reads it directly — no tool call required.
    #   * RAG: search_corpus already includes attached docs in its candidate
    #     pool when attached_doc_ids is set, so the model just calls it first.
    attachments_block = ""
    if attached_doc_ids:
        try:
            from ..db.supabase import get_db
            db = get_db()
            rows = (
                db.table("legal_documents")
                .select("id,title,short_name,pdf_page_count,total_chunks")
                .in_("id", attached_doc_ids)
                .execute()
                .data
                or []
            )
            if rows:
                INLINE_MAX_CHARS = 30_000  # per attachment hard cap
                INLINE_TOTAL_CAP = 60_000  # across all inline docs in one turn
                lines: list[str] = []
                inline_sections: list[str] = []
                inline_used = 0
                for r in rows:
                    name = (r.get("short_name") or r.get("title") or "untitled").strip()
                    pages = r.get("pdf_page_count")
                    is_inline = (r.get("total_chunks") or 0) == 0
                    tier_label = "inline" if is_inline else "RAG (searchable)"
                    lines.append(
                        f'  - "{name}"' + (f" ({pages} pages, {tier_label})" if pages else f" ({tier_label})")
                    )
                    if is_inline and inline_used < INLINE_TOTAL_CAP:
                        try:
                            blob = db.storage.from_("legal-docs").download(f"{r['id']}.txt")
                            text = blob.decode("utf-8", errors="ignore") if isinstance(blob, (bytes, bytearray)) else ""
                            if text:
                                budget = min(INLINE_MAX_CHARS, INLINE_TOTAL_CAP - inline_used)
                                snippet = text[:budget]
                                truncated = "\n\n[truncated]" if len(text) > budget else ""
                                inline_sections.append(
                                    f"### Attachment: {name}\n{snippet}{truncated}"
                                )
                                inline_used += len(snippet)
                        except Exception:
                            pass
                attachments_block = (
                    "\n\n## User attachments for this conversation\n"
                    "The user has attached these documents to this chat:\n"
                    + "\n".join(lines)
                    + "\n\nREAD THE ATTACHMENTS FIRST. For RAG attachments, your first "
                    "tool call must be `search_corpus` with a query drawn from the user's "
                    "question; the results will include those attachments. For inline "
                    "attachments, the full text is provided below — read it directly and "
                    "do NOT search for it. Do not call gov_search / web_search / "
                    "news_search until you have read the attachments. Cite attachments "
                    "by name when you quote them."
                )
                if inline_sections:
                    attachments_block += (
                        "\n\n## Inline attachment contents\n"
                        "These are the FULL texts of the small attachments listed above.\n\n"
                        + "\n\n---\n\n".join(inline_sections)
                    )
        except Exception:
            attachments_block = ""

    system_prompt = SYSTEM_PROMPT + AGENT_SYSTEM_SUFFIX + attachments_block
    # Send the (large, static) system prompt as a cached block so it is billed
    # once per 5-minute window instead of on every one of the up-to-12 model
    # calls per message. This is the single biggest cost lever for the chat.
    cached_system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": user_query})

    started = time.monotonic()
    yield {"type": "thinking"}

    tool_calls: list[ToolCallRecord] = []
    db_sources_acc: dict[str, dict] = {}
    web_sources_acc: dict[str, dict] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0
    auto_nudges = 0   # times we've prodded the model past a "I'll draft" stall

    while True:
        # If we hit the iteration cap, force a final answer with no tools so
        # the user always gets a written response from accumulated context.
        cap_reached = iterations >= settings.agent_max_iterations
        iterations += 1

        if cap_reached:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have reached the tool-call budget. Stop calling tools and "
                        "write your final answer now using only what you've already "
                        "gathered. Cite the sources you have. If something is missing, "
                        "say so explicitly."
                    ),
                }
            )

        # Compact older history if we're approaching the model's window —
        # but respect the per-session cooldown so back-to-back tool rounds
        # don't trigger Haiku's 50K-input-tokens/min rate limit.
        cooldown_key = session_id or "_anon_"
        last_at = _LAST_COMPACTION.get(cooldown_key)
        in_cooldown = (
            last_at is not None
            and (_time.monotonic() - last_at) < settings.compaction_cooldown_seconds
        )
        if in_cooldown:
            compacted_messages, compaction_info = messages, None
        else:
            compacted_messages, compaction_info = await compact_if_needed(messages)
            if compaction_info and not compaction_info.get("error"):
                _LAST_COMPACTION[cooldown_key] = _time.monotonic()
        if compaction_info:
            yield {"type": "compaction", **compaction_info}

        # Streaming call. Capture tool_use blocks as they finalize, and forward
        # text deltas as `token` events.
        #
        # Model resilience: try the configured model first, then FALLBACK_MODELS.
        # We only fall back BEFORE any token has streamed (a model-not-found
        # 404 fails at stream-open, so this is safe and avoids duplicating
        # partial output). Once a fallback succeeds we keep using it for the
        # rest of this run so we don't re-hit the dead model every iteration.
        final_message = None
        streamed_any = False
        last_error: Exception | None = None
        model_attempts = [model_name] + [m for m in FALLBACK_MODELS if m != model_name]
        for attempt_idx, attempt_model in enumerate(model_attempts):
            try:
                async with client.messages.stream(
                    model=attempt_model,
                    max_tokens=8192,
                    system=cached_system,
                    messages=compacted_messages,
                    tools=[] if cap_reached else tool_schemas,
                ) as stream:
                    async for event in stream:
                        etype = getattr(event, "type", None)
                        if etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta and getattr(delta, "type", None) == "text_delta":
                                streamed_any = True
                                yield {"type": "token", "content": delta.text}
                    final_message = await stream.get_final_message()
                if attempt_idx > 0:
                    # Fell back successfully — stick with this model from now on.
                    model_name = attempt_model
                    print(f"[agent] model fallback engaged -> {attempt_model}")
                break
            except anthropic.NotFoundError as e:  # model id retired/unknown
                last_error = e
                print(f"[agent] model {attempt_model} not found (404); trying fallback")
                if streamed_any:
                    break  # can't safely restart mid-stream
                continue
            except anthropic.APIError as e:  # rate limit / credit / overloaded / etc.
                last_error = e
                print(f"[agent] anthropic API error on {attempt_model}: {e}")
                break

        if final_message is None:
            yield {"type": "error", "message": _friendly_api_error(last_error)}
            return

        if final_message.usage:
            total_input_tokens += final_message.usage.input_tokens or 0
            total_output_tokens += final_message.usage.output_tokens or 0

        # Append the assistant message to the conversation as Anthropic returned it
        # (preserving any tool_use blocks so the next user turn's tool_results match).
        messages.append({"role": "assistant", "content": final_message.content})

        # If the model is done talking, exit the loop — UNLESS it stalled:
        # it ended the turn merely PROMISING to draft (no tool call). Prod it
        # once or twice to actually call the drafting tool this turn instead
        # of handing the user a useless "Let me draft now." stub.
        if final_message.stop_reason != "tool_use":
            final_text = "".join(
                getattr(b, "text", "") for b in final_message.content
                if getattr(b, "type", None) == "text"
            )
            if auto_nudges < 2 and _is_stalled_draft_promise(final_text):
                auto_nudges += 1
                messages.append({
                    "role": "user",
                    "content": (
                        "You said you would draft but did not call any drafting tool. "
                        "Produce the document NOW: call the appropriate tool "
                        "(draft_skeletal / draft_affidavit / draft_legal_document / "
                        "pdf_generate / draft_application_bundle) in THIS turn using the "
                        "facts already provided. Do not reply with another promise; if a "
                        "required fact is genuinely missing, ask one specific question."
                    ),
                })
                continue
            break

        # Otherwise, execute every tool_use block in this assistant message
        # and append a single user message containing all tool_results.
        tool_results_content: list[dict] = []
        for block in final_message.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_id = block.id
            tool_name = block.name
            tool_input = block.input or {}

            yield {
                "type": "tool_call",
                "id": tool_id,
                "name": tool_name,
                "input": tool_input,
            }

            t0 = time.monotonic()
            envelope = await execute_tool(
                registry,
                tool_name,
                tool_input,
                timeout_seconds=settings.agent_tool_timeout_seconds,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000)

            result = envelope.get("result", {})
            db = envelope.get("db_sources") or []
            web = envelope.get("web_sources") or []

            for s in db:
                key = s.get("id") or json.dumps(s, sort_keys=True)
                db_sources_acc[str(key)] = s
            for s in web:
                key = s.get("url") or json.dumps(s, sort_keys=True)
                web_sources_acc[str(key)] = s

            tool_calls.append(
                ToolCallRecord(
                    id=tool_id,
                    name=tool_name,
                    input=tool_input,
                    result=result if isinstance(result, dict) else {"value": result},
                    duration_ms=elapsed_ms,
                    db_sources=db,
                    web_sources=web,
                )
            )

            artifact = envelope.get("artifact")
            extras = envelope.get("extra_artifacts") or []
            yield {
                "type": "tool_result",
                "id": tool_id,
                "name": tool_name,
                "ok": "error" not in (result if isinstance(result, dict) else {}),
                "db": db,
                "web": web,
                "artifact": artifact,
                "ms": elapsed_ms,
            }
            if artifact:
                yield {"type": "artifact", "artifact": artifact}
            for extra in extras:
                yield {"type": "artifact", "artifact": extra}

            # Surface the suggested templates so the UI can render clickable
            # cards inline in the chat. Tied to the originating tool_call_id
            # so the chronological reducer on the frontend can position the
            # cards immediately after the tool card.
            template_suggestions = envelope.get("templates")
            if template_suggestions:
                yield {
                    "type": "template_suggestion",
                    "tool_call_id": tool_id,
                    "templates": template_suggestions,
                }

            # Surface the application plan as a structured event so the UI
            # can render a Plan card inline (with cause of action, reliefs,
            # documents to file, etc.).
            application_plan = envelope.get("application_plan")
            if application_plan:
                yield {
                    "type": "application_plan",
                    "tool_call_id": tool_id,
                    "plan": application_plan,
                }

            # Surface the deterministic entitlement breakdown so the UI can
            # render a calculator card inline, immediately after the tool card.
            entitlement_breakdown = envelope.get("entitlement_breakdown")
            if entitlement_breakdown:
                yield {
                    "type": "entitlement_breakdown",
                    "tool_call_id": tool_id,
                    "breakdown": entitlement_breakdown,
                }

            # Surface matched precedent so the UI renders judgment cards inline.
            case_law = envelope.get("case_law")
            if case_law and case_law.get("cases"):
                yield {
                    "type": "case_law",
                    "tool_call_id": tool_id,
                    "cases": case_law["cases"],
                }

            # Study Mode: surface the cheat sheet as an inline revision card.
            cheat_sheet = envelope.get("cheat_sheet")
            if cheat_sheet:
                yield {
                    "type": "cheat_sheet",
                    "tool_call_id": tool_id,
                    "cheat_sheet": cheat_sheet,
                }

            # Study Mode: surface the interactive quiz.
            quiz = envelope.get("quiz")
            if quiz and quiz.get("questions"):
                yield {
                    "type": "quiz",
                    "tool_call_id": tool_id,
                    "quiz": quiz,
                }

            tool_results_content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": truncate_for_model(
                        envelope, settings.agent_max_tool_result_chars
                    ),
                }
            )

        messages.append({"role": "user", "content": tool_results_content})

    yield {
        "type": "sources",
        "db": list(db_sources_acc.values()),
        "web": list(web_sources_acc.values()),
    }

    yield {
        "type": "done",
        "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
        "timing": {"total_ms": round((time.monotonic() - started) * 1000)},
        "iterations": iterations,
        "model": model_name,
    }
