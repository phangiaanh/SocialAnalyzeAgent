# SocialAnalyzeAgent

"Explore More" agent: for one trending post, runs fact-check + comment-attitude +
reaction-prediction and delivers a Vietnamese report back to Telegram via OpenClaw.

## Run

    pip install -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000

## Env

| Var | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:18080/v1` | qwen sidecar (OpenAI-compatible) |
| `LLM_MODEL` | `qwen/qwen3-5-27b` | model name |
| `LLM_API_KEY` | `sidecar` | sidecar token (usually ignored) |
| `LLM_MAX_RETRIES` | `3` | strict-JSON repair attempts |
| `SOCIALCRAWL_API_KEY` | — | SocialCrawl `x-api-key` |

## Test

    pytest

## API

`POST /analyze` (202 + job_id) — see `app/schemas.py:AnalyzeRequest`. `GET /health`.
