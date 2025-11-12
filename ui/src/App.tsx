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
  const viewRef = useRef<{ scale: number; position: { x: number; y: number } } | null>(null);
  const autoFitRef = useRef(true);
  const [status, setStatus] = useState("connecting");
  const [updatedAt, setUpdatedAt] = useState("-");
  const [rationale, setRationale] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [graphStats, setGraphStats] = useState({ nodeCount: 0, edgeCount: 0, missingEndpoints: 0 });
  const [notices, setNotices] = useState<string[]>([]);
  const [staleNotice, setStaleNotice] = useState<string | null>(null);

  const statusClass = useMemo(() => {
    if (status === "connected") return "status connected";
    if (status === "error") return "status error";
    return "status";
  }, [status]);

  const syncGraph = useCallback((graph: GraphPayload | undefined) => {
    const nodesDataset = nodesRef.current;
    const edgesDataset = edgesRef.current;
    const noticeList: string[] = [];
    if (!graph) {
      console.log('[syncGraph] No graph provided');
      nodesDataset.clear();
      edgesDataset.clear();
      setGraphStats({ nodeCount: 0, edgeCount: 0, missingEndpoints: 0 });
      setNotices(["No graph data received from state server."]);
      return;
    }
    console.log('[syncGraph] Received graph:', graph);
    const currentNodeIds = new Set(nodesDataset.getIds());
    const nodeEntries = Object.entries(graph.nodes ?? {});
    const knownNodes = new Set<string>();
    const nodeItems = nodeEntries.map(([id, meta]) => {
      const details = meta as Record<string, unknown>;
      const kind = typeof details.kind === "string" ? details.kind : "unknown";
      const role = typeof details.role === "string" ? details.role : undefined;
      const label = typeof details.label === "string" ? details.label : id;
      const subtitle = role ? `${role}` : kind;
      knownNodes.add(id);
      return {
        id,
        label: `${label}`,
        title: subtitle ? `${id}\n${subtitle}` : id,
        group: kind,
      };
    });
    const placeholderNodes = new Map<string, { id: string; label: string; title: string; group: string }>();
    let edgesWithMissingEndpoints = 0;
    const rawEdges = [...(graph.edges ?? [])];
    rawEdges.forEach((edge) => {
      let missing = false;
      if (!knownNodes.has(edge.src)) {
        knownNodes.add(edge.src);
        missing = true;
        if (!placeholderNodes.has(edge.src)) {
          placeholderNodes.set(edge.src, {
            id: edge.src,
            label: edge.src,
            title: `${edge.src}\nunknown`,
            group: "unknown",
          });
        }
      }
      if (!knownNodes.has(edge.dst)) {
        knownNodes.add(edge.dst);
        missing = true;
        if (!placeholderNodes.has(edge.dst)) {
          placeholderNodes.set(edge.dst, {
            id: edge.dst,
            label: edge.dst,
            title: `${edge.dst}\nunknown`,
            group: "unknown",
          });
        }
      }
      if (missing) {
        edgesWithMissingEndpoints += 1;
      }
    });
    const combinedNodes = [...nodeItems, ...placeholderNodes.values()];
    console.log('[syncGraph] Node items to add:', combinedNodes);
    if (combinedNodes.length > 0) {
      nodesDataset.update(combinedNodes);
      console.log('[syncGraph] Nodes updated. Dataset size:', nodesDataset.length);
    }
    const removedNodes = Array.from(currentNodeIds).filter(id => !knownNodes.has(id as string));
    if (removedNodes.length > 0) {
      nodesDataset.remove(removedNodes);
      console.log('[syncGraph] Removed nodes:', removedNodes);
    }
    const currentEdgeIds = new Set(edgesDataset.getIds());
    const edgeMap = new Map<string, EdgeMeta>();
    rawEdges.forEach((edge) => {
      const id = `${edge.src}-${edge.dst}-${edge.type}`;
      const existing = edgeMap.get(id);
      if (existing) {
        existing.evidence = Array.from(new Set([...existing.evidence, ...edge.evidence]));
        existing.confidence = Math.max(existing.confidence, edge.confidence);
      } else {
        edgeMap.set(id, { ...edge, evidence: [...edge.evidence] });
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
        color: { color: "#2563eb", opacity },
        arrows: "to",
        title: edge.evidence.join("\n"),
      };
    });
    const newEdgeIds = new Set(edgeItems.map(e => e.id));
    console.log('[syncGraph] Edge items to add/update:', edgeItems);
    if (edgeItems.length > 0) {
      edgesDataset.update(edgeItems);
      console.log('[syncGraph] Edges updated. Dataset size:', edgesDataset.length);
    } else {
      noticeList.push("No links received from discovery services.");
    }
    const removedEdges = Array.from(currentEdgeIds).filter(id => !newEdgeIds.has(id as string));
    if (removedEdges.length > 0) {
      edgesDataset.remove(removedEdges);
      console.log('[syncGraph] Removed edges:', removedEdges);
    }
    const placeholderEdges = Array.from(edgeMap.keys()).map((id) => {
      const [src, dst, type] = id.split("-");
      return { id: `placeholder-${src}-${dst}-${type}`, from: src, to: dst };
    });
    if (placeholderEdges.length > 0) {
      console.warn('[syncGraph] Skipped placeholder edges due to zero confidence:', placeholderEdges);
    }
    if (edgesWithMissingEndpoints > 0) {
      noticeList.push(`${edgesWithMissingEndpoints} links reference nodes that were not provided; placeholders are shown.`);
    }
    setGraphStats({ nodeCount: knownNodes.size, edgeCount: edgeItems.length, missingEndpoints: placeholderNodes.size });
    setNotices(noticeList);
    const network = networkRef.current;
    if (network) {
      console.log('[syncGraph] Network instance exists, updating view');
      const hasNodes = combinedNodes.length > 0;
      if (!hasNodes) {
        network.fit();
        viewRef.current = {
          scale: network.getScale(),
          position: network.getViewPosition(),
        };
      } else if (autoFitRef.current || !viewRef.current) {
        network.fit();
        viewRef.current = {
          scale: network.getScale(),
          position: network.getViewPosition(),
        };
        autoFitRef.current = false;
      } else {
        network.moveTo({
          position: viewRef.current.position,
          scale: viewRef.current.scale,
          animation: false,
        });
      }
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
    const network = new Network(
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
    networkRef.current = network;
    const captureView = () => {
      if (!networkRef.current) return;
      viewRef.current = {
        scale: networkRef.current.getScale(),
        position: networkRef.current.getViewPosition(),
      };
    };
    const handleZoom = () => {
      captureView();
      autoFitRef.current = false;
    };
    const handleDragEnd = () => {
      captureView();
    };
    network.on("zoom", handleZoom);
    network.on("dragEnd", handleDragEnd);
    captureView();
    console.log('[Network Effect] Network created:', networkRef.current);
    return () => {
      console.log('[Network Effect] Cleanup');
      network.off("zoom", handleZoom);
      network.off("dragEnd", handleDragEnd);
      networkRef.current?.destroy();
      nodesRef.current.clear();
      edgesRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!apiBase) {
      console.log('[API Effect] No API base configured');
      setNotices(["API base URL is not configured; graph cannot load."]);
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
        setNotices(["Failed to load initial graph from API. Check state-server availability."]);
      }
    };
    load();
  }, [syncGraph]);

  useEffect(() => {
    if (!wsBase) {
      console.log('[WS Effect] No WebSocket base configured');
      setStatus("ws disabled");
      setNotices((prev) => [...prev, "WebSocket base URL missing; live updates disabled."]);
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
      setNotices((prev) => [...prev, "WebSocket error; streaming updates unavailable."]);
    };
    socket.onclose = (event) => {
      console.log('[WS] Disconnected', event);
      setStatus("disconnected");
      setNotices((prev) => [...prev, "WebSocket disconnected; reconnecting automatically." ]);
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
        setNotices((prev) => [...prev, "Received malformed update from state server."]);
      }
    };
    return () => {
      console.log('[WS Effect] Cleanup, closing socket');
      socket.close();
    };
  }, [syncGraph]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (!updatedAt || updatedAt === "-") {
        setStaleNotice("Graph has not received any updates yet.");
        return;
      }
      const updatedTime = Date.parse(updatedAt);
      if (Number.isNaN(updatedTime)) {
        setStaleNotice(null);
        return;
      }
      const ageMs = Date.now() - updatedTime;
      if (ageMs > 120000) {
        setStaleNotice("Graph is stale (no updates for over 2 minutes). Check discovery services.");
      } else if (ageMs > 30000) {
        setStaleNotice(`No graph updates for ${(ageMs / 1000).toFixed(0)} seconds.`);
      } else {
        setStaleNotice(null);
      }
    }, 5000);
    return () => window.clearInterval(interval);
  }, [updatedAt]);

  const combinedNotices = useMemo(() => {
    const messages = new Set(notices);
    if (staleNotice) {
      messages.add(staleNotice);
    }
    return Array.from(messages);
  }, [notices, staleNotice]);

  return (
    <div className="app">
      <div className="toolbar">
        <span className={statusClass}>{status}</span>
        <div className="toolbar-meta">
          <span>{updatedAt !== "-" ? new Date(updatedAt).toLocaleString() : "--"}</span>
          <span>
            Nodes: {graphStats.nodeCount} · Links: {graphStats.edgeCount}
            {graphStats.missingEndpoints > 0 ? ` · Placeholders: ${graphStats.missingEndpoints}` : ""}
          </span>
        </div>
      </div>
      {combinedNotices.length > 0 ? (
        <div className="notices">
          <ul>
            {combinedNotices.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="content">
        <div className="graph" ref={containerRef} />
        <div className="info">
          <h2>Rationale</h2>
          <p>{rationale || "Awaiting model output"}</p>
          <div className="stats">
            <h3>Graph Details</h3>
            <ul>
              <li>Nodes: {graphStats.nodeCount}</li>
              <li>Links: {graphStats.edgeCount}</li>
              <li>Placeholder nodes: {graphStats.missingEndpoints}</li>
            </ul>
          </div>
          {warnings.length > 0 ? (
            <div className="warning-list">
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
