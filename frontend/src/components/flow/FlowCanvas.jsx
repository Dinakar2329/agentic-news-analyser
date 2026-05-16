import { useMemo } from "react";
import { ReactFlow, Background, Handle, Position } from "@xyflow/react";
import { formatPercent } from "@/lib/utils";

const nodeTypes = {
  orchestrator: OrchestratorNode,
  agent: AgentNode,
  source: SourceNode,
};

const NODE_BASE_CLASS =
  "rf-node rounded-[var(--r-md)] border border-[var(--border)] text-[var(--text)] shadow-[var(--shadow-2)] backdrop-blur-xl";

export function FlowCanvas({ graph, agents, sources, confidence, verdict, status = "ready" }) {
  const { nodes, edges } = useMemo(
    () => normalizeGraph(graph, agents, sources, confidence, verdict),
    [agents, confidence, graph, sources, verdict]
  );
  const readyLabel = status === "live" ? "LIVE" : String(status || "ready").toUpperCase();

  return (
    <div className="absolute inset-0 flex flex-col">
      <div className="flow-stage-chrome">
        <span className="dotz">
          <span />
          <span />
          <span />
        </span>
        <span>Agentic News Analyser live investigation graph</span>
        <span className="flow-stage-status">{readyLabel}</span>
      </div>
      <div className="flex-1 min-h-0 relative" style={{ background: "linear-gradient(180deg, var(--bg-deep), var(--bg))" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.28 }}
          minZoom={0.45}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="var(--canvas-grid-line)" gap={56} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
}

function normalizeGraph(graph, agentsById, sourcesById, confidence, verdict) {
  const graphNodes = graph?.nodes?.length ? graph.nodes : fallbackGraphNodes(agentsById, sourcesById, confidence, verdict);
  const graphEdges = graph?.nodes?.length ? graph.edges || [] : fallbackGraphEdges(agentsById, sourcesById);
  const orchestrator = graphNodes.find((node) => node.id === "orchestrator") || {
    id: "orchestrator",
    type: "orchestrator",
    data: {},
  };
  const agentNodes = graphNodes.filter((node) => (node.type || "agent") === "agent");
  const sourceNodes = graphNodes.filter((node) => node.type === "source");
  const agentOrder = agentNodes.map((node) => node.id);
  const agentY = layoutAgentRows(agentNodes.length || 1);
  const sourceParentById = new Map();
  const sourceParent = new Map(
    graphEdges
      .filter((edge) => sourceNodes.some((node) => node.id === edge.target))
      .map((edge) => [edge.target, edge.source])
  );
  const sourcesByAgent = new Map(agentOrder.map((id) => [id, []]));
  sourceNodes.forEach((source, index) => {
    const explicitParent = sourceParent.get(source.id);
    const fallbackAgent = agentOrder[index % Math.max(agentOrder.length, 1)];
    const parent = agentOrder.includes(explicitParent) ? explicitParent : fallbackAgent || "orphan-sources";
    if (!sourcesByAgent.has(parent)) {
      sourcesByAgent.set(parent, []);
    }
    sourcesByAgent.get(parent).push(source);
    sourceParentById.set(source.id, parent);
  });

  const layoutOrder = agentOrder.length ? agentOrder : ["orphan-sources"];
  const laidOutSources = layoutSourceRows(layoutOrder, agentY, sourcesByAgent);
  const yValues = [...agentY, ...laidOutSources.map((item) => item.y), 0];
  const orchestratorY = (Math.min(...yValues) + Math.max(...yValues)) / 2;

  const nodes = [
    {
      id: orchestrator.id,
      type: "orchestrator",
      position: { x: 0, y: orchestratorY },
      data: {
        ...orchestrator.data,
        confidence: confidence || orchestrator.data?.confidence || 0,
        verdict: verdict || orchestrator.data?.verdict,
      },
    },
    ...agentNodes.map((agent, index) => ({
      id: agent.id,
      type: "agent",
      position: { x: 280, y: agentY[index] || 0 },
      data: {
        ...agent.data,
        code: `A${index + 1}`,
        shortLabel: agentLabel(agent.data, index),
      },
    })),
    ...laidOutSources.map(({ node, y, column }, index) => ({
      id: node.id,
      type: "source",
      position: { x: 560 + column * 110, y },
      data: {
        ...node.data,
        shortLabel: sourceLabel(node.data, index),
      },
    })),
  ];

  const edges = graphEdges
    .filter((edge) => nodes.some((node) => node.id === edge.source) && nodes.some((node) => node.id === edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: edge.animated !== false,
      type: "default",
      style: edgeStyle(edge),
    }));
  const connectedSourceIds = new Set(edges.map((edge) => edge.target));
  const fallbackEdges = laidOutSources
    .filter(({ node }) => !connectedSourceIds.has(node.id))
    .map(({ node }) => {
      const parent = sourceParentById.get(node.id);
      if (!nodes.some((candidate) => candidate.id === parent)) return null;
      return {
        id: `fallback-${parent}-${node.id}`,
        source: parent,
        target: node.id,
        animated: false,
        type: "default",
        style: edgeStyle({
          source: parent,
          data: { status: node.data?.stance, weight: (node.data?.reliability_score || 50) / 100 },
        }),
      };
    })
    .filter(Boolean);

  return { nodes, edges: [...edges, ...fallbackEdges] };
}

function fallbackGraphNodes(agentsById, sourcesById, confidence, verdict) {
  const agents = Object.values(agentsById || {});
  const sources = Object.values(sourcesById || {});
  return [
    {
      id: "orchestrator",
      type: "orchestrator",
      data: { label: "Orchestrator Agent", status: "running", confidence, verdict },
    },
    ...agents.map((agent) => ({
      id: agent.id,
      type: "agent",
      data: agentToData(agent),
    })),
    ...sources.map((source) => ({
      id: source.id,
      type: "source",
      data: sourceToData(source),
    })),
  ];
}

function fallbackGraphEdges(agentsById, sourcesById) {
  const agents = Object.values(agentsById || {});
  const sources = Object.values(sourcesById || {});
  return [
    ...agents.map((agent) => ({
      id: `orchestrator-${agent.id}`,
      source: "orchestrator",
      target: agent.id,
      animated: true,
      data: { status: "active", weight: 1 },
    })),
    ...sources
      .filter((source) => source.agent_id)
      .map((source) => ({
        id: `${source.agent_id}-${source.id}`,
        source: source.agent_id,
        target: source.id,
        animated: true,
        data: { status: source.stance, weight: (source.reliability_score || 50) / 100 },
      })),
  ];
}

function layoutAgentRows(count) {
  const gap = count > 4 ? 78 : count > 3 ? 90 : 112;
  const offset = ((count - 1) * gap) / 2;
  return Array.from({ length: count }, (_, index) => index * gap - offset);
}

function layoutSourceRows(agentOrder, agentY, sourcesByAgent) {
  const rows = [];
  let cursor = -Infinity;
  const sourceGap = 46;
  const groupGap = 14;
  const totalSources = Array.from(sourcesByAgent.values()).reduce((sum, items) => sum + items.length, 0);
  const useColumns = totalSources > 12;
  const maxRowsPerColumn = useColumns ? Math.ceil(totalSources / 2) : Infinity;
  let sourceIndex = 0;

  agentOrder.forEach((agentId, agentIndex) => {
    const group = sourcesByAgent.get(agentId) || [];
    if (!group.length) return;
    const centeredStart = (agentY[agentIndex] || 0) - ((group.length - 1) * sourceGap) / 2;
    let y = Math.max(centeredStart, cursor + groupGap);
    group.forEach((node) => {
      const column = Math.floor(sourceIndex / maxRowsPerColumn);
      const rowIndex = useColumns ? sourceIndex % maxRowsPerColumn : sourceIndex;
      rows.push({
        node,
        y: useColumns ? rowIndex * sourceGap - ((maxRowsPerColumn - 1) * sourceGap) / 2 : y,
        column,
      });
      y += sourceGap;
      sourceIndex += 1;
    });
    cursor = y;
  });

  return rows;
}

function edgeStyle(edge) {
  const status = edge.data?.status;
  const isSourceEdge = edge.source !== "orchestrator";
  return {
    stroke: status === "refutes" ? "var(--danger)" : "var(--accent)",
    strokeWidth: isSourceEdge ? 1.2 : 1.4,
    strokeDasharray: "4 6",
    filter: "drop-shadow(0 0 4px var(--accent-glow))",
    opacity: status === "unrelated" ? 0.35 : 0.85,
  };
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

function agentLabel(data = {}, index = 0) {
  const role = String(data.role || "").toLowerCase();
  if (role.includes("official")) return "Official";
  if (role.includes("wire")) return "Newswire";
  if (role.includes("refutation") || role.includes("contradiction")) return "Contradict";
  if (role.includes("context")) return "Context";
  const label = String(data.label || `Agent ${index + 1}`).replace(/\s*Agent\s*$/i, "");
  return label.length > 12 ? label.slice(0, 12) : label;
}

function sourceLabel(data = {}, index = 0) {
  const domain = String(data.domain || data.label || `SRC${index + 1}`)
    .replace(/^www\./i, "")
    .toLowerCase();
  if (data.official_badge) {
    if (domain.includes("sec")) return "SEC";
    if (domain.includes("court")) return "COURT";
    if (domain.includes("eci") || domain.includes("election")) return "ECI";
    if (domain.includes("gov")) return "GOV";
    return "OFFICIAL";
  }
  if (domain.includes("reuters")) return "REUT";
  if (domain.includes("apnews")) return "AP";
  if (domain.includes("bbc")) return "BBC";
  if (domain.includes("fact")) return "FACT";
  if (data.stance === "refutes") return "FACT";
  const clean = domain.split(".")[0].replace(/[^a-z0-9]/g, "");
  return (clean || `SRC${index + 1}`).slice(0, 6).toUpperCase();
}

function OrchestratorNode({ data }) {
  return (
    <div className={`${NODE_BASE_CLASS} rf-orchestrator rf-orchestrator-compact`}>
      <Handle type="source" position={Position.Right} />
      <div className="orch-label">Orchestrator</div>
      <div className="orch-confidence">CONFIDENCE {formatPercent(data.confidence)}</div>
    </div>
  );
}

function AgentNode({ data }) {
  const status = data.status === "complete" ? "complete" : data.status || "running";

  return (
    <div className={`${NODE_BASE_CLASS} rf-agent rf-agent-compact ${status}`}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <span className="agent-code">{data.code || "A"}</span>
      <span className="agent-label">{data.shortLabel || data.label || "Agent"}</span>
    </div>
  );
}

function SourceNode({ data }) {
  return (
    <div
      className={`${NODE_BASE_CLASS} rf-source rf-source-compact ${data.official_badge ? "official" : "unofficial"}`}
      title={data.domain || data.label || "Source"}
    >
      <Handle type="target" position={Position.Left} />
      <span>{data.shortLabel || "SRC"}</span>
    </div>
  );
}

export default FlowCanvas;
