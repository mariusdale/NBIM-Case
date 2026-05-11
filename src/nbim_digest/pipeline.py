from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .actions import ActionCode, get_action
from .config import CONFIG_DIR, DATA_DIR, load_yaml
from .demo import load_demo_articles, load_demo_cached_outputs
from .ingest_google_news import fetch_google_news_articles
from .ingest_rss import fetch_rss_articles
from .llm_client import AnthropicDigestClient, LLMUnavailable
from .models import Article, CostSummary, DigestItem, LLMRelevance, LLMSummaryAction, PipelineEvent, PipelineResult, RuleDecision
from .rule_filter import RuleFilter
from .storage import DigestStore


@dataclass(frozen=True)
class ProcessingCandidate:
    article_id: int
    article: Article
    rule: RuleDecision


class DigestPipeline:
    def __init__(
        self,
        *,
        store: DigestStore,
        anthropic_api_key: str | None,
        data_dir: Path = DATA_DIR,
        config_dir: Path = CONFIG_DIR,
    ):
        self.store = store
        self.anthropic_api_key = anthropic_api_key
        self.data_dir = Path(data_dir)
        self.config_dir = Path(config_dir)
        self.rule_filter = RuleFilter(load_yaml(self.config_dir / "content_filter_taxonomy.yaml"))

    def run(
        self,
        *,
        mode: str,
        use_cached_demo_outputs: bool = True,
        time_horizon: str = "24h",
        review_depth: str = "fast",
        max_articles: int = 25,
    ) -> PipelineResult:
        result: PipelineResult | None = None
        for event in self.stream(
            mode=mode,
            use_cached_demo_outputs=use_cached_demo_outputs,
            time_horizon=time_horizon,
            review_depth=review_depth,
            max_articles=max_articles,
        ):
            if event.kind == "done":
                result = event.result
        if result is None:
            raise RuntimeError("Digest pipeline did not produce a result.")
        return result

    def stream(
        self,
        *,
        mode: str,
        use_cached_demo_outputs: bool = True,
        time_horizon: str = "24h",
        review_depth: str = "fast",
        max_articles: int = 25,
    ) -> Iterator[PipelineEvent]:
        if review_depth not in {"fast", "full"}:
            raise ValueError(f"Unsupported review depth: {review_depth}")
        self.store.initialize()
        use_cache = mode == "demo" and use_cached_demo_outputs
        run_id = self.store.create_run(mode=mode, used_cached_outputs=use_cache)

        if mode == "demo":
            yield from self._stream_demo(run_id, use_cache, review_depth)
        else:
            yield from self._stream_live(
                run_id,
                time_horizon=time_horizon,
                review_depth=review_depth,
                max_articles=max_articles,
            )

    def _stream_demo(self, run_id: int, use_cache: bool, review_depth: str) -> Iterator[PipelineEvent]:
        article_pairs = load_demo_articles(self.data_dir)
        yield PipelineEvent(
            kind="started",
            run_id=run_id,
            candidate_count=len(article_pairs),
            status_message="Processing demo articles...",
        )
        if use_cache:
            cached = load_demo_cached_outputs(self.data_dir)
            items: list[DigestItem] = []
            for demo_id, article in article_pairs:
                article_id = self.store.save_article(run_id, article)
                rule = self.rule_filter.evaluate(article)
                self.store.save_rule_decision(run_id, article_id, rule)
                output = cached[demo_id]
                item = self._cached_item(article, rule, output, article_id)
                self._record_cached_call(run_id, article_id, "relevance", output)
                self._record_cached_call(run_id, article_id, "summary_action", output)
                self._record_cached_call(run_id, article_id, "reviewer", output)
                self._save_item(run_id, article_id, item)
                items.append(item)
                yield PipelineEvent(
                    kind="item",
                    run_id=run_id,
                    item=item,
                    processed_count=len(items),
                    candidate_count=len(article_pairs),
                    status_message=f"Processed {len(items)} demo article(s).",
                )
            result = PipelineResult(
                run_id=run_id,
                mode="demo",
                items=items,
                dropped_count=0,
                cost=CostSummary(),
                status_message="Using cached demo outputs because no API key is configured or cached mode was selected.",
                used_cached_outputs=True,
            )
            yield PipelineEvent(kind="done", run_id=run_id, result=result)
            return

        yield from self._stream_llm(article_pairs, run_id, mode="demo", review_depth=review_depth)

    def _stream_live(
        self,
        run_id: int,
        time_horizon: str,
        review_depth: str,
        max_articles: int,
    ) -> Iterator[PipelineEvent]:
        feed_config = load_yaml(self.config_dir / "feeds.yaml")
        google_config = load_yaml(self.config_dir / "google_news_rss.yaml")
        source_warnings: list[str] = []
        articles = fetch_rss_articles(feed_config, limit_per_feed=10)
        rss_count = len(articles)
        google_count = 0
        try:
            google_articles = fetch_google_news_articles(
                time_horizon=time_horizon,
                config=google_config,
                limit=15,
            )
            google_count = len(google_articles)
            articles.extend(google_articles)
        except Exception as exc:
            source_warnings.append(
                f"Google News RSS failed ({exc}); continuing with configured Norwegian RSS feeds only."
            )
        articles = self._dedupe_articles(articles)
        article_pairs = [(self._stable_id(article), article) for article in articles]
        yield from self._stream_llm(
            article_pairs,
            run_id,
            mode="live",
            review_depth=review_depth,
            source_warnings=source_warnings,
            debug_context={
                "rss_candidates": rss_count,
                "google_news_candidates": google_count,
                "time_horizon": time_horizon,
                "review_depth": review_depth,
            },
        )

    def _stream_llm(
        self,
        article_pairs: list[tuple[str, Article]],
        run_id: int,
        mode: str,
        review_depth: str,
        source_warnings: list[str] | None = None,
        debug_context: dict | None = None,
    ) -> Iterator[PipelineEvent]:
        prompt_config = load_yaml(self.config_dir / "prompts.yaml")
        priorities = load_yaml(self.config_dir / "priorities.yaml")
        threshold = int(prompt_config.get("relevance_threshold", 6))
        llm = AnthropicDigestClient(
            api_key=self.anthropic_api_key,
            store=self.store,
            run_id=run_id,
            prompt_config=prompt_config,
        )
        items: list[DigestItem] = []
        dropped = 0
        fallback_without_llm = not llm.available
        llm_error: str | None = None
        candidates: list[ProcessingCandidate] = []
        for _, article in article_pairs:
            article_id = self.store.save_article(run_id, article)
            rule = self.rule_filter.evaluate(article)
            self.store.save_rule_decision(run_id, article_id, rule)

            if rule.decision == "skip":
                dropped += 1
                self._save_dropped(run_id, article_id)
                continue

            candidates.append(ProcessingCandidate(article_id=article_id, article=article, rule=rule))

        yield PipelineEvent(
            kind="started",
            run_id=run_id,
            candidate_count=len(candidates),
            status_message=f"Processing {len(candidates)} LLM candidate article(s)...",
        )

        for processed_count, candidate in enumerate(candidates, start=1):
            article_id = candidate.article_id
            article = candidate.article
            rule = candidate.rule

            if fallback_without_llm:
                item = self._rule_only_item(article, rule, article_id)
            else:
                try:
                    relevance = llm.classify_relevance(article_id, article, rule, priorities)
                    if not relevance.include or relevance.score < threshold:
                        dropped += 1
                        self._save_dropped(run_id, article_id, relevance.score)
                        yield PipelineEvent(
                            kind="progress",
                            run_id=run_id,
                            processed_count=processed_count,
                            candidate_count=len(candidates),
                            status_message=f"Processed {processed_count} of {len(candidates)} LLM candidate article(s).",
                        )
                        continue
                    summary_action = llm.summarize_and_recommend(article_id, article, rule, relevance, priorities)
                    if review_depth == "full":
                        reviewer = llm.review_action(article_id, article, rule, summary_action, priorities)
                        reviewer_action = reviewer.action
                        final_action = reviewer.action
                        reason_for_action = reviewer.reason_for_action
                        reviewer_skipped = False
                    else:
                        reviewer_action = summary_action.action
                        final_action = summary_action.action
                        reason_for_action = summary_action.reason_for_action
                        reviewer_skipped = True
                    item = DigestItem(
                        article=article,
                        summary=summary_action.summary,
                        rule_decision=rule,
                        llm_relevance_score=relevance.score,
                        initial_action=summary_action.action,
                        reviewer_action=reviewer_action,
                        final_action=final_action,
                        reason_for_action=reason_for_action,
                        recommended_next_step=summary_action.recommended_next_step
                        or get_action(final_action).default_next_step,
                        article_id=article_id,
                        reviewer_skipped=reviewer_skipped,
                    )
                except LLMUnavailable as exc:
                    fallback_without_llm = True
                    llm_error = str(exc)
                    item = self._rule_only_item(article, rule, article_id)
                except Exception as exc:
                    fallback_without_llm = True
                    llm_error = str(exc)
                    item = self._rule_only_item(article, rule, article_id)

            self._save_item(run_id, article_id, item)
            items.append(item)
            yield PipelineEvent(
                kind="item",
                run_id=run_id,
                item=item,
                processed_count=processed_count,
                candidate_count=len(candidates),
                status_message=f"Processed {processed_count} of {len(candidates)} LLM candidate article(s).",
            )

        cost = self._cost_for_run(run_id)
        if llm_error:
            status = f"Anthropic LLM failed: {self._friendly_llm_error(llm_error)} Displayed rule-based fallback decisions."
        else:
            status = (
                "Live monitoring ran without Anthropic API key; displayed rule-based fallback decisions."
                if fallback_without_llm
                else "Live monitoring completed with LLM relevance, summary, and reviewer passes."
            )
        if review_depth == "fast" and not fallback_without_llm and not llm_error:
            status = f"{status} Fast mode skipped adversarial review."
        if mode == "demo":
            if llm_error:
                status = f"Demo mode Anthropic LLM failed: {self._friendly_llm_error(llm_error)} Displayed rule-based fallback decisions."
            else:
                status = (
                    "Demo mode ran with the full LLM pipeline."
                    if not fallback_without_llm
                    else "Demo mode ran with rule-based fallback because no Anthropic API key is configured."
                )
            if review_depth == "fast" and not fallback_without_llm and not llm_error:
                status = f"{status} Fast mode skipped adversarial review."
        if source_warnings:
            status = f"{status} {' '.join(source_warnings)}"
        result = PipelineResult(
            run_id=run_id,
            mode=mode,
            items=items,
            dropped_count=dropped,
            cost=cost,
            status_message=status,
            used_cached_outputs=False,
            debug=debug_context or {},
        )
        yield PipelineEvent(kind="done", run_id=run_id, result=result)

    def _cached_item(self, article: Article, rule: RuleDecision, output: dict, article_id: int) -> DigestItem:
        return DigestItem(
            article=article,
            summary=output["summary"],
            rule_decision=rule,
            llm_relevance_score=int(output["llm_relevance_score"]),
            initial_action=ActionCode(output["initial_action"]),
            reviewer_action=ActionCode(output["reviewer_action"]),
            final_action=ActionCode(output["final_action"]),
            reason_for_action=output["reason_for_action"],
            recommended_next_step=output["recommended_next_step"],
            included=True,
            article_id=article_id,
            reviewer_skipped=False,
        )

    def _record_cached_call(self, run_id: int, article_id: int, stage: str, output: dict) -> None:
        self.store.save_llm_call(
            run_id=run_id,
            article_id=article_id,
            stage=stage,
            model="cached-demo-output",
            prompt_version="nbim-digest-v1",
            prompt_input={"stage": stage, "source": "data/demo_cached_outputs.json"},
            output=output,
            parsed_output=output,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
        )

    def _rule_only_item(self, article: Article, rule: RuleDecision, article_id: int) -> DigestItem:
        action = ActionCode.ALERT_COMMUNICATIONS if rule.decision == "pass" else ActionCode.MONITOR
        if {"ethical exclusions", "geopolitics", "governance"} & set(rule.topic_tags):
            action = ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE
        summary = article.description or "Relevant article matched NBIM monitoring rules. Configure Anthropic API key for LLM summary."
        return DigestItem(
            article=article,
            summary=summary,
            rule_decision=rule,
            llm_relevance_score=6 if rule.decision == "pass" else 4,
            initial_action=action,
            reviewer_action=action,
            final_action=action,
            reason_for_action="Rule-based fallback used because the LLM pipeline is unavailable.",
            recommended_next_step=get_action(action).default_next_step,
            article_id=article_id,
            reviewer_skipped=True,
        )

    def _save_dropped(self, run_id: int, article_id: int, relevance_score: int = 0) -> None:
        self.store.save_digest_decision(
            run_id=run_id,
            article_id=article_id,
            llm_relevance_score=relevance_score,
            initial_action=ActionCode.NO_ACTION,
            reviewer_action=ActionCode.NO_ACTION,
            final_action=ActionCode.NO_ACTION,
            included=False,
            reason_for_action="Dropped from final digest.",
            summary="",
            recommended_next_step=get_action(ActionCode.NO_ACTION).default_next_step,
            reviewer_skipped=False,
        )

    def _save_item(self, run_id: int, article_id: int, item: DigestItem) -> None:
        self.store.save_digest_decision(
            run_id=run_id,
            article_id=article_id,
            llm_relevance_score=item.llm_relevance_score,
            initial_action=item.initial_action,
            reviewer_action=item.reviewer_action,
            final_action=item.final_action,
            included=item.included,
            reason_for_action=item.reason_for_action,
            summary=item.summary,
            recommended_next_step=item.recommended_next_step,
            reviewer_skipped=item.reviewer_skipped,
        )

    def _cost_for_run(self, run_id: int) -> CostSummary:
        raw = self.store.fetch_cost_summary(run_id)
        stages = raw["stages"]
        return CostSummary(
            estimated_cost_usd=round(raw["cost"], 4),
            relevance_articles=int(stages.get("relevance", 0)),
            summary_articles=int(stages.get("summary_action", 0)),
            reviewer_articles=int(stages.get("reviewer", 0)),
            input_tokens=int(raw["input_tokens"]),
            output_tokens=int(raw["output_tokens"]),
        )

    def _dedupe_articles(self, articles: list[Article]) -> list[Article]:
        seen: set[str] = set()
        unique: list[Article] = []
        for article in articles:
            key = self._dedupe_key(article)
            if key in seen:
                continue
            seen.add(key)
            unique.append(article)
        return unique

    def _dedupe_key(self, article: Article) -> str:
        if article.url:
            parts = urlsplit(article.url)
            return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
        return article.title.casefold()

    def _stable_id(self, article: Article) -> str:
        return self._dedupe_key(article).replace("/", "-")[:120]

    def _friendly_llm_error(self, error: str) -> str:
        normalized = error.casefold()
        if "invalid x-api-key" in normalized or "authentication_error" in normalized or "401" in normalized:
            return "the Anthropic API key was rejected."
        return "the model call failed."
