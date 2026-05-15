import json
import logging
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import async_session_maker
from app.models.tables import Agent, Finding, Source
from app.providers.base import ModelProvider, ProviderError
from app.scoring.engine import ScoringEngine, SourceScore
from app.search.duckduckgo import DuckDuckGoSearch
from app.search.extractor import extract_article


logger = logging.getLogger(__name__)


class AgentWorker:
    def __init__(
        self,
        emit,
        scoring: ScoringEngine,
        provider: ModelProvider | None = None,
        model: str | None = None,
        speed_accuracy: int = 60,
    ):
        self.emit = emit
        self.search = DuckDuckGoSearch()
        self.scoring = scoring
        self.provider = provider
        self.model = model
        self.speed_accuracy = max(0, min(100, speed_accuracy))

    async def run(self, investigation_id: str, claim: str, index: int, search_depth: int, role: dict | None = None) -> tuple[list[SourceScore], list[dict]]:
        async with async_session_maker() as db:
            return await self._run_with_session(db, investigation_id, claim, index, search_depth, role or {})

    async def _run_with_session(self, db, investigation_id: str, claim: str, index: int, search_depth: int, role: dict) -> tuple[list[SourceScore], list[dict]]:
        role_name = role.get("name", f"Search Agent {index}")
        query = role.get("query") or f"{claim} source evidence fact check"
        agent = Agent(
            investigation_id=investigation_id,
            name=role_name,
            status="running",
            task=role.get("task", f"Find corroborating and contradicting evidence for: {claim}"),
            progress=5,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        await self.emit("agent_spawned", {"agent": self._agent_payload(agent, role)})

        results = await self.search.search(query, max_results=search_depth)
        scores: list[SourceScore] = []
        findings: list[dict] = []
        if not results:
            agent.status = "complete"
            agent.task = "Search completed, but no reliable web results were returned. Verdict should remain unverified."
            agent.progress = 100
            await db.commit()
            await self.emit("agent_status", {"agent": self._agent_payload(agent, role)})
            return scores, findings

        for position, result in enumerate(results, start=1):
            url = result["url"]
            existing_source = await db.scalar(
                select(Source).where(Source.investigation_id == investigation_id, Source.url == url)
            )
            if existing_source:
                logger.info(
                    "agent_skipping_duplicate_source investigation_id=%s url=%s existing_agent_id=%s",
                    investigation_id,
                    url,
                    existing_source.agent_id,
                )
                continue
            article = await extract_article(url)
            domain = result.get("domain") or urlparse(url).netloc.replace("www.", "")
            score = self.scoring.score_source(domain, article["title"] or result["title"], article["text"])
            relevance = self._claim_relevance(claim, f"{result.get('title', '')} {result.get('snippet', '')} {article['title']} {article['text']}")
            score.relevance_score = relevance
            if relevance < 35:
                score.reliability_score = min(score.reliability_score, 38)
            elif relevance < 55:
                score.reliability_score = round(score.reliability_score * 0.75, 2)
            source = Source(
                investigation_id=investigation_id,
                agent_id=agent.id,
                url=result["url"],
                domain=domain,
                title=article["title"] or result["title"],
                source_type=score.source_type,
                authenticity_score=score.authenticity_score,
                trust_score=score.trust_score,
                reliability_score=score.reliability_score,
                bias_score=score.bias_score,
                official_badge=score.official_badge,
                extracted_text=article["text"] or result.get("snippet", ""),
            )
            db.add(source)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                logger.info(
                    "agent_dropped_duplicate_source_on_commit investigation_id=%s url=%s",
                    investigation_id,
                    url,
                )
                continue
            await db.refresh(source)
            scores.append(score)

            stance_result = await self._classify_stance(
                claim,
                result.get("snippet", ""),
                article["text"],
                score,
                relevance,
                role,
                title=result.get("title", "") or article["title"] or "",
            )
            stance = stance_result["stance"]
            score.stance = stance
            summary = stance_result.get("summary") or self._summarize_source(claim, source, relevance, stance)
            contradictions = [] if stance == "supports" else [self._contradiction_reason(stance)]
            finding = Finding(
                investigation_id=investigation_id,
                agent_id=agent.id,
                source_id=source.id,
                stance=stance,
                summary=summary,
                evidence_json=json.dumps(
                    {
                        "snippet": result.get("snippet", ""),
                        "domain": domain,
                        "relevance_score": relevance,
                        "agent_role": role_name,
                        "query": query,
                        "stance_reason": stance_result.get("reason"),
                        "stance_source": stance_result.get("source"),
                    }
                ),
                contradictions_json=json.dumps(contradictions),
            )
            db.add(finding)
            findings.append(
                {
                    "source": source,
                    "summary": summary,
                    "score": score,
                    "stance": stance,
                    "contradictions": contradictions,
                    "stance_reason": stance_result.get("reason"),
                    "stance_source": stance_result.get("source"),
                    "agent_role": role_name,
                }
            )

            agent.progress = min(95, 15 + int((position / max(len(results), 1)) * 75))
            agent.credibility_score = round(sum(s.reliability_score for s in scores) / len(scores), 1)
            await db.commit()
            await self.emit("source_found", {"agent_id": agent.id, "source": self._source_payload(source, stance)})
            await self.emit("source_ranked", {"source_id": source.id, "scores": score.__dict__})
            await self.emit(
                "source_evaluated",
                {
                    "source_id": source.id,
                    "agent_id": agent.id,
                    "stance": stance,
                    "reason": stance_result.get("reason"),
                    "summary": summary,
                    "analysis_source": stance_result.get("source"),
                },
            )
            await self.emit("agent_status", {"agent": self._agent_payload(agent, role)})

        agent.status = "complete"
        agent.progress = 100
        await db.commit()
        await self.emit("agent_status", {"agent": self._agent_payload(agent, role)})
        return scores, findings

    def _claim_relevance(self, claim: str, evidence: str) -> float:
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "into",
            "about",
            "against",
            "over",
            "under",
            "after",
            "before",
            "claim",
            "claims",
            "news",
            "report",
            "reports",
            "files",
            "filed",
        }
        claim_terms = [
            term
            for term in dict.fromkeys(re.findall(r"[a-z0-9]{3,}", claim.lower()))
            if term not in stop_words
        ]
        if not claim_terms:
            return 0
        evidence_text = evidence.lower()
        weights = [
            1.8 if any(char.isdigit() for char in term) else 1.35 if len(term) >= 7 else 1
            for term in claim_terms
        ]
        matched_weight = sum(weight for term, weight in zip(claim_terms, weights) if term in evidence_text)
        base_score = (matched_weight / sum(weights)) * 100
        phrase_hits = 0
        for size in (2, 3):
            for index in range(0, max(len(claim_terms) - size + 1, 0)):
                phrase = " ".join(claim_terms[index : index + size])
                if phrase in evidence_text:
                    phrase_hits += 1
        phrase_boost = min(18, phrase_hits * 3)
        return round(min(100, base_score + phrase_boost), 2)

    async def _classify_stance(
        self,
        claim: str,
        snippet: str,
        text: str,
        score: SourceScore,
        relevance: float,
        role: dict,
        title: str = "",
    ) -> dict:
        heuristic_stance = self._heuristic_stance(claim, title, snippet, text, score, relevance, role)
        model_relevance_threshold = self._model_relevance_threshold()
        if not self.provider or not self.model or relevance < model_relevance_threshold:
            return {
                "stance": heuristic_stance,
                "reason": "Heuristic classifier used because model stance analysis was unavailable, speed mode was prioritized, or evidence was low relevance.",
                "source": "heuristic",
            }
        prompt = self._stance_prompt(claim, title, snippet, text, score, role)
        try:
            raw_response = await self.provider.generate(prompt, self.model)
            parsed = self._parse_stance_response(raw_response)
            if parsed:
                return parsed
        except ProviderError:
            pass
        return {
            "stance": heuristic_stance,
            "reason": "Heuristic classifier used after model stance analysis failed.",
            "source": "heuristic",
        }

    def _model_relevance_threshold(self) -> int:
        if self.speed_accuracy >= 75:
            return 25
        if self.speed_accuracy <= 25:
            return 55
        return 35

    def _heuristic_stance(self, claim: str, title: str, snippet: str, text: str, score: SourceScore, relevance: float, role: dict) -> str:
        primary_text = f"{title} {snippet}".lower()
        evidence = f"{primary_text} {text[:5000]}".lower()
        strong_refute_markers = (
            "false",
            "fake",
            "hoax",
            "misleading",
            "fabricated",
            "debunked",
            "not true",
            "fact check",
        )
        contextual_refute_markers = (
            "did not",
            "denied",
            "denies",
            "no evidence",
            "not supported",
            "unfounded",
        )
        direct_refute_markers = strong_refute_markers + contextual_refute_markers
        support_markers = (
            "confirmed",
            "confirms",
            "announced",
            "approved",
            "filed",
            "files",
            "sued",
            "sues",
            "lawsuit",
            "according to",
            "published",
            "released",
            "said",
            "says",
            "reported",
            "reports",
            "reporting",
            "statement",
            "filing",
            "document",
            "court",
            "data",
            "study",
            "passed",
            "signed",
            "charged",
            "indicted",
        )
        if relevance < 35:
            return "unrelated"
        office_holder_stance = self._office_holder_stance(claim, primary_text, evidence, relevance, score)
        if office_holder_stance:
            return office_holder_stance
        strong_refute = any(marker in primary_text for marker in direct_refute_markers) or any(
            marker in evidence for marker in strong_refute_markers
        )
        contextual_refute = role.get("stance_bias") == "refute" and any(
            marker in evidence for marker in contextual_refute_markers
        )
        if relevance >= 45 and (strong_refute or contextual_refute):
            return "refutes"
        if role.get("stance_bias") == "refute" and score.reliability_score >= 62 and relevance >= 55:
            return "needs_context"
        support_hit = any(marker in evidence for marker in support_markers)
        if score.official_badge and relevance >= 55 and (support_hit or score.reliability_score >= 72):
            return "supports"
        if score.reliability_score >= 62 and relevance >= 58 and support_hit:
            return "supports"
        if role.get("stance_bias") == "support" and score.reliability_score >= 64 and relevance >= 70:
            return "supports"
        if score.reliability_score >= 72 and relevance >= 78:
            return "supports"
        return "needs_context"

    def _office_holder_stance(
        self,
        claim: str,
        primary_text: str,
        evidence: str,
        relevance: float,
        score: SourceScore,
    ) -> str | None:
        office_claim = self._parse_office_holder_claim(claim)
        if not office_claim or relevance < 35:
            return None

        office = office_claim["office"]
        place = office_claim["place"]
        place_terms = office_claim["place_terms"]
        person_terms = office_claim["person_terms"]
        office_place_phrase = f"{office} of {place}"
        has_office_place = office_place_phrase in evidence or (
            office in evidence and all(term in evidence for term in place_terms[:2])
        )
        if not has_office_place:
            return None

        person_in_evidence = any(term in evidence for term in person_terms)
        direct_support = person_in_evidence and (
            f"{person_terms[-1]} is the {office}" in evidence
            or f"{person_terms[-1]} {office} of {place}" in evidence
            or f"{office} {person_terms[-1]}" in evidence
        )
        if direct_support:
            return "supports"

        holder_markers = (
            "current",
            "incumbent",
            "official",
            "office of",
            "head of state",
            "sworn in",
            "serving",
            "smt",
            "shri",
        )
        evidence_names_another_holder = not person_in_evidence and (
            score.official_badge
            or score.reliability_score >= 68
            or any(marker in primary_text or marker in evidence for marker in holder_markers)
        )
        if evidence_names_another_holder:
            return "refutes"
        return None

    def _parse_office_holder_claim(self, claim: str) -> dict | None:
        match = re.search(
            r"^\s*(?P<person>.+?)\s+"
            r"(?:is|was|became|becomes|will be|serves as|served as)\s+"
            r"(?:the\s+)?(?P<office>president|prime minister|king|queen|governor|chief minister|mayor)\s+"
            r"of\s+(?P<place>.+?)(?:\s+in\s+(?P<year>\d{4}))?\s*[.?!]?\s*$",
            claim,
            re.IGNORECASE,
        )
        if not match:
            return None
        person = match.group("person").strip().lower()
        office = match.group("office").strip().lower()
        place = re.sub(r"\s+", " ", match.group("place").strip().lower())
        person_terms = [
            term
            for term in re.findall(r"[a-z0-9]{3,}", person)
            if term not in {"the", "and", "for", "with"}
        ]
        place_terms = [
            term
            for term in re.findall(r"[a-z0-9]{3,}", place)
            if term not in {"the", "and", "for", "with"}
        ]
        if not person_terms or not place_terms:
            return None
        return {
            "person": person,
            "person_terms": person_terms,
            "office": office,
            "place": place,
            "place_terms": place_terms,
            "year": match.group("year"),
        }

    def _stance_prompt(self, claim: str, title: str, snippet: str, text: str, score: SourceScore, role: dict) -> str:
        excerpt = (text or snippet)[:2500]
        return (
            "Classify how this evidence relates to the claim. "
            "Return only compact JSON with keys: stance, reason, summary. "
            "stance must be one of: supports, refutes, needs_context, unrelated. "
            "Use only the supplied source title, search snippet, and evidence excerpt; do not invent facts. "
            "If a reputable source directly reports the central claim and does not deny it, classify it as supports. "
            "Do not mark evidence as needs_context merely because external browser tools are unavailable; this excerpt is the evidence.\n\n"
            f"Claim: {claim}\n"
            f"Agent role: {role.get('kind', 'general')}\n"
            f"Source reliability: {score.reliability_score}\n"
            f"Source title: {title[:300]}\n"
            f"Search snippet: {snippet[:600]}\n"
            f"Evidence excerpt: {excerpt}"
        )

    def _parse_stance_response(self, raw_response: str) -> dict | None:
        try:
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
            data = json.loads(cleaned)
        except Exception:
            return None
        stance = data.get("stance")
        if stance not in {"supports", "refutes", "needs_context", "unrelated"}:
            return None
        return {
            "stance": stance,
            "reason": str(data.get("reason") or "Model stance analysis completed.")[:500],
            "summary": str(data.get("summary") or "")[:700],
            "source": "model",
        }

    def _contradiction_reason(self, stance: str) -> str:
        if stance == "refutes":
            return "Source contains language that appears to refute or debunk the claim"
        if stance == "unrelated":
            return "Source does not appear to address the submitted claim directly"
        return "Source provides context but does not directly corroborate the full claim"

    def _summarize_source(self, claim: str, source: Source, relevance: float, stance: str) -> str:
        if relevance < 35:
            return f"{source.domain} is reputable, but it does not directly corroborate the submitted claim."
        if stance == "refutes":
            return f"{source.domain} appears to challenge the submitted claim. Reliability: {source.reliability_score:.1f}; relevance: {relevance:.1f}."
        if stance == "supports":
            return f"{source.domain} appears to support the claim with relevant evidence. Reliability: {source.reliability_score:.1f}; relevance: {relevance:.1f}."
        if source.extracted_text:
            return f"{source.domain} contains claim-relevant context. Reliability: {source.reliability_score:.1f}; relevance: {relevance:.1f}."
        return f"{source.domain} was identified as possibly relevant, but article extraction was limited."

    def _agent_payload(self, agent: Agent, role: dict | None = None) -> dict:
        role = role or {}
        return {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "task": agent.task,
            "progress": agent.progress,
            "credibility_score": agent.credibility_score,
            "role": role.get("kind", "general"),
            "query": role.get("query"),
        }

    def _source_payload(self, source: Source, stance: str | None = None) -> dict:
        return {
            "id": source.id,
            "agent_id": source.agent_id,
            "url": source.url,
            "domain": source.domain,
            "title": source.title,
            "source_type": source.source_type,
            "official_badge": source.official_badge,
            "authenticity_score": source.authenticity_score,
            "trust_score": source.trust_score,
            "reliability_score": source.reliability_score,
            "bias_score": source.bias_score,
            "stance": stance,
        }
