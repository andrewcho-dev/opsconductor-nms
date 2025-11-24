import { useEffect, useState } from "react";

interface InventoryDevice {
  id: number;
  ip_address: string;
  mac_address: string | null;
  hostname: string | null;
  all_hostnames: string[] | null;
  status: string;
  device_type: string | null;
  device_name: string | null;
  network_role: string | null;
  network_role_confirmed: boolean;
  vendor: string | null;
  model: string | null;
  open_ports: Record<string, any> | null;
  snmp_data: Record<string, any> | null;
  os_name: string | null;
  os_accuracy: string | null;
  os_detection: any[] | null;
  uptime_seconds: string | null;
  host_scripts: any[] | null;
  nmap_scan_time: string | null;
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
  onNavigateToDiscovery?: () => void;
  onNavigateToRouting?: () => void;
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

const STATE_SERVER_API_BASE = "http://10.120.0.18:8080";

function InventoryGrid({ apiBase, onNavigateToAdmin, onNavigateToTopology, onNavigateToDiscovery, onNavigateToRouting }: InventoryGridProps) {
  const [devices, setDevices] = useState<InventoryDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<keyof InventoryDevice>("ip_address");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [filterType, setFilterType] = useState<string>("");
  const [filterRole, setFilterRole] = useState<string>("");
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
    network_role: "Endpoint",
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
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/inventory`);
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
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/mibs`);
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

  const normalizeRole = (role: string | null): string => {
    if (!role || role === "unknown") {
      return "Endpoint";
    } else if (role.includes("L3") || role === "L3_router") {
      return "L3";
    } else if (role.includes("L2") || role === "L2_switch") {
      return "L2";
    }
    return role;
  };

  const openSnmpModal = async (device: InventoryDevice) => {
    setSnmpModalDevice(device);
    const normalizedRole = normalizeRole(device.network_role);
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
      network_role: normalizedRole,
    });

    try {
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/inventory/${device.ip_address}/mibs/suggestions`);
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
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/inventory/${snmpModalDevice.ip_address}`, {
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
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/inventory/${snmpModalDevice.ip_address}/mibs/reassign`, {
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
      const response = await fetch(`${STATE_SERVER_API_BASE}/api/inventory/${snmpModalDevice.ip_address}/mibs/walk`, {
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

  const filteredDevices = sortedDevices.filter((d) => {
    if (filterType && d.device_type !== filterType) return false;
    if (filterRole) {
      const deviceRole = normalizeRole(d.network_role);
      if (deviceRole !== filterRole) return false;
    }
    return true;
  });

  const deviceTypes = Array.from(new Set(devices.map((d) => d.device_type).filter((t) => t != null)));

  const l3Count = devices.filter(d => normalizeRole(d.network_role) === "L3").length;
  const l2Count = devices.filter(d => normalizeRole(d.network_role) === "L2").length;
  const endpointCount = devices.filter(d => normalizeRole(d.network_role) === "Endpoint").length;

  if (loading) return <div className="inventory-loading">Loading inventory...</div>;
  if (error) return <div className="inventory-error">Error: {error}</div>;

  return (
    <div className="inventory-container">
      <div className="inventory-header">
        <div className="inventory-filters">
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginRight: "1rem" }}>
            <span
              onClick={() => setFilterRole("")}
              style={{
                fontWeight: "bold",
                cursor: "pointer",
                textDecoration: filterRole === "" ? "underline" : "none",
                color: filterRole === "" ? "#2563eb" : "inherit"
              }}
              title="Show all devices"
            >
              Total: {devices.length}
            </span>
            <span
              onClick={() => setFilterRole("L3")}
              style={{
                fontWeight: "bold",
                cursor: "pointer",
                textDecoration: filterRole === "L3" ? "underline" : "none",
                color: filterRole === "L3" ? "#2563eb" : "#059669"
              }}
              title="Show L3 routers only"
            >
              L3: {l3Count}
            </span>
            <span
              onClick={() => setFilterRole("L2")}
              style={{
                fontWeight: "bold",
                cursor: "pointer",
                textDecoration: filterRole === "L2" ? "underline" : "none",
                color: filterRole === "L2" ? "#2563eb" : "#d97706"
              }}
              title="Show L2 switches only"
            >
              L2: {l2Count}
            </span>
            <span
              onClick={() => setFilterRole("Endpoint")}
              style={{
                fontWeight: "bold",
                cursor: "pointer",
                textDecoration: filterRole === "Endpoint" ? "underline" : "none",
                color: filterRole === "Endpoint" ? "#2563eb" : "#6b7280"
              }}
              title="Show endpoints only"
            >
              Ends: {endpointCount}
            </span>
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
          <button onClick={onNavigateToRouting} className="admin-btn" style={{ backgroundColor: "#10b981" }}>
            Routing Table
          </button>
          <button onClick={onNavigateToTopology} className="admin-btn" style={{ backgroundColor: "#7c3aed" }}>
            Topology
          </button>
          {onNavigateToDiscovery && (
            <button onClick={onNavigateToDiscovery} className="admin-btn" style={{ backgroundColor: "#06b6d4" }}>
              Discovery
            </button>
          )}
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
              <th>SNMP</th>
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
                  <div style={{ display: "flex", gap: "0.25rem", alignItems: "center", flexWrap: "nowrap" }}>
                    {["L3", "L2", "End"].map((role) => {
                      const roleValue = role === "End" ? "Endpoint" : role;
                      const normalizedRole = normalizeRole(device.network_role);
                      const isChecked = normalizedRole === roleValue;
                      const isAutoDetected = isChecked && !device.network_role_confirmed;
                      
                      return (
                        <label key={role} style={{ 
                          display: "flex", 
                          alignItems: "center", 
                          cursor: "pointer", 
                          gap: "0.25rem", 
                          position: "relative",
                          padding: "0.2rem 0.4rem",
                          borderRadius: "0.25rem",
                          backgroundColor: isAutoDetected ? "#fef3c7" : "transparent",
                          border: isAutoDetected ? "1px solid #fcd34d" : "none"
                        }}>
                          <input
                            type="radio"
                            name={`role-${device.id}`}
                            value={roleValue}
                            checked={isChecked}
                            onChange={(e) => {
                              const updatedDevice = { ...device, network_role: e.target.value, network_role_confirmed: true };
                              setDevices(devices.map(d => d.id === device.id ? updatedDevice : d));
                              fetch(`${apiBase}/api/inventory/${device.ip_address}`, {
                                method: "PUT",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  network_role: e.target.value,
                                  network_role_confirmed: true
                                }),
                              });
                            }}
                            style={{ cursor: "pointer" }}
                          />
                          <span className={`text-sm ${isAutoDetected ? "font-bold" : "font-normal"}`} style={{ color: isAutoDetected ? "#92400e" : "inherit" }}>
                            {role}
                            {isAutoDetected && <span className="text-xs" style={{ marginLeft: "0.25rem", color: "#f59e0b", fontWeight: "bold" }}>*</span>}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </td>
                <td className="vendor-cell">{device.vendor || "-"}</td>
                <td className="snmp-cell">
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
                </td>
                <td className="services-cell">
                  <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                    {device.open_ports &&
                      Object.keys(device.open_ports)
                        .map((port) => {
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
                    <span>Port</span>
                    <input
                      type="number"
                      value={snmpConfig.snmp_port}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_port: parseInt(e.target.value) })}
                    />
                  </label>

                  {(snmpConfig.snmp_version === "1" || snmpConfig.snmp_version === "2c") && (
                    <label>
                      <span>Community String</span>
                      <input
                        type="text"
                        value={snmpConfig.snmp_community}
                        onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_community: e.target.value })}
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
                        <span>Priv Protocol</span>
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
                          <span>Priv Key</span>
                          <input
                            type="password"
                            value={snmpConfig.snmp_priv_key}
                            onChange={(e) => setSnmpConfig({ ...snmpConfig, snmp_priv_key: e.target.value })}
                          />
                        </label>
                      )}
                    </>
                  )}

                  <label>
                    <span>Network Role</span>
                    <select
                      value={snmpConfig.network_role}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, network_role: e.target.value })}
                    >
                      <option value="L3">L3 (Router)</option>
                      <option value="L2">L2 (Switch)</option>
                      <option value="Endpoint">Endpoint</option>
                    </select>
                  </label>

                  <label>
                    <span>MIB</span>
                    <select
                      value={snmpConfig.mib_id || ""}
                      onChange={(e) => setSnmpConfig({ ...snmpConfig, mib_id: e.target.value ? parseInt(e.target.value) : null })}
                    >
                      <option value="">Auto-detect</option>
                      {suggestedMibs.length > 0 && <optgroup label="Suggested">
                        {suggestedMibs.map((mib) => (
                          <option key={mib.id} value={mib.id}>
                            {mib.name} ({mib.vendor})
                          </option>
                        ))}
                      </optgroup>}
                      {allMibs.length > 0 && <optgroup label="All MIBs">
                        {allMibs.map((mib) => (
                          <option key={mib.id} value={mib.id}>
                            {mib.name} ({mib.vendor})
                          </option>
                        ))}
                      </optgroup>}
                    </select>
                  </label>

                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
                    <button onClick={saveSnmpConfig} disabled={saving} className="save-btn">
                      {saving ? "Saving..." : "Save"}
                    </button>
                    <button onClick={handleReassignMib} disabled={saving} className="action-btn">
                      Reassign MIB
                    </button>
                    <button onClick={handleWalkMib} disabled={saving} className="action-btn">
                      Walk MIB
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto" }}>
                {snmpModalDevice.os_name && (
                  <>
                    <h4>OS Detection (Nmap)</h4>
                    <div className="snmp-data-display" style={{ marginBottom: "1.5rem", padding: "1rem", backgroundColor: "#f9fafb", borderRadius: "0.5rem" }}>
                      <div style={{ marginBottom: "0.5rem" }}>
                        <strong>OS:</strong> {snmpModalDevice.os_name}
                        {snmpModalDevice.os_accuracy && <span style={{ marginLeft: "0.5rem", color: "#10b981", fontWeight: "600" }}>({snmpModalDevice.os_accuracy}% accuracy)</span>}
                      </div>
                      {snmpModalDevice.uptime_seconds && (
                        <div style={{ marginBottom: "0.5rem" }}>
                          <strong>Uptime:</strong> {Math.floor(parseInt(snmpModalDevice.uptime_seconds) / 86400)} days
                        </div>
                      )}
                      {snmpModalDevice.nmap_scan_time && (
                        <div style={{ marginBottom: "0.5rem", fontSize: "0.85rem", color: "#6b7280" }}>
                          <strong>Last Scan:</strong> {new Date(snmpModalDevice.nmap_scan_time).toLocaleString()}
                        </div>
                      )}
                      {snmpModalDevice.os_detection && snmpModalDevice.os_detection.length > 0 && (
                        <details style={{ marginTop: "1rem" }}>
                          <summary style={{ cursor: "pointer", fontWeight: "600", color: "#374151" }}>All OS Matches ({snmpModalDevice.os_detection.length})</summary>
                          <div style={{ paddingLeft: "1rem", marginTop: "0.5rem" }}>
                            {renderComplexValue(snmpModalDevice.os_detection)}
                          </div>
                        </details>
                      )}
                    </div>
                  </>
                )}
                
                {snmpModalDevice.host_scripts && snmpModalDevice.host_scripts.length > 0 && (
                  <>
                    <h4>NSE Script Results</h4>
                    <div className="snmp-data-display" style={{ marginBottom: "1.5rem" }}>
                      {snmpModalDevice.host_scripts.map((script: any, idx: number) => (
                        <details key={idx} style={{ marginBottom: "1rem", padding: "0.75rem", backgroundColor: "#fffbeb", borderRadius: "0.5rem", border: "1px solid #fbbf24" }}>
                          <summary style={{ cursor: "pointer", fontWeight: "600", color: "#92400e" }}>
                            {script.id}
                          </summary>
                          <pre style={{ marginTop: "0.5rem", padding: "0.5rem", backgroundColor: "white", borderRadius: "0.25rem", fontSize: "0.85rem", overflow: "auto", maxHeight: "300px" }}>
                            {script.output}
                          </pre>
                        </details>
                      ))}
                    </div>
                  </>
                )}
                
                {snmpModalDevice.open_ports && Object.keys(snmpModalDevice.open_ports).some(port => snmpModalDevice.open_ports![port].scripts) && (
                  <>
                    <h4>Port-Specific Scripts</h4>
                    <div className="snmp-data-display" style={{ marginBottom: "1.5rem" }}>
                      {Object.entries(snmpModalDevice.open_ports).map(([port, portInfo]: [string, any]) => {
                        if (!portInfo.scripts || portInfo.scripts.length === 0) return null;
                        return (
                          <div key={port} style={{ marginBottom: "1rem" }}>
                            <h5 style={{ color: "#1f2937", marginBottom: "0.5rem" }}>Port {port} ({portInfo.service})</h5>
                            {portInfo.scripts.map((script: any, idx: number) => (
                              <details key={idx} style={{ marginBottom: "0.75rem", padding: "0.75rem", backgroundColor: "#fef3c7", borderRadius: "0.5rem" }}>
                                <summary style={{ cursor: "pointer", fontWeight: "600", color: "#78350f" }}>
                                  {script.id}
                                </summary>
                                <pre style={{ marginTop: "0.5rem", padding: "0.5rem", backgroundColor: "white", borderRadius: "0.25rem", fontSize: "0.85rem", overflow: "auto", maxHeight: "200px" }}>
                                  {script.output}
                                </pre>
                              </details>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}

                <h4>SNMP Data</h4>
                {snmpModalDevice.snmp_data ? (
                  <div className="snmp-data-display">
                    {renderComplexValue(snmpModalDevice.snmp_data)}
                  </div>
                ) : (
                  <p style={{ color: "#9ca3af", fontStyle: "italic" }}>No SNMP data available</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default InventoryGrid;
