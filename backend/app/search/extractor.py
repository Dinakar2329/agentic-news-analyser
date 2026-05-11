import asyncio
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from newspaper import Article


async def extract_article(url: str) -> dict:
    newspaper_result = await _extract_with_newspaper(url)
    if len(newspaper_result["text"]) > 500:
        return newspaper_result

    try:
        response = None
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    response = await client.get(url, headers={"User-Agent": "AgenticFactCheck/0.1"})
                    response.raise_for_status()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.3 * (attempt + 1))
        if response is None:
            raise RuntimeError("Article fetch returned no response")
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else urlparse(url).netloc
        text = " ".join(p.get_text(" ", strip=True) for p in soup.select("p")[:12])
        return {"title": title[:300], "text": text[:4000]}
    except Exception:
        return newspaper_result


async def _extract_with_newspaper(url: str) -> dict:
    def parse():
        article = Article(url)
        article.download()
        article.parse()
        return {
            "title": (article.title or urlparse(url).netloc)[:300],
            "text": (article.text or "")[:4000],
        }

    try:
        return await asyncio.to_thread(parse)
    except Exception:
        return {"title": urlparse(url).netloc, "text": ""}
