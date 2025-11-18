import { useEffect, useState } from "react";

interface InventoryDevice {
  id: number;
  ip_address: string;
  mac_address: string | null;
  status: string;
  device_type: string | null;
  device_name: string | null;
  network_role: string | null;
  vendor: string | null;
  model: string | null;
  open_ports: Record<string, any> | null;
  snmp_data: Record<string, any> | null;
  snmp_enabled: boolean;
  snmp_port: number;
  snmp_version: string | null;
  snmp_community: string | null;
  snmp_username: string | null;
  snmp_auth_protocol: string | null;
  snmp_auth_key: string | null;
  snmp_priv_protocol: string | null;
  snmp_priv_key: string | null;
  mib_id: number | null;
  mib_ids: number[] | null;
  confidence_score: number | null;
  classification_notes: string | null;
  first_seen: string;
  last_seen: string;
  last_probed: string | null;
}

interface InventoryGridProps {
  apiBase: string;
  onNavigateToAdmin: () => void;
  onNavigateToTopology: () => void;
}

interface SnmpConfig {
  snmp_enabled: boolean;
  snmp_port: number;
  snmp_version: string;
  snmp_community: string;
  snmp_username: string;
  snmp_auth_protocol: string;
  snmp_auth_key: string;
  snmp_priv_protocol: string;
  snmp_priv_key: string;
  mib_id: number | null;
  network_role: string;
}

interface Mib {
  id: number;
  name: string;
  vendor: string;
  device_types: string[] | null;
  version: string | null;
  description: string | null;
}

function renderComplexValue(value: any, depth: number = 0): React.ReactNode {
  if (value === null || value === undefined) {
    return <span style={{ color: "#9ca3af", fontStyle: "italic" }}>null</span>;
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span style={{ color: "#9ca3af", fontStyle: "italic" }}>[]</span>;
    }
    return (
      <div style={{ marginTop: "0.25rem" }}>
        {value.map((item, idx) => (
          <div key={idx} style={{ paddingLeft: "1rem", borderLeft: "2px solid #e5e7eb", marginBottom: "0.25rem" }}>
            {renderComplexValue(item, depth + 1)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return <span style={{ color: "#9ca3af", fontStyle: "italic" }}>{'{}'}</span>;
    }

    const isComplexNested = entries.some(([_, v]) => typeof v === 'object' && v !== null && !Array.isArray(v) && Object.keys(v).length > 3);
    
    if (isComplexNested && depth < 2) {
      return (
        <div style={{ marginTop: "0.5rem" }}>
          {entries.map(([subKey, subValue]) => (
            <details key={subKey} style={{ marginBottom: "0.5rem", paddingLeft: "0.5rem", borderLeft: "2px solid #e5e7eb" }}>
              <summary style={{ cursor: "pointer", fontWeight: "500", color: "#374151", fontSize: "0.85rem", padding: "0.25rem" }}>
                {subKey}
              </summary>
              <div style={{ paddingLeft: "1rem", marginTop: "0.25rem" }}>
                {renderComplexValue(subValue, depth + 1)}
              </div>
            </details>
          ))}
        </div>
      );
    }

    return (
      <table className="snmp-table" style={{ fontSize: "0.8rem", marginTop: "0.25rem", width: "100%" }}>
        <thead>
          <tr>
            <th style={{ width: "40%" }}>Key</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([subKey, subValue]) => (
            <tr key={subKey}>
              <td style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "#6b7280" }}>{subKey}</td>
              <td>{renderComplexValue(subValue, depth + 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return String(value);
}

function InventoryGrid({ apiBase, onNavigateToAdmin, onNavigateToTopology }: InventoryGridProps) {
  const [devices, setDevices] = useState<InventoryDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<keyof InventoryDevice>("ip_address");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [filterType, setFilterType] = useState<string>("");
  const [snmpModalDevice, setSnmpModalDevice] = useState<InventoryDevice | null>(null);
  const [snmpConfig, setSnmpConfig] = useState<SnmpConfig>({
    snmp_enabled: true,
    snmp_port: 161,
    snmp_version: "2c",
    snmp_community: "public",
    snmp_username: "",
    snmp_auth_protocol: "",
    snmp_auth_key: "",
    snmp_priv_protocol: "",
    snmp_priv_key: "",
    mib_id: null,
    network_role: "unknown",
  });
  const [suggestedMibs, setSuggestedMibs] = useState<Mib[]>([]);
  const [allMibs, setAllMibs] = useState<Mib[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadInventory();
    loadMibs();
    const interval = setInterval(loadInventory, 30000);
    return () => clearInterval(interval);
  }, [apiBase]);

  const handlePortClick = (ipAddress: string, port: string) => {
    const portNum = parseInt(port);
    
    if (portNum === 80) {
      window.open(`http://${ipAddress}`, '_blank');
    } else if (portNum === 443) {
      window.open(`https://${ipAddress}`, '_blank');
    } else if (portNum === 22 || portNum === 23) {
      const protocol = portNum === 22 ? 'ssh' : 'telnet';
      const terminalType = localStorage.getItem('terminalType') || 'native';
      
      if (terminalType === 'putty') {
        window.location.href = `putty://${protocol}@${ipAddress}:${portNum}`;
      } else if (terminalType === 'url') {
        if (protocol === 'ssh') {
          window.location.href = `ssh://${ipAddress}`;
        } else {
          window.location.href = `telnet://${ipAddress}`;
        }
      } else {
        const message = `To connect to this device:\n\nProtocol: ${protocol.toUpperCase()}\nHost: ${ipAddress}\nPort: ${portNum}\n\nCommand to run:\n${protocol} ${ipAddress}\n\nConfigure terminal settings in Admin for automatic launching.`;
        
        if (confirm(message + '\n\nCopy command to clipboard?')) {
          navigator.clipboard.writeText(`${protocol} ${ipAddress}`);
        }
      }
    }
  };

  const loadInventory = async () => {
    try {
      const response = await fetch(`${apiBase}/api/inventory`);
      if (!response.ok) throw new Error("Failed to fetch inventory");
      const data = await response.json();
      setDevices(data);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setLoading(false);
    }
  };

  const loadMibs = async () => {
    try {
      const response = await fetch(`${apiBase}/api/mibs`);
      if (!response.ok) throw new Error("Failed to fetch MIBs");
      const data = await response.json();
      setAllMibs(data);
    } catch (err) {
      console.error("Failed to load MIBs:", err);
    }
  };

  const handleSort = (field: keyof InventoryDevice) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("asc");
    }
  };

  const openSnmpModal = async (device: InventoryDevice) => {
    setSnmpModalDevice(device);
    setSnmpConfig({
      snmp_enabled: device.snmp_enabled || false,
      snmp_port: device.snmp_port || 161,
      snmp_version: device.snmp_version || "2c",
      snmp_community: device.snmp_community || "public",
      snmp_username: device.snmp_username || "",
      snmp_auth_protocol: device.snmp_auth_protocol || "",
      snmp_auth_key: device.snmp_auth_key || "",
      snmp_priv_protocol: device.snmp_priv_protocol || "",
      snmp_priv_key: device.snmp_priv_key || "",
      mib_id: device.mib_id || null,
      network_role: device.network_role || "unknown",
    });

    try {
      const response = await fetch(`${apiBase}/api/inventory/${device.ip_address}/mibs/suggestions`);
      if (response.ok) {
        const suggestions = await response.json();
        setSuggestedMibs(suggestions);
      } else {
        setSuggestedMibs([]);
      }
    } catch (err) {
      console.error("Failed to load MIB suggestions:", err);
      setSuggestedMibs([]);
    }
  };

  const saveSnmpConfig = async () => {
    if (!snmpModalDevice) return;

    setSaving(true);
    try {
      const response = await fetch(`${apiBase}/api/inventory/${snmpModalDevice.ip_address}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...snmpConfig,
          network_role_confirmed: true
        }),
      });

      if (!response.ok) throw new Error("Failed to save SNMP config");

      await loadInventory();
      setSnmpModalDevice(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save SNMP config");
    } finally {
      setSaving(false);
    }
  };

  const handleReassignMib = async () => {
    if (!snmpModalDevice) return;

    setSaving(true);
    try {
      const response = await fetch(`${apiBase}/api/inventory/${snmpModalDevice.ip_address}/mibs/reassign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to reassign MIB");
      }

      const updatedDevice = await response.json();
      const primaryMib = allMibs.find(m => m.id === updatedDevice.mib_id)?.name || updatedDevice.mib_id;
      const assignedMibs = updatedDevice.mib_ids 
        ? updatedDevice.mib_ids.map((id: number) => allMibs.find(m => m.id === id)?.name || id).join(", ")
        : primaryMib;
      alert(`MIB reassignment completed!\n\nPrimary MIB: ${primaryMib}\nAll Assigned MIBs (${updatedDevice.mib_ids?.length || 1}): ${assignedMibs}`);
      
      await loadInventory();
      setSnmpModalDevice(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to reassign MIB");
    } finally {
      setSaving(false);
    }
  };

  const handleWalkMib = async () => {
    if (!snmpModalDevice) return;

    setSaving(true);
    try {
      const response = await fetch(`${apiBase}/api/inventory/${snmpModalDevice.ip_address}/mibs/walk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to walk MIB");
      }

      const result = await response.json();
      const mibCount = result.mibs_walked || 1;
      const mibText = mibCount === 1 ? "1 MIB" : `${mibCount} MIBs`;
      alert(`MIB walk completed successfully!\n\nMIBs walked: ${mibText}\nWalked at: ${new Date(result.walked_at).toLocaleString()}`);
      
      await loadInventory();
      setSnmpModalDevice(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to walk MIB");
    } finally {
      setSaving(false);
    }
  };

  const sortedDevices = [...devices].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    
    let comparison = 0;
    if (sortField === "ip_address") {
      const aOctets = String(aVal).split('.').map(Number);
      const bOctets = String(bVal).split('.').map(Number);
      for (let i = 0; i < 4; i++) {
        if (aOctets[i] !== bOctets[i]) {
          comparison = aOctets[i] - bOctets[i];
          break;
        }
      }
    } else {
      comparison = String(aVal).localeCompare(String(bVal));
    }
    
    return sortOrder === "asc" ? comparison : -comparison;
  });

  const filteredDevices = filterType
    ? sortedDevices.filter((d) => d.device_type === filterType)
    : sortedDevices;

  const deviceTypes = Array.from(new Set(devices.map((d) => d.device_type).filter((t) => t != null)));

  if (loading) return <div className="inventory-loading">Loading inventory...</div>;
  if (error) return <div className="inventory-error">Error: {error}</div>;

  return (
    <div className="inventory-container">
      <div className="inventory-header">
        <div className="inventory-filters">
          <div style={{ fontWeight: "bold", marginRight: "1rem" }}>
            Devices: {filteredDevices.length}{filterType ? ` (of ${devices.length} total)` : ""}
          </div>
          <label>
            Filter by type:
            <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
              <option value="">All</option>
              {deviceTypes.map((type) => (
                <option key={type} value={type || ""}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <button onClick={loadInventory} className="refresh-btn">
            Refresh
          </button>
          <button onClick={onNavigateToTopology} className="admin-btn" style={{ backgroundColor: "#7c3aed" }}>
            Topology
          </button>
          <button onClick={onNavigateToAdmin} className="admin-btn">
            Admin
          </button>
        </div>
      </div>
      <div className="inventory-grid-wrapper">
        <table className="inventory-table">
          <thead>
            <tr>
              <th onClick={() => handleSort("ip_address")} className="sortable">
                IP Address {sortField === "ip_address" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th onClick={() => handleSort("mac_address")} className="sortable">
                MAC {sortField === "mac_address" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th onClick={() => handleSort("device_type")} className="sortable">
                Type {sortField === "device_type" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th onClick={() => handleSort("network_role")} className="sortable">
                Role {sortField === "network_role" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th onClick={() => handleSort("vendor")} className="sortable">
                Vendor {sortField === "vendor" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th>Services</th>
              <th onClick={() => handleSort("confidence_score")} className="sortable">
                Conf {sortField === "confidence_score" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
              <th onClick={() => handleSort("last_seen")} className="sortable">
                Last Seen {sortField === "last_seen" ? (sortOrder === "asc" ? "▲" : "▼") : ""}
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredDevices.map((device) => (
              <tr key={device.id}>
                <td className="ip-cell">{device.ip_address}</td>
                <td className="mac-cell">{device.mac_address || "-"}</td>
                <td className="type-cell">
                  <span className={`type-badge ${device.device_type || "unknown"}`}>
                    {(device.device_type || "unknown").split("_")[0]}
                  </span>
                </td>
                <td className="type-cell">
                  <span 
                    className={`type-badge ${device.network_role || "unknown"}`}
                    onClick={() => openSnmpModal(device)}
                    style={{ cursor: 'pointer' }}
                    title="Click to configure SNMP and network role"
                  >
                    {device.network_role === "L2_switch" ? "L2" : device.network_role === "L3_router" ? "L3" : device.network_role || "?"}
                  </span>
                </td>
                <td className="vendor-cell">{device.vendor || "-"}</td>
                <td className="services-cell">
                  <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                    {device.open_ports &&
                      Object.keys(device.open_ports).map((port) => {
                        const portNum = parseInt(port);
                        const isClickable = portNum === 80 || portNum === 443 || portNum === 22 || portNum === 23;
                        return (
                          <span 
                            key={port} 
                            className={`port-badge ${isClickable ? 'clickable' : ''}`}
                            onClick={isClickable ? () => handlePortClick(device.ip_address, port) : undefined}
                            style={isClickable ? { cursor: 'pointer' } : undefined}
                            title={
                              portNum === 80 ? 'Click to open HTTP' :
                              portNum === 443 ? 'Click to open HTTPS' :
                              portNum === 22 ? 'Click to open SSH' :
                              portNum === 23 ? 'Click to open Telnet' :
                              undefined
                            }
                          >
                            {port}
                          </span>
                        );
                      })}
                    {device.snmp_data ? (
                      <button
                        className="snmp-badge snmp-enabled"
                        onClick={() => openSnmpModal(device)}
                        title="SNMP Discovered - Click for details"
                      >
                        SNMP
                      </button>
                    ) : (
                      <button
                        className="snmp-badge snmp-disabled"
                        onClick={() => openSnmpModal(device)}
                        title="Configure SNMP"
                      >
                        SNMP
                      </button>
                    )}
                    {!device.open_ports && "-"}
                  </div>
                </td>
                <td className="confidence-cell">
                  {device.confidence_score != null ? (device.confidence_score * 100).toFixed(0) + "%" : "-"}
                </td>
                <td className="time-cell">{new Date(device.last_seen).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {snmpModalDevice && (
        <div className="modal-overlay" onClick={() => setSnmpModalDevice(null)}>
          <div className="modal-content snmp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>SNMP Configuration - {snmpModalDevice.ip_address}</h3>
              <button className="modal-close" onClick={() => setSnmpModalDevice(null)}>
                ×
              </button>
            </div>
            <div className="modal-body" style={{ display: "flex", gap: "0.5rem", height: "calc(100vh - 120px)" }}>
              <div style={{ flex: "0 0 350px", overflowY: "auto", paddingRight: "0.5rem", borderRight: "1px solid #e5e7eb" }}>
                <h4>SNMP Configuration</h4>
                <div className="snmp-config-form">
                  <label className="snmp-checkbox-label">
                    <input
                      type="checkbox"
                      checked={snmpConfig.snmp_enabled}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_enabled: e.target.checked })}
                    />
                    <span>Enable SNMP</span>
                  </label>

                  <label>
                    <span>SNMP Version</span>
                    <select
                      value={snmpConfig.snmp_version}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_version: e.target.value })}
                    >
                      <option value="1">v1</option>
                      <option value="2c">v2c</option>
                      <option value="3">v3</option>
                    </select>
                  </label>

                  <label>
                    <span>SNMP Port</span>
                    <input
                      type="number"
                      value={snmpConfig.snmp_port}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_port: parseInt(e.target.value) || 161 })}
                    />
                  </label>

                  <label>
                    <span>Primary MIB</span>
                    <select
                      value={snmpConfig.mib_id || ""}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, mib_id: e.target.value ? parseInt(e.target.value) : null })}
                    >
                      <option value="">None</option>
                      {suggestedMibs.length > 0 && (
                        <optgroup label="Suggested MIBs">
                          {suggestedMibs.map((mib) => (
                            <option key={mib.id} value={mib.id}>
                              {mib.name} ({mib.vendor})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {allMibs.filter(m => !suggestedMibs.find(s => s.id === m.id)).length > 0 && (
                        <optgroup label="All MIBs">
                          {allMibs
                            .filter(m => !suggestedMibs.find(s => s.id === m.id))
                            .map((mib) => (
                              <option key={mib.id} value={mib.id}>
                                {mib.name} ({mib.vendor})
                              </option>
                            ))}
                        </optgroup>
                      )}
                    </select>
                  </label>

                  {snmpModalDevice.mib_ids && snmpModalDevice.mib_ids.length > 0 && (
                    <div style={{ marginTop: "0.5rem", padding: "0.75rem", background: "#f3f4f6", borderRadius: "0.375rem" }}>
                      <strong style={{ fontSize: "0.875rem", color: "#374151", display: "block", marginBottom: "0.5rem" }}>
                        Assigned MIBs ({snmpModalDevice.mib_ids.length}):
                      </strong>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                        {snmpModalDevice.mib_ids.map((mibId) => {
                          const mib = allMibs.find(m => m.id === mibId);
                          const isPrimary = mibId === snmpModalDevice.mib_id;
                          return mib ? (
                            <span 
                              key={mibId} 
                              style={{ 
                                fontSize: "0.75rem", 
                                padding: "0.25rem 0.5rem", 
                                background: isPrimary ? "#3b82f6" : "#6b7280",
                                color: "white",
                                borderRadius: "0.25rem",
                                fontWeight: isPrimary ? "600" : "400"
                              }}
                              title={`${mib.name} (${mib.vendor})${isPrimary ? ' - Primary' : ''}`}
                            >
                              {mib.name}
                            </span>
                          ) : null;
                        })}
                      </div>
                    </div>
                  )}

                  <label>
                    <span>Network Role</span>
                    <select
                      value={snmpConfig.network_role}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, network_role: e.target.value })}
                    >
                      <option value="unknown">Unknown</option>
                      <option value="L2_switch">L2 Switch</option>
                      <option value="L3_router">L3 Router</option>
                    </select>
                  </label>

                  {(snmpConfig.snmp_version === "1" || snmpConfig.snmp_version === "2c") && (
                    <label>
                      <span>Community String</span>
                      <input
                        type="text"
                        value={snmpConfig.snmp_community}
                        onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_community: e.target.value })}
                        placeholder="public"
                      />
                    </label>
                  )}

                  {snmpConfig.snmp_version === "3" && (
                    <>
                      <label>
                        <span>Username</span>
                        <input
                          type="text"
                          value={snmpConfig.snmp_username}
                          onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_username: e.target.value })}
                        />
                      </label>

                      <label>
                        <span>Auth Protocol</span>
                        <select
                          value={snmpConfig.snmp_auth_protocol}
                          onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_auth_protocol: e.target.value })}
                        >
                          <option value="">None</option>
                          <option value="MD5">MD5</option>
                          <option value="SHA">SHA</option>
                        </select>
                      </label>

                      {snmpConfig.snmp_auth_protocol && (
                        <label>
                          <span>Auth Key</span>
                          <input
                            type="password"
                            value={snmpConfig.snmp_auth_key}
                            onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_auth_key: e.target.value })}
                          />
                        </label>
                      )}

                      <label>
                        <span>Privacy Protocol</span>
                        <select
                          value={snmpConfig.snmp_priv_protocol}
                          onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_priv_protocol: e.target.value })}
                        >
                          <option value="">None</option>
                          <option value="DES">DES</option>
                          <option value="AES">AES</option>
                        </select>
                      </label>

                      {snmpConfig.snmp_priv_protocol && (
                        <label>
                          <span>Privacy Key</span>
                          <input
                            type="password"
                            value={snmpConfig.snmp_priv_key}
                            onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_priv_key: e.target.value })}
                          />
                        </label>
                      )}
                    </>
                  )}
                </div>
              </div>
              <div style={{ flex: "1", overflowY: "auto", paddingLeft: "0.5rem" }}>
                <h4 style={{ marginTop: 0 }}>MIB Data</h4>
                {snmpModalDevice.snmp_data && (
                  <>
                    <div className="snmp-section">
                      <h5>Basic Information</h5>
                      <div className="snmp-details">
                        {Object.entries(snmpModalDevice.snmp_data)
                          .filter(([key]) => !["interfaces", "storage", "system", "walked_at", "mib_used", "mib_results", "VENDOR_MIB_DATA"].includes(key))
                          .map(([key, value]) => (
                            <div key={key} className="snmp-detail-row">
                              <strong className="snmp-key">{key}:</strong>
                              <span className="snmp-value">{String(value)}</span>
                            </div>
                          ))}
                      </div>
                    </div>

                    {snmpModalDevice.snmp_data.interfaces && (
                      <div className="snmp-section">
                        <h5>Network Interfaces ({Object.keys(snmpModalDevice.snmp_data.interfaces).length})</h5>
                        <div style={{ overflowX: "auto" }}>
                          <table className="snmp-table">
                            <thead>
                              <tr>
                                <th>Index</th>
                                <th>Description</th>
                                <th>Type</th>
                                <th>Speed</th>
                                <th>Admin</th>
                                <th>Oper</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(snmpModalDevice.snmp_data.interfaces as Record<string, any>).map(([idx, iface]) => (
                                <tr key={idx}>
                                  <td>{idx}</td>
                                  <td>{iface.description}</td>
                                  <td>{iface.type}</td>
                                  <td>{parseInt(iface.speed) >= 1000000000 ? `${parseInt(iface.speed) / 1000000000} Gbps` : parseInt(iface.speed) >= 1000000 ? `${parseInt(iface.speed) / 1000000} Mbps` : `${iface.speed} bps`}</td>
                                  <td>{iface.admin_status === "1" ? "Up" : "Down"}</td>
                                  <td>{iface.oper_status === "1" ? "Up" : "Down"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {snmpModalDevice.snmp_data.storage && (
                      <div className="snmp-section">
                        <h5>Storage ({Object.keys(snmpModalDevice.snmp_data.storage).length})</h5>
                        <div style={{ overflowX: "auto" }}>
                          <table className="snmp-table">
                            <thead>
                              <tr>
                                <th>Index</th>
                                <th>Description</th>
                                <th>Units</th>
                                <th>Size</th>
                                <th>Used</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(snmpModalDevice.snmp_data.storage as Record<string, any>).map(([idx, store]) => {
                                const units = parseInt(store.units) || 1;
                                const size = parseInt(store.size) || 0;
                                const used = parseInt(store.used) || 0;
                                const sizeBytes = size * units;
                                const usedBytes = used * units;
                                const formatBytes = (bytes: number) => {
                                  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`;
                                  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(2)} MB`;
                                  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`;
                                  return `${bytes} B`;
                                };
                                return (
                                  <tr key={idx}>
                                    <td>{idx}</td>
                                    <td>{store.description}</td>
                                    <td>{units} bytes</td>
                                    <td>{formatBytes(sizeBytes)}</td>
                                    <td>{formatBytes(usedBytes)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {snmpModalDevice.snmp_data.system && (
                      <div className="snmp-section">
                        <h5>System Information</h5>
                        <div className="snmp-details">
                          {Object.entries(snmpModalDevice.snmp_data.system as Record<string, any>).map(([key, value]) => (
                            <div key={key} className="snmp-detail-row">
                              <strong className="snmp-key">{key}:</strong>
                              <span className="snmp-value">{String(value)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {snmpModalDevice.snmp_data.VENDOR_MIB_DATA && (
                      <div className="snmp-section">
                        <h5>Vendor-Specific MIB Data ({Object.keys(snmpModalDevice.snmp_data.VENDOR_MIB_DATA).length} OIDs)</h5>
                        <div style={{ overflowX: "auto", maxHeight: "400px", overflowY: "auto" }}>
                          <table className="snmp-table">
                            <thead>
                              <tr>
                                <th>OID</th>
                                <th>Value</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(snmpModalDevice.snmp_data.VENDOR_MIB_DATA as Record<string, any>).map(([label, data]) => {
                                const isNewFormat = typeof data === 'object' && data !== null && 'oid' in data && 'value' in data;
                                const oidValue = isNewFormat ? data.oid : label;
                                const displayValue = isNewFormat ? data.value : data;
                                const displayLabel = label;
                                
                                return (
                                  <tr key={oidValue}>
                                    <td style={{ fontFamily: "monospace" }} title={oidValue}>{displayLabel}</td>
                                    <td>{String(displayValue)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {snmpModalDevice.snmp_data.mib_results && (
                      <div className="snmp-section">
                        <h5>Per-MIB Results</h5>
                        {Object.entries(snmpModalDevice.snmp_data.mib_results as Record<string, any>).map(([mibName, mibData]) => (
                          <div key={mibName} style={{ marginBottom: "1rem", padding: "0.75rem", background: "#f9fafb", borderRadius: "0.375rem", border: "1px solid #e5e7eb" }}>
                            <strong style={{ fontSize: "0.9rem", color: "#111827", display: "block", marginBottom: "0.5rem" }}>
                              {mibName}
                            </strong>
                            {typeof mibData === 'object' && mibData !== null ? (
                              <div style={{ overflowX: "auto", maxHeight: "300px", overflowY: "auto" }}>
                                <table className="snmp-table" style={{ fontSize: "0.875rem" }}>
                                  <thead>
                                    <tr>
                                      <th>Key</th>
                                      <th>Value</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {Object.entries(mibData).map(([key, value]) => (
                                      <tr key={key}>
                                        <td style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>{key}</td>
                                        <td>{renderComplexValue(value, 1)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            ) : (
                              <span style={{ fontSize: "0.875rem", color: "#6b7280" }}>No data available</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {snmpModalDevice.snmp_data.mib_used && (
                      <div className="snmp-section" style={{ color: "#666", marginTop: "0.5rem" }}>
                        MIB: {snmpModalDevice.snmp_data.mib_used} | Last walked: {snmpModalDevice.snmp_data.walked_at ? new Date(snmpModalDevice.snmp_data.walked_at as string).toLocaleString() : "Never"}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
            <div className="modal-footer">
              <div style={{ display: "flex", gap: "0.5rem", flex: 1 }}>
                <button 
                  className="modal-btn modal-btn-secondary" 
                  onClick={handleReassignMib} 
                  disabled={saving || !snmpModalDevice.snmp_data}
                  title="Re-suggest and assign the best MIB for this device"
                >
                  Reassign MIB
                </button>
                <button 
                  className="modal-btn modal-btn-secondary" 
                  onClick={handleWalkMib} 
                  disabled={saving || !snmpModalDevice.mib_id || !snmpModalDevice.snmp_enabled}
                  title="Trigger an immediate SNMP walk for this device"
                >
                  Walk MIB Now
                </button>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button className="modal-btn modal-btn-secondary" onClick={() => setSnmpModalDevice(null)}>
                  Cancel
                </button>
                <button className="modal-btn" onClick={saveSnmpConfig} disabled={saving}>
                  {saving ? "Saving..." : "Save Configuration"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default InventoryGrid;
