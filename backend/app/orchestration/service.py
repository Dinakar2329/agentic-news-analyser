import asyncio
import json
from datetime import datetime

from sqlalchemy import select

from app.agents.worker import AgentWorker
from app.auth.security import decrypt_api_key
from app.database.session import async_session_maker
from app.models.tables import ApiKey, Event, GraphSnapshot, Investigation
from app.providers.base import ModelProvider, ProviderError
from app.providers.registry import provider_for_name
from app.scoring.engine import ScoringEngine
from app.websocket.manager import manager


class OrchestratorService:
    def __init__(self):
        self.scoring = ScoringEngine()

    async def start(self, investigation_id: str):
        graph = self._initial_graph(investigation_id)
        graph_lock = asyncio.Lock()

        async with async_session_maker() as db:
            investigation = await db.get(Investigation, investigation_id)
            if not investigation:
                return
            investigation.status = "running"
            await db.commit()

            async def emit(event_type: str, payload: dict):
                await self._emit(investigation_id, event_type, payload)
                await self._update_graph_from_event(investigation_id, graph, graph_lock, event_type, payload)

            await emit(
                "investigation_started",
                {
                    "claim": investigation.claim,
                    "agent_count": investigation.agent_count,
                    "model": investigation.selected_model,
                    "provider": investigation.selected_provider,
                },
            )

            await self._emit(investigation_id, "graph_updated", graph)
            roles = self._agent_roles(investigation.claim, investigation.agent_count)
            provider = await self._provider_for_investigation(investigation)
            worker = AgentWorker(
                emit=emit,
                scoring=self.scoring,
                provider=provider,
                model=investigation.selected_model,
            )
            tasks = [
                worker.run(investigation_id, investigation.claim, index + 1, investigation.search_depth, roles[index])
                for index in range(len(roles))
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_scores = []
            all_findings = []
            errors = []
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                else:
                    scores, findings = result
                    all_scores.extend(scores)
                    all_findings.extend(findings)
            if errors:
                await emit("error", {"message": "Some agents failed", "details": errors[:3]})

            stance_counts = self._stance_counts(all_findings)
            contradiction_count = stance_counts.get("refutes", 0) + stance_counts.get("unrelated", 0)
            verdict = self.scoring.aggregate_verdict(all_scores, contradiction_count, stance_counts)
            investigation.status = "complete"
            investigation.verdict = verdict["verdict"]
            investigation.confidence = verdict["confidence"]
            investigation.completed_at = datetime.utcnow()
            await db.commit()

            summary = {
                **verdict,
                "key_evidence": [item["summary"] for item in all_findings[:5]],
                "contradictions_found": contradiction_count,
                "stance_counts": stance_counts,
                "most_reliable_sources": [
                    {
                        "title": item["source"].title,
                        "url": item["source"].url,
                        "reliability_score": item["source"].reliability_score,
                    }
                    for item in sorted(all_findings, key=lambda row: row["source"].reliability_score, reverse=True)[:5]
                ],
                "timeline": self._build_timeline(all_findings),
                "source_spread": self._source_spread(all_findings),
                "risk_indicators": ["Extraction limits may affect source coverage"] if not all_findings else [],
                "bias_indicators": ["Social or secondary sources are weighted below official and wire sources"],
                "source_quality_analysis": f"Evaluated {len(all_scores)} sources across {investigation.agent_count} agents.",
            }
            if provider:
                try:
                    summary["ai_summary"] = await provider.generate(
                        self._summary_prompt(investigation.claim, summary, all_findings),
                        investigation.selected_model,
                    )
                    summary["model_used"] = {
                        "provider": investigation.selected_provider,
                        "model": investigation.selected_model,
                    }
                except ProviderError as exc:
                    await emit("error", {"message": str(exc), "scope": "final_summary"})
            await emit("confidence_updated", verdict)
            await emit("orchestrator_summary", summary)
            await emit("final_verdict", summary)

    async def _emit(self, investigation_id: str, event_type: str, payload: dict):
        async with async_session_maker() as db:
            event = Event(investigation_id=investigation_id, type=event_type, payload_json=json.dumps(payload))
            db.add(event)
            if event_type == "graph_updated":
                db.add(
                    GraphSnapshot(
                        investigation_id=investigation_id,
                        nodes_json=json.dumps(payload["nodes"]),
                        edges_json=json.dumps(payload["edges"]),
                    )
                )
            await db.commit()
        await manager.broadcast(investigation_id, event_type, payload)

    def _graph_payload(self, investigation_id: str, nodes: list, edges: list) -> dict:
        return {"investigation_id": investigation_id, "nodes": nodes, "edges": edges}

    def _initial_graph(self, investigation_id: str) -> dict:
        return self._graph_payload(
            investigation_id,
            [
                {
                    "id": "orchestrator",
                    "type": "orchestrator",
                    "position": {"x": 0, "y": 0},
                        "data": {
                            "label": "Orchestrator Agent",
                            "status": "running",
                            "confidence": 0,
                            "task": "Planning investigation",
                            "phase": "planning",
                        },
                }
            ],
            [],
        )

    async def _update_graph_from_event(self, investigation_id: str, graph: dict, graph_lock: asyncio.Lock, event_type: str, payload: dict):
        if event_type == "graph_updated":
            return
        changed = False
        async with graph_lock:
            if event_type == "agent_spawned":
                agent = payload["agent"]
                agent_index = len([node for node in graph["nodes"] if node["type"] == "agent"])
                graph["nodes"].append(
                    {
                        "id": agent["id"],
                        "type": "agent",
                        "position": {"x": -280 + agent_index * 280, "y": 180},
                        "data": {
                            "label": agent["name"],
                            "status": agent["status"],
                            "task": agent["task"],
                            "progress": agent["progress"],
                            "credibility_score": agent["credibility_score"],
                            "role": agent.get("role"),
                            "query": agent.get("query"),
                            "phase": "searching",
                        },
                    }
                )
                graph["edges"].append(
                    {
                        "id": f"orchestrator-{agent['id']}",
                        "source": "orchestrator",
                        "target": agent["id"],
                        "animated": True,
                        "data": {"weight": 1, "status": "active"},
                    }
                )
                changed = True
            elif event_type == "agent_status":
                agent = payload["agent"]
                node = self._node_by_id(graph, agent["id"])
                if node:
                    node["data"].update(
                        {
                            "status": agent["status"],
                            "task": agent["task"],
                            "progress": agent["progress"],
                            "credibility_score": agent["credibility_score"],
                        }
                    )
                    changed = True
            elif event_type == "source_found":
                source = payload["source"]
                source_count = len([node for node in graph["nodes"] if node["type"] == "source"])
                graph["nodes"].append(
                    {
                        "id": source["id"],
                        "type": "source",
                        "position": {"x": -360 + (source_count % 4) * 240, "y": 380 + (source_count // 4) * 140},
                        "data": {
                            "label": source["title"],
                            "domain": source["domain"],
                            "url": source["url"],
                            "source_type": source["source_type"],
                            "official_badge": source["official_badge"],
                            "authenticity_score": source["authenticity_score"],
                            "trust_score": source["trust_score"],
                            "reliability_score": source["reliability_score"],
                            "bias_score": source["bias_score"],
                            "stance": source.get("stance"),
                            "phase": "discovered",
                        },
                    }
                )
                graph["edges"].append(
                    {
                        "id": f"{source['agent_id']}-{source['id']}",
                        "source": source["agent_id"],
                        "target": source["id"],
                        "animated": True,
                        "data": {"weight": round(source["reliability_score"] / 100, 2), "status": "evaluating"},
                    }
                )
                changed = True
            elif event_type == "source_ranked":
                node = self._node_by_id(graph, payload["source_id"])
                if node:
                    node["data"].update(payload["scores"])
                    node["data"]["phase"] = "ranked"
                    changed = True
            elif event_type == "source_evaluated":
                node = self._node_by_id(graph, payload["source_id"])
                if node:
                    node["data"].update(
                        {
                            "stance": payload["stance"],
                            "stance_reason": payload.get("reason"),
                            "summary": payload.get("summary"),
                            "analysis_source": payload.get("analysis_source"),
                            "phase": "evaluated",
                        }
                    )
                    edge = self._edge_by_target(graph, payload["source_id"])
                    if edge:
                        edge["data"]["status"] = payload["stance"]
                    changed = True
            elif event_type == "confidence_updated":
                node = self._node_by_id(graph, "orchestrator")
                if node:
                    node["data"].update(
                        {
                            "status": "complete",
                            "confidence": payload["confidence"],
                            "verdict": payload["verdict"],
                            "truth_probability": payload["truth_probability"],
                            "phase": "complete",
                        }
                    )
                    changed = True
            if changed:
                snapshot = json.loads(json.dumps(graph))
            else:
                snapshot = None
        if snapshot:
            await self._emit(investigation_id, "graph_updated", snapshot)

    def _node_by_id(self, graph: dict, node_id: str) -> dict | None:
        return next((node for node in graph["nodes"] if node["id"] == node_id), None)

    def _edge_by_target(self, graph: dict, target_id: str) -> dict | None:
        return next((edge for edge in graph["edges"] if edge["target"] == target_id), None)

    async def _provider_for_investigation(self, investigation: Investigation) -> ModelProvider | None:
        async with async_session_maker() as db:
            stored_key = await db.scalar(
                select(ApiKey).where(
                    ApiKey.user_id == investigation.user_id,
                    ApiKey.provider == investigation.selected_provider,
                )
            )
            api_key = decrypt_api_key(stored_key.encrypted_key) if stored_key else None
        return provider_for_name(investigation.selected_provider, api_key=api_key)

    def _agent_roles(self, claim: str, agent_count: int) -> list[dict]:
        templates = [
            {
                "kind": "official",
                "name": "Official Records Agent",
                "task": "Find primary documents, government records, filings, court documents, or official statements.",
                "query": f"{claim} official source filing statement government court document",
                "stance_bias": "support",
            },
            {
                "kind": "wire",
                "name": "Trusted News Agent",
                "task": "Find trusted reporting from wire services and high-reputation newsrooms.",
                "query": f"{claim} Reuters AP BBC report verified",
                "stance_bias": "support",
            },
            {
                "kind": "refutation",
                "name": "Contradiction Agent",
                "task": "Look for denials, corrections, fact checks, or evidence that refutes the claim.",
                "query": f"{claim} false denied fake hoax fact check debunked no evidence",
                "stance_bias": "refute",
            },
            {
                "kind": "context",
                "name": "Context Agent",
                "task": "Find background, timeline, source spread, and context that changes interpretation.",
                "query": f"{claim} timeline background context source origin",
                "stance_bias": "context",
            },
        ]
        return templates[:agent_count]

    def _stance_counts(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in findings:
            stance = finding.get("stance", "needs_context")
            counts[stance] = counts.get(stance, 0) + 1
        return counts

    def _build_timeline(self, findings: list[dict]) -> list[dict]:
        timeline = [{"label": "Claim submitted", "kind": "system", "description": "The orchestrator accepted the claim and planned specialist searches."}]
        for index, finding in enumerate(findings[:8], start=1):
            source = finding["source"]
            timeline.append(
                {
                    "label": f"Evidence {index}: {source.domain}",
                    "kind": finding.get("stance", "needs_context"),
                    "description": finding["summary"],
                    "url": source.url,
                    "source_type": source.source_type,
                    "reliability_score": source.reliability_score,
                    "agent_role": finding.get("agent_role"),
                }
            )
        timeline.append(
            {
                "label": "Verdict synthesized",
                "kind": "system",
                "description": "The orchestrator combined source reliability, stance counts, contradictions, and cross-source evidence.",
            }
        )
        return timeline

    def _source_spread(self, findings: list[dict]) -> dict:
        domains: dict[str, int] = {}
        source_types: dict[str, int] = {}
        analysis_sources: dict[str, int] = {}
        for finding in findings:
            source = finding["source"]
            domains[source.domain] = domains.get(source.domain, 0) + 1
            source_types[source.source_type] = source_types.get(source.source_type, 0) + 1
            analysis_source = finding.get("stance_source") or "unknown"
            analysis_sources[analysis_source] = analysis_sources.get(analysis_source, 0) + 1
        return {
            "domains": domains,
            "source_types": source_types,
            "stance_analysis_sources": analysis_sources,
            "unique_domains": len(domains),
        }

    def _summary_prompt(self, claim: str, summary: dict, findings: list[dict]) -> str:
        evidence_rows = []
        for item in findings[:8]:
            source = item["source"]
            evidence_rows.append(
                {
                    "title": source.title,
                    "domain": source.domain,
                    "url": source.url,
                    "reliability_score": source.reliability_score,
                    "bias_score": source.bias_score,
                    "source_type": source.source_type,
                    "stance": item.get("stance"),
                    "finding": item["summary"],
                }
            )
        return (
            "Fact-check this claim using only the supplied evidence. "
            "Return a short final assessment with verdict rationale, strongest evidence, limitations, and what would change the conclusion.\n\n"
            f"Claim: {claim}\n"
            f"Computed verdict: {summary['verdict']}\n"
            f"Computed confidence: {summary['confidence']}\n"
            f"Evidence: {json.dumps(evidence_rows, ensure_ascii=False)}"
        )


orchestrator = OrchestratorService()
