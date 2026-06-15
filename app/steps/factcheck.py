import datetime
from app.schemas import FactCheckResult, Claim, ClaimExtraction, VerificationResult
from app.steps.base import AnalysisContext, register

_EXTRACT_SYSTEM = (
    "Bạn là trợ lý kiểm chứng cho lĩnh vực {domain}. Trích các tuyên bố CÓ THỂ kiểm chứng "
    "(dữ kiện khách quan) trong bài đăng; bỏ qua ý kiến và cảm xúc. "
    'Trả về JSON dạng {{"claims": ["tuyên bố 1", "tuyên bố 2"]}}.'
)
_VERIFY_SYSTEM = (
    "Hôm nay là {today}. "
    "Bạn là trợ lý kiểm chứng cho lĩnh vực {domain}. Với mỗi tuyên bố kèm các nguồn web, "
    "gán nhãn supported/disputed/unverifiable và giải thích ngắn gọn bằng tiếng Việt trong "
    "trường evidence. Nếu không có nguồn hỗ trợ, dùng unverifiable. "
    "Lưu ý: các nguồn có ngày tháng trong năm {year} là HIỆN TẠI, không phải tương lai. "
    'Trả về JSON có mảng "verdicts" THEO ĐÚNG THỨ TỰ tuyên bố (mỗi phần tử gồm label, '
    'confidence, evidence) và "overall_confidence".'
)


def _render_verify(checked: list) -> str:
    blocks = []
    for i, (claim, sources) in enumerate(checked, 1):
        refs = "\n".join(f"  - {s.title}: {s.snippet} ({s.url})" for s in sources)
        blocks.append(f"[{i}] TUYÊN BỐ: {claim}\nNGUỒN:\n{refs or '  (không có nguồn)'}")
    return "\n\n".join(blocks)


@register("factcheck")
async def run(ctx: AnalysisContext, llm) -> FactCheckResult:
    extraction = await llm.complete_json(
        system=_EXTRACT_SYSTEM.format(domain=ctx.profile.domain_hint),
        user=ctx.request.post.text,
        schema=ClaimExtraction,
    )
    claims = [c for c in extraction.claims if c and c.strip()]
    if not claims:
        return FactCheckResult(claims=[], overall_confidence="low")

    max_claims = ctx.settings.factcheck_max_claims if ctx.settings else 5
    to_check, overflow = claims[:max_claims], claims[max_claims:]

    checked = []
    for claim in to_check:
        sources = await ctx.tv.search(claim) if ctx.tv is not None else []
        checked.append((claim, sources))

    today = datetime.date.today().isoformat()
    verification = await llm.complete_json(
        system=_VERIFY_SYSTEM.format(
            domain=ctx.profile.domain_hint,
            today=today,
            year=today[:4],
        ),
        user=_render_verify(checked),
        schema=VerificationResult,
    )
    verdicts = verification.verdicts

    out_claims = []
    for i, (text, sources) in enumerate(checked):
        v = verdicts[i] if i < len(verdicts) else None
        # A claim with no web sources cannot be confirmed: force unverifiable.
        label = (v.label if v else "unverifiable") if sources else "unverifiable"
        out_claims.append(Claim(
            text=text,
            label=label,
            confidence=v.confidence if v else "low",
            evidence=v.evidence if v else "",
            sources=sources,
        ))
    for text in overflow:
        out_claims.append(Claim(text=text, label="unverifiable", confidence="low"))

    return FactCheckResult(claims=out_claims,
                           overall_confidence=verification.overall_confidence)
