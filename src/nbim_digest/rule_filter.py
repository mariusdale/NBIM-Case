from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .config import CONFIG_DIR, load_yaml
from .models import Article, RuleDecision

_WORD = "0-9A-Za-zÆØÅæøå"


@dataclass(frozen=True)
class Match:
    signal: str
    category: str


class RuleFilter:
    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    @classmethod
    def default(cls) -> "RuleFilter":
        return cls(load_yaml(CONFIG_DIR / "content_filter_taxonomy.yaml"))

    def evaluate(self, article: Article) -> RuleDecision:
        raw_text = article.text_for_filtering
        normalized = self._normalize(raw_text)

        promotional = self.taxonomy.get("exclusions", {}).get("promotional", {})
        for pattern in promotional.get("patterns", []):
            if self._contains(normalized, pattern):
                return RuleDecision(
                    decision="skip",
                    score=0,
                    matched_signals=[],
                    topic_tags=[],
                    reason="Promotional or sponsored content is excluded.",
                    exclusion_reason="promotional",
                )

        tier1 = self._match_tier(normalized, self.taxonomy.get("tier_1_direct", {}))
        tier1 = [match for match in tier1 if self._passes_ambiguity(match.signal, normalized)]
        tier2 = self._match_tier(normalized, self.taxonomy.get("tier_2_contextual", {}))
        tier3 = self._match_tier(normalized, self.taxonomy.get("tier_3_topical", {}))

        score = 0
        if tier1:
            score += min(len(tier1) * 100, 100)

        score += len(tier2) * 60
        if tier1 or tier2:
            score += len(tier3) * 20

        topic_tags = sorted({self._humanize_category(match.category) for match in tier3 if tier1 or tier2})
        matched_signals = self._dedupe([match.signal for match in tier1 + tier2 + tier3 if tier1 or tier2])

        pass_threshold = int(self.taxonomy.get("config", {}).get("decision", {}).get("pass_threshold", 100))
        review_threshold = int(self.taxonomy.get("config", {}).get("decision", {}).get("review_threshold", 40))

        if tier1 or score >= pass_threshold:
            decision = "pass"
        elif score >= review_threshold:
            decision = "review"
        else:
            decision = "skip"
            score = 0
            topic_tags = []
            matched_signals = []

        score = min(score, pass_threshold) if decision == "pass" else score
        reason = self._reason(decision, tier1, tier2, tier3)
        return RuleDecision(
            decision=decision,
            score=score,
            matched_signals=matched_signals,
            topic_tags=topic_tags,
            reason=reason,
        )

    def _match_tier(self, text: str, tier: dict) -> list[Match]:
        matches: list[Match] = []
        for category, terms in tier.items():
            if category in {"weight", "rule", "cooccurrence_targets"}:
                continue
            for term in terms or []:
                if self._term_matches(text, term, regex=category.endswith("_stemmed")):
                    matches.append(Match(signal=self._display_signal(term, text), category=category))
        return matches

    def _passes_ambiguity(self, signal: str, text: str) -> bool:
        ambiguous = self.taxonomy.get("ambiguous", {})
        if signal == "Norges Bank":
            required = ["Investment Management", "fondet", "Tangen", "aktivt eierskap", "oljefond"]
            return any(self._contains(text, term) for term in required)
        central_bank_terms = ambiguous.get("central_bank_terms", {}).get("terms", [])
        if any(self._contains(text, term) for term in central_bank_terms):
            return "oljefond" in text or "investment management" in text
        return True

    def _term_matches(self, text: str, term: str, regex: bool = False) -> bool:
        if regex:
            return re.search(term.lower(), text, flags=re.IGNORECASE) is not None
        return self._contains(text, term)

    def _contains(self, normalized_text: str, term: str) -> bool:
        normalized_term = self._normalize(term)
        if " " in normalized_term:
            return normalized_term in normalized_text
        pattern = rf"(?<![{_WORD}]){re.escape(normalized_term)}(?![{_WORD}])"
        return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text or "")
        return text.casefold()

    def _display_signal(self, term: str, text: str) -> str:
        if term.startswith("oljefond"):
            match = re.search(r"oljefond[a-zæøå]*", text, flags=re.IGNORECASE)
            return match.group(0) if match else "oljefondet"
        if term == "pensjonsfond[a-zæøå]+ utland":
            return "Statens pensjonsfond utland"
        return term

    def _humanize_category(self, category: str) -> str:
        return category.replace("_", " ")

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                out.append(value)
        return out

    def _reason(self, decision: str, tier1: list[Match], tier2: list[Match], tier3: list[Match]) -> str:
        if decision == "pass" and tier1:
            return "Direct NBIM/Oil Fund reference matched the highest-priority rule tier."
        if decision == "pass":
            return "Multiple contextual ownership or investment signals matched NBIM priority areas."
        if decision == "review":
            return "Some contextual signals matched, but not enough for automatic inclusion."
        if tier3:
            return "Only broad topical signals matched; NBIM-specific context was missing."
        return "No NBIM-relevant signals matched."
