import logging
from app.schemas import AnalyzeRequest, CallbackPayload
from app.profiles import resolve_profile
from app.steps.base import AnalysisContext, STEP_REGISTRY
from app.report import format_report
from app.callback import deliver
# ensure steps self-register
from app.steps import factcheck, attitude, predict  # noqa: F401

log = logging.getLogger("pipeline")


async def _gather_comments(sc, req, profile):
    try:
        return await sc.fetch_comments(req.post.platform, req.post.post_id,
                                       req.post.url, limit=profile.comment_sample_size)
    except Exception as e:  # degrade: no comments
        log.warning("comment fetch failed: %s", e)
        return []


async def run_job(req: AnalyzeRequest, *, sc, llm, tv=None, settings=None) -> None:
    profile = resolve_profile(req.mode.id)
    comments = await _gather_comments(sc, req, profile)
    ctx = AnalysisContext(request=req, profile=profile, comments=comments, results={},
                          sc=sc, tv=tv, settings=settings)
    for name in profile.steps:
        step = STEP_REGISTRY.get(name)
        if not step:
            continue
        try:
            ctx.results[name] = await step(ctx, llm)
        except Exception as e:  # degrade: missing section
            log.warning("step %s failed: %s", name, e)
    report = format_report(req, ctx.results, profile)
    payload = CallbackPayload(job_id=req.job_id, status="ok", report_text=report,
                              delivery=req.delivery)
    await deliver(payload, req.callback)
