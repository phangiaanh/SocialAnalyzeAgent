# app/main.py
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.schemas import AnalyzeRequest
from app.jobs import JobRegistry
from app.pipeline import run_job
from app.llm import LLMClient
from app.socialcrawl import SocialCrawlClient
from app.tavily import TavilyClient

app = FastAPI(title="SocialAnalyzeAgent")
registry = JobRegistry()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    async def job():
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.request_timeout) as http:
            sc = SocialCrawlClient(settings, http=http)
            llm = LLMClient(settings, http=http)
            tv = TavilyClient(settings, http=http)
            await run_job(req, sc=sc, llm=llm, tv=tv, settings=settings)

    if not registry.start(req.job_id, job()):
        return JSONResponse(status_code=409, content={"job_id": req.job_id,
                                                      "status": "already_running"})
    return JSONResponse(status_code=202, content={"job_id": req.job_id, "status": "accepted"})
