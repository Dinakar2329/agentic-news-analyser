import { useEffect } from "react";
import { getInvestigation, investigationWsUrl } from "@/lib/api";
import { useAppStore } from "@/store/appStore";

export function useInvestigationSocket(investigationId) {
  const ingestEvent = useAppStore((state) => state.ingestEvent);
  const setWsStatus = useAppStore((state) => state.setWsStatus);

  useEffect(() => {
    if (!investigationId) return undefined;

    let closed = false;
    let ws;

    async function replayCurrentState() {
      try {
        const detail = await getInvestigation(investigationId);
        for (const event of detail.events || []) {
          ingestEvent({
            id: event.id || `${event.created_at}-${event.type}`,
            type: event.type,
            investigation_id: event.investigation_id || investigationId,
            payload: event.payload,
            created_at: event.created_at,
          });
        }
        return detail;
      } catch {
        // WebSocket replay is authoritative; REST detail is only a catch-up fallback.
        return null;
      }
    }

    function connect() {
      setWsStatus("connecting");
      ws = new WebSocket(investigationWsUrl(investigationId));

      ws.onopen = () => {
        if (!closed) setWsStatus("live");
      };
      ws.onmessage = (message) => {
        try {
          ingestEvent(JSON.parse(message.data));
        } catch {
          ingestEvent({
            type: "error",
            investigation_id: investigationId,
            payload: { message: "Received malformed websocket event" },
            created_at: new Date().toISOString(),
          });
        }
      };
      ws.onerror = () => {
        if (!closed) setWsStatus("error");
      };
      ws.onclose = () => {
        if (!closed) setWsStatus("closed");
      };
    }

    async function start() {
      setWsStatus("loading");
      const detail = await replayCurrentState();
      if (closed) return;
      if (detail?.status === "complete" || detail?.status === "failed") {
        setWsStatus("closed");
        return;
      }
      connect();
    }

    start();

    return () => {
      closed = true;
      setWsStatus("closed");
      ws?.close();
    };
  }, [ingestEvent, investigationId, setWsStatus]);
}
