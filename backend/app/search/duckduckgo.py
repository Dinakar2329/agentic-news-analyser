import asyncio
import logging
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


logger = logging.getLogger(__name__)


# A more browser-like UA — DuckDuckGo's HTML endpoint serves a near-empty
# page (no `.result` elements) when it detects a bot-like UA, which is the
# root cause of the silent "no results" failure we kept hitting.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class DuckDuckGoSearch:
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        endpoints = [
            ("https://html.duckduckgo.com/html/", "html"),
            ("https://lite.duckduckgo.com/lite/", "lite"),
        ]

        async with httpx.AsyncClient(
            timeout=settings.duckduckgo_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://duckduckgo.com/",
            },
        ) as client:
            for endpoint_url, flavor in endpoints:
                results = await self._fetch_endpoint(client, endpoint_url, flavor, query, max_results)
                if results:
                    return results
                logger.info(
                    "duckduckgo_endpoint_empty endpoint=%s query=%r",
                    flavor,
                    query,
                )

        logger.warning("duckduckgo_all_endpoints_empty query=%r", query)
        return []

    async def _fetch_endpoint(
        self,
        client: httpx.AsyncClient,
        endpoint_url: str,
        flavor: str,
        query: str,
        max_results: int,
    ) -> list[dict]:
        for attempt in range(3):
            try:
                # POST works for both /html/ and /lite/ and matches what a
                # real browser submitting the search form does.
                response = await client.post(endpoint_url, data={"q": query, "b": "", "kl": "us-en"})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "duckduckgo_http_error endpoint=%s attempt=%d error=%s query=%r",
                    flavor,
                    attempt + 1,
                    exc,
                    query,
                )
                if attempt == 2:
                    return []
                await asyncio.sleep(0.4 * (attempt + 1))
                continue

            body = response.text
            logger.info(
                "duckduckgo_response endpoint=%s status=%d bytes=%d query=%r",
                flavor,
                response.status_code,
                len(body),
                query,
            )
            results = self._parse(body, flavor, max_results)
            if results:
                return results
            # Got a 200 but no parseable results — likely anti-bot blank page.
            # Retry once with a small backoff before falling through to the
            # next endpoint.
            if attempt == 0:
                await asyncio.sleep(0.6)
                continue
            return []
        return []

    def _parse(self, html: str, flavor: str, max_results: int) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []

        if flavor == "html":
            items = soup.select(".result")
            for item in items[:max_results]:
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
        else:  # lite
            # The lite endpoint renders results as a flat table of <a class="result-link"> rows.
            for link in soup.select("a.result-link")[:max_results]:
                href = link.get("href")
                if not href:
                    continue
                href = self._normalize_result_url(href)
                # The snippet sits in the next <td.result-snippet> sibling row.
                snippet_text = ""
                parent_row = link.find_parent("tr")
                if parent_row:
                    snippet_node = parent_row.find_next("td", class_="result-snippet")
                    if snippet_node:
                        snippet_text = snippet_node.get_text(" ", strip=True)
                results.append(
                    {
                        "title": link.get_text(" ", strip=True),
                        "url": href,
                        "snippet": snippet_text,
                        "domain": urlparse(href).netloc.replace("www.", ""),
                    }
                )

        logger.info(
            "duckduckgo_parsed endpoint=%s parsed_count=%d",
            flavor,
            len(results),
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
