from __future__ import annotations

import json
import os
import time
from typing import Any

from .actions import ActionCode, clamp_action
from .costs import estimate_call_cost, estimate_tokens
from .models import Article, LLMRelevance, LLMReviewerAction, LLMSummaryAction, RuleDecision
from .storage import DigestStore


class LLMUnavailable(RuntimeError):
    pass


class AnthropicDigestClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        store: DigestStore,
        run_id: int,
        prompt_config: dict,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.store = store
        self.run_id = run_id
        self.prompt_config = prompt_config
        self.prompt_version = prompt_config.get("prompt_version", "nbim-digest-v1")
        self.models = dict(prompt_config.get("models", {}))
        if os.getenv("ANTHROPIC_RELEVANCE_MODEL"):
            self.models["relevance"] = os.getenv("ANTHROPIC_RELEVANCE_MODEL")
        if os.getenv("ANTHROPIC_STRONG_MODEL"):
            self.models["summary"] = os.getenv("ANTHROPIC_STRONG_MODEL")
            self.models["reviewer"] = os.getenv("ANTHROPIC_STRONG_MODEL")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def classify_relevance(self, article_id: int, article: Article, rule: RuleDecision, priorities: dict) -> LLMRelevance:
        payload = self._base_payload(article, rule, priorities)
        data = self._call_json(
            article_id=article_id,
            stage="relevance",
            model=self.models.get("relevance", "claude-haiku-4-5"),
            instruction=self.prompt_config.get("relevance_prompt", ""),
            payload=payload,
            max_tokens=600,
        )
        return LLMRelevance(
            score=int(data.get("score", 0)),
            include=bool(data.get("include", False)),
            reason=str(data.get("reason", "")),
        )

    def summarize_and_recommend(
        self,
        article_id: int,
        article: Article,
        rule: RuleDecision,
        relevance: LLMRelevance,
        priorities: dict,
    ) -> LLMSummaryAction:
        payload = self._base_payload(article, rule, priorities) | {
            "llm_relevance": {
                "score": relevance.score,
                "include": relevance.include,
                "reason": relevance.reason,
            },
            "allowed_actions": [action.value for action in ActionCode],
        }
        data = self._call_json(
            article_id=article_id,
            stage="summary_action",
            model=self.models.get("summary", "claude-sonnet-4-6"),
            instruction=self.prompt_config.get("summary_action_prompt", ""),
            payload=payload,
            max_tokens=900,
        )
        return LLMSummaryAction(
            summary=str(data.get("summary", "")),
            action=clamp_action(data.get("action")),
            recommended_next_step=str(data.get("recommended_next_step", "")),
            reason_for_action=str(data.get("reason_for_action", "")),
        )

    def review_action(
        self,
        article_id: int,
        article: Article,
        rule: RuleDecision,
        summary_action: LLMSummaryAction,
        priorities: dict,
    ) -> LLMReviewerAction:
        payload = self._base_payload(article, rule, priorities) | {
            "proposed": {
                "summary": summary_action.summary,
                "action": summary_action.action.value,
                "recommended_next_step": summary_action.recommended_next_step,
                "reason_for_action": summary_action.reason_for_action,
            },
            "allowed_actions": [action.value for action in ActionCode],
        }
        data = self._call_json(
            article_id=article_id,
            stage="reviewer",
            model=self.models.get("reviewer", "claude-sonnet-4-6"),
            instruction=self.prompt_config.get("reviewer_prompt", ""),
            payload=payload,
            max_tokens=700,
        )
        return LLMReviewerAction(
            action=clamp_action(data.get("action")),
            reason_for_action=str(data.get("reason_for_action", "")),
        )

    def _base_payload(self, article: Article, rule: RuleDecision, priorities: dict) -> dict:
        return {
            "article": {
                "title": article.title,
                "source": article.source,
                "url": article.url,
                "published_at": article.published_at,
                "description": article.description,
                "discovery_path": article.discovery_path,
                "discovery_query": article.discovery_query,
            },
            "rule_decision": {
                "decision": rule.decision,
                "score": rule.score,
                "matched_signals": rule.matched_signals,
                "topic_tags": rule.topic_tags,
                "reason": rule.reason,
            },
            "nbim_priorities": priorities,
        }

    def _call_json(
        self,
        *,
        article_id: int,
        stage: str,
        model: str,
        instruction: str,
        payload: dict,
        max_tokens: int,
    ) -> dict:
        if not self.api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not configured.")

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise LLMUnavailable("The anthropic package is not installed.") from exc

        request_payload = {
            "instruction": instruction,
            "payload": payload,
            "response_format": "valid JSON object only",
        }
        prompt = json.dumps(request_payload, ensure_ascii=False)
        start = time.monotonic()
        try:
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=self.prompt_config.get("system_prompt", ""),
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            parsed = self._parse_json(text)
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", estimate_tokens(prompt)))
            output_tokens = int(getattr(usage, "output_tokens", estimate_tokens(text)))
            cost = estimate_call_cost(model, input_tokens, output_tokens)
            self.store.save_llm_call(
                run_id=self.run_id,
                article_id=article_id,
                stage=stage,
                model=model,
                prompt_version=self.prompt_version,
                prompt_input=request_payload,
                output={"text": text},
                parsed_output=parsed,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_estimate_usd=cost.estimated_cost_usd,
            )
            return parsed
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            self.store.save_llm_call(
                run_id=self.run_id,
                article_id=article_id,
                stage=stage,
                model=model,
                prompt_version=self.prompt_version,
                prompt_input=request_payload,
                latency_ms=latency_ms,
                error=str(exc),
            )
            raise

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
