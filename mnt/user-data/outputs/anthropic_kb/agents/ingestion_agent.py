"""
Ingestion Agent
Scrapes all public Anthropic documentation, research, and web content.
Handles: HTML pages, PDFs, GitHub repos, sitemaps, and RSS feeds.
"""

import asyncio
import hashlib
import httpx
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse
from utils.logger import setup_logger

logger = setup_logger("ingestion_agent")


# All public Anthropic knowledge sources
ANTHROPIC_SOURCES = {
    "documentation": [
        "https://docs.anthropic.com",
        "https://docs.anthropic.com/en/docs/about-claude/models/overview",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview",
        "https://docs.anthropic.com/en/docs/build-with-claude/tool-use",
        "https://docs.anthropic.com/en/docs/build-with-claude/computer-use",
        "https://docs.anthropic.com/en/docs/build-with-claude/vision",
        "https://docs.anthropic.com/en/docs/build-with-claude/files",
        "https://docs.anthropic.com/en/docs/test-and-evaluate/eval-overview",
        "https://docs.anthropic.com/en/docs/about-claude/claude-ai-usage-policy",
        "https://docs.anthropic.com/en/api/getting-started",
        "https://docs.anthropic.com/en/api/messages",
        "https://docs.anthropic.com/en/api/streaming",
        "https://docs.anthropic.com/en/api/claude-on-amazon-bedrock",
        "https://docs.anthropic.com/en/api/claude-on-vertex-ai",
    ],
    "support": [
        "https://support.anthropic.com",
        "https://support.anthropic.com/en/collections/9356185-claude-ai",
    ],
    "research": [
        "https://www.anthropic.com/research",
        "https://www.anthropic.com/news",
        "https://www.anthropic.com/safety",
        "https://www.anthropic.com/index/core-views-on-ai-safety",
        "https://www.anthropic.com/index/constitutional-ai-harmlessness-from-ai-feedback",
        "https://www.anthropic.com/index/claude-s-constitution",
        "https://www.anthropic.com/index/anthropics-responsible-scaling-policy",
    ],
    "model_cards": [
        "https://www.anthropic.com/index/claude-3-model-card",
        "https://www-cdn.anthropic.com/de8ba9b01c9ab7cbabf5c33b80b7bbc618857627/claude-3-model-card.pdf",
    ],
    "github": [
        "https://github.com/anthropics/anthropic-sdk-python",
        "https://github.com/anthropics/anthropic-sdk-typescript",
        "https://github.com/anthropics/anthropic-cookbook",
        "https://github.com/anthropics/claude-code",
        "https://github.com/anthropics/model-spec",
    ],
}


class IngestionAgent:
    """
    Crawls and scrapes all public Anthropic knowledge sources.
    Produces clean, structured document objects ready for categorization.
    """

    def __init__(self, config: dict):
        self.config = config
        self.timeout = config.get("scrape_timeout", 30)
        self.max_depth = config.get("max_crawl_depth", 3)
        self.visited_urls: set = set()
        self.headers = {
            "User-Agent": "AnthropicKB-Bot/1.0 (Research; contact@yourdomain.com)"
        }

    async def scrape_all(self, source_urls: Optional[list] = None) -> list:
        """
        Scrape all Anthropic public sources concurrently.
        Returns a list of raw document dicts.
        """
        all_sources = []
        for category, urls in ANTHROPIC_SOURCES.items():
            for url in urls:
                all_sources.append((category, url))

        if source_urls:
            all_sources = [("custom", u) for u in source_urls]

        logger.info(f"Scraping {len(all_sources)} source URLs...")

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        ) as client:
            tasks = [self._scrape_source(client, cat, url) for cat, url in all_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        documents = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Scrape error: {result}")
            elif isinstance(result, list):
                documents.extend(result)
            elif result:
                documents.append(result)

        # Deduplicate by content hash
        seen = set()
        unique_docs = []
        for doc in documents:
            if doc["content_hash"] not in seen:
                seen.add(doc["content_hash"])
                unique_docs.append(doc)

        logger.info(f"Collected {len(unique_docs)} unique documents (from {len(documents)} total)")
        return unique_docs

    async def scrape_incremental(self, source_urls: list) -> list:
        """Only return documents that are new or have changed content."""
        # In a full implementation, compare content hashes against DB
        all_docs = await self.scrape_all(source_urls)
        logger.info(f"Incremental scrape: found {len(all_docs)} documents to check")
        return all_docs

    async def _scrape_source(self, client: httpx.AsyncClient, category: str, url: str):
        """Scrape a single source URL, auto-detecting type."""
        if url in self.visited_urls:
            return None
        self.visited_urls.add(url)

        try:
            if url.endswith(".pdf"):
                return await self._scrape_pdf(client, category, url)
            elif "github.com" in url:
                return await self._scrape_github(client, category, url)
            else:
                return await self._scrape_webpage(client, category, url)
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error scraping {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error scraping {url}: {e}")
            return None

    async def _scrape_webpage(self, client: httpx.AsyncClient, category: str, url: str):
        """Scrape an HTML webpage and extract clean text content."""
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove nav, footer, scripts, styles
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Extract title
        title = soup.title.string if soup.title else url

        # Extract main content
        main = soup.find("main") or soup.find("article") or soup.body
        content = main.get_text(separator="\n", strip=True) if main else ""
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Extract all internal links for potential further crawling
        links = []
        if soup.body:
            base_domain = urlparse(url).netloc
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                if urlparse(href).netloc == base_domain:
                    links.append(href)

        return self._build_document(
            url=url,
            title=str(title).strip(),
            content=content,
            category=category,
            doc_type="webpage",
            metadata={
                "internal_links": links[:50],  # Cap at 50 links
                "status_code": response.status_code,
                "content_length": len(content),
            },
        )

    async def _scrape_pdf(self, client: httpx.AsyncClient, category: str, url: str):
        """Download and extract text from PDF files."""
        response = await client.get(url)
        response.raise_for_status()

        # Note: Full PDF text extraction requires PyMuPDF (fitz) or pdfplumber
        # This returns the raw bytes reference; categorization agent handles extraction
        content = f"[PDF Document from {url}] - requires PDF text extraction"
        title = url.split("/")[-1].replace("-", " ").replace(".pdf", "").title()

        return self._build_document(
            url=url,
            title=title,
            content=content,
            category=category,
            doc_type="pdf",
            metadata={
                "file_size": len(response.content),
                "content_type": response.headers.get("content-type", ""),
            },
        )

    async def _scrape_github(self, client: httpx.AsyncClient, category: str, url: str):
        """Scrape GitHub repository README and key files via GitHub API."""
        # Convert github.com URL to API URL
        parts = url.replace("https://github.com/", "").split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"

            try:
                readme_response = await client.get(
                    api_url,
                    headers={**self.headers, "Accept": "application/vnd.github.v3.raw"},
                )
                content = readme_response.text if readme_response.status_code == 200 else ""
            except Exception:
                content = f"[GitHub repo: {owner}/{repo}]"

            # Also get repo metadata
            meta_response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=self.headers,
            )
            meta = meta_response.json() if meta_response.status_code == 200 else {}

            return self._build_document(
                url=url,
                title=f"GitHub: {owner}/{repo}",
                content=content,
                category=category,
                doc_type="github_repo",
                metadata={
                    "stars": meta.get("stargazers_count", 0),
                    "description": meta.get("description", ""),
                    "topics": meta.get("topics", []),
                    "language": meta.get("language", ""),
                    "last_updated": meta.get("updated_at", ""),
                },
            )
        return None

    def _build_document(
        self,
        url: str,
        title: str,
        content: str,
        category: str,
        doc_type: str,
        metadata: dict,
    ) -> dict:
        """Build a standardized document dict."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return {
            "id": hashlib.md5(url.encode()).hexdigest(),  # nosec B324
            "url": url,
            "title": title,
            "content": content,
            "content_hash": content_hash,
            "source_category": category,
            "doc_type": doc_type,
            "scraped_at": datetime.now().isoformat(),
            "metadata": metadata,
            # These will be filled by the categorization agent:
            "domain": None,
            "capability_tags": [],
            "model_versions": [],
            "summary": None,
            "embedding": None,
        }
