from app.schemas import FactCheckResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn là trợ lý kiểm chứng thông tin cho lĩnh vực {domain}. "
    "Trích các tuyên bố có thể kiểm chứng trong bài đăng, đánh giá mỗi tuyên bố là "
    "supported/disputed/unverifiable dựa trên bằng chứng được cung cấp (bài liên quan và "
    "tín hiệu từ bình luận). Trả lời bằng tiếng Việt trong trường evidence."
)


def _render_user(ctx: AnalysisContext, related: list[str]) -> str:
    comments = "\n".join(f"- {c.text}" for c in ctx.comments[:50])
    refs = "\n".join(f"- {t}" for t in related)
    return (f"BÀI ĐĂNG:\n{ctx.request.post.text}\n\n"
            f"BÀI LIÊN QUAN (đối chiếu):\n{refs or '(không có)'}\n\n"
            f"BÌNH LUẬN (mẫu):\n{comments or '(không có)'}")


@register("factcheck")
async def run(ctx: AnalysisContext, llm) -> FactCheckResult:
    related: list[str] = []
    if ctx.sc is not None:
        try:
            related = await ctx.sc.cross_reference(ctx.request.post.text, limit=10)
        except Exception:  # degrade: cross-reference is best-effort
            related = []
    system = _SYSTEM.format(domain=ctx.profile.domain_hint)
    return await llm.complete_json(system=system, user=_render_user(ctx, related),
                                   schema=FactCheckResult)
