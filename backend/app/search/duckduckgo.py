from urllib.parse import parse_qs, quote_plus, unquote, urlparse
import asyncio

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


class DuckDuckGoSearch:
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        response = None
        async with httpx.AsyncClient(timeout=settings.duckduckgo_timeout, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    response = await client.get(url, headers={"User-Agent": "AgenticFactCheck/0.1"})
                    response.raise_for_status()
                    break
                except Exception:
                    if attempt == 2:
                        return []
                    await asyncio.sleep(0.4 * (attempt + 1))
        if response is None:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for item in soup.select(".result")[:max_results]:
            link = item.select_one(".result__a")
            snippet = item.select_one(".result__snippet")
            if not link or not link.get("href"):
                continue
            href = self._normalize_result_url(link.get("href"))
            results.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "url": href,
                    "snippet": snippet.get_text(" ", strip=True) if snippet else "",
                    "domain": urlparse(href).netloc.replace("www.", ""),
                }
            )
        return results

    def _normalize_result_url(self, href: str) -> str:
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("/"):
            return f"https://duckduckgo.com{href}"
        return href
