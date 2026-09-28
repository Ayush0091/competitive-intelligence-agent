"""Keyless search providers (DuckDuckGo HTML, Bing RSS) and the default live search chain."""

import httpx
import pytest

from app.agent import _live_search_tools
from app.config import Settings
from app.models.tool_result import ErrorType
from app.tools.keyless_search import BingRssProvider, DuckDuckGoProvider
from app.tools.web_search import WebSearchTool
from app.validator import ResultValidator

DDG_HTML = """
<html><body>
<div class="result results_links results_links_deep result--ad">
  <h2 class="result__title"><a class="result__a" href="https://ads.example.com/x">Sponsored</a></h2>
</div>
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fnvidia%2Damd&amp;rut=abc">
       NVIDIA vs AMD in AI accelerators</a></h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">AMD's MI-series chips compete with
     <b>NVIDIA</b> in data-center AI.</a>
</div>
<div class="result results_links web-result">
  <h2 class="result__title"><a class="result__a" href="https://news.example.org/story">Second</a></h2>
</div>
</body></html>"""

BING_NEWS_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel><title>Bing: nvidia</title>
<item><title>NVIDIA unveils new accelerator</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=1&amp;url=https%3a%2f%2fwww.example.com%2fnews%2fnvidia-launch&amp;c=1&amp;mkt=en-us</link>
<description>The company announced a &lt;b&gt;new&lt;/b&gt; chip.</description>
<pubDate>Sun, 27 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>No link item</title><description>skip me</description></item>
</channel></rss>"""


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_duckduckgo_parses_results_skips_ads_and_unwraps_redirects():
    hits = DuckDuckGoProvider.parse(DDG_HTML, 10)
    assert [h["url"] for h in hits] == ["https://www.example.com/nvidia-amd",
                                        "https://news.example.org/story"]
    assert hits[0]["title"] == "NVIDIA vs AMD in AI accelerators"
    assert "compete with NVIDIA" in hits[0]["snippet"]


def test_duckduckgo_tool_end_to_end_and_validated():
    def handler(req):
        assert req.method == "POST" and b"q=nvidia" in req.content
        return httpx.Response(200, text=DDG_HTML)
    tool = WebSearchTool(DuckDuckGoProvider(client=_client(handler)))
    result = tool.run(query="nvidia")
    assert ResultValidator().validate(result).valid
    assert result.data["provider"] == "duckduckgo"


def test_duckduckgo_bot_check_page_becomes_empty_result_for_fallback():
    captcha = "<html><body><div class='anomaly-modal'>Please verify you are human</div></body></html>"
    tool = WebSearchTool(DuckDuckGoProvider(client=_client(lambda r: httpx.Response(202, text=captcha))))
    report = ResultValidator().validate(tool.run(query="nvidia"))
    assert not report.valid and report.error_type == ErrorType.EMPTY  # -> fallback provider


def test_bing_news_rss_parses_and_unwraps_apiclick_links():
    hits = BingRssProvider.parse(BING_NEWS_RSS, 10)
    assert hits == [{"title": "NVIDIA unveils new accelerator",
                     "url": "https://www.example.com/news/nvidia-launch",
                     "snippet": "The company announced a new chip."}]


def test_bing_rss_request_and_malformed_xml():
    def handler(req):
        assert req.url.params["format"] == "rss" and req.url.path == "/news/search"
        return httpx.Response(200, text=BING_NEWS_RSS)
    ok = WebSearchTool(BingRssProvider("news", client=_client(handler))).run(query="nvidia")
    assert ok.success and ok.data["provider"] == "bing-news-rss"
    bad = WebSearchTool(BingRssProvider("web", client=_client(
        lambda r: httpx.Response(200, text="<html>not rss")))).run(query="x")
    assert not bad.success and bad.error.type == ErrorType.MALFORMED


def test_bing_rejects_unknown_kind():
    with pytest.raises(ValueError):
        BingRssProvider("images")


def _names(tools):
    return [t.provider.name for t in tools]


def test_default_live_chain_needs_no_keys_or_login():
    chain = _live_search_tools(Settings(), timeout=5)
    assert _names(chain) == ["duckduckgo", "bing-web-rss", "bing-news-rss"]


def test_wikipedia_only_added_with_contact_and_tavily_first_with_key():
    with_contact = _live_search_tools(Settings(agent_contact="me@example.com"), timeout=5)
    assert _names(with_contact)[-1] == "wikipedia"
    with_key = _live_search_tools(Settings(tavily_api_key="tvly-test"), timeout=5)
    assert _names(with_key)[0] == "tavily"
