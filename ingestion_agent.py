"""
Universal Ingestion Agent
Scrapes web URLs, parses local directories, documents, PDFs, and Excel R&D workbooks.
"""

import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional
from bs4 import BeautifulSoup
import httpx

import os as _os
from pathlib import Path as _Path

def _safe_path(user_path: str, base_dir: Optional[str] = None) -> str:
    if base_dir is None:
        base_dir = str(_Path(__file__).resolve().parent)
    real = _os.path.realpath(_os.path.abspath(user_path))
    allowed = _os.path.realpath(_os.path.abspath(base_dir))
    if not real.startswith(allowed + _os.sep) and real != allowed:
        raise ValueError(f"Path traversal attempt detected: {user_path!r}")
    return real

try:
    from logger import setup_logger  # type: ignore
    logger = setup_logger("ingestion_agent")
except ImportError:
    try:
        from utils.logger import setup_logger  # type: ignore
        logger = setup_logger("ingestion_agent")
    except ImportError:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("ingestion_agent")


class IngestionAgent:
    """Ingests data from arbitrary URLs, local directories, documents, and spreadsheets."""

    def __init__(self, config: dict):
        self.config = config
        self.timeout = config.get("scrape_timeout", 30)
        self.visited_urls: set = set()
        self.headers = {
            "User-Agent": "UniversalResearchAgent/1.0 (KnowledgeBase Research Bot)"
        }

    async def scrape_all(self, source_targets: Optional[list[str]] = None) -> list[dict]:
        targets: list[str] = source_targets if source_targets is not None else self.config.get("research_targets", [
            "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
            "https://docs.anthropic.com",
        ])

        web_urls: list[str] = []
        local_targets: list[str] = []

        for target in targets:
            target_str = str(target).strip()
            if target_str.startswith("http://") or target_str.startswith("https://"):
                web_urls.append(target_str)
            else:
                local_targets.append(target_str)

        documents: list[dict] = []

        # 1. Ingest Web URLs
        if web_urls:
            logger.info(f"Ingesting {len(web_urls)} web source targets...")
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                tasks = [self._scrape_web_target(client, u) for u in web_urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        logger.warning(f"Web ingestion notice: {res}")
                    elif isinstance(res, dict):
                        documents.append(res)
                    elif isinstance(res, list):
                        documents.extend(res)

        # 2. Ingest Local Files & Spreadsheets
        if local_targets:
            logger.info(f"Scanning {len(local_targets)} local target paths...")
            for path in local_targets:
                resolved_path = os.path.abspath(path)
                # If relative path is not found directly, check script root directory
                if not os.path.exists(resolved_path):
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    alt_path = os.path.join(script_dir, os.path.basename(path))
                    parent_alt = os.path.join(os.path.dirname(script_dir), os.path.basename(path))
                    if os.path.exists(alt_path):
                        resolved_path = alt_path
                    elif os.path.exists(parent_alt):
                        resolved_path = parent_alt

                if os.path.exists(resolved_path):
                    if os.path.isdir(resolved_path):
                        for root, _, files in os.walk(resolved_path):
                            for f in files:
                                if f.endswith((".txt", ".md", ".json", ".csv", ".py", ".pdf", ".xlsx", ".xls")):
                                    full_p = os.path.join(root, f)
                                    res = self._read_local_file(full_p)
                                    if isinstance(res, list):
                                        documents.extend(res)
                                    elif isinstance(res, dict):
                                        documents.append(res)
                    else:
                        res = self._read_local_file(resolved_path)
                        if isinstance(res, list):
                            documents.extend(res)
                        elif isinstance(res, dict):
                            documents.append(res)
                else:
                    logger.warning(f"Local target path does not exist: {path} (Checked: {resolved_path})")

        # Deduplicate by content hash
        seen_hashes = set()
        unique_documents: list[dict] = []
        for doc in documents:
            chash = doc.get("content_hash")
            if chash and chash not in seen_hashes:
                seen_hashes.add(chash)
                unique_documents.append(doc)

        logger.info(f"Ingestion complete: {len(unique_documents)} unique items processed.")
        return unique_documents

    async def _scrape_web_target(self, client: httpx.AsyncClient, url: str) -> Optional[dict]:
        if url in self.visited_urls:
            return None
        self.visited_urls.add(url)

        try:
            if "github.com" in url:
                return await self._scrape_github(client, url)
            else:
                return await self._scrape_html(client, url)
        except Exception as e:
            logger.warning(f"Error scraping {url}: {e}")
            return None

    async def _scrape_html(self, client: httpx.AsyncClient, url: str) -> Optional[dict]:
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for elem in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            elem.decompose()

        title = soup.title.string.strip() if (soup.title and soup.title.string) else url
        main_content = soup.find("main") or soup.find("article") or soup.body
        raw_text = main_content.get_text(separator="\n", strip=True) if main_content else ""
        content = re.sub(r"\n{3,}", "\n\n", raw_text)

        return self._build_document(
            source=url,
            title=str(title),
            content=content,
            doc_type="webpage",
            category="web_research",
        )

    async def _scrape_github(self, client: httpx.AsyncClient, url: str) -> Optional[dict]:
        parts = url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            try:
                readme_resp = await client.get(
                    api_url,
                    headers={**self.headers, "Accept": "application/vnd.github.v3.raw"},
                )
                content = readme_resp.text if readme_resp.status_code == 200 else f"GitHub repo: {owner}/{repo}"
            except Exception:
                content = f"GitHub repository: {owner}/{repo}"

            return self._build_document(
                source=url,
                title=f"GitHub: {owner}/{repo}",
                content=content,
                doc_type="github_repo",
                category="code_repository",
            )
        return None

    def _read_local_file(self, filepath: str) -> Any:
        try:
            filename = os.path.basename(filepath)
            title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()

            # 1. Parse Excel Spreadsheets
            if filepath.endswith((".xlsx", ".xls")):
                return self._parse_excel_workbook(filepath, filename)

            # 2. Parse PDF Files
            elif filepath.endswith(".pdf"):
                content = f"[PDF File: {filename}]"
                try:
                    import fitz  # type: ignore
                    pdf_doc: Any = fitz.open(filepath)
                    extracted_pages: list[str] = [str(page.get_text()) for page in pdf_doc]
                    content = "\n".join(extracted_pages)
                except Exception:
                    pass
                return self._build_document(
                    source=os.path.abspath(filepath),
                    title=title,
                    content=content,
                    doc_type="local_document",
                    category="local_knowledge",
                )

            # 3. Parse Text/Markdown Files
            else:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                return self._build_document(
                    source=os.path.abspath(filepath),
                    title=title,
                    content=content,
                    doc_type="local_document",
                    category="local_knowledge",
                )
        except Exception as e:
            logger.warning(f"Error reading local file {filepath}: {e}")
            return None

    def _parse_excel_workbook(self, filepath: str, filename: str) -> list[dict]:
        """Parses all sheets in the Excel workbook into structured R&D records."""
        documents: list[dict] = []
        try:
            import pandas as pd  # type: ignore
        except ImportError:
            logger.error("Pandas is not installed. Please run: pip install pandas openpyxl")
            return documents

        try:
            xls: Any = pd.ExcelFile(filepath)
            logger.info(f"Parsing Excel workbook '{filename}' across {len(xls.sheet_names)} sheets...")

            for sheet_name in xls.sheet_names:
                df: Any = pd.read_excel(xls, sheet_name=sheet_name)
                if df.empty:
                    continue

                # Locate header row if metadata banner precedes the table
                header_idx: Optional[int] = None
                for idx, row in df.iterrows():
                    row_vals = [str(v).strip().lower() for v in row.values]
                    if any("project code" in v or "activity description" in v or "test component" in v or "date" in v for v in row_vals):
                        header_idx = int(idx)  # type: ignore
                        break

                if header_idx is not None:
                    df.columns = [str(c).strip() for c in df.iloc[header_idx]]
                    df = df.iloc[header_idx + 1:].reset_index(drop=True)

                for idx, row in df.iterrows():
                    row_num = int(idx)  # type: ignore
                    row_dict = {str(k): ("" if pd.isna(v) else str(v).strip()) for k, v in row.items()}

                    activity = row_dict.get("Activity Description") or row_dict.get("Description") or row_dict.get("Requirement") or ""
                    proj_name = row_dict.get("Project Name") or row_dict.get("Project Code") or row_dict.get("Test Component") or ""
                    if not activity and not proj_name:
                        continue

                    date_val = row_dict.get("Date", "")
                    uncertainty = row_dict.get("Technical Uncertainty", "")
                    experiment = row_dict.get("Experimentation Method") or row_dict.get("CDLS Examples") or ""
                    hours = row_dict.get("Hours") or row_dict.get("Budget Hours (Year 1)") or ""
                    code = row_dict.get("Project Code", "")

                    parts = [
                        f"Sheet: {sheet_name}",
                        f"Project / Area: {proj_name} {f'({code})' if code else ''}",
                    ]
                    if date_val:
                        parts.append(f"Date: {date_val}")
                    if hours:
                        parts.append(f"Allocated Hours: {hours}")
                    if activity:
                        parts.append(f"Activity / Scope: {activity}")
                    if uncertainty:
                        parts.append(f"Technical Uncertainty: {uncertainty}")
                    if experiment:
                        parts.append(f"Experimentation & Testing: {experiment}")

                    content = "\n".join(parts)
                    doc_title = f"{proj_name} - {date_val}" if date_val else f"{sheet_name} - {proj_name or 'Entry'} #{row_num + 1}"

                    documents.append(
                        self._build_document(
                            source=f"{os.path.abspath(filepath)}#{sheet_name}!R{row_num + 2}",
                            title=doc_title,
                            content=content,
                            doc_type="work_log_entry",
                            category="rd_time_tracker",
                        )
                    )

            logger.info(f"Successfully extracted {len(documents)} structured R&D records from {filename}")
        except Exception as e:
            logger.error(f"Failed parsing workbook {filename}: {e}")
        return documents

    def _build_document(self, source: str, title: str, content: str, doc_type: str, category: str) -> dict:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        doc_id = hashlib.md5(source.encode("utf-8")).hexdigest()  # nosec B324

        return {
            "id": doc_id,
            "url": source,
            "title": title,
            "content": content,
            "content_hash": content_hash,
            "source_category": category,
            "doc_type": doc_type,
            "scraped_at": datetime.now().isoformat(),
            "domain": None,
            "subdomain": "",
            "capability_tags": [],
            "model_versions": [],
            "summary": None,
            "key_facts": [],
            "audience": "general",
            "importance_score": 5,
            "date_context": "",
            "metadata": {},
        }