import { useState, useEffect } from "react";

interface AdminProps {
  apiBase: string;
  onBack: () => void;
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

function Admin({ apiBase, onBack }: AdminProps) {
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
        <button className="back-button" onClick={onBack}>
          ← Back to Inventory
        </button>
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
                <span className="status-value">{ouiStatus.oui_entries.toLocaleString()}</span>
              </div>
              <div className="status-row">
                <span className="status-label">File:</span>
                <span className="status-value mono">{ouiStatus.oui_file}</span>
              </div>
              <div className="status-row">
                <span className="status-label">Exists:</span>
                <span className="status-value">{ouiStatus.oui_exists ? "Yes" : "No"}</span>
              </div>
              {ouiStatus.oui_age_days !== null && (
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
