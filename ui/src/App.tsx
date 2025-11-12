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
    if (!graph) {
      console.log('[syncGraph] No graph provided');
      return;
    }
    console.log('[syncGraph] Received graph:', graph);
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
    console.log('[syncGraph] Node items to add:', nodeItems);
    if (nodeItems.length > 0) {
      nodesDataset.update(nodeItems);
      console.log('[syncGraph] Nodes added. Dataset size:', nodesDataset.length);
    }
    edgesDataset.clear();
    const edgeMap = new Map<string, EdgeMeta>();
    (graph.edges ?? []).forEach((edge) => {
      const id = `${edge.src}-${edge.dst}-${edge.type}`;
      const existing = edgeMap.get(id);
      if (existing) {
        existing.evidence.push(...edge.evidence);
        existing.confidence = Math.max(existing.confidence, edge.confidence);
      } else {
        edgeMap.set(id, { ...edge });
      }
    });
    const edgeItems = Array.from(edgeMap.values()).map((edge) => {
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
    console.log('[syncGraph] Edge items to add:', edgeItems);
    if (edgeItems.length > 0) {
      edgesDataset.update(edgeItems);
      console.log('[syncGraph] Edges added. Dataset size:', edgesDataset.length);
    }
    if (networkRef.current) {
      console.log('[syncGraph] Network instance exists, calling fit');
      networkRef.current.fit();
    } else {
      console.log('[syncGraph] WARNING: No network instance!');
    }
  }, []);

  useEffect(() => {
    console.log('[Network Effect] Container ref:', containerRef.current);
    if (!containerRef.current) return;
    nodesRef.current = new DataSet([]);
    edgesRef.current = new DataSet([]);
    console.log('[Network Effect] Creating Network instance');
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
    console.log('[Network Effect] Network created:', networkRef.current);
    return () => {
      console.log('[Network Effect] Cleanup');
      networkRef.current?.destroy();
      nodesRef.current.clear();
      edgesRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!apiBase) {
      console.log('[API Effect] No API base configured');
      return;
    }
    console.log('[API Effect] Loading initial graph from:', apiBase);
    const load = async () => {
      try {
        const response = await fetch(`${apiBase.replace(/\/$/, "")}/graph`);
        console.log('[API Effect] Fetch response:', response.status, response.ok);
        if (!response.ok) throw new Error("failed to load graph");
        const data: PatchMessage = await response.json();
        console.log('[API Effect] Received data:', data);
        syncGraph(data.graph);
        setUpdatedAt(data.updated_at ?? "-");
      } catch (error) {
        console.error('[API Effect] Error loading graph:', error);
        setStatus("error");
      }
    };
    load();
  }, [syncGraph]);

  useEffect(() => {
    if (!wsBase) {
      console.log('[WS Effect] No WebSocket base configured');
      setStatus("ws disabled");
      return;
    }
    const url = `${wsBase.replace(/\/$/, "")}/ws`;
    console.log('[WS Effect] Connecting to:', url);
    const socket = new WebSocket(url);
    socket.onopen = () => {
      console.log('[WS] Connected');
      setStatus("connected");
    };
    socket.onerror = (err) => {
      console.error('[WS] Error:', err);
      setStatus("error");
    };
    socket.onclose = () => {
      console.log('[WS] Disconnected');
      setStatus("disconnected");
    };
    socket.onmessage = (event) => {
      try {
        const payload: PatchMessage = JSON.parse(event.data);
        console.log('[WS] Message received:', payload);
        syncGraph(payload.graph);
        setUpdatedAt(payload.updated_at ?? "-");
        setRationale(payload.rationale ?? "");
        setWarnings(payload.warnings ?? []);
      } catch (error) {
        console.error('[WS] Error parsing message:', error);
        setStatus("error");
      }
    };
    return () => {
      console.log('[WS Effect] Cleanup, closing socket');
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
