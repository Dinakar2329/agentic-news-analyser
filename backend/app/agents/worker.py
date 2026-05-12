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

            stance_result = await self._classify_stance(claim, result.get("snippet", ""), article["text"], score, relevance, role)
            stance = stance_result["stance"]
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
        stop_words = {"the", "and", "for", "with", "that", "this", "from", "into", "about", "against", "files", "filed"}
        claim_terms = {
            term
            for term in re.findall(r"[a-z0-9]{3,}", claim.lower())
            if term not in stop_words
        }
        if not claim_terms:
            return 0
        evidence_text = evidence.lower()
        matched = sum(1 for term in claim_terms if term in evidence_text)
        return round((matched / len(claim_terms)) * 100, 2)

    async def _classify_stance(self, claim: str, snippet: str, text: str, score: SourceScore, relevance: float, role: dict) -> dict:
        heuristic_stance = self._heuristic_stance(claim, snippet, text, score, relevance, role)
        model_relevance_threshold = self._model_relevance_threshold()
        if not self.provider or not self.model or relevance < model_relevance_threshold:
            return {
                "stance": heuristic_stance,
                "reason": "Heuristic classifier used because model stance analysis was unavailable, speed mode was prioritized, or evidence was low relevance.",
                "source": "heuristic",
            }
        prompt = self._stance_prompt(claim, snippet, text, score, role)
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

    def _heuristic_stance(self, claim: str, snippet: str, text: str, score: SourceScore, relevance: float, role: dict) -> str:
        evidence = f"{snippet} {text}".lower()
        refute_markers = (
            "false",
            "fake",
            "hoax",
            "did not",
            "denied",
            "no evidence",
            "misleading",
            "fabricated",
            "debunked",
            "not true",
        )
        support_markers = (
            "confirmed",
            "announced",
            "filed",
            "according to",
            "said",
            "reported",
            "statement",
            "filing",
            "lawsuit",
        )
        if relevance < 35:
            return "unrelated"
        if any(marker in evidence for marker in refute_markers):
            return "refutes"
        if role.get("stance_bias") == "refute" and score.reliability_score >= 62 and relevance >= 55:
            return "needs_context"
        if score.reliability_score >= 68 and relevance >= 55 and any(marker in evidence for marker in support_markers):
            return "supports"
        return "needs_context"

    def _stance_prompt(self, claim: str, snippet: str, text: str, score: SourceScore, role: dict) -> str:
        excerpt = (text or snippet)[:2500]
        return (
            "Classify how this evidence relates to the claim. "
            "Return only compact JSON with keys: stance, reason, summary. "
            "stance must be one of: supports, refutes, needs_context, unrelated. "
            "Use only the evidence excerpt; do not invent facts.\n\n"
            f"Claim: {claim}\n"
            f"Agent role: {role.get('kind', 'general')}\n"
            f"Source reliability: {score.reliability_score}\n"
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
