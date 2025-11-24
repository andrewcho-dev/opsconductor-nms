import { useState, useEffect, FormEvent, ChangeEvent } from "react";

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

interface RouterRouteInfo {
  cidr: string;
  network: string;
  netmask: string;
  prefix_len: number;
  next_hop: string | null;
  protocol: string | null;
}

interface RouterDetail {
  id: number;
  ip: string;
  hostname: string | null;
  is_router: boolean;
  router_score: number;
  classification_reason: string;
  vendor: string | null;
  model: string | null;
  networks: string[];
  routes: RouterRouteInfo[];
}

interface Topology {
  nodes: RouterNode[];
  edges: TopologyEdge[];
}

interface CredentialPair {
  username: string;
  password: string;
  vrf?: string | null;
}

export default function DiscoveryPage({
  apiBase,
  onBack,
}: {
  apiBase: string;
  onBack: () => void;
}) {
  const discoveryBase = apiBase.replace(':8080', ':8200');
  const [rootIp, setRootIp] = useState("");
  const [snmpCommunity, setSnmpCommunity] = useState("public");
  const [snmpVersion, setSnmpVersion] = useState("2c");
  const [loading, setLoading] = useState(false);
  const [currentRun, setCurrentRun] = useState<DiscoveryRun | null>(null);
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRouterId, setSelectedRouterId] = useState<number | null>(null);
  const [routerDetail, setRouterDetail] = useState<RouterDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showCliModal, setShowCliModal] = useState(false);
  const [cliUsername, setCliUsername] = useState("");
  const [cliPassword, setCliPassword] = useState("");
  const [cliVrf, setCliVrf] = useState("");
  const [cliLoading, setCliLoading] = useState(false);
  const [cliError, setCliError] = useState<string | null>(null);
  const [defaultCliCredentials, setDefaultCliCredentials] = useState<CredentialPair[]>([]);
  const [useCustomCliCredentials, setUseCustomCliCredentials] = useState(false);
  const [customCliCredentials, setCustomCliCredentials] = useState<CredentialPair[]>([
    { username: "", password: "", vrf: "" },
  ]);
  const [cliDefaultsFetchError, setCliDefaultsFetchError] = useState<string | null>(null);
  const [cliDefaultsSaveError, setCliDefaultsSaveError] = useState<string | null>(null);
  const [cliDefaultsSaveSuccess, setCliDefaultsSaveSuccess] = useState<string | null>(null);
  const [isSavingCliDefaults, setIsSavingCliDefaults] = useState(false);

  // Poll for run status
  useEffect(() => {
    if (!currentRun || !["RUNNING", "PENDING"].includes(currentRun.status)) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const response = await fetch(
          `${discoveryBase}/api/router-discovery/runs/${currentRun.id}/state`
        );
        if (response.ok) {
          const run: DiscoveryRun = await response.json();
          setCurrentRun(run);

          // If completed, fetch topology
          if (run.status === "COMPLETED") {
            const topoResponse = await fetch(
              `${discoveryBase}/api/router-discovery/runs/${currentRun.id}/topology`
            );
            if (topoResponse.ok) {
              const topo: Topology = await topoResponse.json();
              setTopology(topo);
              setSelectedRouterId(null);
              setRouterDetail(null);
              setDetailError(null);
            }
          }
        }
      } catch (err) {
        console.error("Failed to poll run status:", err);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [currentRun, discoveryBase]);

  useEffect(() => {
    if (!selectedRouterId || !currentRun || currentRun.status !== "COMPLETED") {
      return;
    }
    let cancelled = false;
    const runId = currentRun.id;
    const controller = new AbortController();
    const fetchDetail = async () => {
      try {
        setDetailLoading(true);
        setDetailError(null);
        const response = await fetch(
          `${discoveryBase}/api/router-discovery/runs/${runId}/routers/${selectedRouterId}`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const detail: RouterDetail = await response.json();
        if (!cancelled) {
          setRouterDetail(detail);
        }
      } catch (err) {
        if (!cancelled) {
          setRouterDetail(null);
          setDetailError(
            err instanceof Error ? err.message : "Failed to load router detail"
          );
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };
    fetchDetail();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [selectedRouterId, currentRun, discoveryBase]);

  // On mount, load the most recent completed run so refreshes still show topology
  useEffect(() => {
    let cancelled = false;
    const fetchLatestRun = async () => {
      try {
        const runsResponse = await fetch(
          `${discoveryBase}/api/router-discovery/runs?status=COMPLETED&limit=1`
        );
        if (!runsResponse.ok) {
          return;
        }
        const runs = await runsResponse.json();
        if (!Array.isArray(runs) || runs.length === 0) {
          return;
        }
        const latestRun: DiscoveryRun = runs[0];
        if (cancelled) return;
        setCurrentRun(latestRun);
        if (latestRun.status === "COMPLETED") {
          const topoResponse = await fetch(
            `${discoveryBase}/api/router-discovery/runs/${latestRun.id}/topology`
          );
          if (cancelled || !topoResponse.ok) {
            return;
          }
          const topo: Topology = await topoResponse.json();
          setTopology(topo);
          setSelectedRouterId(null);
          setRouterDetail(null);
          setDetailError(null);
        }
      } catch (err) {
        console.error("Failed to load latest completed discovery run:", err);
      }
    };

    fetchLatestRun();
    return () => {
      cancelled = true;
    };
  }, [discoveryBase]);

  // Ensure topology is loaded when there is a completed run but no topology yet
  useEffect(() => {
    if (!currentRun || currentRun.status !== "COMPLETED" || topology) {
      return;
    }

    const fetchTopology = async () => {
      try {
        const topoResponse = await fetch(
          `${discoveryBase}/api/router-discovery/runs/${currentRun.id}/topology`
        );
        if (topoResponse.ok) {
          const topo: Topology = await topoResponse.json();
          console.log("[Discovery] Loaded topology for run", currentRun.id);
          setTopology(topo);
          setSelectedRouterId(null);
          setRouterDetail(null);
          setDetailError(null);
        }
      } catch (err) {
        console.error("Failed to fetch topology:", err);
      }
    };

    fetchTopology();
  }, [currentRun, discoveryBase, topology]);

  // Load default CLI credentials from backend
  useEffect(() => {
    let cancelled = false;
    const fetchDefaults = async () => {
      try {
        setCliDefaultsFetchError(null);
        const response = await fetch(`${discoveryBase}/api/router-discovery/default-cli-credentials`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data: CredentialPair[] = await response.json();
        if (!cancelled) {
          setDefaultCliCredentials(data.length > 0 ? data : [{ username: "", password: "", vrf: "" }]);
        }
      } catch (err) {
        if (!cancelled) {
          setCliDefaultsFetchError(err instanceof Error ? err.message : "Failed to load CLI defaults");
          setDefaultCliCredentials((prev) => prev.length > 0 ? prev : [{ username: "", password: "", vrf: "" }]);
        }
      }
    };
    fetchDefaults();
    return () => {
      cancelled = true;
    };
  }, [discoveryBase]);

  useEffect(() => {
    if (!cliDefaultsSaveSuccess) {
      return;
    }
    const timer = setTimeout(() => setCliDefaultsSaveSuccess(null), 3000);
    return () => clearTimeout(timer);
  }, [cliDefaultsSaveSuccess]);

  const handleToggleCustomCli = (checked: boolean) => {
    setUseCustomCliCredentials(checked);
    if (!checked) {
      setCustomCliCredentials([{ username: "", password: "", vrf: "" }]);
    }
  };

  const handleCustomCredentialChange = (index: number, field: keyof CredentialPair, value: string) => {
    setCustomCliCredentials((prev: CredentialPair[]) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        [field]: field === "vrf" ? value : value,
      } as CredentialPair;
      return next;
    });
  };

  const handleAddCustomCredential = () => {
    setCustomCliCredentials((prev: CredentialPair[]) => [...prev, { username: "", password: "", vrf: "" }]);
  };

  const handleRemoveCustomCredential = (index: number) => {
    setCustomCliCredentials((prev: CredentialPair[]) => prev.filter((_: CredentialPair, i: number) => i !== index));
  };

  const handleDefaultCredentialChange = (index: number, field: keyof CredentialPair, value: string) => {
    setDefaultCliCredentials((prev: CredentialPair[]) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        [field]: field === "vrf" ? value : value,
      } as CredentialPair;
      return next;
    });
  };

  const handleAddDefaultCredential = () => {
    setDefaultCliCredentials((prev: CredentialPair[]) => [...prev, { username: "", password: "", vrf: "" }]);
  };

  const handleRemoveDefaultCredential = (index: number) => {
    setDefaultCliCredentials((prev: CredentialPair[]) => prev.filter((_: CredentialPair, i: number) => i !== index));
  };

  const handleSaveDefaultCredentials = async () => {
    setCliDefaultsSaveError(null);
    setCliDefaultsSaveSuccess(null);
    const cleaned = defaultCliCredentials
      .map((cred: CredentialPair) => ({
        username: cred.username?.trim() ?? "",
        password: cred.password?.trim() ?? "",
        vrf: cred.vrf?.trim() ? cred.vrf.trim() : null,
      }))
      .filter((cred: CredentialPair) => cred.username && cred.password);

    if (cleaned.length === 0) {
      setCliDefaultsSaveError("Provide at least one credential with username and password.");
      return;
    }

    setIsSavingCliDefaults(true);
    try {
      const response = await fetch(`${discoveryBase}/api/router-discovery/default-cli-credentials`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credentials: cleaned }),
      });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || `HTTP ${response.status}`);
      }
      const updated: CredentialPair[] = await response.json();
      setDefaultCliCredentials(updated);
      setCliDefaultsSaveSuccess("Defaults saved");
    } catch (err) {
      setCliDefaultsSaveError(err instanceof Error ? err.message : "Failed to save CLI defaults");
    } finally {
      setIsSavingCliDefaults(false);
    }
  };

  const handleStartDiscovery = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const payload: Record<string, unknown> = {
        root_ip: rootIp,
        snmp_community: snmpCommunity,
        snmp_version: snmpVersion,
      };

      if (useCustomCliCredentials) {
        const cleanedCustom = customCliCredentials
          .map((cred: CredentialPair) => ({
            username: cred.username?.trim() ?? "",
            password: cred.password?.trim() ?? "",
            vrf: cred.vrf?.trim() ? cred.vrf.trim() : null,
          }))
          .filter((cred: CredentialPair) => cred.username && cred.password);

        if (cleanedCustom.length > 0) {
          payload.cli_default_credentials = cleanedCustom;
        }
      }

      const response = await fetch(
        `${discoveryBase}/api/router-discovery/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      if (response.ok) {
        const data = await response.json();
        const runResponse = await fetch(
          `${discoveryBase}/api/router-discovery/runs/${data.run_id}/state`
        );
        if (runResponse.ok) {
          const run: DiscoveryRun = await runResponse.json();
          setCurrentRun(run);
          setTopology(null);
          setSelectedRouterId(null);
          setRouterDetail(null);
          setDetailError(null);

          // If the run has already completed by the time we fetch its state,
          // immediately load topology so the UI populates without waiting for polling.
          if (run.status === "COMPLETED") {
            try {
              const topoResponse = await fetch(
                `${discoveryBase}/api/router-discovery/runs/${run.id}/topology`
              );
              if (topoResponse.ok) {
                const topo: Topology = await topoResponse.json();
                console.log("[Discovery] Loaded topology immediately after run", run.id);
                setTopology(topo);
                setSelectedRouterId(null);
                setRouterDetail(null);
                setDetailError(null);
              }
            } catch (err) {
              console.error("Failed to fetch topology after start:", err);
            }
          }
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

  const handleSelectRouter = (routerId: number) => {
    if (!currentRun || currentRun.status !== "COMPLETED") {
      return;
    }
    if (selectedRouterId === routerId) {
      setSelectedRouterId(null);
      setRouterDetail(null);
      setDetailError(null);
      return;
    }
    setSelectedRouterId(routerId);
  };

  const handleOpenCliModal = () => {
    if (!routerDetail) return;
    setCliUsername("");
    setCliPassword("");
    setCliVrf("");
    setCliError(null);
    setShowCliModal(true);
  };

  const handleSubmitCliRoutes = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentRun || !routerDetail) return;
    setCliLoading(true);
    setCliError(null);
    try {
      const response = await fetch(
        `${discoveryBase}/api/router-discovery/runs/${currentRun.id}/routers/${routerDetail.id}/cli-routes`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: cliUsername,
            password: cliPassword,
            vrf: cliVrf || null,
          }),
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      // Refresh router detail to show newly added routes
      setShowCliModal(false);
      setCliPassword("");
      // Trigger detail reload by re-setting selectedRouterId
      setSelectedRouterId(null);
      setRouterDetail(null);
      setDetailError(null);
      setSelectedRouterId(routerDetail.id);
    } catch (err) {
      setCliError(err instanceof Error ? err.message : "Failed to fetch routes via CLI");
    } finally {
      setCliLoading(false);
    }
  };

  const handlePause = async (runId: number) => {
    try {
      const response = await fetch(
        `${discoveryBase}/api/router-discovery/runs/${runId}/pause`,
        { method: "POST" }
      );
      if (response.ok) {
        const data = await response.json();
        setCurrentRun({ ...currentRun!, status: data.status });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to pause");
    }
  };

  const handleResume = async (runId: number) => {
    try {
      const response = await fetch(
        `${discoveryBase}/api/router-discovery/runs/${runId}/resume`,
        { method: "POST" }
      );
      if (response.ok) {
        const data = await response.json();
        setCurrentRun({ ...currentRun!, status: data.status });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume");
    }
  };

  const handleCancel = async (runId: number) => {
    if (!window.confirm("Are you sure you want to cancel this discovery?")) {
      return;
    }
    try {
      const response = await fetch(
        `${discoveryBase}/api/router-discovery/runs/${runId}/cancel`,
        { method: "POST" }
      );
      if (response.ok) {
        const data = await response.json();
        setCurrentRun({ ...currentRun!, status: data.status });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel");
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
                onChange={(e: ChangeEvent<HTMLInputElement>) => setRootIp(e.target.value)}
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
                onChange={(e: ChangeEvent<HTMLInputElement>) => setSnmpCommunity(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="snmp_version">SNMP Version</label>
              <select
                id="snmp_version"
                value={snmpVersion}
                onChange={(e: ChangeEvent<HTMLSelectElement>) => setSnmpVersion(e.target.value)}
              >
                <option value="2c">SNMPv2c</option>
                <option value="3">SNMPv3</option>
              </select>
            </div>

            <div className="form-group">
              <label>Default CLI Credentials</label>
              <p className="help-text">
                The discovery crawler will try SNMP first, then walk through this list over SSH/CLI.
              </p>
              {cliDefaultsFetchError && (
                <div className="error-message">{cliDefaultsFetchError}</div>
              )}
              <div className="credential-list">
                {defaultCliCredentials.map((cred: CredentialPair, idx: number) => (
                  <div key={`default-${idx}`} className="credential-row">
                    <input
                      type="text"
                      placeholder="username"
                      value={cred.username}
                      onChange={(e: ChangeEvent<HTMLInputElement>) =>
                        handleDefaultCredentialChange(idx, "username", e.target.value)
                      }
                    />
                    <input
                      type="text"
                      placeholder="password"
                      value={cred.password}
                      onChange={(e: ChangeEvent<HTMLInputElement>) =>
                        handleDefaultCredentialChange(idx, "password", e.target.value)
                      }
                    />
                    <input
                      type="text"
                      placeholder="VRF (optional)"
                      value={cred.vrf ?? ""}
                      onChange={(e: ChangeEvent<HTMLInputElement>) =>
                        handleDefaultCredentialChange(idx, "vrf", e.target.value)
                      }
                    />
                    <button
                      type="button"
                      className="btn btn-icon"
                      onClick={() => handleRemoveDefaultCredential(idx)}
                      disabled={defaultCliCredentials.length === 1}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
              <div className="credential-actions">
                <button type="button" className="btn btn-secondary" onClick={handleAddDefaultCredential}>
                  + Add Credential
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleSaveDefaultCredentials}
                  disabled={isSavingCliDefaults}
                >
                  {isSavingCliDefaults ? "Saving..." : "Save Defaults"}
                </button>
              </div>
              {cliDefaultsSaveError && <div className="error-message">{cliDefaultsSaveError}</div>}
              {cliDefaultsSaveSuccess && <div className="success-message">{cliDefaultsSaveSuccess}</div>}
            </div>

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={useCustomCliCredentials}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => handleToggleCustomCli(e.target.checked)}
                />
                Use custom CLI credentials for this run only
              </label>
              {useCustomCliCredentials && (
                <div className="credential-list">
                  {customCliCredentials.map((cred: CredentialPair, idx: number) => (
                    <div key={`custom-${idx}`} className="credential-row">
                      <input
                        type="text"
                        placeholder="username"
                        value={cred.username}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          handleCustomCredentialChange(idx, "username", e.target.value)
                        }
                      />
                      <input
                        type="text"
                        placeholder="password"
                        value={cred.password}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          handleCustomCredentialChange(idx, "password", e.target.value)
                        }
                      />
                      <input
                        type="text"
                        placeholder="VRF (optional)"
                        value={cred.vrf ?? ""}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          handleCustomCredentialChange(idx, "vrf", e.target.value)
                        }
                      />
                      <button
                        type="button"
                        className="btn btn-icon"
                        onClick={() => handleRemoveCustomCredential(idx)}
                        disabled={customCliCredentials.length === 1}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <button type="button" className="btn btn-secondary" onClick={handleAddCustomCredential}>
                    + Add Credential
                  </button>
                </div>
              )}
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
            <div className="status-header">
              <h2>Discovery Status</h2>
              <div className="control-buttons">
                {["RUNNING", "PENDING"].includes(currentRun.status) && (
                  <>
                    <button
                      className="btn btn-pause"
                      onClick={() => handlePause(currentRun.id)}
                    >
                      ⏸ Pause
                    </button>
                    <button
                      className="btn btn-cancel"
                      onClick={() => handleCancel(currentRun.id)}
                    >
                      ✕ Cancel
                    </button>
                  </>
                )}
                {currentRun.status === "PAUSED" && (
                  <>
                    <button
                      className="btn btn-resume"
                      onClick={() => handleResume(currentRun.id)}
                    >
                      ▶ Resume
                    </button>
                    <button
                      className="btn btn-cancel"
                      onClick={() => handleCancel(currentRun.id)}
                    >
                      ✕ Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
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
                <strong>{topology.nodes.filter((n: RouterNode) => n.is_router).length}</strong>{" "}
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
                  {topology.nodes.map((node: RouterNode) => (
                    <tr
                      key={node.id}
                      className={`clickable${selectedRouterId === node.id ? " selected" : ""}`}
                      onClick={() => handleSelectRouter(node.id)}
                    >
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

            <div className="detail-container">
              <div className="detail-header">
                <h3>Routing Table</h3>
                {routerDetail && (
                  <span className="detail-meta">{routerDetail.ip}</span>
                )}
              </div>
              {detailLoading && (
                <div className="detail-message">Loading routes…</div>
              )}
              {!detailLoading && detailError && (
                <div className="detail-error">{detailError}</div>
              )}
              {!detailLoading && !detailError && routerDetail && (
                <>
                  <div className="detail-summary">
                    <div>
                      <strong>{routerDetail.networks.length}</strong> Networks
                    </div>
                    <div>
                      <strong>{routerDetail.routes.length}</strong> Routes
                    </div>
                    <div>
                      <strong>{routerDetail.router_score}</strong> Score
                    </div>
                    {routerDetail.routes.length === 0 && (
                      <div>
                        <button
                          className="btn btn-secondary"
                          onClick={handleOpenCliModal}
                        >
                          Fetch routes via SSH/CLI
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="detail-networks">
                    {routerDetail.networks.map((net: string) => (
                      <span key={net} className="tag">
                        {net}
                      </span>
                    ))}
                    {routerDetail.networks.length === 0 && (
                      <span className="detail-message">No interfaces recorded.</span>
                    )}
                  </div>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>CIDR</th>
                        <th>Network</th>
                        <th>Netmask</th>
                        <th>Prefix</th>
                        <th>Next Hop</th>
                        <th>Protocol</th>
                      </tr>
                    </thead>
                    <tbody>
                      {routerDetail.routes.map((route: RouterRouteInfo, idx: number) => (
                        <tr key={`${route.cidr}-${route.next_hop || "none"}-${idx}`}>
                          <td className="mono">{route.cidr}</td>
                          <td className="mono">{route.network}</td>
                          <td className="mono">{route.netmask}</td>
                          <td>{route.prefix_len}</td>
                          <td className="mono">{route.next_hop || "—"}</td>
                          <td>{route.protocol || "—"}</td>
                        </tr>
                      ))}
                      {routerDetail.routes.length === 0 && (
                        <tr>
                          <td colSpan={6} className="detail-message">
                            No routes discovered.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </>
              )}
              {!detailLoading && !detailError && !routerDetail && (
                <div className="detail-message">
                  {selectedRouterId
                    ? "No route data available."
                    : "Select a router above to inspect its routing table."}
                </div>
              )}
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
                  {topology.edges.map((edge: TopologyEdge, idx: number) => {
                    const fromNode = topology.nodes.find((n: RouterNode) => n.id === edge.from_id);
                    const toNode = topology.nodes.find((n: RouterNode) => n.id === edge.to_id);
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
        {showCliModal && routerDetail && (
          <div className="modal-backdrop">
            <div className="modal">
              <h3>Fetch Routes via SSH/CLI</h3>
              <p className="small">
                Enter credentials to run <code>show ip route</code> on {routerDetail.ip}.
                Password is used only for this request and not stored.
              </p>
              <form onSubmit={handleSubmitCliRoutes}>
                <div className="form-group">
                  <label>Username</label>
                  <input
                    type="text"
                    value={cliUsername}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setCliUsername(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Password</label>
                  <input
                    type="password"
                    value={cliPassword}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setCliPassword(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>VRF (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. vss-network"
                    value={cliVrf}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setCliVrf(e.target.value)}
                  />
                </div>
                {cliError && <div className="error-message">{cliError}</div>}
                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setShowCliModal(false);
                      setCliPassword("");
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="submit-button"
                    disabled={cliLoading}
                  >
                    {cliLoading ? "Fetching..." : "Fetch Routes"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
