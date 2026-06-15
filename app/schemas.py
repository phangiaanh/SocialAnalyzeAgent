from typing import Literal
from pydantic import BaseModel


class ModeRef(BaseModel):
    id: str
    label: str
    icon: str = "📌"


class Post(BaseModel):
    platform: str
    post_id: str
    url: str
    text: str = ""
    author: str = ""
    language: str = ""
    likes: int = 0
    views: int = 0
    comments: int = 0
    shares: int = 0
    score: float = 0.0
    age_hours: float = 0.0


class Delivery(BaseModel):
    chat_id: int
    message_id: int


class Callback(BaseModel):
    url: str
    token: str


class AnalyzeRequest(BaseModel):
    job_id: str
    mode: ModeRef
    topic: ModeRef
    tick_id: str
    post: Post
    delivery: Delivery
    callback: Callback


# ---- step result models ----
class Claim(BaseModel):
    text: str
    label: Literal["supported", "disputed", "unverifiable"]
    confidence: Literal["low", "medium", "high"]
    evidence: str = ""


class FactCheckResult(BaseModel):
    claims: list[Claim] = []
    overall_confidence: Literal["low", "medium", "high"] = "low"


class Theme(BaseModel):
    name: str
    count: int = 0


class AttitudeResult(BaseModel):
    sampled: int = 0
    positive_pct: int = 0
    neutral_pct: int = 0
    negative_pct: int = 0
    themes: list[Theme] = []
    quotes: list[str] = []


class Prediction(BaseModel):
    direction: Literal["up", "steady", "down"] = "steady"
    text: str = ""
    risk: str = ""
    momentum: Literal["rising", "steady", "fading"] = "steady"


class CallbackPayload(BaseModel):
    job_id: str
    status: Literal["ok", "error"]
    report_text: str
    delivery: Delivery
