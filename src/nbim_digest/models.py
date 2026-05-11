from dataclasses import dataclass, field
from typing import Any

from .actions import ActionCode


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: str | None
    description: str = ""
    discovery_path: str = "RSS feed"
    discovery_query: str | None = None
    is_demo: bool = False

    @property
    def text_for_filtering(self) -> str:
        return " ".join(part for part in [self.title, self.description, self.source] if part)


@dataclass(frozen=True)
class RuleDecision:
    decision: str
    score: int
    matched_signals: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    reason: str = ""
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class LLMRelevance:
    score: int
    include: bool
    reason: str


@dataclass(frozen=True)
class LLMSummaryAction:
    summary: str
    action: ActionCode
    recommended_next_step: str
    reason_for_action: str


@dataclass(frozen=True)
class LLMReviewerAction:
    action: ActionCode
    reason_for_action: str


@dataclass(frozen=True)
class DigestItem:
    article: Article
    summary: str
    rule_decision: RuleDecision
    llm_relevance_score: int
    initial_action: ActionCode
    reviewer_action: ActionCode
    final_action: ActionCode
    reason_for_action: str
    recommended_next_step: str
    included: bool = True
    article_id: int | None = None
    reviewer_skipped: bool = False


@dataclass(frozen=True)
class CostSummary:
    estimated_cost_usd: float = 0.0
    relevance_articles: int = 0
    summary_articles: int = 0
    reviewer_articles: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class PipelineResult:
    run_id: int
    mode: str
    items: list[DigestItem]
    dropped_count: int
    cost: CostSummary
    status_message: str
    used_cached_outputs: bool = False
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineEvent:
    kind: str
    run_id: int
    item: DigestItem | None = None
    result: PipelineResult | None = None
    processed_count: int = 0
    candidate_count: int = 0
    status_message: str = ""
