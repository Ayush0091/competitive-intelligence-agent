import json

import httpx
import pytest

from app.models.tool_result import ErrorType
from app.tools.calculator import CalculationError, CalculatorTool, safe_eval
from app.tools.url_fetcher import UrlFetcherTool, extract_text, validate_url
from app.tools.web_search import TavilyProvider, WebSearchTool, WikipediaProvider

# ------------------------------------------------------------------ calculator


@pytest.mark.parametrize("expr,expected", [
    ("2 + 3 * 4", 14.0),
    ("(18.4 - 10.2) / 10.2 * 100", pytest.approx(80.392, rel=1e-3)),
    ("-5 + abs(-2)", -3.0),
    ("round(2.567, 2)", 2.57),
    ("max(1, 7, 3) ** 2", 49.0),
    ("7 % 4", 3.0),
])
def test_calculator_valid(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "open('x')",
    "(1).__class__",
    "a + 1",
    "[1, 2]",
    "'abc' * 3",
    "True + 1",
    "lambda: 1",
    "",
    "1 +",
    "9 ** 9999",
    "1" * 250,
])
def test_calculator_rejects_unsafe_or_invalid(expr):
    with pytest.raises(CalculationError):
        safe_eval(expr)


def test_calculator_tool_division_by_zero_is_structured_error():
    r = CalculatorTool().run(expression="1 / 0")
    assert not r.success
    assert r.error.type == ErrorType.INVALID_INPUT and "division by zero" in r.error.message
    assert r.error.retryable is False


def test_calculator_tool_success_shape():
    r = CalculatorTool().run(expression="10 / 4")
    assert r.success and r.data == {"expression": "10 / 4", "result": 2.5}
    assert r.duration_ms >= 0


# ------------------------------------------------------------------ URL validation


@pytest.mark.parametrize("url", ["https://example.com/a", "http://news.example.org/x?y=1"])
def test_validate_url_accepts_public_http(url):
    assert validate_url(url) is None


@pytest.mark.parametrize("url,reason", [
    ("", "empty"),
    ("ftp://example.com/file", "scheme"),
    ("javascript:alert(1)", "scheme"),
    ("https://", "host"),
    ("http://localhost:8000/admin", "local"),
    ("http://127.0.0.1/", "private"),
    ("http://192.168.1.10/", "private"),
    ("http://169.254.169.254/latest/meta-data", "private"),
    ("https://example.com/" + "a" * 3000, "too long"),
])
def test_validate_url_rejects(url, reason):
    assert reason in validate_url(url)


# ------------------------------------------------------------------ URL fetcher

HTML = ("<html><head><title>Test page</title><script>var secret=1;</script></head><body>"
        "<nav>Home | About | Contact us navigation</nav>"
        "<p>The company reported quarterly revenue of $4.1 billion, up strongly year over year.</p>"
        "<p>It also announced a new accelerator product aimed at data-center customers globally.</p>"
        "<p>Analysts expect competition to intensify as rivals ship competing products next year.</p>"
        "<footer>Copyright footer text that should not be extracted</footer></body></html>")


def _fetcher(handler, **kw) -> UrlFetcherTool:
    return UrlFetcherTool(client=httpx.Client(transport=httpx.MockTransport(handler),
                                              follow_redirects=True), **kw)


def test_extract_text_drops_scripts_and_chrome():
    title, text = extract_text(HTML)
    assert title == "Test page"
    assert "revenue of $4.1 billion" in text
    assert "secret" not in text and "navigation" not in text and "footer" not in text


def test_fetch_success_and_truncation():
    tool = _fetcher(lambda req: httpx.Response(200, text=HTML,
                                               headers={"content-type": "text/html"}),
                    max_chars=100)
    r = tool.run(url="https://example.com/article")
    assert r.success
    assert len(r.data["text"]) == 100 and r.data["truncated"] is True
    assert r.data["title"] == "Test page"


def test_fetch_timeout_is_structured_and_retryable():
    def handler(req):
        raise httpx.ReadTimeout("timed out", request=req)
    r = _fetcher(handler).run(url="https://example.com/slow")
    assert not r.success and r.error.type == ErrorType.TIMEOUT and r.error.retryable


@pytest.mark.parametrize("status,retryable", [(404, False), (403, False), (503, True), (429, True)])
def test_fetch_http_errors(status, retryable):
    r = _fetcher(lambda req: httpx.Response(status)).run(url="https://example.com/x")
    assert not r.success and r.error.type == ErrorType.HTTP_ERROR
    assert str(status) in r.error.message and r.error.retryable is retryable


def test_fetch_rejects_binary_content():
    r = _fetcher(lambda req: httpx.Response(200, content=b"%PDF-1.7",
                                            headers={"content-type": "application/pdf"})
                 ).run(url="https://example.com/file.pdf")
    assert not r.success and r.error.type == ErrorType.UNSUPPORTED_CONTENT


def test_fetch_rejects_near_empty_page():
    r = _fetcher(lambda req: httpx.Response(200, text="<html><body><p>hi</p></body></html>",
                                            headers={"content-type": "text/html"})
                 ).run(url="https://example.com/empty")
    assert not r.success and r.error.type == ErrorType.EMPTY


def test_fetch_blocks_ssrf_without_network_call():
    called = []
    r = _fetcher(lambda req: called.append(req) or httpx.Response(200)).run(url="http://127.0.0.1/")
    assert not r.success and r.error.type == ErrorType.INVALID_INPUT and not called


def test_fetch_blocks_redirect_to_internal_host():
    def handler(req):
        if req.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.5/admin"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    r = _fetcher(handler).run(url="https://example.com/redirect")
    assert not r.success and "redirected to disallowed URL" in r.error.message


# ------------------------------------------------------------------ web search


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tavily_success_normalizes_results():
    def handler(req):
        assert req.headers["authorization"] == "Bearer k-test-123456"
        assert json.loads(req.content)["query"] == "nvidia competitors"
        return httpx.Response(200, json={"results": [
            {"title": "A", "url": "https://a.com", "content": "snippet a", "score": 0.9}]})
    tool = WebSearchTool(TavilyProvider("k-test-123456", client=_client(handler)))
    r = tool.run(query="nvidia competitors")
    assert r.success
    assert r.data["results"] == [{"title": "A", "url": "https://a.com", "snippet": "snippet a"}]
    assert r.data["provider"] == "tavily"


def test_tavily_malformed_json_body():
    tool = WebSearchTool(TavilyProvider("k", client=_client(
        lambda req: httpx.Response(200, text="<html>not json</html>"))))
    r = tool.run(query="x")
    assert not r.success and r.error.type == ErrorType.MALFORMED


def test_tavily_missing_results_field():
    tool = WebSearchTool(TavilyProvider("k", client=_client(
        lambda req: httpx.Response(200, json={"unexpected": "invalid response"}))))
    r = tool.run(query="x")
    assert not r.success and r.error.type == ErrorType.MALFORMED and "results" in r.error.message


def test_tavily_server_error_and_timeout():
    tool = WebSearchTool(TavilyProvider("k", client=_client(lambda req: httpx.Response(500))))
    r = tool.run(query="x")
    assert r.error.type == ErrorType.HTTP_ERROR and r.error.retryable

    def slow(req):
        raise httpx.ConnectTimeout("slow", request=req)
    r = WebSearchTool(TavilyProvider("k", client=_client(slow))).run(query="x")
    assert r.error.type == ErrorType.TIMEOUT


def test_wikipedia_provider_strips_html_and_builds_urls():
    payload = {"query": {"search": [{"title": "Nvidia", "snippet": "<span>Nvidia</span> &amp; co"}]}}
    tool = WebSearchTool(WikipediaProvider(client=_client(lambda req: httpx.Response(200, json=payload))))
    r = tool.run(query="nvidia")
    assert r.data["results"][0] == {"title": "Nvidia", "url": "https://en.wikipedia.org/wiki/Nvidia",
                                    "snippet": "Nvidia & co"}


def test_search_rejects_empty_query_without_calling_provider():
    called = []
    tool = WebSearchTool(WikipediaProvider(client=_client(lambda r: called.append(r))))
    r = tool.run(query="   ")
    assert not r.success and r.error.type == ErrorType.INVALID_INPUT and not called
