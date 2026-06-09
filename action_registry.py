"""
action_registry.py — Town Learning Assistant capability layer.

The ActionRegistry maps abstract action names (referenced by Routine steps) to
concrete Python implementations. This module provides production-grade
implementations for the research pipeline (`web_search`, `summarize_content`)
backed by real external services, plus structured stubs for the remaining
executive and strategic actions.

Design tenets
-------------
* **Modular providers**: Web search and LLM calls are isolated behind small
  provider classes so backends (Tavily, SerpApi, DuckDuckGo, OpenAI, Anthropic)
  can be swapped without touching action wiring.
* **Graceful degradation**: When API keys are missing or upstream calls fail,
  the registry returns a well-typed, structured fallback rather than raising —
  routines stay observable instead of crashing.
* **Zero hard external deps**: Uses `httpx` if installed (preferred, async-ready
  client), else falls back to stdlib `urllib`. SDKs (`openai`, `anthropic`) are
  detected at import time and used opportunistically.
* **Singleton compatibility**: The module-level `action_registry` instance is
  preserved so existing callers (`routine_engine`, `town_brain`) keep working.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import quote_plus

# ---------------------------------------------------------------------------
# Optional dependencies — detected once, used if present.
# ---------------------------------------------------------------------------
try:
    import httpx  # type: ignore

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore
    _HTTPX_AVAILABLE = False

try:
    from urllib import request as _urllib_request
    from urllib import error as _urllib_error
except ImportError:  # pragma: no cover  — stdlib should always be present
    _urllib_request = None  # type: ignore
    _urllib_error = None  # type: ignore

try:
    import openai  # type: ignore

    _OPENAI_SDK_AVAILABLE = True
except ImportError:
    openai = None  # type: ignore
    _OPENAI_SDK_AVAILABLE = False

try:
    import anthropic  # type: ignore

    _ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    anthropic = None  # type: ignore
    _ANTHROPIC_SDK_AVAILABLE = False


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActionRegistry")


# ---------------------------------------------------------------------------
# Result data classes (kept lightweight; `asdict` keeps registry output
# compatible with downstream code that expects plain dicts).
# ---------------------------------------------------------------------------
@dataclass
class SearchHit:
    """A single search result hit normalized across providers."""

    title: str
    url: str
    snippet: str
    score: Optional[float] = None
    source: Optional[str] = None  # which provider produced this hit


@dataclass
class SearchResponse:
    """Normalized search-response envelope."""

    query: str
    provider: str
    results: List[SearchHit] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# HTTP helper — unifies httpx and urllib so the rest of the module is
# transport-agnostic.
# ---------------------------------------------------------------------------
class _Http:
    """Tiny HTTP shim. Prefers httpx, falls back to urllib."""

    DEFAULT_TIMEOUT = 15.0
    DEFAULT_UA = "TownLearningAssistant/1.0 (+https://localhost)"

    @classmethod
    def request(
        cls,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Execute an HTTP call and return {status, headers, text, json}.

        Raises `RuntimeError` on transport failure; HTTP status errors are
        surfaced via the returned dict so callers can branch on `status`.
        """
        hdrs = {"User-Agent": cls.DEFAULT_UA, "Accept": "application/json"}
        if headers:
            hdrs.update(headers)

        if _HTTPX_AVAILABLE:
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.request(method, url, headers=hdrs, json=json_body)
                payload: Dict[str, Any] = {
                    "status": resp.status_code,
                    "headers": dict(resp.headers),
                    "text": resp.text,
                    "json": None,
                }
                try:
                    payload["json"] = resp.json()
                except Exception:
                    payload["json"] = None
                return payload
            except httpx.HTTPError as exc:  # type: ignore[attr-defined]
                raise RuntimeError(f"httpx transport error: {exc}") from exc

        # --- stdlib fallback ---
        if _urllib_request is None:  # pragma: no cover
            raise RuntimeError("No HTTP client available (httpx + urllib missing).")
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = _urllib_request.Request(url, data=data, headers=hdrs, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with _urllib_request.urlopen(req, timeout=timeout) as resp:  # type: ignore[union-attr]
                body = resp.read().decode("utf-8", errors="replace")
                payload = {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "text": body,
                    "json": None,
                }
                try:
                    payload["json"] = json.loads(body)
                except Exception:
                    payload["json"] = None
                return payload
        except _urllib_error.HTTPError as exc:  # type: ignore[union-attr]
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return {"status": exc.code, "headers": dict(exc.headers or {}), "text": body, "json": None}
        except Exception as exc:
            raise RuntimeError(f"urllib transport error: {exc}") from exc


# ---------------------------------------------------------------------------
# Search providers.
# ---------------------------------------------------------------------------
class _SearchProvider:
    """Base class for search backends."""

    name: str = "base"

    def is_available(self) -> bool:  # pragma: no cover — overridden
        return False

    def search(self, query: str, max_results: int = 5) -> SearchResponse:  # pragma: no cover
        raise NotImplementedError


class _TavilyProvider(_SearchProvider):
    """Tavily Search API — high-quality, LLM-tuned web search."""

    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self) -> None:
        self.api_key = os.getenv("TAVILY_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        body = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            resp = _Http.request("POST", self.ENDPOINT, json_body=body, timeout=20.0)
        except RuntimeError as exc:
            return SearchResponse(query=query, provider=self.name, error=str(exc))

        if resp["status"] != 200 or not isinstance(resp.get("json"), dict):
            return SearchResponse(
                query=query,
                provider=self.name,
                error=f"Tavily HTTP {resp['status']}: {resp.get('text', '')[:200]}",
            )

        hits: List[SearchHit] = []
        for item in resp["json"].get("results", [])[:max_results]:
            hits.append(
                SearchHit(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=item.get("content", "") or "",
                    score=item.get("score"),
                    source=self.name,
                )
            )
        return SearchResponse(query=query, provider=self.name, results=hits)


class _SerpApiProvider(_SearchProvider):
    """SerpApi — Google/Bing search via a managed API."""

    name = "serpapi"
    ENDPOINT = "https://serpapi.com/search.json"

    def __init__(self) -> None:
        self.api_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        url = (
            f"{self.ENDPOINT}?engine=google&q={quote_plus(query)}"
            f"&num={max_results}&api_key={self.api_key}"
        )
        try:
            resp = _Http.request("GET", url, timeout=20.0)
        except RuntimeError as exc:
            return SearchResponse(query=query, provider=self.name, error=str(exc))

        if resp["status"] != 200 or not isinstance(resp.get("json"), dict):
            return SearchResponse(
                query=query,
                provider=self.name,
                error=f"SerpApi HTTP {resp['status']}",
            )

        hits: List[SearchHit] = []
        for item in resp["json"].get("organic_results", [])[:max_results]:
            hits.append(
                SearchHit(
                    title=item.get("title", "") or "",
                    url=item.get("link", "") or "",
                    snippet=item.get("snippet", "") or "",
                    score=None,
                    source=self.name,
                )
            )
        return SearchResponse(query=query, provider=self.name, results=hits)


class _DuckDuckGoProvider(_SearchProvider):
    """DuckDuckGo HTML scrape — keyless fallback. Best-effort.

    DDG's HTML endpoint returns a result list we can parse with a tolerant
    regex. This is intentionally minimal: it's a safety net, not a primary
    backend. Set a Tavily or SerpApi key for production use.
    """

    name = "duckduckgo"
    ENDPOINT = "https://html.duckduckgo.com/html/"

    # Matches a result block: <a class="result__a" href="URL">TITLE</a> ...
    # <a class="result__snippet" ...>SNIPPET</a>
    _RESULT_RE = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    _TAG_RE = re.compile(r"<[^>]+>")

    def is_available(self) -> bool:
        return True  # always available — keyless

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        url = f"{self.ENDPOINT}?q={quote_plus(query)}"
        try:
            resp = _Http.request(
                "GET",
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=15.0,
            )
        except RuntimeError as exc:
            return SearchResponse(query=query, provider=self.name, error=str(exc))

        if resp["status"] != 200:
            return SearchResponse(
                query=query,
                provider=self.name,
                error=f"DDG HTML HTTP {resp['status']}",
            )

        hits: List[SearchHit] = []
        for match in self._RESULT_RE.finditer(resp["text"]):
            raw_url, raw_title, raw_snippet = match.groups()
            title = self._TAG_RE.sub("", raw_title).strip()
            snippet = self._TAG_RE.sub("", raw_snippet).strip()
            hits.append(
                SearchHit(
                    title=title,
                    url=raw_url,
                    snippet=snippet,
                    score=None,
                    source=self.name,
                )
            )
            if len(hits) >= max_results:
                break

        return SearchResponse(query=query, provider=self.name, results=hits)


def _select_search_provider() -> _SearchProvider:
    """Choose the first available provider in priority order."""
    for cls in (_TavilyProvider, _SerpApiProvider, _DuckDuckGoProvider):
        provider = cls()
        if provider.is_available():
            logger.info(f"Search provider selected: {provider.name}")
            return provider
    # Should be unreachable — DDG is always available — but keep a safe default.
    return _DuckDuckGoProvider()


# ---------------------------------------------------------------------------
# LLM providers — summarization.
# ---------------------------------------------------------------------------
DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "You are a precise research analyst. Given raw web-search results, "
    "produce a tight, factual, executive-grade synthesis. "
    "Lead with a one-sentence verdict, then 3-5 bullet takeaways, "
    "then a short 'open questions' line if any. Cite source URLs inline "
    "where claims map to specific hits."
)


class _LLMProvider:
    """Base LLM provider."""

    name: str = "base"

    def is_available(self) -> bool:  # pragma: no cover
        return False

    def summarize(
        self,
        content: str,
        *,
        instruction: Optional[str] = None,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:  # pragma: no cover
        raise NotImplementedError


class _OpenAIProvider(_LLMProvider):
    """OpenAI Chat Completions provider (SDK if available, else raw HTTP)."""

    name = "openai"
    ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def summarize(
        self,
        content: str,
        *,
        instruction: Optional[str] = None,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:
        system = instruction or DEFAULT_SUMMARY_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

        if _OPENAI_SDK_AVAILABLE:
            try:
                client = openai.OpenAI(api_key=self.api_key)  # type: ignore[attr-defined,union-attr]
                resp = client.chat.completions.create(  # type: ignore[arg-type]
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=30.0,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"OpenAI SDK call failed, falling back to HTTP: {exc}")

        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = _Http.request("POST", self.ENDPOINT, headers=headers, json_body=body, timeout=30.0)
        if resp["status"] != 200 or not isinstance(resp.get("json"), dict):
            raise RuntimeError(f"OpenAI HTTP {resp['status']}: {resp.get('text', '')[:300]}")
        choices = resp["json"].get("choices", [])
        if not choices:
            raise RuntimeError("OpenAI returned no choices.")
        return (choices[0].get("message", {}).get("content") or "").strip()


class _AnthropicProvider(_LLMProvider):
    """Anthropic Messages API provider."""

    name = "anthropic"
    ENDPOINT = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def summarize(
        self,
        content: str,
        *,
        instruction: Optional[str] = None,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:
        system = instruction or DEFAULT_SUMMARY_SYSTEM_PROMPT

        if _ANTHROPIC_SDK_AVAILABLE:
            try:
                client = anthropic.Anthropic(api_key=self.api_key)  # type: ignore[attr-defined]
                msg = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": content}],
                    timeout=30.0,
                )
                # Concatenate text blocks
                parts: List[str] = []
                for block in getattr(msg, "content", []) or []:
                    text = getattr(block, "text", None)
                    if text:
                        parts.append(text)
                return "\n".join(parts).strip()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Anthropic SDK call failed, falling back to HTTP: {exc}")

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }
        resp = _Http.request("POST", self.ENDPOINT, headers=headers, json_body=body, timeout=30.0)
        if resp["status"] != 200 or not isinstance(resp.get("json"), dict):
            raise RuntimeError(f"Anthropic HTTP {resp['status']}: {resp.get('text', '')[:300]}")
        parts = []
        for block in resp["json"].get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()


def _select_llm_provider() -> Optional[_LLMProvider]:
    """Choose the first available LLM provider, or None if none configured."""
    for cls in (_OpenAIProvider, _AnthropicProvider):
        provider = cls()
        if provider.is_available():
            logger.info(f"LLM provider selected: {provider.name}")
            return provider
    logger.warning(
        "No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY "
        "to enable real summarization."
    )
    return None


# ---------------------------------------------------------------------------
# Heuristic fallback summarizer — used only when no LLM key is configured.
# ---------------------------------------------------------------------------
def _heuristic_summarize(query: str, hits: Sequence[SearchHit]) -> str:
    """Deterministic, dependency-free summary when no LLM is available."""
    if not hits:
        return f"No results found for '{query}'."
    bullets = []
    for h in hits[:5]:
        snippet = (h.snippet or "").strip().replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        bullets.append(f"- {h.title.strip() or '(untitled)'} — {snippet} [{h.url}]")
    return (
        f"Heuristic summary for '{query}' "
        f"(LLM provider not configured; set OPENAI_API_KEY or ANTHROPIC_API_KEY):\n"
        + "\n".join(bullets)
    )


# ---------------------------------------------------------------------------
# Helpers used by action implementations.
# ---------------------------------------------------------------------------
def _coerce_query(params: Dict[str, Any], inputs: Dict[str, Any]) -> Optional[str]:
    """Pick a query string from params / inputs with sensible fallbacks."""
    for src in (params, inputs):
        for key in ("query", "topic", "q", "search"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _coerce_max_results(params: Dict[str, Any], default: int = 5) -> int:
    raw = params.get("max_results", params.get("n", default))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, 15))


def _serialize_results_for_llm(query: str, hits: Sequence[SearchHit]) -> str:
    """Format search hits into a compact, model-readable digest."""
    lines = [f"QUERY: {query}", ""]
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h.title}")
        lines.append(f"    URL: {h.url}")
        snippet = (h.snippet or "").strip().replace("\n", " ")
        if snippet:
            lines.append(f"    SNIPPET: {snippet}")
        lines.append("")
    return "\n".join(lines).strip()


def _extract_hits_from_inputs(inputs: Dict[str, Any]) -> List[SearchHit]:
    """Find search hits nested under various keys produced by upstream steps."""
    candidate_blobs: List[Any] = []
    # Most common: previous web_search output was placed under 'results' or
    # under a step-specific key by RoutineRunner.
    for key in ("results", "search_results", "hits", "web_search"):
        if key in inputs:
            candidate_blobs.append(inputs[key])
    # Also scan all values for SearchResponse-like dicts.
    for v in inputs.values():
        if isinstance(v, dict) and "results" in v and "query" in v:
            candidate_blobs.append(v["results"])

    hits: List[SearchHit] = []
    for blob in candidate_blobs:
        if isinstance(blob, list):
            for item in blob:
                if isinstance(item, dict):
                    hits.append(
                        SearchHit(
                            title=str(item.get("title", "")),
                            url=str(item.get("url", "")),
                            snippet=str(item.get("snippet", item.get("content", ""))),
                            score=item.get("score"),
                            source=item.get("source"),
                        )
                    )
                elif isinstance(item, str):
                    # Legacy/mocked format: a plain string per hit.
                    hits.append(SearchHit(title=item[:80], url="", snippet=item, source="legacy"))
            if hits:
                break
    return hits


# ===========================================================================
#  ActionRegistry
# ===========================================================================
class ActionRegistry:
    """
    The Action Registry is the execution core of the Town Learning Assistant.

    It maps abstract action names (used in routine steps) to actual Python
    implementations. Each implementation has the signature
    `func(params: Dict[str, Any], inputs: Dict[str, Any]) -> Any`.
    """

    def __init__(self) -> None:
        self._actions: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}
        # Lazily-initialized providers — created on first use.
        self._search_provider: Optional[_SearchProvider] = None
        self._llm_provider_resolved: bool = False
        self._llm_provider: Optional[_LLMProvider] = None
        self._register_defaults()

    # ------------------------------------------------------------------
    # Public API (preserved for TownBrain / RoutineRunner compatibility)
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        func: Callable[[Dict[str, Any], Dict[str, Any]], Any],
    ) -> None:
        """Register a new action handler under `name`."""
        logger.info(f"Registering action: {name}")
        self._actions[name] = func

    def execute(
        self,
        action_name: str,
        params: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Any:
        """Execute a registered action by name.

        Raises:
            ValueError: when `action_name` is not registered.
        """
        if action_name not in self._actions:
            logger.error(f"Action '{action_name}' not found in registry.")
            raise ValueError(f"Unsupported action: {action_name}")

        logger.info(
            f"Executing action: {action_name} | "
            f"params_keys={list(params.keys())} | input_keys={list(inputs.keys())}"
        )
        start = time.perf_counter()
        try:
            return self._actions[action_name](params, inputs)
        except Exception as exc:
            logger.exception(f"Action '{action_name}' raised: {exc}")
            # Surface a structured error so the routine engine can keep going
            # and downstream steps can see something rather than crash.
            return {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "action": action_name,
            }
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.info(f"Action '{action_name}' completed in {elapsed_ms:.1f}ms")

    # ------------------------------------------------------------------
    # Provider accessors (lazy)
    # ------------------------------------------------------------------
    def _get_search_provider(self) -> _SearchProvider:
        if self._search_provider is None:
            self._search_provider = _select_search_provider()
        return self._search_provider

    def _get_llm_provider(self) -> Optional[_LLMProvider]:
        if not self._llm_provider_resolved:
            self._llm_provider = _select_llm_provider()
            self._llm_provider_resolved = True
        return self._llm_provider

    # ------------------------------------------------------------------
    # Default action registration
    # ------------------------------------------------------------------
    def _register_defaults(self) -> None:
        """Initialize the system with core 'Gold Standard' action implementations."""
        # Utility actions
        self.register("fetch", self._fetch_impl)
        self.register("format", self._format_impl)

        # --- RESEARCH ACTIONS ---
        self.register("web_search", self._web_search_impl)
        self.register("summarize_content", self._summarize_impl)
        self.register("format_brief", self._format_brief_impl)

        # --- EXECUTIVE ACTIONS ---
        self.register("fetch_calendar", self._fetch_calendar_impl)
        self.register("fetch_emails", self._fetch_emails_impl)
        self.register("synthesize_briefing", self._synthesize_briefing_impl)

        # --- STRATEGIC ACTIONS ---
        self.register("analyze_event", self._analyze_event_impl)
        self.register("check_alignment", self._check_alignment_impl)
        self.register("notify_executive", self._notify_executive_impl)

    # ------------------------------------------------------------------
    # Utility actions
    # ------------------------------------------------------------------
    def _fetch_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        url = params.get("url") or inputs.get("url")
        if not url:
            return "No URL provided to fetch."
        try:
            resp = _Http.request("GET", url, timeout=20.0)
            if resp["status"] >= 400:
                return f"Fetch failed ({resp['status']}) for {url}"
            return resp["text"][:5000]  # cap returned size
        except RuntimeError as exc:
            return f"Fetch error for {url}: {exc}"

    def _format_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        style = params.get("style", "default")
        content = inputs.get("content") or params.get("content", "")
        if style == "markdown":
            return f"### Formatted Output\n\n{content}"
        return str(content) if content else f"Formatted content using style {style}"

    # ------------------------------------------------------------------
    # Research actions (REAL implementations)
    # ------------------------------------------------------------------
    def _web_search_impl(
        self,
        params: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform a real web search.

        Provider priority: Tavily (`TAVILY_API_KEY`) -> SerpApi
        (`SERPAPI_API_KEY`) -> DuckDuckGo HTML (no key required).

        Returns a dict (SearchResponse) with `query`, `provider`, `results`,
        and optional `error`. The `results` array contains hits with
        `title`, `url`, `snippet`, `score`, `source`.
        """
        query = _coerce_query(params, inputs)
        if not query:
            return SearchResponse(
                query="",
                provider="none",
                error="No query/topic provided to web_search.",
            ).to_dict()

        max_results = _coerce_max_results(params, default=5)
        provider = self._get_search_provider()

        try:
            response = provider.search(query=query, max_results=max_results)
        except Exception as exc:
            logger.exception("web_search provider raised")
            return SearchResponse(
                query=query, provider=provider.name, error=str(exc)
            ).to_dict()

        # If the primary provider returned an error AND wasn't DDG, try DDG.
        if (response.error or not response.results) and provider.name != "duckduckgo":
            logger.warning(
                f"Primary search provider '{provider.name}' returned no results "
                f"({response.error}); falling back to DuckDuckGo."
            )
            fallback = _DuckDuckGoProvider()
            try:
                response = fallback.search(query=query, max_results=max_results)
            except Exception as exc:
                response = SearchResponse(query=query, provider="duckduckgo", error=str(exc))

        return response.to_dict()

    def _summarize_impl(
        self,
        params: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Summarize search results (or arbitrary content) using an LLM.

        Resolution order for content:
          1. `params['content']` if explicitly provided.
          2. `inputs['results']` (the SearchResponse-like dict from web_search).
          3. Any nested SearchResponse in `inputs`.
          4. Fallback string representation of `inputs`.

        Provider priority: OpenAI (`OPENAI_API_KEY`) -> Anthropic
        (`ANTHROPIC_API_KEY`). If neither is configured, returns a
        deterministic heuristic summary so routines never hard-fail.
        """
        query = _coerce_query(params, inputs) or "the requested topic"
        instruction = params.get("instruction") or params.get("system_prompt")
        max_tokens = int(params.get("max_tokens", 700))
        temperature = float(params.get("temperature", 0.2))

        # Build content to summarize.
        explicit_content = params.get("content") or inputs.get("content")
        if isinstance(explicit_content, str) and explicit_content.strip():
            content_for_llm = explicit_content
            hits: List[SearchHit] = []
        else:
            hits = _extract_hits_from_inputs(inputs)
            if hits:
                content_for_llm = _serialize_results_for_llm(query, hits)
            else:
                # Fall back to a serialized view of whatever inputs are present.
                try:
                    content_for_llm = json.dumps(inputs, default=str, indent=2)[:8000]
                except Exception:
                    content_for_llm = str(inputs)[:8000]

        llm = self._get_llm_provider()
        if llm is None:
            summary_text = _heuristic_summarize(query, hits)
            return {
                "summary": summary_text,
                "provider": "heuristic",
                "query": query,
                "warning": (
                    "No LLM provider configured. Set OPENAI_API_KEY or "
                    "ANTHROPIC_API_KEY for real summarization."
                ),
            }

        # Try the primary LLM; on failure, try the other if available.
        last_error: Optional[str] = None
        for attempt_provider in self._llm_attempt_order(llm):
            try:
                summary_text = attempt_provider.summarize(
                    content_for_llm,
                    instruction=instruction,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if summary_text:
                    return {
                        "summary": summary_text,
                        "provider": attempt_provider.name,
                        "query": query,
                        "model": getattr(attempt_provider, "model", None),
                    }
                last_error = f"{attempt_provider.name} returned empty summary"
            except Exception as exc:
                last_error = f"{attempt_provider.name} error: {exc}"
                logger.warning(last_error)

        # All LLM attempts failed — degrade gracefully.
        summary_text = _heuristic_summarize(query, hits)
        return {
            "summary": summary_text,
            "provider": "heuristic",
            "query": query,
            "error": last_error or "All LLM providers failed.",
        }

    def _llm_attempt_order(self, primary: _LLMProvider) -> List[_LLMProvider]:
        """Return primary then the other configured provider (if any)."""
        order: List[_LLMProvider] = [primary]
        other_cls = _AnthropicProvider if isinstance(primary, _OpenAIProvider) else _OpenAIProvider
        other = other_cls()
        if other.is_available():
            order.append(other)
        return order

    def _format_brief_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        """Render the summary as a human-readable research brief."""
        summary_obj = inputs.get("summary")
        if isinstance(summary_obj, dict):
            summary_text = summary_obj.get("summary", "")
            provider = summary_obj.get("provider", "unknown")
            query = summary_obj.get("query", "")
        else:
            summary_text = str(summary_obj or "No summary available")
            provider = "unknown"
            query = inputs.get("query") or inputs.get("topic", "")

        header = "--- RESEARCH BRIEF ---"
        footer = "--- END BRIEF ---"
        title_line = f"Topic: {query}" if query else ""
        meta_line = f"(synthesized via {provider})"
        body_parts = [p for p in (title_line, meta_line, "", summary_text) if p]
        return "\n".join([header, *body_parts, footer])

    # ------------------------------------------------------------------
    # Executive actions (structured stubs — wire to Nylas/Zapier later)
    # ------------------------------------------------------------------
    def _fetch_calendar_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: integrate with Nylas / Google Calendar via zapier_connector.
        return {"events": ["10:00 AM: Board Meeting", "2:00 PM: Product Review"]}

    def _fetch_emails_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: integrate with Nylas / Gmail.
        return {"emails": ["From: CEO - Urgent Strategy Update", "From: Ops - Weekly Report"]}

    def _synthesize_briefing_impl(
        self, params: Dict[str, Any], inputs: Dict[str, Any]
    ) -> str:
        events = inputs.get("events", []) or []
        emails = inputs.get("emails", []) or []
        return (
            f"Good morning. You have {len(events)} events and "
            f"{len(emails)} priority emails today."
        )

    # ------------------------------------------------------------------
    # Strategic actions
    # ------------------------------------------------------------------
    def _analyze_event_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        event_data = inputs.get("event_payload", {}) or {}
        return {
            "analysis": f"Analyzed event: {event_data.get('event_type', 'unknown')}. Priority: High."
        }

    def _check_alignment_impl(
        self, params: Dict[str, Any], inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        profile = inputs.get("user_profile", {}) or {}
        goals = profile.get("goals", "general excellence")
        return {
            "aligned": True,
            "score": 0.9,
            "reason": f"Event aligns with goals: {goals}",
        }

    def _notify_executive_impl(self, params: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        reason = inputs.get("reason", "Strategic alignment detected")
        return f"NOTIFICATION SENT: High-priority opportunity detected. Reason: {reason}"


# ---------------------------------------------------------------------------
# Singleton instance for system-wide use (preserved for backward compat).
# ---------------------------------------------------------------------------
action_registry = ActionRegistry()


__all__ = [
    "ActionRegistry",
    "action_registry",
    "SearchHit",
    "SearchResponse",
]
