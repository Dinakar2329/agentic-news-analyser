import { create } from "zustand";

const initialInvestigation = {
  id: null,
  claim: "",
  status: "idle",
  events: [],
  logs: [],
  agents: {},
  sources: {},
  graph: null,
  summary: null,
  verdict: null,
  confidence: 0,
  truthProbability: 0,
  errors: [],
  wsStatus: "idle",
};

function eventLog(event) {
  const payload = event.payload || {};
  switch (event.type) {
    case "investigation_started":
      return `Orchestrator started ${payload.agent_count || 0} agents using ${payload.provider}/${payload.model}`;
    case "agent_spawned":
      return `${payload.agent?.name || "Agent"} spawned: ${payload.agent?.task || "Investigating"}`;
    case "agent_status":
      return `${payload.agent?.name || "Agent"} ${payload.agent?.status || "updated"} - ${Math.round(payload.agent?.progress || 0)}%`;
    case "source_found":
      return `${payload.source?.domain || "Source"} discovered: ${payload.source?.title || "Untitled"}`;
    case "source_ranked":
      return `Source ranked with reliability ${Math.round(payload.scores?.reliability_score || 0)}%`;
    case "source_evaluated":
      return `Evidence stance: ${payload.stance || "needs_context"}`;
    case "confidence_updated":
      return `Confidence updated: ${payload.verdict || "UNVERIFIED"} ${Math.round(payload.confidence || 0)}%`;
    case "final_verdict":
      return `Final verdict: ${payload.verdict || "UNVERIFIED"}`;
    case "error":
      return payload.message || "Investigation warning";
    default:
      return event.type.replaceAll("_", " ");
  }
}

function reduceEvent(state, event) {
  const payload = event.payload || {};
  const next = {
    ...state,
    events: state.events.some((item) => item.id && item.id === event.id) ? state.events : [...state.events, event],
    logs: [...state.logs, { id: event.id || `${event.type}-${state.logs.length}`, type: event.type, text: eventLog(event), created_at: event.created_at }],
  };

  if (event.type === "investigation_started") {
    next.status = "running";
    next.claim = payload.claim || next.claim;
  }

  if (event.type === "agent_spawned" || event.type === "agent_status") {
    const agent = payload.agent;
    if (agent?.id) {
      next.agents = { ...next.agents, [agent.id]: { ...next.agents[agent.id], ...agent } };
    }
  }

  if (event.type === "source_found") {
    const source = payload.source;
    if (source?.id) {
      next.sources = { ...next.sources, [source.id]: source };
    }
  }

  if (event.type === "source_ranked") {
    const sourceId = payload.source_id;
    if (sourceId && next.sources[sourceId]) {
      next.sources = {
        ...next.sources,
        [sourceId]: { ...next.sources[sourceId], ...payload.scores },
      };
    }
  }

  if (event.type === "source_evaluated") {
    const sourceId = payload.source_id;
    if (sourceId && next.sources[sourceId]) {
      next.sources = {
        ...next.sources,
        [sourceId]: { ...next.sources[sourceId], stance: payload.stance, summary: payload.summary, stance_reason: payload.reason },
      };
    }
  }

  if (event.type === "graph_updated") {
    next.graph = payload;
  }

  if (event.type === "confidence_updated") {
    next.verdict = payload.verdict;
    next.confidence = payload.confidence || 0;
    next.truthProbability = payload.truth_probability || 0;
  }

  if (event.type === "orchestrator_summary" || event.type === "final_verdict") {
    next.summary = payload;
    next.verdict = payload.verdict || next.verdict;
    next.confidence = payload.confidence || next.confidence;
    next.truthProbability = payload.truth_probability || next.truthProbability;
  }

  if (event.type === "final_verdict") {
    next.status = "complete";
  }

  if (event.type === "error") {
    next.errors = [...next.errors, payload.message || "Investigation warning"];
  }

  return next;
}

export const useAppStore = create((set) => ({
  screen: "landing",
  user: null,
  models: [],
  authOpen: false,
  byokOpen: false,
  investigation: initialInvestigation,
  setScreen: (screen) => set({ screen }),
  setUser: (user) => set({ user }),
  setModels: (models) => set({ models }),
  setAuthOpen: (authOpen) => set({ authOpen }),
  setByokOpen: (byokOpen) => set({ byokOpen }),
  resetInvestigation: () => set({ investigation: initialInvestigation }),
  startInvestigation: ({ id, claim }) =>
    set({
      screen: "investigation",
      investigation: { ...initialInvestigation, id, claim, status: "queued", wsStatus: "connecting" },
    }),
  setWsStatus: (wsStatus) =>
    set((state) => ({ investigation: { ...state.investigation, wsStatus } })),
  ingestEvent: (event) =>
    set((state) => ({
      investigation: reduceEvent(state.investigation, event),
    })),
}));
