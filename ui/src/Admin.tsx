import { useState, useEffect } from "react";

interface AdminProps {
  apiBase: string;
}

interface OUIStatus {
  status: string;
  oui_entries: number;
  oui_file: string;
  oui_exists: boolean;
  oui_age_days: number | null;
}

interface MIB {
  id: number;
  name: string;
  vendor: string;
  device_types: string[];
  version: string;
  file_path: string;
  oid_prefix?: string;
  description: string;
  uploaded_at: string;
}

function Admin({ apiBase }: AdminProps) {
  const [ouiStatus, setOuiStatus] = useState<OUIStatus | null>(null);
  const [ouiLoading, setOuiLoading] = useState(false);
  const [ouiMessage, setOuiMessage] = useState("");
  
  const [mibs, setMibs] = useState<MIB[]>([]);
  const [mibsLoading, setMibsLoading] = useState(false);
  const [uploadingMib, setUploadingMib] = useState(false);
  const [mibMessage, setMibMessage] = useState("");
  
  const [newMib, setNewMib] = useState({
    name: "",
    vendor: "",
    device_types: "",
    version: "",
    file_path: "",
    oid_prefix: "",
    description: ""
  });

  const [terminalType, setTerminalType] = useState(
    localStorage.getItem('terminalType') || 'native'
  );
  const [terminalMessage, setTerminalMessage] = useState("");

  const handleSaveTerminalSettings = () => {
    localStorage.setItem('terminalType', terminalType);
    setTerminalMessage("Terminal settings saved successfully");
    setTimeout(() => setTerminalMessage(""), 3000);
  };

  const macEnricherUrl = apiBase.replace(':8080', ':9400');

  useEffect(() => {
    fetchOUIStatus();
    fetchMIBs();
  }, []);

  const fetchOUIStatus = async () => {
    try {
      const response = await fetch(`${macEnricherUrl}/health`);
      if (response.ok) {
        const data = await response.json();
        setOuiStatus(data);
      }
    } catch (err) {
      console.error("Failed to fetch OUI status:", err);
    }
  };

  const fetchMIBs = async () => {
    setMibsLoading(true);
    try {
      const response = await fetch(`${apiBase}/api/mibs`);
      if (response.ok) {
        const data = await response.json();
        setMibs(data);
      }
    } catch (err) {
      console.error("Failed to fetch MIBs:", err);
    } finally {
      setMibsLoading(false);
    }
  };

  const updateOUI = async () => {
    setOuiLoading(true);
    setOuiMessage("");
    try {
      const response = await fetch(`${macEnricherUrl}/update`, {
        method: "POST"
      });
      if (response.ok) {
        const data = await response.json();
        setOuiMessage(`Updated successfully: ${data.entries} entries`);
        fetchOUIStatus();
      } else {
        setOuiMessage("Update failed");
      }
    } catch (err) {
      setOuiMessage("Update failed: " + (err as Error).message);
    } finally {
      setOuiLoading(false);
    }
  };

  const handleAddMib = async () => {
    if (!newMib.name || !newMib.vendor || !newMib.file_path) {
      setMibMessage("Name, Vendor, and File Path are required");
      return;
    }

    setUploadingMib(true);
    setMibMessage("");
    
    try {
      const payload = {
        ...newMib,
        device_types: newMib.device_types.split(",").map(t => t.trim()).filter(Boolean),
        oid_prefix: newMib.oid_prefix || undefined
      };

      const response = await fetch(`${apiBase}/api/mibs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        setMibMessage("MIB added successfully");
        setNewMib({
          name: "",
          vendor: "",
          device_types: "",
          version: "",
          file_path: "",
          oid_prefix: "",
          description: ""
        });
        fetchMIBs();
      } else {
        const error = await response.text();
        setMibMessage(`Failed to add MIB: ${error}`);
      }
    } catch (err) {
      setMibMessage("Failed to add MIB: " + (err as Error).message);
    } finally {
      setUploadingMib(false);
    }
  };

  const handleDeleteMib = async (mibId: number) => {
    if (!confirm("Are you sure you want to delete this MIB?")) {
      return;
    }

    try {
      const response = await fetch(`${apiBase}/api/mibs/${mibId}`, {
        method: "DELETE"
      });

      if (response.ok) {
        setMibMessage("MIB deleted successfully");
        fetchMIBs();
      } else {
        setMibMessage("Failed to delete MIB");
      }
    } catch (err) {
      setMibMessage("Failed to delete MIB: " + (err as Error).message);
    }
  };



  return (
    <div className="admin-container">
      <div className="admin-header">
        <h1>System Administration</h1>
      </div>

      <div className="admin-content">
        <section className="admin-section">
          <h2>OUI Database Management</h2>
          
          {ouiStatus && (
            <div className="status-panel">
              <div className="status-row">
                <span className="status-label">Status:</span>
                <span className="status-value">{ouiStatus.status}</span>
              </div>
              <div className="status-row">
                <span className="status-label">Entries:</span>
                <span className="status-value">{ouiStatus.oui_entries?.toLocaleString() || "0"}</span>
              </div>
              <div className="status-row">
                <span className="status-label">File:</span>
                <span className="status-value mono">{ouiStatus.oui_file}</span>
              </div>
              <div className="status-row">
                <span className="status-label">Exists:</span>
                <span className="status-value">{ouiStatus.oui_exists ? "Yes" : "No"}</span>
              </div>
              {ouiStatus.oui_age_days && (
                <div className="status-row">
                  <span className="status-label">Age:</span>
                  <span className="status-value">
                    {ouiStatus.oui_age_days.toFixed(1)} days
                    {ouiStatus.oui_age_days > 90 && (
                      <span className="warning-text"> (Consider updating)</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="action-panel">
            <button 
              className="action-button" 
              onClick={updateOUI}
              disabled={ouiLoading}
            >
              {ouiLoading ? "Updating..." : "Update OUI Database"}
            </button>
            {ouiMessage && <div className="message">{ouiMessage}</div>}
          </div>
        </section>

<section className="admin-section">
          <h2>Terminal Launch Settings</h2>
          <p style={{ color: "#6b7280", marginBottom: "1rem" }}>
            Configure how SSH and Telnet connections are launched when clicking port badges.
          </p>
          
          <div className="form-grid" style={{ maxWidth: "700px" }}>
            <div className="form-field full-width">
              <label>Terminal Launch Method</label>
              <select
                value={terminalType}
                onChange={e => setTerminalType(e.target.value)}
                style={{ padding: "0.5rem", fontSize: "1rem" }}
              >
                <option value="native">Show Connection Info (Copy to Clipboard)</option>
                <option value="url">Use URL Protocol (ssh:// or telnet://)</option>
                <option value="putty">PuTTY Protocol Handler (Windows)</option>
              </select>
              <small style={{ color: "#6b7280", fontSize: "0.875rem", marginTop: "0.5rem", display: "block" }}>
                <strong>Show Connection Info:</strong> Displays connection details and copies the command to clipboard<br/>
                <strong>Use URL Protocol:</strong> Attempts to open ssh:// or telnet:// URLs (requires protocol handler installed)<br/>
                <strong>PuTTY Protocol:</strong> Uses putty:// protocol (requires PuTTY with protocol handler registered)
              </small>
            </div>

            <div className="form-field full-width" style={{ 
              backgroundColor: "#f0f9ff", 
              border: "1px solid #0284c7",
              borderRadius: "4px",
              padding: "1rem",
              marginTop: "1rem"
            }}>
              <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem", color: "#0369a1" }}>
                📝 Setup Instructions
              </h3>
              
              {terminalType === 'native' && (
                <div style={{ fontSize: "0.875rem", color: "#0c4a6e" }}>
                  <p><strong>Default Method - No Setup Required</strong></p>
                  <p>When you click an SSH or Telnet badge:</p>
                  <ul style={{ marginLeft: "1.5rem", marginTop: "0.5rem" }}>
                    <li>A dialog shows connection details</li>
                    <li>Click OK to copy the command to clipboard</li>
                    <li>Paste into your preferred terminal</li>
                  </ul>
                </div>
              )}
              
              {terminalType === 'url' && (
                <div style={{ fontSize: "0.875rem", color: "#0c4a6e" }}>
                  <p><strong>URL Protocol Method</strong></p>
                  <p>Requires a protocol handler installed on your system:</p>
                  <ul style={{ marginLeft: "1.5rem", marginTop: "0.5rem" }}>
                    <li><strong>macOS/Linux:</strong> Most terminals support ssh:// by default</li>
                    <li><strong>Windows:</strong> Install a handler like <a href="https://github.com/PowerShell/Win32-OpenSSH" target="_blank" style={{ color: "#0369a1", textDecoration: "underline" }}>Win32-OpenSSH</a></li>
                    <li>Some browsers may require permission to open external protocols</li>
                  </ul>
                </div>
              )}
              
              {terminalType === 'putty' && (
                <div style={{ fontSize: "0.875rem", color: "#0c4a6e" }}>
                  <p><strong>PuTTY Protocol Method (Windows)</strong></p>
                  <p>Steps to enable:</p>
                  <ol style={{ marginLeft: "1.5rem", marginTop: "0.5rem" }}>
                    <li>Install PuTTY from <a href="https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html" target="_blank" style={{ color: "#0369a1", textDecoration: "underline" }}>official site</a></li>
                    <li>Run this in Command Prompt (as Administrator):
                      <pre style={{ 
                        backgroundColor: "#1e293b", 
                        color: "#e2e8f0", 
                        padding: "0.5rem", 
                        borderRadius: "4px",
                        marginTop: "0.5rem",
                        fontSize: "0.8rem",
                        overflowX: "auto"
                      }}>
{`reg add HKCR\putty /ve /d "URL:PuTTY Protocol" /f
reg add HKCR\putty /v "URL Protocol" /d "" /f
reg add HKCR\putty\shell\open\command /ve /d "\"C:\Program Files\PuTTY\putty.exe\" %1" /f`}
                      </pre>
                    </li>
                    <li>Restart your browser</li>
                  </ol>
                </div>
              )}
            </div>
          </div>
          
          <div className="action-panel">
            <button 
              className="action-button"
              onClick={handleSaveTerminalSettings}
            >
              Save Terminal Settings
            </button>
            {terminalMessage && <div className="message">{terminalMessage}</div>}
          </div>
        </section>

        <section className="admin-section">
          <h2>Vendor MIB Management</h2>
          
          <div className="mib-form">
            <h3>Add New MIB</h3>
            <div className="form-grid">
              <div className="form-field">
                <label>Name *</label>
                <input
                  type="text"
                  value={newMib.name}
                  onChange={e => setNewMib({...newMib, name: e.target.value})}
                  placeholder="CISCO-PROCESS-MIB"
                />
              </div>
              <div className="form-field">
                <label>Vendor *</label>
                <input
                  type="text"
                  value={newMib.vendor}
                  onChange={e => setNewMib({...newMib, vendor: e.target.value})}
                  placeholder="Cisco"
                />
              </div>
              <div className="form-field">
                <label>Device Types (comma-separated)</label>
                <input
                  type="text"
                  value={newMib.device_types}
                  onChange={e => setNewMib({...newMib, device_types: e.target.value})}
                  placeholder="router, switch, network_device"
                />
              </div>
              <div className="form-field">
                <label>Version</label>
                <input
                  type="text"
                  value={newMib.version}
                  onChange={e => setNewMib({...newMib, version: e.target.value})}
                  placeholder="1.0"
                />
              </div>
              <div className="form-field full-width">
                <label>File Path *</label>
                <input
                  type="text"
                  value={newMib.file_path}
                  onChange={e => setNewMib({...newMib, file_path: e.target.value})}
                  placeholder="/usr/share/snmp/mibs/cisco/CISCO-PROCESS-MIB"
                />
              </div>
              <div className="form-field full-width">
                <label>OID Prefix</label>
                <input
                  type="text"
                  value={newMib.oid_prefix}
                  onChange={e => setNewMib({...newMib, oid_prefix: e.target.value})}
                  placeholder="1.3.6.1.4.1.9"
                />
              </div>
              <div className="form-field full-width">
                <label>Description</label>
                <textarea
                  value={newMib.description}
                  onChange={e => setNewMib({...newMib, description: e.target.value})}
                  placeholder="Cisco CPU and process utilization"
                  rows={2}
                />
              </div>
            </div>
            <div className="action-panel">
              <button 
                className="action-button"
                onClick={handleAddMib}
                disabled={uploadingMib}
              >
                {uploadingMib ? "Adding..." : "Add MIB"}
              </button>
              {mibMessage && <div className="message">{mibMessage}</div>}
            </div>
          </div>

          <div className="mib-list">
            <h3>Installed MIBs ({mibs.length})</h3>
            {mibsLoading ? (
              <div className="loading">Loading MIBs...</div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Vendor</th>
                    <th>Device Types</th>
                    <th>Version</th>
                    <th>Description</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mibs.map(mib => (
                    <tr key={mib.id}>
                      <td className="mono">{mib.name}</td>
                      <td>{mib.vendor}</td>
                      <td>{mib.device_types.join(", ")}</td>
                      <td>{mib.version}</td>
                      <td className="description-cell">{mib.description}</td>
                      <td>
                        <button
                          className="delete-button"
                          onClick={() => handleDeleteMib(mib.id)}
                          title="Delete MIB"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default Admin;
