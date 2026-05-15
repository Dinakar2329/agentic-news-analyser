from dataclasses import dataclass


OFFICIAL_HINTS = ("gov", "sec.gov", "who.int", "courtlistener", "congress.gov", "europa.eu")
HIGH_TRUST = ("reuters.com", "apnews.com", "bbc.", "npr.org", "theguardian.com", "ft.com")
SOCIAL_HINTS = ("x.com", "twitter.com", "facebook.com", "tiktok.com", "reddit.com", "instagram.com")


@dataclass
class SourceScore:
    authenticity_score: float
    trust_score: float
    reliability_score: float
    bias_score: float
    source_type: str
    official_badge: bool
    relevance_score: float = 0
    citation_score: float = 0
    primary_source_score: float = 0
    recency_score: float = 50
    stance: str = "needs_context"


class ScoringEngine:
    def score_source(self, domain: str, title: str, text: str) -> SourceScore:
        normalized = domain.lower()
        combined_text = f"{title} {text}".lower()
        official = any(hint in normalized for hint in OFFICIAL_HINTS)
        high_trust = official or any(hint in normalized for hint in HIGH_TRUST)
        social = any(hint in normalized for hint in SOCIAL_HINTS)
        has_depth = len(text) > 800
        primary_markers = ("filing", "press release", "statement", "complaint", "lawsuit", "report", "transcript")
        citation_markers = ("according to", "cited", "source", "document", "filing", "statement", "data", "court")

        authenticity = 92 if official else 82 if high_trust else 48 if social else 62
        trust = 95 if official else 88 if high_trust else 35 if social else 58
        citation_score = min(100, 35 + sum(12 for marker in citation_markers if marker in combined_text))
        primary_source_score = 88 if official else 76 if any(marker in combined_text for marker in primary_markers) else 45
        reliability = (
            trust * 0.42
            + authenticity * 0.22
            + citation_score * 0.12
            + primary_source_score * 0.14
            + (10 if has_depth else 3)
        )
        bias = 18 if official else 24 if high_trust else 68 if social else 42
        source_type = "official" if official else "wire" if high_trust else "community" if social else "secondary"
        return SourceScore(
            authenticity_score=round(min(authenticity, 100), 2),
            trust_score=round(min(trust, 100), 2),
            reliability_score=round(min(reliability, 100), 2),
            bias_score=round(min(bias, 100), 2),
            source_type=source_type,
            official_badge=official,
            citation_score=round(citation_score, 2),
            primary_source_score=round(primary_source_score, 2),
        )

    def aggregate_verdict(self, source_scores: list[SourceScore], contradiction_count: int, stance_counts: dict[str, int] | None = None) -> dict:
        if not source_scores:
            return {"verdict": "UNVERIFIED", "confidence": 12, "truth_probability": 25}
        relevant_scores = [score for score in source_scores if score.relevance_score >= 35]
        if not relevant_scores:
            return {"verdict": "UNVERIFIED", "confidence": 18, "truth_probability": 30}
        stance_counts = stance_counts or self._stance_counts_from_scores(relevant_scores)
        support_count = stance_counts.get("supports", 0)
        refute_count = stance_counts.get("refutes", 0)
        context_count = stance_counts.get("needs_context", 0)
        avg_reliability = sum(score.reliability_score for score in relevant_scores) / len(relevant_scores)
        avg_relevance = sum(score.relevance_score for score in relevant_scores) / len(relevant_scores)
        official_count = sum(1 for score in relevant_scores if score.official_badge)

        support_scores = [score for score in relevant_scores if score.stance == "supports"]
        refute_scores = [score for score in relevant_scores if score.stance == "refutes"]
        if support_count and not support_scores:
            support_scores = relevant_scores
        if refute_count and not refute_scores:
            refute_scores = relevant_scores

        support_weight = self._stance_weight(support_scores)
        refute_weight = self._stance_weight(refute_scores)
        official_bonus = min(official_count * 5, 12)
        corroboration_bonus = min(max(len(relevant_scores) - 1, 0) * 3, 12)
        stance_bonus = min(support_count * 5 + context_count * 1.5, 14)
        penalty = min(refute_count * 7 + contradiction_count * 8, 34)
        confidence = max(
            12,
            min(
                94,
                avg_reliability * 0.62
                + avg_relevance * 0.28
                + official_bonus
                + corroboration_bonus
                + stance_bonus
                - penalty,
            ),
        )

        if (
            refute_count >= 1
            and support_count == 0
            and refute_weight >= 48
            and (official_count or avg_reliability >= 68)
            and avg_relevance >= 45
        ):
            verdict = "FALSE"
            truth_probability = max(5, min(35, 34 - refute_count * 6))
        elif refute_count >= 2 and refute_count >= support_count and refute_weight >= max(55, support_weight * 0.9):
            verdict = "FALSE"
            truth_probability = max(5, min(35, 36 - refute_count * 7 + support_count * 4))
        elif refute_count and support_count:
            verdict = "PARTIALLY TRUE" if support_count >= refute_count else "MISLEADING"
            truth_probability = max(20, min(70, confidence - refute_count * 8 + support_count * 5))
        elif support_count >= 3 and confidence >= 82 and contradiction_count == 0:
            verdict = "TRUE"
            truth_probability = min(98, confidence + 3)
        elif support_count >= 2 and confidence >= 68 and contradiction_count == 0:
            verdict = "MOSTLY TRUE"
            truth_probability = min(95, confidence)
        elif support_count >= 1 and confidence >= 55 and contradiction_count == 0:
            verdict = "MOSTLY TRUE" if confidence >= 75 and avg_relevance >= 65 else "PARTIALLY TRUE"
            truth_probability = max(30, min(78, confidence - contradiction_count * 5))
        elif refute_count and confidence >= 48:
            verdict = "MISLEADING"
            truth_probability = max(20, min(62, confidence - contradiction_count * 5))
        else:
            verdict = "UNVERIFIED"
            truth_probability = max(10, min(45, confidence - contradiction_count * 5))
        return {
            "verdict": verdict,
            "confidence": round(confidence, 1),
            "truth_probability": round(truth_probability, 1),
        }

    def _stance_counts_from_scores(self, source_scores: list[SourceScore]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for score in source_scores:
            counts[score.stance] = counts.get(score.stance, 0) + 1
        return counts

    def _stance_weight(self, source_scores: list[SourceScore]) -> float:
        if not source_scores:
            return 0
        weighted = [
            score.reliability_score * max(score.relevance_score, 35) / 100
            for score in source_scores
        ]
        return sum(weighted) / len(weighted)
