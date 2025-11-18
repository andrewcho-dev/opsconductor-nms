import { useState, useEffect, useRef } from "react";
import { Network } from "vis-network";
import { DataSet } from "vis-data";

interface TopologyMapProps {
  apiBase: string;
  onBack: () => void;
}

interface Node {
  ip: string;
  hostname: string | null;
  device_type: string | null;
  network_role: string | null;
  vendor: string | null;
  chassis_id: string | null;
  system_name: string | null;
  kind: string | null;
}

interface Edge {
  from: string;
  to: string;
  label?: string;
  local_port: string;
  remote_port: string;
  remote_port_desc?: string;
}

interface TopologyData {
  nodes: Node[];
  edges: Edge[];
}

interface NeighborInfo {
  local_system: {
    chassis_id: string;
    system_name: string;
    system_description: string;
  };
  neighbors: Array<{
    local_port: string;
    remote_chassis_id: string;
    remote_port_id: string;
    remote_port_description: string;
    remote_system_name: string;
    remote_system_description: string;
    remote_ip: string | null;
  }>;
}

function TopologyMap({ apiBase, onBack }: TopologyMapProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [neighborInfo, setNeighborInfo] = useState<NeighborInfo | null>(null);
  const networkContainer = useRef<HTMLDivElement>(null);
  const networkInstance = useRef<Network | null>(null);

  useEffect(() => {
    fetchTopology();
  }, [apiBase]);

  const fetchTopology = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/topology/layer2`);
      if (!response.ok) {
        throw new Error(`Failed to fetch topology: ${response.statusText}`);
      }
      const data = await response.json();
      setTopology(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const fetchNeighborInfo = async (ip: string) => {
    try {
      const response = await fetch(`${apiBase}/api/inventory/${ip}/neighbors`);
      if (!response.ok) {
        throw new Error(`Failed to fetch neighbor info: ${response.statusText}`);
      }
      const data = await response.json();
      setNeighborInfo(data);
    } catch (err) {
      console.error("Error fetching neighbor info:", err);
      setNeighborInfo(null);
    }
  };

  useEffect(() => {
    if (!topology || !networkContainer.current) return;

    const getDeviceTier = (network_role: string | null, kind: string | null) => {
      const role = network_role || kind;
      if (!role) return "endpoint";
      const lower = role.toLowerCase();
      if (lower === "l3_router" || lower === "router" || lower === "gateway" || lower === "firewall") return "router";
      if (lower === "l2_switch" || lower === "switch") return "switch";
      return "endpoint";
    };

    const getTierConfig = (tier: string) => {
      switch (tier) {
        case "router":
          return {
            level: 0,
            shape: "diamond",
            size: 35,
            background: "#FF6B6B",
            border: "#D32F2F",
            fontSize: 14,
            bold: true
          };
        case "switch":
          return {
            level: 1,
            shape: "circle",
            size: 30,
            background: "#4CAF50",
            border: "#2E7D32",
            fontSize: 13,
            bold: true
          };
        case "endpoint":
          return {
            level: 2,
            shape: "box",
            size: 20,
            background: "#2196F3",
            border: "#1976D2",
            fontSize: 11,
            bold: false
          };
      }
    };

    const nodes = new DataSet(
      topology.nodes.map((node) => {
        const tier = getDeviceTier(node.network_role, node.kind || node.device_type);
        const config = getTierConfig(tier);
        return {
          id: node.ip,
          label: node.hostname || node.system_name || node.ip,
          title: `${node.ip}\n${node.device_type || 'Unknown'}\nRole: ${node.network_role || 'Unknown'}\n${node.vendor || ''}`,
          shape: config!.shape,
          size: config!.size,
          level: config!.level,
          color: {
            background: config!.background,
            border: config!.border,
            highlight: {
              background: "#FFC107",
              border: "#F57C00"
            }
          },
          font: {
            color: "#ffffff",
            size: config!.fontSize,
            bold: config!.bold
          }
        };
      })
    );

    const edges = new DataSet(
      topology.edges.map((edge, idx) => ({
        id: `edge-${idx}`,
        from: edge.from,
        to: edge.to,
        label: edge.label || "",
        color: {
          color: "#666666",
          highlight: "#FFC107"
        },
        width: 2,
        smooth: {
          type: "continuous"
        }
      }))
    );

    const options = {
      layout: {
        hierarchical: {
          enabled: true,
          direction: "UD",
          sortMethod: "directed",
          levelSeparation: 300,
          nodeSpacing: 150,
          blockShifting: true,
          edgeMinimization: true
        }
      },
      nodes: {
        borderWidth: 2,
        borderWidthSelected: 3,
        shadow: {
          enabled: true,
          color: "rgba(0,0,0,0.2)",
          size: 5,
          x: 2,
          y: 2
        }
      },
      edges: {
        font: {
          size: 11,
          color: "#333333",
          background: "#ffffff",
          strokeWidth: 0
        },
        arrows: {
          to: {
            enabled: false
          }
        },
        smooth: {
          enabled: true,
          type: "cubicBezier",
          roundness: 0.5
        }
      },
      physics: {
        enabled: false
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
        dragView: true
      }
    };

    networkInstance.current = new Network(
      networkContainer.current,
      { nodes, edges },
      options
    );

    networkInstance.current.on("selectNode", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        setSelectedNode(nodeId);
        fetchNeighborInfo(nodeId);
      }
    });

    networkInstance.current.on("deselectNode", () => {
      setSelectedNode(null);
      setNeighborInfo(null);
    });

    return () => {
      if (networkInstance.current) {
        networkInstance.current.destroy();
      }
    };
  }, [topology]);

  return (
    <div className="topology-container">
      <div className="topology-header">
        <h1>Layer 2 Network Topology</h1>
        <div className="topology-actions">
          <button onClick={fetchTopology} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
          <button onClick={onBack}>Back to Inventory</button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="topology-main">
        <div className="topology-graph" ref={networkContainer} />
        
        {selectedNode && neighborInfo && (
          <div className="topology-sidebar">
            <h2>Device Details</h2>
            <div className="device-info">
              <h3>Local System</h3>
              <p><strong>IP:</strong> {selectedNode}</p>
              <p><strong>Chassis ID:</strong> {neighborInfo.local_system.chassis_id}</p>
              <p><strong>System Name:</strong> {neighborInfo.local_system.system_name}</p>
              <p><strong>Description:</strong> {neighborInfo.local_system.system_description}</p>
            </div>

            {neighborInfo.neighbors.length > 0 && (
              <div className="neighbors-info">
                <h3>LLDP Neighbors ({neighborInfo.neighbors.length})</h3>
                {neighborInfo.neighbors.map((neighbor, idx) => (
                  <div key={idx} className="neighbor-card">
                    <p><strong>Local Port:</strong> {neighbor.local_port}</p>
                    <p><strong>Remote Device:</strong> {neighbor.remote_system_name || "Unknown"}</p>
                    <p><strong>Remote Port:</strong> {neighbor.remote_port_id}</p>
                    {neighbor.remote_port_description && (
                      <p><strong>Port Desc:</strong> {neighbor.remote_port_description}</p>
                    )}
                    <p><strong>Chassis ID:</strong> {neighbor.remote_chassis_id}</p>
                    {neighbor.remote_ip && (
                      <p><strong>Remote IP:</strong> {neighbor.remote_ip}</p>
                    )}
                    <p className="description">{neighbor.remote_system_description}</p>
                  </div>
                ))}
              </div>
            )}

            {neighborInfo.neighbors.length === 0 && (
              <div className="no-neighbors">
                <p>No LLDP neighbors detected on this device.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {topology && (
        <div className="topology-stats">
          <span>{topology.nodes.length} devices</span>
          <span>{topology.edges.length} connections</span>
        </div>
      )}
    </div>
  );
}

export default TopologyMap;
