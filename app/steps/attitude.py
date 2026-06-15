from app.schemas import AttitudeResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn phân tích thái độ bình luận cho lĩnh vực {domain}. Dựa trên mẫu bình luận, "
    "ước lượng phân bố cảm xúc (positive/neutral/negative, tổng 100), liệt kê chủ đề nổi bật "
    "kèm số lượng, và trích 2-3 câu tiêu biểu. Trả lời bằng tiếng Việt."
)


@register("attitude")
async def run(ctx: AnalysisContext, llm) -> AttitudeResult:
    sample = ctx.comments[: ctx.profile.comment_sample_size]
    if not sample:
        return AttitudeResult(sampled=0)
    body = "\n".join(f"- {c.text}" for c in sample if c.text)
    res = await llm.complete_json(
        system=_SYSTEM.format(domain=ctx.profile.domain_hint),
        user=f"BÌNH LUẬN ({len(sample)} mẫu):\n{body}",
        schema=AttitudeResult,
    )
    res.sampled = len(sample)
    return res
