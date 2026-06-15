# tests/test_main.py
import httpx
import pytest
from app import main, pipeline
from tests.test_schemas import SAMPLE


@pytest.mark.anyio
async def test_health():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_analyze_enqueues(monkeypatch):
    seen = {}
    async def fake_run_job(req, **kw):
        seen["job"] = req.job_id
    monkeypatch.setattr(main, "run_job", fake_run_job)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/analyze", json=SAMPLE)
    assert r.status_code == 202
    assert r.json()["job_id"] == "j1"
    await main.registry.wait_all()
    assert seen["job"] == "j1"


@pytest.mark.anyio
async def test_analyze_dedup(monkeypatch):
    async def slow_run_job(req, **kw):
        import asyncio; await asyncio.sleep(0.05)
    monkeypatch.setattr(main, "run_job", slow_run_job)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r1 = await c.post("/analyze", json={**SAMPLE, "job_id": "dup"})
        r2 = await c.post("/analyze", json={**SAMPLE, "job_id": "dup"})
    assert r1.status_code == 202 and r2.status_code == 409
    await main.registry.wait_all()
