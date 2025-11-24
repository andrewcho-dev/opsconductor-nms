import { useEffect, useState } from "react";

interface Route {
  destination: string;
  netmask: string;
  next_hop: string | null;
  protocol: string | null;
}

interface RoutingData {
  device_ip: string;
  hostname: string | null;
  total_routes: number;
  routes: Route[];
}

interface RoutingTableProps {
  apiBase: string;
  onBack: () => void;
}

function RoutingTable({ apiBase, onBack }: RoutingTableProps) {
  const [data, setData] = useState<RoutingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadRoutingTable = async () => {
    try {
      setRefreshing(true);
      const response = await fetch(`${apiBase}/api/routing/10.120.0.1`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch routing table");
      }
      const routingData = await response.json();
      setData(routingData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadRoutingTable();
  }, [apiBase]);

  const uniqueNextHops = data?.routes
    ? Array.from(new Set(data.routes.map(r => r.next_hop).filter(nh => nh !== null)))
    : [];

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <button
            onClick={onBack}
            style={{
              padding: "0.5rem 1rem",
              marginRight: "1rem",
              backgroundColor: "#6b7280",
              color: "white",
              border: "none",
              borderRadius: "0.375rem",
              cursor: "pointer",
              fontSize: "0.875rem",
              fontWeight: "500",
            }}
          >
            ← Back
          </button>
          <button
            onClick={loadRoutingTable}
            disabled={refreshing}
            style={{
              padding: "0.5rem 1rem",
              backgroundColor: refreshing ? "#9ca3af" : "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: "0.375rem",
              cursor: refreshing ? "not-allowed" : "pointer",
              fontSize: "0.875rem",
              fontWeight: "500",
            }}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <h1 style={{ margin: 0, fontSize: "1.5rem", fontWeight: "600" }}>
          Routing Table - 10.120.0.1
        </h1>
        <div style={{ width: "180px" }}></div>
      </div>

      {loading && <div style={{ textAlign: "center", padding: "2rem", color: "#6b7280" }}>Loading routing table...</div>}
      
      {error && (
        <div style={{ 
          padding: "1rem", 
          backgroundColor: "#fee", 
          border: "1px solid #fcc", 
          borderRadius: "0.375rem",
          color: "#c00",
          marginBottom: "1rem"
        }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {data && (
        <>
          <div style={{ 
            marginBottom: "1.5rem", 
            padding: "1rem", 
            backgroundColor: "#f9fafb", 
            borderRadius: "0.5rem",
            border: "1px solid #e5e7eb"
          }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem" }}>
              <div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                  Device IP
                </div>
                <div style={{ fontSize: "1rem", fontWeight: "500" }}>{data.device_ip}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                  Hostname
                </div>
                <div style={{ fontSize: "1rem", fontWeight: "500" }}>{data.hostname || "N/A"}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                  Total Routes
                </div>
                <div style={{ fontSize: "1rem", fontWeight: "500" }}>{data.total_routes}</div>
              </div>
            </div>
          </div>

          <div style={{ 
            marginBottom: "1.5rem", 
            padding: "1rem", 
            backgroundColor: "#f0f9ff", 
            borderRadius: "0.5rem",
            border: "1px solid #bfdbfe"
          }}>
            <div style={{ fontSize: "0.875rem", fontWeight: "600", color: "#1e40af", marginBottom: "0.5rem" }}>
              Next Hops Found ({uniqueNextHops.length})
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {uniqueNextHops.length > 0 ? (
                uniqueNextHops.map((nh, idx) => (
                  <span 
                    key={idx}
                    style={{
                      padding: "0.25rem 0.75rem",
                      backgroundColor: "#dbeafe",
                      border: "1px solid #93c5fd",
                      borderRadius: "0.375rem",
                      fontSize: "0.875rem",
                      fontFamily: "monospace",
                      color: "#1e40af"
                    }}
                  >
                    {nh}
                  </span>
                ))
              ) : (
                <span style={{ color: "#6b7280", fontSize: "0.875rem" }}>No next hops found</span>
              )}
            </div>
          </div>

          <div style={{ 
            border: "1px solid #e5e7eb", 
            borderRadius: "0.5rem", 
            overflow: "hidden",
            backgroundColor: "white"
          }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead style={{ backgroundColor: "#f9fafb" }}>
                <tr>
                  <th style={{ 
                    padding: "0.75rem 1rem", 
                    textAlign: "left", 
                    fontSize: "0.75rem", 
                    fontWeight: "600", 
                    color: "#374151",
                    textTransform: "uppercase",
                    borderBottom: "2px solid #e5e7eb"
                  }}>
                    #
                  </th>
                  <th style={{ 
                    padding: "0.75rem 1rem", 
                    textAlign: "left", 
                    fontSize: "0.75rem", 
                    fontWeight: "600", 
                    color: "#374151",
                    textTransform: "uppercase",
                    borderBottom: "2px solid #e5e7eb"
                  }}>
                    Destination
                  </th>
                  <th style={{ 
                    padding: "0.75rem 1rem", 
                    textAlign: "left", 
                    fontSize: "0.75rem", 
                    fontWeight: "600", 
                    color: "#374151",
                    textTransform: "uppercase",
                    borderBottom: "2px solid #e5e7eb"
                  }}>
                    Netmask
                  </th>
                  <th style={{ 
                    padding: "0.75rem 1rem", 
                    textAlign: "left", 
                    fontSize: "0.75rem", 
                    fontWeight: "600", 
                    color: "#374151",
                    textTransform: "uppercase",
                    borderBottom: "2px solid #e5e7eb"
                  }}>
                    Next Hop
                  </th>
                  <th style={{ 
                    padding: "0.75rem 1rem", 
                    textAlign: "left", 
                    fontSize: "0.75rem", 
                    fontWeight: "600", 
                    color: "#374151",
                    textTransform: "uppercase",
                    borderBottom: "2px solid #e5e7eb"
                  }}>
                    Protocol
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.routes.map((route, idx) => (
                  <tr 
                    key={idx}
                    style={{ 
                      borderBottom: idx < data.routes.length - 1 ? "1px solid #f3f4f6" : "none",
                      backgroundColor: idx % 2 === 0 ? "white" : "#fafafa"
                    }}
                  >
                    <td style={{ padding: "0.75rem 1rem", color: "#6b7280", fontSize: "0.875rem" }}>
                      {idx + 1}
                    </td>
                    <td style={{ padding: "0.75rem 1rem", fontFamily: "monospace", fontSize: "0.875rem" }}>
                      {route.destination}
                    </td>
                    <td style={{ padding: "0.75rem 1rem", fontFamily: "monospace", fontSize: "0.875rem" }}>
                      {route.netmask}
                    </td>
                    <td style={{ 
                      padding: "0.75rem 1rem", 
                      fontFamily: "monospace", 
                      fontSize: "0.875rem",
                      fontWeight: route.next_hop ? "500" : "normal",
                      color: route.next_hop ? "#1e40af" : "#9ca3af"
                    }}>
                      {route.next_hop || "—"}
                    </td>
                    <td style={{ padding: "0.75rem 1rem", fontSize: "0.875rem", color: "#6b7280" }}>
                      {route.protocol || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default RoutingTable;
