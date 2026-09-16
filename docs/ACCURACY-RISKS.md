# Where Levy can be wrong

Written 16 September 2026, after the repealed-Act bug. Plain language on
purpose. The question behind it: what can make Levy give a user an answer
that is confidently wrong about Zambian law.

Levy does not invent law out of nothing. It answers from documents it holds,
and it cites them. So almost every wrong answer comes from one of four
things:

1. The document it quoted is no longer the law.
2. The document it needed is not in the library, and it answered from a
   weaker one instead of saying so.
3. The document is in the library but damaged, so it quoted broken text.
4. The document is right and current, but the reasoning on top of it is
   wrong.

Below, each hole, how big it is today, and what closes it. Ranked by how
likely it is to hit a real user.

---

## 1. Status: an Act that has been repealed

**This is the one that already bit us.** A user asked about sentencing a
child and Levy answered from the Juveniles Act 1956, which the Children's
Code Act 2022 repealed. The library holds both, and to a search engine they
look identical. This is the single most dangerous class of error, because
the answer is fluent, cited, and completely out of date.

**What we did about it.** There is now a law map built out of the corpus
itself: it reads the repeal clauses ("the X Act, 1956, is repealed") and the
long titles ("An Act to repeal and replace the X Act") and records what
killed what. Every search result now carries its status, so before the model
writes a word it has been told "REPEALED, replaced by the Children's Code
Act". The Legislation pages show a Repealed badge and link to the Act that
replaced it.

**What is still open.**

- 84 Acts are known to be repealed. 414 of the 873 Acts in the library have
  some status evidence. **459 have none.** That does not mean they are
  repealed. It means the corpus contains no clause either way, so Levy is
  quiet about their status rather than confident.
- **A repeal is only visible if the repealing Act is in the library.** If
  Parliament passes an Act in 2026 that repeals something, and we never
  harvest it, the old Act keeps looking alive forever. This is the biggest
  remaining version of the original bug.
- 114 repeal mentions still do not resolve to a document, mostly because the
  Act named was never harvested.

## 2. Coverage: the law we simply do not hold

**Zero statutory instruments.** Not one. SIs are where the actual numbers
live: fees, thresholds, forms, commencement dates, minimum wage, road
traffic charges. A user asking "what is the fee to register a company" is
asking an SI question, and the library cannot answer it. Levy should go to
the web for those, and often does, but the library will never back it up.

**98 Acts from Parliament's own index are missing**, 15 of them from 2020 or
later, including the Anti-Human Trafficking Act 2022, the Mobile Money
Transactions Levy Act 2024, and several 2021 amendment Acts. If someone asks
about human trafficking, Levy has no Act to quote.

**Case law is thin and recent years are thinnest.** 1,137 judgments, but
only 32 dated 2025 and 4 dated 2026, and 991 carry no year at all in their
metadata. A user asking "what is the current position of the Court of
Appeal" can get a 2019 answer presented as settled.

**Why this causes wrong answers rather than honest gaps.** The prompt tells
Levy that a miss means go to the official web, and a miss is defined as zero
results or low similarity. The failure mode is the opposite: retrieval
returns something that *looks* like a good hit, so nothing escalates. A
question about company registration fees pulls in the Companies Act, which
is genuinely relevant and genuinely does not contain the fee. The gap is
invisible to the trigger.

## 3. Damage: text that is broken in the library

Most Acts were scanned and run through OCR, and OCR breaks words. The corpus
is full of "Educati on Act", "Commissi on", "Hum an Rights", "Cred its". We
fixed the matching side of this today, which found 25 repealed Acts that had
been hiding behind split words. But the damage is still in the text Levy
quotes, and a user reading a mangled section reasonably concludes the tool is
sloppy.

Also:

- **14 duplicate title groups covering 42 documents.** The same Act ingested
  twice, sometimes one copy complete and one truncated. Retrieval can pick
  the worse copy.
- **7 documents with zero chunks.** They exist in the index and are invisible
  to search.
- **At least one Act truncated at 120 chunks** (National Health Insurance Act
  2018), meaning the back half of the Act is not in the library at all.
  Levy will answer "that is not in the Act" when it is.

## 4. Reasoning on top of good documents

- **Citation badges verify that a source exists, not that it says what the
  answer claims.** A green badge means "this Act and section are real". It
  does not mean the proposition is supported. We learned this with an Order
  14 citation that was real but did not say what the answer said.
- **A principal Act quoted without its amendments.** Levy now flags "amended
  by N amendment Acts", but the amendments are separate documents. The
  section text it quotes is the original wording, not the wording as amended.
  For tax and companies law, where amendments come yearly, this matters.
- **Section numbering shifts between editions.** Two copies of the same Act
  from different years can number sections differently.
- **Persuasive vs binding.** Levy can cite a High Court judgment as though it
  settles a point the Supreme Court has since taken the other way.

---

## Does Levy check for new law on a schedule?

**No. There is no scheduler of any kind.** No cron, no GitHub Actions, no
background job. Every harvest has been a script I run by hand, and the law
map is a file in the repo that only changes when I rebuild it. Nothing in
production goes looking for new Acts.

**Does the harness having web access cover it?** Partly, and only during a
question. When Levy is answering, it can search parliament.gov.zm and the
Judiciary site and read what it finds, and it is told to do that whenever the
library falls short. So a user who asks about a 2026 Act can still get a good
answer.

But web access at question time does not fix the corpus, and it does not fire
when the library thinks it already has the answer. Three consequences:

1. Nothing learned from a web search is kept. The next user pays the same
   latency and gets the same gap.
2. A repeal passed last month is invisible until someone asks a question that
   happens to miss.
3. The law map cannot know about an Act the library never saw.

**What would close it**, cheapest first:

- **A monthly harvest.** Pull Parliament's Acts index, diff it against the
  library, ingest anything new, rebuild the law map, redeploy. The diff
  script already exists. This is the single highest-value habit, and it is
  the thing that keeps the repealed-Act fix working over time.
- **Ingest statutory instruments.** Biggest coverage gap by user impact.
- **Trigger the web fallback on staleness, not just on a miss.** If the best
  hit is an Act with no known status and the question is about something
  current, check the source. Today the trigger only fires on a bad score.
- **A freshness line in the answer.** "This Act is in the library as at
  September 2026, and I have not checked for amendments since." Honest, and
  cheap.
- **Fix the 42 duplicates, 7 empty documents, and the truncated Act.** Small,
  mechanical, removes a whole class of confusing answers.

## The honest summary

The dangerous hole was Acts that are no longer law being quoted as law. That
one is now substantially closed: 84 repealed Acts are flagged to the model
and to readers, and the flag travels with every search result.

The hole that remains open is **age**. Levy's library is a snapshot, nothing
tells it when the snapshot went stale, and no job refreshes it. Everything
else on this page is a smaller version of that.
