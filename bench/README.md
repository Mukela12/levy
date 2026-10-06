# Is the harness worth it?

A weekly head-to-head: the same nine Zambian legal questions put to Levy,
ChatGPT and Claude, scored the same way.

The question this answers is not "which writes better". A general model writes
beautifully about Zambian law and gets the section number wrong, and that is
the failure that matters to someone filing a document on Monday. So the scoring
is mechanical and checks three things:

| | |
|---|---|
| **grounded** | did it name the right instrument and provision? |
| **correct**  | did it state the operative fact? |
| **honest**   | did it avoid the traps? |

A trap is not a missing mark, it is a separate count, because inventing the
facts of a case that does not exist is not "one point short" — it is the whole
reason a lawyer cannot rely on the tool.

## The questions

Nine, in `questions.json`, seven of them asked by real users in September 2026.
Every ground truth was read out of Levy's own corpus and law map, and each
question records where (`verified_against`). They are chosen to separate a
harness from a model:

- **statutory detail** (2) — the exact section and figure. A model that has
  read about the Employment Code will know the shape and miss the number.
- **currency** (2) — an Act passed but not commenced, and a Bill that is still
  a Bill. Training data goes stale here; a law map does not.
- **repeal trap** (1) — the Juveniles Act, repealed by the Children's Code Act
  2022. Confidently applying the dead statute is the classic failure.
- **hallucination trap** (1) — a case that does not exist. Describing its facts
  is an automatic trap.
- **procedure** (1), **case law** (1) — things only the corpus holds.
- **control** (1) — "what is estoppel", where the harness should NOT help. If
  Levy is worse here, the harness is costing something.

## Running it

```bash
# 1. Levy, through the live API as the QA probe. Costs nine answers.
python bench/run_levy.py

# 2. The rivals. Print the block, paste it into ChatGPT and into Claude,
#    save each whole reply to a file, then file it.
python bench/capture.py --prompt
python bench/capture.py --model chatgpt --from /tmp/chatgpt-reply.txt
python bench/capture.py --model claude  --from /tmp/claude-reply.txt

# 3. Score them together.
python bench/grade.py bench/results/$(date +%F)-*.json
```

Results are kept per week in `bench/results/YYYY-MM-DD-<model>.json`, so the
interesting number is not any one week's score but whether the gap is closing.

## Reading the result

The headline is the gap on **currency**, **repeal trap** and **hallucination
trap**. Those are the three a general model cannot fix by getting bigger,
because they depend on knowing what the law is *today* and what the library
actually holds.

If Levy leads on those and roughly ties on the control question, the harness is
earning its keep. If the gap on them closes to nothing, it is not.

## Scoring, since 6 October 2026

`grade.py` gives every answer one grade on the rubric of Magesh et al.
(Stanford, 2024/2025), so the numbers can be set beside the published
legal-research studies:

| grade | meaning |
|---|---|
| **hallucinated** | a trap tripped, dead law applied as current, or a false premise accepted |
| **correct** | none of those, and every required element is there |
| **incomplete** | nothing false, but something missing, or a refusal where an answer existed |

What each question can ask for (all optional, all in `questions.json`):

- `must_cite`, `must_state`, `must_not`: regex alternatives, as before.
- `provisions`: the right instrument **and** the right section or rule,
  within 220 characters of each other ("Employment Code" near "section 77").
  General chatbots name the Act and skip the section; this is where it shows.
- `dead_law`: a repealed Act or section, or an Act passed but not in force.
  Mentioning it is fine; every top-level section of the answer that mentions
  it must also say it is dead. Applying it as current law is a hallucination.
- `false_premise`: the question carries a wrong assumption; the answer must
  reject it (`reject` patterns). Models tend to accept a user's wrong legal
  assumption and answer on it.

Options: `--audit` runs Levy's own citation audit over any model's answers
(free: database reads only) and reports citations not in the library and dead
law relied on without saying so, sentence by sentence. `--export-judge FILE`
writes question, ground truth, answer and rubric per line, for grading by a
person or a model later; nothing is sent anywhere.

The correct rate is printed with its 95% Wilson interval. On ten questions it
spans 40 points or more, which is the honest statement of what a weekly run
can show: it is a smoke test. A claim that Levy is more accurate needs the
frozen gold set (150 to 200 questions, ground truth from official texts, not
from Levy's library: the 28 September answer key inherited Levy's own s.24
error).

Re-grading the 28 September run with these rules: ChatGPT 9 correct, 1
incomplete; Levy 9 correct, 1 hallucinated (the s.24 answer); the Claude app
6 correct, 4 incomplete (no section numbers on the statutory questions).

`python -m unittest bench/test_grade.py` tests the grader's own rules.

## Known bias, and why the gap is the number to read

Levy scored 22/22 with no traps on the first run, 28 September 2026. That is a
warning about the benchmark, not a result. Seven of the questions come from
sessions Levy had already answered well, and every ground truth was verified by
reading Levy's own corpus and law map — so by construction Levy holds the source
for each one. A home team that picks the fixtures wins.

`old-authority` was added specifically as a counter-test, on a gap found the
week before: the Judiciary publishes nothing before 2000, so Levy cannot hold
the 1985 judgment. It answered correctly anyway, because a modern judgment
carries the citation in its case list. Worth knowing, and worth trying to break
again.

So Levy's own column means little. What means something is the rivals' column
beside it, and specifically the gap on **currency**, **repeal trap** and
**hallucination trap**. If that gap is wide, the harness is doing work no model
size fixes. If it closes, it is not.

When a question stops discriminating — everyone gets it — replace it with one
drawn from that week's real conversations, especially one Levy got wrong.

## What this does not measure

Retrieval quality on its own (that is `backend/tests/evaluate.py`), answer
style, speed, or how any of them handle a long document. It is a narrow
instrument pointed at one question.
