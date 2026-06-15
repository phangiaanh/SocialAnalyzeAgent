# Tavily-grounded fact-checking — Design

**Date:** 2026-06-15
**Status:** Approved (pending spec review)

## Problem

The `factcheck` step produces unreliable results because it has no real evidence:

- `factcheck.py` calls `SocialCrawlClient.cross_reference()`, which returns the **text of other social posts** from SocialCrawl's `/threads/search`. Other people's posts are not evidence of truth.
- The `Claim.evidence` field is **free-text the LLM writes from its own head** — no source, no URL, nothing verifiable.

As a result the model "fact-checks" against social chatter (or nothing) and fabricates evidence prose.

Separately, the **attitude** step sometimes returns no results, and the comment sample is taken in arbitrary order (see "Secondary fix" below).

## Goal

Ground fact-checking in real web sources via the Tavily search API, and attach structured, cited evidence to each claim.

## Approach — two-pass deterministic verification

Chosen over a single-pass augment and over an agentic tool-calling loop, because it produces reliable per-claim citations and slots into the existing deterministic-step pipeline without rebuilding the LLM client.

```
post text
  │
  ▼  Pass 1 (LLM): extract checkable claims  ──► list[str] claims
  │
  ▼  for top N claims:  TavilyClient.search(claim) ──► list[Source]
  │
  ▼  Pass 2 (LLM): given claims + their web sources, label each
     (supported/disputed/unverifiable) + write evidence + keep sources
  │
  ▼  FactCheckResult  (claims carry real source URLs)
```

`cross_reference` is no longer called by `factcheck` (it remains in the codebase, unused by this step).

## Components

### New module — `app/tavily.py`
Mirrors `socialcrawl.py`'s shape.

- `TavilyClient(settings, http)` — reuses the shared `httpx.AsyncClient`.
- `async def search(query) -> list[Source]` — POSTs to `{tavily_base_url}/search` with
  `{api_key, query, search_depth, max_results}`, maps each result to a `Source`.
  Returns `[]` on any error (best-effort, never raises into the pipeline).
- `TavilyError` defined for completeness; callers degrade rather than raise.

### Schema changes — `app/schemas.py`
```python
class Source(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""

class Claim(BaseModel):
    text: str
    label: Literal["supported", "disputed", "unverifiable"]
    confidence: Literal["low", "medium", "high"]
    evidence: str = ""
    sources: list[Source] = []        # NEW
```

### `factcheck.py` rewrite
- **Pass 1** prompt: extract only verifiable claims (Vietnamese), return JSON list.
- For each of the top `factcheck_max_claims` claims, call `TavilyClient.search(claim)`.
- **Pass 2** prompt: per claim, here are its web sources — assign `label`, justify in
  `evidence` (Vietnamese), and echo back the sources used.
- Claims beyond the cap, or whose search yields nothing, are labeled `unverifiable`
  with empty `sources`.

### Wiring — `app/steps/base.py` + `app/main.py`
- Add `tv: Any = None` to `AnalysisContext` in `base.py`.
- Construct `TavilyClient(settings, http=http)` in `main.py`'s job, alongside `sc`/`llm`,
  and pass it into the context.

### Config — `app/config.py`
```python
tavily_api_key: str = ""
tavily_base_url: str = "https://api.tavily.com"
tavily_search_depth: str = "basic"
tavily_max_results: int = 5
factcheck_max_claims: int = 5
```

### Report rendering — `app/report.py`
Render each claim's sources as compact references beneath it:
```
• "claim text" — ⚠️ tranh cãi
  <evidence sentence>
  ↳ [1] VnExpress — https://…
  ↳ [2] Reuters — https://…
```

## Secondary fix — comment sampling (folded into this spec)

The attitude step sometimes returns nothing, and the comment sample is arbitrary.

**Findings:**
- **Limit exists:** `comment_sample_size = 200` (`profiles/__init__.py`), applied in
  `fetch_comments` (`socialcrawl.py`) and again in `attitude.py`.
- **No sort:** `socialcrawl.py` takes the first 200 items in raw API order — not the
  most-engaged comments.
- **Empty results causes:** (1) Threads has no comments endpoint in `_COMMENT_PATHS`, so
  Threads posts always yield zero comments; (2) fetch failures degrade to `[]`;
  (3) blank-text comments shrink the LLM body while `sampled` still reports a count.

**Fix in this spec:**
- In `SocialCrawlClient.fetch_comments`, **sort normalized comments by `likes` descending
  before truncating to `limit`**, so the sample is the most-engaged comments rather than
  arbitrary order.

**Known limitation (not fixed now):** Threads posts have no comment source, so attitude
remains unavailable for Threads. Tracked for a future cycle.

## Error handling / degradation

- Missing `TAVILY_API_KEY` → `search` returns `[]`; every claim degrades to
  `unverifiable`. The step never crashes the pipeline (consistent with the existing
  `try/except` degradation in `pipeline.py`).
- Tavily timeout / non-200 / empty → `[]` for that claim.

## Testing

- `TavilyClient.search` (mock httpx): success, non-200, empty, malformed payload.
- Two-pass `factcheck.run` (mock LLM + mock Tavily): claims get sources; search failure →
  `unverifiable`; claim count capped at `factcheck_max_claims`.
- `fetch_comments` sort: comments returned sorted by `likes` desc before truncation.

## Deployment

- New env var `TAVILY_API_KEY` (provided by user) patched into the runtime.
- Code change → rebuild + push + runtime update → verify `/health`.

## Defaults summary

| Setting | Default |
|---|---|
| `factcheck_max_claims` | 5 |
| `tavily_search_depth` | `basic` |
| `tavily_max_results` | 5 |
| Tavily failure for a claim | → `unverifiable`, no sources |
| Comment sort | by `likes` desc, then truncate to 200 |
