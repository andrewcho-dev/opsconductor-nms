import { useState, useEffect } from "react";

interface DiscoveryRun {
  id: number;
  status: string;
  root_ip: string;
  snmp_community: string;
  snmp_version: string;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
}

interface RouterNode {
  id: number;
  ip: string;
  hostname: string | null;
  is_router: boolean;
  router_score: number;
  classification_reason: string;
  vendor: string | null;
  model: string | null;
}

interface TopologyEdge {
  from_id: number;
  to_id: number;
  reason: string;
}

interface Topology {
  nodes: RouterNode[];
  edges: TopologyEdge[];
}

export default function DiscoveryPage({
  apiBase,
  onBack,
}: {
  apiBase: string;
  onBack: () => void;
}) {
  const [rootIp, setRootIp] = useState("");
  const [snmpCommunity, setSnmpCommunity] = useState("public");
  const [snmpVersion, setSnmpVersion] = useState("2c");
  const [loading, setLoading] = useState(false);
  const [currentRun, setCurrentRun] = useState<DiscoveryRun | null>(null);
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll for run status
  useEffect(() => {
    if (!currentRun || !["RUNNING", "PENDING"].includes(currentRun.status)) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/router-discovery/runs/${currentRun.id}/state`
        );
        if (response.ok) {
          const run: DiscoveryRun = await response.json();
          setCurrentRun(run);

          // If completed, fetch topology
          if (run.status === "COMPLETED") {
            const topoResponse = await fetch(
              `${apiBase}/api/router-discovery/runs/${currentRun.id}/topology`
            );
            if (topoResponse.ok) {
              const topo: Topology = await topoResponse.json();
              setTopology(topo);
            }
          }
        }
      } catch (err) {
        console.error("Failed to poll run status:", err);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [currentRun, apiBase]);

  const handleStartDiscovery = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(
        `${apiBase}/api/router-discovery/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            root_ip: rootIp,
            snmp_community: snmpCommunity,
            snmp_version: snmpVersion,
          }),
        }
      );

      if (response.ok) {
        const data = await response.json();
        const runResponse = await fetch(
          `${apiBase}/api/router-discovery/runs/${data.run_id}/state`
        );
        if (runResponse.ok) {
          setCurrentRun(await runResponse.json());
          setTopology(null);
        }
      } else {
        const error = await response.json();
        setError(error.detail || "Failed to start discovery");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="discovery-page">
      <div className="page-header">
        <h1>Router Discovery</h1>
        <button className="back-button" onClick={onBack}>
          ← Back
        </button>
      </div>

      <div className="discovery-container">
        {/* Form Section */}
        <div className="form-section">
          <h2>Start Discovery</h2>
          <form onSubmit={handleStartDiscovery}>
            <div className="form-group">
              <label htmlFor="root_ip">Gateway Router IP</label>
              <input
                id="root_ip"
                type="text"
                placeholder="e.g., 10.0.0.1"
                value={rootIp}
                onChange={(e) => setRootIp(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="snmp_community">SNMP Community</label>
              <input
                id="snmp_community"
                type="text"
                placeholder="public"
                value={snmpCommunity}
                onChange={(e) => setSnmpCommunity(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="snmp_version">SNMP Version</label>
              <select
                id="snmp_version"
                value={snmpVersion}
                onChange={(e) => setSnmpVersion(e.target.value)}
              >
                <option value="2c">SNMPv2c</option>
                <option value="3">SNMPv3</option>
              </select>
            </div>

            {error && <div className="error-message">{error}</div>}

            <button
              type="submit"
              disabled={loading || !rootIp}
              className="submit-button"
            >
              {loading ? "Starting..." : "Start Discovery"}
            </button>
          </form>
        </div>

        {/* Status Section */}
        {currentRun && (
          <div className="status-section">
            <h2>Discovery Status</h2>
            <div className="status-info">
              <div className="status-item">
                <span className="label">Run ID:</span>
                <span>{currentRun.id}</span>
              </div>
              <div className="status-item">
                <span className="label">Status:</span>
                <span className={`status-badge ${currentRun.status}`}>
                  {currentRun.status}
                </span>
              </div>
              <div className="status-item">
                <span className="label">Root IP:</span>
                <span>{currentRun.root_ip}</span>
              </div>
              <div className="status-item">
                <span className="label">Started:</span>
                <span>{new Date(currentRun.started_at).toLocaleString()}</span>
              </div>
              {currentRun.finished_at && (
                <div className="status-item">
                  <span className="label">Finished:</span>
                  <span>
                    {new Date(currentRun.finished_at).toLocaleString()}
                  </span>
                </div>
              )}
              {currentRun.error_message && (
                <div className="status-item error">
                  <span className="label">Error:</span>
                  <span>{currentRun.error_message}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Topology Section */}
        {topology && (
          <div className="topology-section">
            <h2>Discovered Topology</h2>

            <div className="topology-stats">
              <div className="stat">
                <strong>{topology.nodes.length}</strong> Devices
              </div>
              <div className="stat">
                <strong>{topology.nodes.filter((n) => n.is_router).length}</strong>{" "}
                Routers
              </div>
              <div className="stat">
                <strong>{topology.edges.length}</strong> Connections
              </div>
            </div>

            {/* Nodes Table */}
            <div className="table-container">
              <h3>Discovered Devices</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>IP Address</th>
                    <th>Hostname</th>
                    <th>Type</th>
                    <th>Score</th>
                    <th>Vendor</th>
                    <th>Classification</th>
                  </tr>
                </thead>
                <tbody>
                  {topology.nodes.map((node) => (
                    <tr key={node.id}>
                      <td className="mono">{node.ip}</td>
                      <td>{node.hostname || "—"}</td>
                      <td>
                        <span
                          className={`device-type ${
                            node.is_router ? "router" : "other"
                          }`}
                        >
                          {node.is_router ? "Router" : "Other"}
                        </span>
                      </td>
                      <td>{node.router_score}</td>
                      <td>{node.vendor || "—"}</td>
                      <td className="small">{node.classification_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Edges Table */}
            <div className="table-container">
              <h3>Topology Connections</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>From Device</th>
                    <th>To Device</th>
                    <th>Connection Type</th>
                  </tr>
                </thead>
                <tbody>
                  {topology.edges.map((edge, idx) => {
                    const fromNode = topology.nodes.find((n) => n.id === edge.from_id);
                    const toNode = topology.nodes.find((n) => n.id === edge.to_id);
                    return (
                      <tr key={idx}>
                        <td className="mono">{fromNode?.ip || `Device ${edge.from_id}`}</td>
                        <td className="mono">{toNode?.ip || `Device ${edge.to_id}`}</td>
                        <td>{edge.reason}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
