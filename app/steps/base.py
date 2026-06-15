from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class AnalysisContext:
    request: Any
    profile: Any
    comments: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    sc: Any = None  # SocialCrawlClient handle (steps may cross-reference)


Step = Callable[[AnalysisContext, Any], Awaitable[Any]]
STEP_REGISTRY: dict[str, Step] = {}


def register(name: str):
    def deco(fn: Step) -> Step:
        STEP_REGISTRY[name] = fn
        return fn
    return deco
