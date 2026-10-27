"""Levy News: a daily check of Zambia's most check-worthy stories (shadow mode).

sources   reads the outlet feeds, Google News, r/Zambia and iVerify
triage    groups new headlines into stories and picks the claims worth checking
verify    gathers evidence, checks quotes on their pages, and writes the verdict
store     keeps items, stories, checks and runs in Supabase
pipeline  runs it all once, or every NEWS_WATCH_HOURS inside the API

Shadow mode: every check waits for the editor's review, and nothing is shown to
users. Choices behind it are in ~/levy-research/news-pilot/RESULTS.md.
"""
