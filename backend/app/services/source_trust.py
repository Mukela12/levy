"""How far a web page can be trusted as a source of Zambian law.

Levy answers from its library first. When the library misses, it may go
online, and then the question is which page is allowed to stand behind a
statement of law. Four tiers, decided by the host alone:

    official       the State speaking for itself: Parliament, the Judiciary,
                   the Government Gazette, ministries and statutory bodies.
                   A statement of law may rest on these.
    institutional  professional bodies, universities, law firms, banks and
                   legal publishers. Good leads and commentary, never the
                   law itself: say who says it, then confirm on an official
                   source or in the library.
    news           the established press. Evidence that something happened,
                   not of what the law is.
    unofficial     everything else. A lead to follow, never a citation.

Kept apart from tools.py so the citation audit can ask the same question
without importing the whole tool registry.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Hosts that are official without ending in .gov.zm.
OFFICIAL_HOSTS: frozenset[str] = frozenset({
    "judiciaryzambia.com",       # the Judiciary of Zambia
    "gazettes.africa",           # the Government Gazette archive
    "archive.gazettes.africa",
    # Statutory bodies and regulators publishing their own rules, fees and forms.
    "zra.org.zm", "boz.zm", "pacra.org.zm", "rtsa.org.zm", "nhima.co.zm",
    "napsa.co.zm", "workers.com.zm", "zppa.org.zm", "eprocure.zppa.org.zm",
    "seczambia.org.zm", "pia.org.zm", "ccpc.org.zm", "zicta.zm", "erb.org.zm",
    "zema.org.zm", "rda.org.zm", "zesco.co.zm",
})

NEWS_HOSTS: frozenset[str] = frozenset({
    "znbc.co.zm", "daily-mail.co.zm", "times.co.zm", "diggers.news",
    "lusakatimes.com", "mwebantu.com", "themastonline.com",
})

INSTITUTIONAL_HOSTS: frozenset[str] = frozenset({
    "lawsofzambia.com", "lazcouncil.org.zm", "laz.org.zm", "zica.co.zm",
    "eiz.org.zm", "hpcz.org.zm", "gnc.org.zm", "unza.zm", "cbu.ac.zm",
    "mu.ac.zm", "zcas.ac.zm", "zambialii.org", "africanlii.org",
    "bowmanslaw.com", "dentons.com", "dlapiperafrica.com", "corpus.co.zm",
    "eiti.org", "zmeiti.com", "pmrc.org.zm", "luse.co.zm", "zanaco.co.zm",
    "stanbicbank.co.zm", "absa.co.zm", "fnbzambia.co.zm", "izb.co.zm",
    "accessbankplc.com", "firstalliancebankzambia.com",
})

TIERS = ("official", "institutional", "news", "unofficial")

_NOTES = {
    "official": "Official source. A statement of law may rest on this page; quote it and cite the URL.",
    "institutional": ("Institutional source, not the law itself. Say who says it, and confirm the point "
                      "in the library or on an official site before stating it as law."),
    "news": "News report. Evidence that something happened, never of what the law is.",
    "unofficial": ("Unofficial page. A lead only: do not cite it for what Zambian law says. Confirm on "
                   "an official site, or say the point is unconfirmed."),
}


def host_of(url: str) -> str:
    try:
        host = (urlparse(url if "//" in (url or "") else "//" + (url or "")).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return host[4:] if host.startswith("www.") else host


def _in(host: str, hosts: frozenset[str]) -> bool:
    return any(host == h or host.endswith("." + h) for h in hosts)


def trust_of(url: str) -> str:
    """The tier of the page at `url`."""
    host = host_of(url)
    if not host:
        return "unofficial"
    if host == "gov.zm" or host.endswith(".gov.zm") or _in(host, OFFICIAL_HOSTS):
        return "official"
    if _in(host, NEWS_HOSTS):
        return "news"
    if _in(host, INSTITUTIONAL_HOSTS):
        return "institutional"
    return "unofficial"


def trust_note(tier: str) -> str:
    return _NOTES.get(tier, _NOTES["unofficial"])
