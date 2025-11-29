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

interface Router {
  id: number;
  ip_address: string;
  hostname: string | null;
  vendor: string | null;
  model: string | null;
  discovered_via: string;
  created_at: string;
}

interface RoutingTableProps {
  apiBase: string;
  selectedRouterId?: number | null;
}

function RoutingTable({ apiBase, selectedRouterId: propSelectedRouterId }: RoutingTableProps) {
  const [data, setData] = useState<RoutingData | null>(null);
  const [routers, setRouters] = useState<Router[]>([]);
  const [selectedRouterId, setSelectedRouterId] = useState<number | null>(propSelectedRouterId || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadRouters = async () => {
    try {
      const response = await fetch(`${apiBase}/api/v1/routers`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to fetch routers");
      }
      const routerData = await response.json();
      setRouters(routerData);
      
      // Auto-select first router if none selected
      if (routerData.length > 0 && !selectedRouterId) {
        setSelectedRouterId(routerData[0].id);
      }
    } catch (err) {
      console.error("Error in loadRouters:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  };

  const loadRoutingTable = async () => {
    if (!selectedRouterId) return;
    
    try {
      setRefreshing(true);
      
      // Get routes first
      const response = await fetch(`${apiBase}/api/v1/routers/${selectedRouterId}/routes`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to fetch routing table");
      }
      const routes = await response.json();
      
      // Get router details with separate error handling
      let router = null;
      try {
        const routerResponse = await fetch(`${apiBase}/api/v1/routers/${selectedRouterId}`);
        if (routerResponse.ok) {
          router = await routerResponse.json();
        }
      } catch (routerErr) {
        console.warn("Failed to fetch router details, using fallback:", routerErr);
        router = {
          ip_address: `Router ${selectedRouterId}`,
          hostname: "Unknown"
        };
      }
      
      const routingData: RoutingData = {
        device_ip: router?.ip_address || `Router ${selectedRouterId}`,
        hostname: router?.hostname || "Unknown",
        total_routes: routes.length,
        routes: routes
      };
      
      setData(routingData);
      setError(null);
    } catch (err) {
      console.error("Error in loadRoutingTable:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadRouters();
  }, [apiBase]);

  useEffect(() => {
    // Update selected router ID when prop changes
    if (propSelectedRouterId !== undefined && propSelectedRouterId !== selectedRouterId) {
      setSelectedRouterId(propSelectedRouterId);
    }
  }, [propSelectedRouterId, selectedRouterId]);

  useEffect(() => {
    if (selectedRouterId) {
      loadRoutingTable();
    }
  }, [selectedRouterId, apiBase]);

  const uniqueNextHops = data?.routes
    ? Array.from(new Set(data.routes.map(r => r.next_hop).filter(nh => nh !== null)))
    : [];

  const selectedRouter = routers.find(r => r.id === selectedRouterId);

  return (
    <div className="inventory-container">
      <div className="inventory-header">
        <h2 style={{ margin: 0, color: "#0f172a", fontSize: "1.125rem" }}>
          Routes
        </h2>
        <div className="inventory-filters">
          <select
            value={selectedRouterId || ""}
            onChange={(e) => setSelectedRouterId(e.target.value ? parseInt(e.target.value) : null)}
            style={{
              width: "100%",
              padding: "0.375rem 0.5rem",
              fontSize: "0.875rem",
              border: "1px solid #d1d5db",
              borderRadius: "0.375rem"
            }}
          >
            <option value="">Select a router</option>
            {routers.map((router) => (
              <option key={router.id} value={router.id}>
                {router.hostname || router.ip_address}
              </option>
            ))}
          </select>
          <button 
            onClick={loadRoutingTable}
            disabled={refreshing}
            className="refresh-btn"
          >
            {refreshing ? "Refreshing..." : "↻ Refresh"}
          </button>
        </div>
      </div>

      {loading && <div className="inventory-loading">Loading routing table...</div>}
      
      {error && (
        <div className="inventory-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {data && selectedRouter && (
        <>
          <div style={{ 
            marginBottom: "1.5rem", 
            padding: "1rem", 
            backgroundColor: "#f9fafb", 
            borderRadius: "0.5rem",
            border: "1px solid #e5e7eb"
          }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem" }}>
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
              <div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                  Discovery Method
                </div>
                <div style={{ 
                  fontSize: "0.875rem", 
                  fontWeight: "500", 
                  padding: "0.125rem 0.5rem",
                  backgroundColor: selectedRouter.discovered_via === 'cli' ? '#dcfce7' : '#dbeafe',
                  color: selectedRouter.discovered_via === 'cli' ? '#166534' : '#1e40af',
                  borderRadius: '0.25rem',
                  display: 'inline-block'
                }}>
                  {selectedRouter.discovered_via.toUpperCase()}
                </div>
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

          <div className="inventory-grid-wrapper">
            <table className="inventory-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Destination</th>
                  <th>Netmask</th>
                  <th>Next Hop</th>
                  <th>Protocol</th>
                </tr>
              </thead>
              <tbody>
                {data.routes.map((route, idx) => (
                  <tr key={idx}>
                    <td>{idx + 1}</td>
                    <td>{route.destination}</td>
                    <td>{route.netmask}</td>
                    <td>{route.next_hop || "—"}</td>
                    <td>{route.protocol || "—"}</td>
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
