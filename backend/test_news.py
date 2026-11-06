"""Headlines from newspaper RSS: only safe links to the publisher, traffic stories flagged.  python -m pytest -q"""
import email.utils
import time

import news

# published an hour ago: a fixed date would fall out of the API's 36-hour window and fail the test later
_PUB = email.utils.formatdate(time.time() - 3600).encode()
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Dhaka tailback stretches 10 km on Airport Road</title><link>https://www.thedailystar.net/a</link>
  <pubDate>""" + _PUB + b"""</pubDate></item>
<item><title><![CDATA[<b>Cricket</b> &amp; more]]></title><link>https://www.thedailystar.net/b</link></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
<item><title>Bus fare hike</title><link>https://evil.example/thedailystar.net</link></item>
<item><title>Lookalike</title><link>https://notthedailystar.net/x</link></item>
</channel></rss>"""


def test_parse_keeps_only_publisher_links_and_flags_traffic():
    items = news.parse(RSS, "The Daily Star", "en", ("thedailystar.net",))
    assert [i["url"] for i in items] == ["https://www.thedailystar.net/a", "https://www.thedailystar.net/b"]
    assert items[0]["traffic"] and not items[1]["traffic"]
    assert items[1]["title"] == "Cricket & more"          # tags stripped, entities decoded: plain text only
    assert items[0]["published"] is not None


def test_bangla_traffic_words_are_recognised():
    xml = "<rss><channel><item><title>মহাসড়কে তীব্র যানজট</title><link>https://www.prothomalo.com/x</link></item>" \
          "<item><title>নির্বাচন</title><link>https://www.prothomalo.com/y</link></item></channel></rss>"
    items = news.parse(xml.encode(), "প্রথম আলো", "bn", ("prothomalo.com",))
    assert [i["traffic"] for i in items] == [True, False]


def test_entity_bombs_are_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss>&b;</rss>'
    try:
        news.parse(bomb, "x", "en", ("x.com",))
    except Exception:
        return
    raise AssertionError("entity declarations must be rejected")


def test_api_filters_and_handles_a_dead_feed(monkeypatch):
    def fake_fetch(url):
        if "jagonews24" in url:
            raise TimeoutError
        return RSS if "thedailystar" in url else b"<rss><channel></channel></rss>"
    monkeypatch.setattr(news, "_fetch", fake_fetch)
    news.refresh()
    traffic = news.news(kind="traffic")
    assert [i["url"] for i in traffic["items"]] == ["https://www.thedailystar.net/a"]
    assert "জাগো নিউজ" in traffic["unavailable"]
    assert len(news.news(kind="top")["items"]) == 2
    assert news.news(kind="top", lang="bn")["items"] == []
    old = {"title": "Old jam", "url": "https://www.thedailystar.net/old", "source": "s", "lang": "en",
           "published": time.time() - 5 * 86400, "traffic": True}
    news._items.append(old)
    assert old not in news.news(kind="traffic")["items"]   # "daily": older stories drop off


def test_short_words_do_not_match_inside_other_words():
    hit = lambda t: bool(news.TRAFFIC.search(t))   # noqa: E731
    for t in ("প্রবাসীরা রেমিট্যান্সের উৎস", "১০৭ অভিবাসীকে ফেরত", "বাসি খাবার বিক্রি", "অবিশ্বাস", "কন্ট্রাক্ট",
              "Bangladeshis abroad", "social welfare fund"):
        assert not hit(t), t
    for t in ("বাস চাপায় নিহত ২", "বাসের ধাক্কায়", "ট্রাকের চাপায়", "সড়কে ঝরল প্রাণ", "Bus fares up 20%",
              "Airport Road jam", "গাড়ি ভাড়া বেড়েছে", "সড়কে", "সড়কে"):  # both ড় spellings
        assert hit(t), t
