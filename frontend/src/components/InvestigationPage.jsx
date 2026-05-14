import { useMemo, useState } from "react";
import { Icon } from "@/components/icons.jsx";
import { FlowCanvas } from "@/components/flow/FlowCanvas.jsx";
import { useInvestigationSocket } from "@/hooks/useInvestigationSocket";
import { useAppStore } from "@/store/appStore";
import { formatPercent, shortId, verdictKey } from "@/lib/utils";

const VERDICT_META = {
  TRUE: { color: "var(--v-true)", risk: "LOW", bias: "LOW" },
  MOSTLY_TRUE: { color: "var(--v-mostly)", risk: "LOW", bias: "MODERATE" },
  PARTIALLY_TRUE: {
    color: "var(--v-partial)",
    risk: "MODERATE",
    bias: "MODERATE",
  },
  MISLEADING: { color: "var(--v-mislead)", risk: "HIGH", bias: "HIGH" },
  UNVERIFIED: { color: "var(--v-unver)", risk: "UNKNOWN", bias: "UNKNOWN" },
  FALSE: { color: "var(--v-false)", risk: "CRITICAL", bias: "HIGH" },
};

export function InvestigationPage({ onBack }) {
  const [tab, setTab] = useState("chat");
  const investigation = useAppStore((state) => state.investigation);
  const agents = useMemo(
    () => Object.values(investigation.agents),
    [investigation.agents],
  );
  const sources = useMemo(
    () => Object.values(investigation.sources),
    [investigation.sources],
  );

  useInvestigationSocket(investigation.id);

  return (
    <div className="inv" data-screen-label="03 Investigation">
      <div className="inv-left">
        <div className="inv-left-head">
          <div className="claim-mini">
            <span className="lbl">CLAIM</span>
            {investigation.claim}
          </div>
          <button
            className="iconbtn"
            onClick={onBack}
            title="New investigation"
          >
            <Icon.Plus />
          </button>
        </div>

        <div className="tabs">
          <button
            className={"tab " + (tab === "chat" ? "active" : "")}
            onClick={() => setTab("chat")}
          >
            <Icon.Brain /> Reasoning
          </button>
          <button
            className={"tab " + (tab === "logs" ? "active" : "")}
            onClick={() => setTab("logs")}
          >
            <Icon.Zap /> Live Logs{" "}
            <span className="count">{investigation.logs.length}</span>
          </button>
          <button
            className={"tab " + (tab === "verdict" ? "active" : "")}
            onClick={() => setTab("verdict")}
          >
            <Icon.Check /> Verdict
          </button>
        </div>

        <div className="inv-left-body">
          {tab === "chat" && (
            <ChatFeed
              investigation={investigation}
              agents={agents}
              sources={sources}
            />
          )}
          {tab === "logs" && (
            <LogsFeed
              logs={investigation.logs}
              status={investigation.wsStatus}
            />
          )}
          {tab === "verdict" && (
            <VerdictPane investigation={investigation} sources={sources} />
          )}
        </div>
      </div>

      <div className="canvas-wrap" data-screen-label="03.canvas Flow">
        <FlowCanvas
          graph={investigation.graph}
          agents={investigation.agents}
          sources={investigation.sources}
          confidence={investigation.confidence}
          verdict={investigation.verdict}
        />
        <CanvasToolbar investigation={investigation} />
        <CanvasLegend />
      </div>

      <div className="toast">
        <span className="led" /> {investigation.wsStatus} - session{" "}
        {shortId(investigation.id)} - {agents.length} agents - {sources.length}{" "}
        sources
      </div>
    </div>
  );
}

function ChatFeed({ investigation, agents, sources }) {
  const summary = investigation.summary;
  const aiSummary = summary?.ai_summary;

  return (
    <div className="chat-feed">
      <div className="msg user">
        <div className="role">
          <span className="av">U</span>YOU
        </div>
        <div className="body">{investigation.claim}</div>
      </div>

      <div className="msg orchestrator">
        <div className="role">
          <span className="av">O</span>ORCHESTRATOR
        </div>
        <div className="body">
          {investigation.status === "queued"
            ? "Investigation queued. Waiting for the backend worker to claim the job."
            : `Running ${agents.length || "the requested"} agents and streaming source evidence as it arrives.`}
        </div>
      </div>

      <ReasoningCard investigation={investigation} aiSummary={aiSummary} />

      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}

      {sources.slice(0, 5).map((source) => (
        <SourceCard key={source.id} source={source} />
      ))}
    </div>
  );
}

function ReasoningCard({ investigation, aiSummary }) {
  const body =
    aiSummary ||
    investigation.summary?.key_evidence?.join("\n\n") ||
    investigation.logs
      .slice(-5)
      .map((log) => log.text)
      .join("\n") ||
    "Waiting for orchestrator events...";

  return (
    <div className="reason-card">
      <div className="rc-head">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="led" />
          ORCHESTRATOR STREAM
        </span>
        <span>{investigation.status}</span>
      </div>
      <div className="rc-body">
        {body}
        {investigation.status !== "complete" && <span className="cursor" />}
      </div>
    </div>
  );
}

function AgentCard({ agent }) {
  return (
    <div className="msg agent">
      <div className="role">
        <span className="av">{agent.name?.slice(0, 1) || "A"}</span>
        {agent.name}
      </div>
      <div className="body">
        <div className="agent-card-row">
          <span style={{ color: "var(--text-2)" }}>{agent.task}</span>
          <span className="mono agent-status">
            {agent.status} {Math.round(agent.progress || 0)}%
          </span>
        </div>
        <div className="agent-progress">
          <span style={{ width: `${Math.round(agent.progress || 0)}%` }} />
        </div>
      </div>
    </div>
  );
}

function SourceCard({ source }) {
  return (
    <div className="msg agent source-message">
      <div className="role">
        <span className="av">
          {source.domain?.slice(0, 1)?.toUpperCase() || "S"}
        </span>
        SOURCE {source.domain}
      </div>
      <div className="body">
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer"
          className="source-link-title"
        >
          {source.title}
        </a>
        <div className="source-score-line">
          Reliability {formatPercent(source.reliability_score)} - Trust{" "}
          {formatPercent(source.trust_score)} - Bias{" "}
          {formatPercent(source.bias_score)}
        </div>
      </div>
    </div>
  );
}

function LogsFeed({ logs, status }) {
  return (
    <div className="logs-feed">
      {logs.map((log, index) => (
        <div key={log.id || index} className={"log t-" + logKind(log.type)}>
          <span className="ts">{String(index + 1).padStart(2, "0")}</span>
          <span className="ic">{logIcon(log.type)}</span>
          <span className="txt">{log.text}</span>
        </div>
      ))}
      <div className="log t-info">
        <span className="ts">--</span>
        <span className="ic" />
        <span className="txt muted">
          <em>
            WebSocket {status || "idle"}{" "}
            {status === "live" && (
              <span className="cursor" style={{ height: "0.8em" }} />
            )}
          </em>
        </span>
      </div>
    </div>
  );
}

function VerdictPane({ investigation, sources }) {
  const summary = investigation.summary || {};
  const verdictText =
    investigation.verdict?.trim() || summary.verdict?.trim() || "UNVERIFIED";
  const key = verdictKey(verdictText);
  const meta = VERDICT_META[key] || VERDICT_META.UNVERIFIED;

  return (
    <div
      className="verdict-wrap"
      style={{
        "--vc-color": meta.color,
        "--vc-tint": `color-mix(in oklch, ${meta.color} 22%, transparent)`,
      }}
    >
      <div className="verdict-card">
        <div className="v-label">VERDICT - CONFIDENCE-WEIGHTED SYNTHESIS</div>
        <div className="v-verdict">{verdictText}</div>
        <div className="v-claim">
          {summary.ai_summary ||
            summary.key_evidence?.[0] ||
            "The backend has not emitted a final verdict yet."}
        </div>
        <Meter label="Confidence" value={investigation.confidence} />
        <Meter
          label="Truth probability"
          value={investigation.truthProbability}
        />
      </div>

      <div className="indicators">
        <Indicator
          label="Risk"
          value={summary.risk_indicators?.length ? "ELEVATED" : meta.risk}
          tone={meta.risk === "LOW" ? "ok" : "warn"}
        />
        <Indicator
          label="Bias index"
          value={summary.bias_indicators?.length ? "CHECKED" : meta.bias}
          tone={meta.bias === "HIGH" ? "bad" : "ok"}
        />
        <Indicator
          label="Source quality"
          value={`${sources.length} cited`}
          tone="ok"
        />
        <Indicator
          label="Contradictions"
          value={String(summary.contradictions_found || 0)}
        />
      </div>

      <div>
        <div className="source-list-head">
          <span className="mono">SOURCE GRAPH - {sources.length} CITED</span>
        </div>
        <div className="src-list">
          {sources.map((source) => (
            <a
              key={source.id}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="src-row"
            >
              <div className="fav">
                {source.domain?.slice(0, 2)?.toUpperCase()}
              </div>
              <div>
                <div className="title">{source.title}</div>
                <div className="url">{source.url}</div>
              </div>
              <div className="scores">
                <div className="auth">
                  rel {Math.round(source.reliability_score || 0)}
                </div>
                <div
                  className={"badge " + (source.official_badge ? "" : "unof")}
                >
                  {source.official_badge ? "OFFICIAL" : source.source_type}
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

function Meter({ label, value }) {
  const normalized = Math.round(value || 0);
  return (
    <div className="meter">
      <div className="m-top">
        <span className="ml">{label}</span>
        <span className="mr">{normalized}%</span>
      </div>
      <div className="bar">
        <span style={{ width: `${normalized}%` }} />
      </div>
    </div>
  );
}

function Indicator({ label, value, tone = "" }) {
  return (
    <div className="indicator">
      <div className="il">{label}</div>
      <div className={"iv " + tone}>{value}</div>
    </div>
  );
}

function CanvasToolbar({ investigation }) {
  return (
    <div className="canvas-toolbar">
      <span className="pill">
        <span className="led" />
        {investigation.wsStatus.toUpperCase()}
      </span>
      <span className="pill">
        <span className="led idle" />
        SESS {shortId(investigation.id)}
      </span>
      <span className="pill">
        {investigation.verdict?.trim() ||
          investigation.summary?.verdict?.trim() ||
          "INVESTIGATING"}
      </span>
    </div>
  );
}

function CanvasLegend() {
  return (
    <div className="canvas-legend">
      <div className="row">
        <span className="swatch" style={{ background: "var(--accent)" }} />
        Orchestrator
      </div>
      <div className="row">
        <span
          className="swatch"
          style={{
            background: "var(--surface-2)",
            borderColor: "var(--border)",
          }}
        />
        Agent
      </div>
      <div className="row">
        <span
          className="swatch"
          style={{
            background: "var(--surface)",
            borderColor: "var(--accent-dim)",
          }}
        />
        Official source
      </div>
      <div className="row">
        <span className="swatch" style={{ background: "var(--surface)" }} />
        Reporting source
      </div>
    </div>
  );
}

function logKind(type) {
  if (type === "error") return "warn";
  if (
    [
      "source_found",
      "source_ranked",
      "final_verdict",
      "confidence_updated",
    ].includes(type)
  )
    return "ok";
  return "info";
}

function logIcon(type) {
  if (type === "error") return "!";
  if (
    [
      "source_found",
      "source_ranked",
      "final_verdict",
      "confidence_updated",
    ].includes(type)
  )
    return <Icon.Check />;
  return "";
}
