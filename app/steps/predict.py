from app.schemas import Prediction, AttitudeResult, FactCheckResult
from app.steps.base import AnalysisContext, register

_SYSTEM = (
    "Bạn dự đoán phản ứng cộng đồng trong 24–48 giờ tới cho lĩnh vực {domain}. "
    "Dựa trên quỹ đạo bài đăng (điểm, tuổi, tương tác), thái độ bình luận và kết quả kiểm "
    "chứng, đưa ra hướng (up/steady/down), mô tả ngắn, rủi ro chính và đà (rising/steady/"
    "fading). Trả lời bằng tiếng Việt."
)


@register("predict")
async def run(ctx: AnalysisContext, llm) -> Prediction:
    att: AttitudeResult | None = ctx.results.get("attitude")
    fc: FactCheckResult | None = ctx.results.get("factcheck")
    p = ctx.request.post
    user = (
        f"QUỸ ĐẠO: score={p.score} age_hours={p.age_hours} likes={p.likes} "
        f"comments={p.comments} shares={p.shares}\n"
        f"THÁI ĐỘ: positive={getattr(att, 'positive_pct', 'n/a')} "
        f"neutral={getattr(att, 'neutral_pct', 'n/a')} "
        f"negative={getattr(att, 'negative_pct', 'n/a')}\n"
        f"KIỂM CHỨNG: độ tin={getattr(fc, 'overall_confidence', 'n/a')} "
        f"số tuyên bố tranh cãi={sum(1 for c in getattr(fc, 'claims', []) if c.label=='disputed')}"
    )
    return await llm.complete_json(system=_SYSTEM.format(domain=ctx.profile.domain_hint),
                                   user=user, schema=Prediction)
