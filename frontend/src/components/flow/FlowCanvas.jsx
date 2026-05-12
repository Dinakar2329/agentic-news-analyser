import { useMemo } from "react";
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from "@xyflow/react";
import { formatPercent } from "@/lib/utils";

const nodeTypes = {
  orchestrator: OrchestratorNode,
  agent: AgentNode,
  source: SourceNode,
};

export function FlowCanvas({ graph, agents, sources, confidence, verdict }) {
  const { nodes, edges } = useMemo(
    () => normalizeGraph(graph, agents, sources, confidence, verdict),
    [agents, confidence, graph, sources, verdict]
  );

  return (
    <div className="react-flow-shell">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.24 }}
        minZoom={0.35}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="rgba(255,255,255,0.08)" gap={28} size={1} />
        <Controls position="top-right" />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeColor={(node) => {
            if (node.type === "orchestrator") return "var(--accent)";
            if (node.type === "source") return node.data?.official_badge ? "var(--accent)" : "var(--info)";
            return "var(--surface-3)";
          }}
        />
      </ReactFlow>
    </div>
  );
}

function normalizeGraph(graph, agentsById, sourcesById, confidence, verdict) {
  if (graph?.nodes?.length) {
    return {
      nodes: graph.nodes.map((node) => ({
        id: node.id,
        type: node.type || "agent",
        position: node.position || { x: 0, y: 0 },
        data: {
          ...node.data,
          confidence: node.id === "orchestrator" ? confidence || node.data?.confidence || 0 : node.data?.confidence,
          verdict: verdict || node.data?.verdict,
        },
      })),
      edges: (graph.edges || []).map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        animated: edge.animated !== false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: {
          stroke: edge.data?.status === "refutes" ? "var(--danger)" : edge.data?.status === "supports" ? "var(--accent)" : "rgba(255,255,255,0.22)",
          strokeWidth: Math.max(1, (edge.data?.weight || 0.5) * 3),
        },
      })),
    };
  }

  const agents = Object.values(agentsById || {});
  const sources = Object.values(sourcesById || {});
  const nodes = [
    {
      id: "orchestrator",
      type: "orchestrator",
      position: { x: 0, y: 160 },
      data: { label: "Orchestrator Agent", status: "running", confidence, verdict, task: "Waiting for graph events" },
    },
    ...agents.map((agent, index) => ({
      id: agent.id,
      type: "agent",
      position: { x: 360, y: 40 + index * 160 },
      data: agentToData(agent),
    })),
    ...sources.map((source, index) => ({
      id: source.id,
      type: "source",
      position: { x: 760 + (index % 2) * 120, y: 40 + index * 92 },
      data: sourceToData(source),
    })),
  ];

  const edges = [
    ...agents.map((agent) => ({
      id: `orchestrator-${agent.id}`,
      source: "orchestrator",
      target: agent.id,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "rgba(255,255,255,0.2)" },
    })),
    ...sources.map((source) => ({
      id: `${source.agent_id}-${source.id}`,
      source: source.agent_id,
      target: source.id,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: source.stance === "supports" ? "var(--accent)" : source.stance === "refutes" ? "var(--danger)" : "rgba(255,255,255,0.18)" },
    })),
  ];

  return { nodes, edges };
}

function agentToData(agent) {
  return {
    label: agent.name,
    status: agent.status,
    task: agent.task,
    progress: agent.progress,
    credibility_score: agent.credibility_score,
    role: agent.role,
    query: agent.query,
  };
}

function sourceToData(source) {
  return {
    label: source.title,
    domain: source.domain,
    url: source.url,
    source_type: source.source_type,
    official_badge: source.official_badge,
    authenticity_score: source.authenticity_score,
    trust_score: source.trust_score,
    reliability_score: source.reliability_score,
    bias_score: source.bias_score,
    stance: source.stance,
  };
}

function OrchestratorNode({ data }) {
  return (
    <div className="rf-node rf-orchestrator">
      <Handle type="source" position={Position.Right} />
      <div className="nrow">
        <div className="navatar">O</div>
        <div>
          <div className="nname">{data.label || "Orchestrator"}</div>
          <div className="ntype">ROOT ROUTER</div>
        </div>
      </div>
      <div className="confidence-mini">
        <div className="ctop">
          <span className="l">{data.verdict || "Investigating"}</span>
          <span className="v">{formatPercent(data.confidence)}</span>
        </div>
        <div className="cbar">
          <span style={{ width: `${Math.round(data.confidence || 0)}%` }} />
        </div>
      </div>
    </div>
  );
}

function AgentNode({ data }) {
  return (
    <div className={"rf-node rf-agent " + (data.status || "running")}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="nrow">
        <div className="navatar">{(data.label || "A").slice(0, 1)}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="nname">{data.label || "Search Agent"}</div>
          <div className="ntype">AGENT {String(data.role || "general").toUpperCase()}</div>
        </div>
      </div>
      <div className="nsub">{data.task || data.query || "Searching for evidence"}</div>
      <div className="nstat">
        <span className="led" />
        <span className="lbl">{data.status || "running"} {Math.round(data.progress || 0)}%</span>
        <span className="mono score-mini">cred {Math.round(data.credibility_score || 0)}</span>
      </div>
      <div className="progress">
        <span style={{ width: `${Math.round(data.progress || 0)}%` }} />
      </div>
    </div>
  );
}

function SourceNode({ data }) {
  return (
    <div className={"rf-node rf-source " + (data.official_badge ? "official" : "unofficial")}>
      <Handle type="target" position={Position.Left} />
      <div className="nrow">
        <div className="navatar">{String(data.domain || "src").slice(0, 2).toUpperCase()}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="nname source-title">{data.label || "Source"}</div>
          <div className="ntype">{data.official_badge ? "OFFICIAL" : data.source_type || "SOURCE"}</div>
        </div>
      </div>
      <div className="miniscore">
        <span>rel</span>
        <span className={"ms-bar " + (data.official_badge ? "" : "unof")}>
          <span style={{ width: `${Math.round(data.reliability_score || 0)}%` }} />
        </span>
        <span className="mono">{Math.round(data.reliability_score || 0)}</span>
      </div>
      {data.stance && <div className={"stance-chip stance-" + data.stance}>{data.stance}</div>}
    </div>
  );
}

export default FlowCanvas;