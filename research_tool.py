"""
Pluggable web-research interface used by the orchestrator.

Two implementations are provided:

  - ComposioResearchTool: uses Composio's own hosted toolkits so the
    "research agent" is itself built on the product being evaluated.
    Requires COMPOSIO_API_KEY. Uses a search toolkit (e.g. Composio's
    search/Tavily integration) for `search()` and a browser/fetch toolkit
    for `fetch()` on pages that need real rendering (help centers behind
    JS, etc).

  - RequestsResearchTool: a plain requests + trafilatura/BeautifulSoup
    fallback for local dev / offline testing without API keys.

Swap which one `make_default_tool()` returns depending on what's configured
in your environment.
"""

import os


class ResearchTool:
    def search(self, query: str, max_results: int = 3) -> list:
        raise NotImplementedError

    def fetch(self, url: str) -> str:
        raise NotImplementedError


class ComposioResearchTool(ResearchTool):
    def __init__(self):
        from composio import Composio  # composio-core SDK
        self.client = Composio(api_key=os.environ["COMPOSIO_API_KEY"])

    def search(self, query, max_results=3):
        # Uses Composio's hosted search toolkit action. Action slug depends
        # on which search toolkit is enabled on your Composio project
        # (e.g. COMPOSIO_SEARCH_SEARCH, TAVILY_SEARCH). Adjust accordingly.
        res = self.client.tools.execute(
            "COMPOSIO_SEARCH_SEARCH",
            arguments={"query": query, "num_results": max_results},
        )
        return [r["url"] for r in res.get("data", {}).get("results", [])][:max_results]

    def fetch(self, url):
        # Uses a browser/fetch-capable toolkit for pages needing JS rendering.
        res = self.client.tools.execute(
            "COMPOSIO_SEARCH_FETCH",  # or a browser-use toolkit action
            arguments={"url": url},
        )
        return res.get("data", {}).get("content", "")


class RequestsResearchTool(ResearchTool):
    """Offline-friendly fallback: plain HTTP GET + basic text extraction."""

    def __init__(self):
        import requests
        self.requests = requests

    def search(self, query, max_results=3):
        # No API key search fallback: caller should pass known hint URLs
        # directly, or plug in a search API (Bing/Serper/Tavily) here.
        raise NotImplementedError(
            "RequestsResearchTool has no search backend configured; "
            "set COMPOSIO_API_KEY to use ComposioResearchTool, or wire in "
            "a search API key here."
        )

    def fetch(self, url):
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            text = trafilatura.extract(downloaded) if downloaded else None
            if text:
                return text
        except ImportError:
            pass
        resp = self.requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        return resp.text[:20000]


def make_default_tool() -> ResearchTool:
    if os.environ.get("COMPOSIO_API_KEY"):
        return ComposioResearchTool()
    return RequestsResearchTool()
