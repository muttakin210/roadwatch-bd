"""Daily top news: headlines and links from Bangladeshi newspapers' public RSS feeds.

Only the headline, source, time and a link to the publisher are shown (never the article text or images).
Feeds are fetched in the background every REFRESH_S and kept in memory, so a visitor never waits on a newspaper,
and the newspapers get a few requests per hour from us, not one per visitor.
"""
from __future__ import annotations

import email.utils
import html
import re
import threading
import time
import unicodedata
import urllib.request
from urllib.parse import urlparse

from defusedxml import ElementTree as ET   # untrusted XML: no entity-expansion or external-entity tricks
from fastapi import APIRouter, HTTPException

router = APIRouter()

FEEDS = [   # (source name, language, feed url, the publisher's own domains: links elsewhere are dropped)
    ("The Daily Star", "en", "https://www.thedailystar.net/frontpage/rss.xml", ("thedailystar.net",)),
    ("Prothom Alo English", "en", "https://en.prothomalo.com/feed/", ("prothomalo.com",)),
    ("The Business Standard", "en", "https://www.tbsnews.net/rss.xml", ("tbsnews.net",)),
    ("প্রথম আলো", "bn", "https://www.prothomalo.com/feed/", ("prothomalo.com",)),
    ("জাগো নিউজ", "bn", "https://www.jagonews24.com/rss/rss.xml", ("jagonews24.com",)),
    ("বিবিসি বাংলা", "bn", "https://feeds.bbci.co.uk/bengali/rss.xml", ("bbc.com", "bbc.co.uk")),
]
REFRESH_S = 2 * 3600
MAX_BYTES = 3_000_000
UA = "RoadWatchBD/1.0 (+https://roadwatch-bd-alpha.vercel.app; headlines only)"
# Bangla has no \b that works across vowel signs, so short words get explicit "not inside another word"
# guards: বাস (bus) must not match প্রবাসী or বিশ্বাস, ট্রাক not কন্ট্রাক্ট; English road ≠ abroad, fare ≠ welfare.
_BN = "ঀ-৿"


def _bn_word(w: str) -> str:
    return f"(?<![{_BN}]){w}(?:ে|ের|টি|টির|গুলো|গুলোর|চাপায়)?(?![{_BN}])"


TRAFFIC = re.compile(unicodedata.normalize("NFC", 
    r"\btraffic|tailback|gridlock|congestion|\bjams?\b|\broads?\b|highway|expressway|flyover|\baccidents?\b|"
    r"\bcrash|collision|\bbus(es)?\b|\btrucks?\b|motorcycle|motorbike|rickshaw|\bcng\b|\bbrta\b|\bdmp\b|"
    r"\btransport|metro ?rail|\bfares?\b|pedestrian|"
    r"যানজট|সড়ক|মহাসড়ক|দুর্ঘটনা|ট্রাফিক|পরিবহ|বিআরটিএ|মেট্রোরেল|ফ্লাইওভার|এক্সপ্রেসওয়ে|রিকশা|মোটরসাইকেল|পথচারী|"
    + "|".join(_bn_word(w) for w in ("বাস", "ট্রাক", "গাড়ি", "ভাড়া", "লঞ্চ"))),
    re.I,
)

_items: list[dict] = []
_updated: float = 0.0
_errors: dict[str, str] = {}
_lock = threading.Lock()


def _text(el, tag: str) -> str:
    x = el.find(tag)
    raw = (x.text or "") if x is not None else ""
    # one Unicode spelling of Bangla (ড় can be one code point or ড + nukta) so keyword matching works
    raw = unicodedata.normalize("NFC", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _own(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def parse(xml: bytes, source: str, lang: str, domains: tuple[str, ...]) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        title, link = _text(it, "title")[:300], _text(it, "link")
        u = urlparse(link)
        # only real web links to the publisher's own site (no javascript:, no third-party redirects)
        if not title or u.scheme not in ("http", "https") or not u.hostname or not _own(u.hostname, domains):
            continue
        ts = None
        pub = _text(it, "pubDate")
        if pub:
            try:
                ts = email.utils.parsedate_to_datetime(pub).timestamp()
            except (TypeError, ValueError):
                ts = None
        out.append({"title": title, "url": link, "source": source, "lang": lang, "published": ts,
                    "traffic": bool(TRAFFIC.search(title))})
    return out


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=20) as r:   # noqa: S310 (fixed https URLs above)
        return r.read(MAX_BYTES + 1)[:MAX_BYTES]


def refresh() -> None:
    global _items, _updated
    got: list[dict] = []
    errors: dict[str, str] = {}
    for source, lang, url, domains in FEEDS:
        try:
            got += parse(_fetch(url), source, lang, domains)
        except Exception as e:   # one broken feed must not hide the others
            errors[source] = f"{type(e).__name__}"
    seen, unique = set(), []
    for it in sorted(got, key=lambda x: x["published"] or 0, reverse=True):
        if it["url"] not in seen:
            seen.add(it["url"])
            unique.append(it)
    with _lock:
        if unique or not _items:
            _items = unique
        _errors.clear()
        _errors.update(errors)
        _updated = time.time()


def _loop() -> None:
    while True:
        refresh()
        time.sleep(REFRESH_S)


def start() -> None:
    threading.Thread(target=_loop, daemon=True, name="news").start()


@router.get("/api/news")
def news(kind: str = "traffic", lang: str = "", limit: int = 30):
    if kind not in ("traffic", "top") or lang not in ("", "en", "bn"):
        raise HTTPException(400, "unknown filter")
    limit = max(1, min(limit, 60))
    day_ago = time.time() - 36 * 3600   # "daily": the last day and a half, so morning papers still show
    with _lock:
        items = [i for i in _items if (kind == "top" or i["traffic"]) and (not lang or i["lang"] == lang)
                 and (i["published"] or day_ago) >= day_ago]
        return {"items": items[:limit], "updated": _updated or None, "sources": [f[0] for f in FEEDS],
                "unavailable": sorted(_errors)}
