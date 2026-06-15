from app.schemas import AnalyzeRequest, FactCheckResult, AttitudeResult, Prediction

_PLATFORM = {"tiktok": "TikTok", "reddit": "Reddit", "threads": "Threads"}
_LABEL = {"supported": "✅ xác nhận", "disputed": "⚠️ tranh cãi", "unverifiable": "❓ chưa rõ"}
_ARROW = {"up": "↑", "steady": "→", "down": "↓"}
_NA = "  • không thể phân tích phần này"


def _factcheck(fc: FactCheckResult | None) -> str:
    if not fc:
        return f"✅ KIỂM CHỨNG\n{_NA}"
    lines = [f"✅ KIỂM CHỨNG  (độ tin: {fc.overall_confidence})"]
    if not fc.claims:
        lines.append("  • Không có tuyên bố cần kiểm chứng")
    for c in fc.claims[:5]:
        lines.append(f'• "{c.text}" — {_LABEL.get(c.label, c.label)}')
        if c.evidence:
            lines.append(f"  {c.evidence}")
    return "\n".join(lines)


def _attitude(a: AttitudeResult | None) -> str:
    if not a or a.sampled == 0:
        return f"💬 THÁI ĐỘ BÌNH LUẬN\n{_NA}"
    themes = ", ".join(f"{t.name} ({t.count})" for t in a.themes[:5])
    quotes = " · ".join(f'"{q}"' for q in a.quotes[:2])
    return ("\n".join([
        f"💬 THÁI ĐỘ BÌNH LUẬN  ({a.sampled} mẫu)",
        f"🟢 Tích cực {a.positive_pct}%  🟡 Trung lập {a.neutral_pct}%  🔴 Tiêu cực {a.negative_pct}%",
        f"Chủ đề nổi bật: {themes}" if themes else "",
        quotes,
    ])).strip()


def _predict(p: Prediction | None) -> str:
    if not p:
        return f"🔮 DỰ ĐOÁN PHẢN ỨNG (24–48h)\n{_NA}"
    out = [f"🔮 DỰ ĐOÁN PHẢN ỨNG (24–48h)", f"{_ARROW.get(p.direction, '→')} {p.text}"]
    if p.risk:
        out.append(f"Rủi ro: {p.risk}")
    out.append(f"🔥 đà: {p.momentum}")
    return "\n".join(out)


def format_report(req: AnalyzeRequest, results: dict, profile) -> str:
    platform = _PLATFORM.get(req.post.platform, req.post.platform.title())
    snippet = req.post.text.replace("\n", " ")
    if len(snippet) > 90:
        snippet = snippet[:89] + "…"
    header = f'🔍 Explore More — {req.mode.label} · {platform}\n"{snippet}"'
    body = "\n\n".join([
        "—" * 20,
        _factcheck(results.get("factcheck")),
        _attitude(results.get("attitude")),
        _predict(results.get("predict")),
    ])
    text = f"{header}\n{body}"
    return text[:4096]
