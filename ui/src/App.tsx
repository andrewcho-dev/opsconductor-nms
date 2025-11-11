import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import "vis-network/styles/vis-network.css";

type NodeMeta = Record<string, unknown>;
type EdgeMeta = {
  src: string;
  dst: string;
  type: string;
  confidence: number;
  evidence: string[];
  notes?: string;
};
type GraphPayload = {
  nodes: Record<string, NodeMeta>;
  edges: EdgeMeta[];
};
type PatchMessage = {
  graph: GraphPayload;
  updated_at: string;
  patch: unknown[];
  rationale: string;
  warnings: string[];
};

const apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const wsBase = (import.meta.env.VITE_WS_BASE as string | undefined) ?? "";

function App() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef(new DataSet<any>([]));
  const edgesRef = useRef(new DataSet<any>([]));
  const [status, setStatus] = useState("connecting");
  const [updatedAt, setUpdatedAt] = useState("-");
  const [rationale, setRationale] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  const statusClass = useMemo(() => {
    if (status === "connected") return "status connected";
    if (status === "error") return "status error";
    return "status";
  }, [status]);

  const syncGraph = useCallback((graph: GraphPayload | undefined) => {
    if (!graph) return;
    const nodesDataset = nodesRef.current;
    const edgesDataset = edgesRef.current;
    nodesDataset.clear();
    const nodeItems = Object.entries(graph.nodes ?? {}).map(([id, meta]) => {
      const details = meta as Record<string, unknown>;
      const kind = typeof details.kind === "string" ? details.kind : "unknown";
      const role = typeof details.role === "string" ? details.role : undefined;
      const label = typeof details.label === "string" ? details.label : id;
      const subtitle = role ? `${role}` : kind;
      return {
        id,
        label: `${label}`,
        title: subtitle ? `${id}\n${subtitle}` : id,
        group: kind,
      };
    });
    if (nodeItems.length > 0) {
      nodesDataset.add(nodeItems);
    }
    edgesDataset.clear();
    const edgeItems = (graph.edges ?? []).map((edge) => {
      const opacity = Math.min(1, Math.max(0.2, edge.confidence));
      const label = `${edge.type} ${edge.confidence.toFixed(2)}`;
      return {
        id: `${edge.src}-${edge.dst}-${edge.type}`,
        from: edge.src,
        to: edge.dst,
        label,
        width: Math.max(1, edge.confidence * 4),
        color: { color: "#38bdf8", opacity },
        arrows: "to",
        title: edge.evidence.join("\n"),
      };
    });
    if (edgeItems.length > 0) {
      edgesDataset.add(edgeItems);
    }
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    nodesRef.current = new DataSet([]);
    edgesRef.current = new DataSet([]);
    networkRef.current = new Network(
      containerRef.current,
      { nodes: nodesRef.current, edges: edgesRef.current },
      {
        physics: {
          enabled: true,
          solver: "forceAtlas2Based",
        },
        edges: {
          smooth: true,
        },
      }
    );
    return () => {
      networkRef.current?.destroy();
      nodesRef.current.clear();
      edgesRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!apiBase) return;
    const load = async () => {
      try {
        const response = await fetch(`${apiBase.replace(/\/$/, "")}/graph`);
        if (!response.ok) throw new Error("failed to load graph");
        const data: PatchMessage = await response.json();
        syncGraph(data.graph);
        setUpdatedAt(data.updated_at ?? "-");
      } catch (error) {
        setStatus("error");
      }
    };
    load();
  }, [syncGraph]);

  useEffect(() => {
    if (!wsBase) {
      setStatus("ws disabled");
      return;
    }
    const url = `${wsBase.replace(/\/$/, "")}/ws`;
    const socket = new WebSocket(url);
    socket.onopen = () => setStatus("connected");
    socket.onerror = () => setStatus("error");
    socket.onclose = () => setStatus("disconnected");
    socket.onmessage = (event) => {
      try {
        const payload: PatchMessage = JSON.parse(event.data);
        syncGraph(payload.graph);
        setUpdatedAt(payload.updated_at ?? "-");
        setRationale(payload.rationale ?? "");
        setWarnings(payload.warnings ?? []);
      } catch (error) {
        setStatus("error");
      }
    };
    return () => {
      socket.close();
    };
  }, [syncGraph]);

  return (
    <div className="app">
      <div className="toolbar">
        <span className={statusClass}>{status}</span>
        <span>{updatedAt !== "-" ? new Date(updatedAt).toLocaleString() : "--"}</span>
      </div>
      <div className="content">
        <div className="graph" ref={containerRef} />
        <div className="info">
          <h2>Rationale</h2>
          <p>{rationale || "Awaiting model output"}</p>
          {warnings.length > 0 ? (
            <div>
              <h3>Warnings</h3>
              <ul>
                {warnings.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default App;
