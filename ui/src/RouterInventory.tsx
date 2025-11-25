import { useEffect, useState } from "react";

interface Router {
  id: number;
  ip_address: string;
  hostname: string | null;
  vendor: string | null;
  model: string | null;
  discovered_via: string;
  created_at: string;
}

interface Route {
  id: number;
  destination: string;
  netmask: string;
  next_hop: string | null;
  protocol: string | null;
  router_id: number;
}

interface Network {
  id: number;
  network: string;
  interface: string;
  is_connected: boolean;
  router_id: number;
}

interface RouterDetail {
  router: Router;
  routes: Route[];
  networks: Network[];
}

interface RouterInventoryProps {
  apiBase: string;
  onBack: () => void;
}

function RouterInventory({ apiBase, onBack }: RouterInventoryProps) {
  const [routers, setRouters] = useState<Router[]>([]);
  const [selectedRouter, setSelectedRouter] = useState<Router | null>(null);
  const [routerDetail, setRouterDetail] = useState<RouterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadRouters = async () => {
    try {
      setRefreshing(true);
      const response = await fetch(`${apiBase}/api/v1/routers`);
      if (!response.ok) {
        throw new Error("Failed to fetch routers");
      }
      const data = await response.json();
      setRouters(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadRouterDetail = async (router: Router) => {
    try {
      setDetailLoading(true);
      setDetailError(null);
      
      // Get routes for this router
      const routesResponse = await fetch(`${apiBase}/api/v1/routers/${router.id}/routes`);
      if (!routesResponse.ok) {
        throw new Error("Failed to fetch routes");
      }
      const routes = await routesResponse.json();
      
      // Get networks for this router  
      const networksResponse = await fetch(`${apiBase}/api/v1/routers/${router.id}/networks`);
      if (!networksResponse.ok) {
        throw new Error("Failed to fetch networks");
      }
      const networks = await networksResponse.json();
      
      setRouterDetail({
        router,
        routes,
        networks
      });
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadRouters();
  }, [apiBase]);

  const handleRouterClick = (router: Router) => {
    if (selectedRouter?.id === router.id) {
      setSelectedRouter(null);
      setRouterDetail(null);
    } else {
      setSelectedRouter(router);
      loadRouterDetail(router);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const getVendorColor = (vendor: string | null) => {
    if (!vendor) return "#6b7280";
    switch (vendor.toLowerCase()) {
      case 'cisco': return '#10b981';
      case 'juniper': return '#3b82f6';
      case 'arista': return '#f59e0b';
      default: return '#8b5cf6';
    }
  };

  const getDiscoveryColor = (discoveredVia: string) => {
    switch (discoveredVia.toLowerCase()) {
      case 'cli': return '#10b981';
      case 'snmp': return '#3b82f6';
      default: return '#6b7280';
    }
  };

  const uniqueNextHops = routerDetail?.routes
    ? Array.from(new Set(routerDetail.routes.map(r => r.next_hop).filter(nh => nh !== null)))
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
            onClick={loadRouters}
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
          Router Inventory ({routers.length})
        </h1>
        <div style={{ width: "180px" }}></div>
      </div>

      {loading && <div style={{ textAlign: "center", padding: "2rem", color: "#6b7280" }}>Loading routers...</div>}
      
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

      {!loading && !error && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.5rem", height: "calc(100vh - 200px)" }}>
          {/* Router List */}
          <div style={{ 
            border: "1px solid #e5e7eb", 
            borderRadius: "0.5rem", 
            overflow: "hidden",
            backgroundColor: "white"
          }}>
            <div style={{ 
              padding: "1rem", 
              backgroundColor: "#f9fafb", 
              borderBottom: "1px solid #e5e7eb",
              fontWeight: "600",
              color: "#374151"
            }}>
              Discovered Routers
            </div>
            <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 280px)" }}>
              {routers.map((router) => (
                <div
                  key={router.id}
                  onClick={() => handleRouterClick(router)}
                  style={{
                    padding: "1rem",
                    borderBottom: "1px solid #f3f4f6",
                    cursor: "pointer",
                    backgroundColor: selectedRouter?.id === router.id ? "#eff6ff" : "white",
                    borderLeft: selectedRouter?.id === router.id ? "4px solid #3b82f6" : "4px solid transparent",
                    transition: "all 0.2s ease"
                  }}
                  onMouseEnter={(e) => {
                    if (selectedRouter?.id !== router.id) {
                      e.currentTarget.style.backgroundColor = "#f9fafb";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedRouter?.id !== router.id) {
                      e.currentTarget.style.backgroundColor = "white";
                    }
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <div style={{ fontWeight: "600", fontFamily: "monospace", fontSize: "0.95rem" }}>
                      {router.ip_address}
                    </div>
                    <div style={{ 
                      padding: "0.25rem 0.5rem", 
                      backgroundColor: getDiscoveryColor(router.discovered_via),
                      color: "white",
                      borderRadius: "0.25rem",
                      fontSize: "0.75rem",
                      fontWeight: "500",
                      textTransform: "uppercase"
                    }}>
                      {router.discovered_via}
                    </div>
                  </div>
                  <div style={{ fontSize: "0.875rem", color: "#6b7280", marginBottom: "0.25rem" }}>
                    {router.hostname || "Unknown hostname"}
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    {router.vendor && (
                      <span style={{
                        padding: "0.125rem 0.5rem",
                        backgroundColor: getVendorColor(router.vendor),
                        color: "white",
                        borderRadius: "0.25rem",
                        fontSize: "0.75rem",
                        fontWeight: "500"
                      }}>
                        {router.vendor}
                      </span>
                    )}
                    {router.model && (
                      <span style={{
                        fontSize: "0.75rem",
                        color: "#6b7280",
                        fontFamily: "monospace"
                      }}>
                        {router.model}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "0.5rem" }}>
                    Discovered: {formatDate(router.created_at)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Router Details */}
          <div style={{ 
            border: "1px solid #e5e7eb", 
            borderRadius: "0.5rem", 
            overflow: "hidden",
            backgroundColor: "white"
          }}>
            {selectedRouter ? (
              <>
                <div style={{ 
                  padding: "1rem", 
                  backgroundColor: "#f9fafb", 
                  borderBottom: "1px solid #e5e7eb"
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: "1.125rem", fontWeight: "600", color: "#111827" }}>
                        Router Details
                      </h3>
                      <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.875rem", color: "#6b7280", fontFamily: "monospace" }}>
                        {selectedRouter.ip_address}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <span style={{
                        padding: "0.25rem 0.75rem",
                        backgroundColor: getDiscoveryColor(selectedRouter.discovered_via),
                        color: "white",
                        borderRadius: "0.375rem",
                        fontSize: "0.875rem",
                        fontWeight: "500"
                      }}>
                        {selectedRouter.discovered_via.toUpperCase()}
                      </span>
                    </div>
                  </div>
                </div>

                <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 280px)" }}>
                  {detailLoading && (
                    <div style={{ textAlign: "center", padding: "2rem", color: "#6b7280" }}>
                      Loading router details...
                    </div>
                  )}

                  {detailError && (
                    <div style={{ 
                      padding: "1rem", 
                      backgroundColor: "#fee", 
                      border: "1px solid #fcc", 
                      borderRadius: "0.375rem",
                      color: "#c00",
                      margin: "1rem"
                    }}>
                      <strong>Error:</strong> {detailError}
                    </div>
                  )}

                  {!detailLoading && !detailError && routerDetail && (
                    <div style={{ padding: "1rem" }}>
                      {/* Summary Cards */}
                      <div style={{ 
                        display: "grid", 
                        gridTemplateColumns: "repeat(3, 1fr)", 
                        gap: "1rem", 
                        marginBottom: "1.5rem" 
                      }}>
                        <div style={{ 
                          padding: "1rem", 
                          backgroundColor: "#f0f9ff", 
                          borderRadius: "0.5rem",
                          border: "1px solid #bfdbfe"
                        }}>
                          <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                            Networks
                          </div>
                          <div style={{ fontSize: "1.5rem", fontWeight: "700", color: "#1e40af" }}>
                            {routerDetail.networks.length}
                          </div>
                        </div>
                        <div style={{ 
                          padding: "1rem", 
                          backgroundColor: "#f0fdf4", 
                          borderRadius: "0.5rem",
                          border: "1px solid #bbf7d0"
                        }}>
                          <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                            Routes
                          </div>
                          <div style={{ fontSize: "1.5rem", fontWeight: "700", color: "#166534" }}>
                            {routerDetail.routes.length}
                          </div>
                        </div>
                        <div style={{ 
                          padding: "1rem", 
                          backgroundColor: "#fefce8", 
                          borderRadius: "0.5rem",
                          border: "1px solid #fef3c7"
                        }}>
                          <div style={{ fontSize: "0.75rem", color: "#6b7280", textTransform: "uppercase", fontWeight: "600", marginBottom: "0.25rem" }}>
                            Next Hops
                          </div>
                          <div style={{ fontSize: "1.5rem", fontWeight: "700", color: "#a16207" }}>
                            {uniqueNextHops.length}
                          </div>
                        </div>
                      </div>

                      {/* Networks */}
                      <div style={{ marginBottom: "2rem" }}>
                        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1rem", fontWeight: "600", color: "#374151" }}>
                          Connected Networks
                        </h4>
                        {routerDetail.networks.length > 0 ? (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                            {routerDetail.networks.map((network) => (
                              <div
                                key={network.id}
                                style={{
                                  padding: "0.5rem 0.75rem",
                                  backgroundColor: network.is_connected ? "#ecfdf5" : "#f3f4f6",
                                  border: network.is_connected ? "1px solid #a7f3d0" : "1px solid #d1d5db",
                                  borderRadius: "0.375rem",
                                  fontFamily: "monospace",
                                  fontSize: "0.875rem",
                                  color: network.is_connected ? "#065f46" : "#374151"
                                }}
                              >
                                <div style={{ fontWeight: "600" }}>{network.network}</div>
                                <div style={{ fontSize: "0.75rem", color: network.is_connected ? "#047857" : "#6b7280" }}>
                                  {network.interface} {network.is_connected ? "• Connected" : "• Not Connected"}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ padding: "1rem", color: "#6b7280", fontStyle: "italic" }}>
                            No networks discovered
                          </div>
                        )}
                      </div>

                      {/* Routes */}
                      <div>
                        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1rem", fontWeight: "600", color: "#374151" }}>
                          Routing Table
                        </h4>
                        {routerDetail.routes.length > 0 ? (
                          <div style={{ 
                            border: "1px solid #e5e7eb", 
                            borderRadius: "0.5rem", 
                            overflow: "hidden"
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
                                {routerDetail.routes.map((route, idx) => (
                                  <tr 
                                    key={route.id}
                                    style={{ 
                                      borderBottom: idx < routerDetail.routes.length - 1 ? "1px solid #f3f4f6" : "none",
                                      backgroundColor: idx % 2 === 0 ? "white" : "#fafafa"
                                    }}
                                  >
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
                        ) : (
                          <div style={{ padding: "1rem", color: "#6b7280", fontStyle: "italic" }}>
                            No routes discovered
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div style={{ 
                display: "flex", 
                alignItems: "center", 
                justifyContent: "center", 
                height: "100%",
                color: "#6b7280",
                textAlign: "center"
              }}>
                <div>
                  <div style={{ fontSize: "1.125rem", fontWeight: "500", marginBottom: "0.5rem" }}>
                    Select a Router
                  </div>
                  <div style={{ fontSize: "0.875rem" }}>
                    Click on a router from the list to view its details, networks, and routing table
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RouterInventory;
