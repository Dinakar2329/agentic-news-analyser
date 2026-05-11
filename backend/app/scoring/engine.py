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
        stance_counts = stance_counts or {}
        support_count = stance_counts.get("supports", 0)
        refute_count = stance_counts.get("refutes", 0)
        context_count = stance_counts.get("needs_context", 0)
        avg_reliability = sum(score.reliability_score for score in relevant_scores) / len(relevant_scores)
        avg_relevance = sum(score.relevance_score for score in relevant_scores) / len(relevant_scores)
        official_count = sum(1 for score in relevant_scores if score.official_badge)
        penalty = min(contradiction_count * 12, 36)
        corroboration_bonus = min(max(len(relevant_scores) - 1, 0) * 4, 12)
        relevance_gate = max(0.55, avg_relevance / 100)
        confidence = max(12, min(94, (avg_reliability * relevance_gate) + official_count * 4 + corroboration_bonus - penalty))
        if refute_count >= 2 and refute_count >= support_count and avg_reliability >= 62:
            verdict = "FALSE"
            truth_probability = max(5, min(35, 42 - refute_count * 8 + support_count * 5))
        elif refute_count and support_count:
            verdict = "PARTIALLY TRUE" if support_count >= refute_count else "MISLEADING"
            truth_probability = max(20, min(70, confidence - refute_count * 9 + support_count * 5))
        elif confidence >= 90 and support_count >= 3 and contradiction_count == 0:
            verdict = "TRUE"
            truth_probability = min(98, confidence + 3)
        elif confidence >= 78 and support_count >= 2 and contradiction_count == 0:
            verdict = "MOSTLY TRUE"
            truth_probability = min(95, confidence)
        elif confidence >= 58 and (support_count or context_count):
            verdict = "PARTIALLY TRUE" if support_count else "MISLEADING"
            truth_probability = max(30, min(78, confidence - contradiction_count * 5))
        elif confidence >= 48:
            verdict = "MISLEADING" if contradiction_count else "UNVERIFIED"
            truth_probability = max(20, min(62, confidence - contradiction_count * 5))
        else:
            verdict = "UNVERIFIED"
            truth_probability = max(10, min(45, confidence - contradiction_count * 5))
        return {
            "verdict": verdict,
            "confidence": round(confidence, 1),
            "truth_probability": round(truth_probability, 1),
        }
