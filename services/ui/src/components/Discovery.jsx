import React, { useState, useEffect } from 'react';
import './Discovery.css';

const Discovery = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [networkCidr, setNetworkCidr] = useState('');
    const [scans, setScans] = useState([]);
    const [devices, setDevices] = useState([]);
    const [selectedDevices, setSelectedDevices] = useState([]);
    const [activeTab, setActiveTab] = useState('scans');
    const [loading, setLoading] = useState(false);
    const [rescanning, setRescanning] = useState(false);
    const [error, setError] = useState(null);

    const fetchScans = async () => {
        try {
            const response = await fetch('/api/discovery/scans');
            const data = await response.json();
            setScans(data);
        } catch (err) {
            setError('Failed to fetch scans');
        }
    };

    const fetchDevices = async () => {
        try {
            const response = await fetch('/api/discovery/devices?limit=500');
            const data = await response.json();
            setDevices(data);
        } catch (err) {
            setError('Failed to fetch devices');
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchScans();
            fetchDevices();
            const interval = setInterval(() => {
                fetchScans();
                fetchDevices();
            }, 5000);
            return () => clearInterval(interval);
        }
    }, [isOpen]);

    const startScan = async () => {
        if (!networkCidr) {
            setError('Please enter a network CIDR');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch('/api/discovery/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    network_cidr: networkCidr,
                    scan_ping: true,
                    scan_ssh: true,
                    scan_snmp: true,
                    scan_https: true
                })
            });

            if (response.ok) {
                const data = await response.json();
                setNetworkCidr('');
                fetchScans();
                setActiveTab('scans');
            } else {
                setError('Failed to start scan');
            }
        } catch (err) {
            setError('Error starting scan: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    const importDevices = async () => {
        if (selectedDevices.length === 0) {
            setError('Please select devices to import');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch('/api/discovery/devices/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ips: selectedDevices,
                    import_to_suzieq: false,
                    import_to_snmp_poller: false
                })
            });

            if (response.ok) {
                const data = await response.json();
                setSelectedDevices([]);
                fetchDevices();
                alert(`Imported ${data.imported_count} devices`);
            } else {
                setError('Failed to import devices');
            }
        } catch (err) {
            setError('Error importing devices: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    const rescanDevices = async () => {
        if (selectedDevices.length === 0) {
            setError('Please select devices to rescan');
            return;
        }

        setLoading(true);
        setRescanning(true);
        setError(null);

        try {
            const response = await fetch('/api/discovery/devices/rescan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ips: selectedDevices
                })
            });

            if (response.ok) {
                const data = await response.json();
                setSelectedDevices([]);
                setLoading(false);
                
                setTimeout(() => {
                    fetchDevices();
                }, 3000);
                
                setTimeout(() => {
                    setRescanning(false);
                }, 10000);
            } else {
                setError('Failed to request rescan');
                setRescanning(false);
            }
        } catch (err) {
            setError('Error requesting rescan: ' + err.message);
            setRescanning(false);
        } finally {
            setLoading(false);
        }
    };

    const toggleDeviceSelection = (ip) => {
        setSelectedDevices(prev =>
            prev.includes(ip) ? prev.filter(i => i !== ip) : [...prev, ip]
        );
    };

    return (
        <>
            <button className="discovery-open-btn" onClick={() => setIsOpen(true)}>
                🔍 Network Discovery
            </button>

            {isOpen && (
                <div className="discovery-modal-overlay" onClick={() => setIsOpen(false)}>
                    <div className="discovery-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="discovery-modal-header">
                            <h2>Network Discovery</h2>
                            <button className="close-btn" onClick={() => setIsOpen(false)}>×</button>
                        </div>

                        <div className="discovery-modal-body">
                            <div className="scan-form">
                                <input
                                    type="text"
                                    placeholder="Network CIDR (e.g., 10.121.19.0/24)"
                                    value={networkCidr}
                                    onChange={(e) => setNetworkCidr(e.target.value)}
                                    onKeyPress={(e) => e.key === 'Enter' && startScan()}
                                    disabled={loading}
                                />
                                <button onClick={startScan} disabled={loading}>
                                    {loading ? 'Scanning...' : 'Start Scan'}
                                </button>
                            </div>

                            {error && <div className="error-message">{error}</div>}

                            <div className="tabs">
                                <button
                                    className={activeTab === 'scans' ? 'active' : ''}
                                    onClick={() => setActiveTab('scans')}
                                >
                                    Scans ({scans.length})
                                </button>
                                <button
                                    className={activeTab === 'devices' ? 'active' : ''}
                                    onClick={() => setActiveTab('devices')}
                                >
                                    Discovered Devices ({devices.filter(d => d.discovery_status === 'reachable' || d.discovery_status === 'online').length})
                                </button>
                            </div>

                            {activeTab === 'scans' && (
                                <div className="scans-table">
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>Network</th>
                                                <th>Status</th>
                                                <th>Found</th>
                                                <th>Reachable</th>
                                                <th>Started</th>
                                                <th>Completed</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {scans.map(scan => (
                                                <tr key={scan.id}>
                                                    <td>{scan.network_cidr}</td>
                                                    <td>
                                                        <span className={`status-badge status-${scan.status}`}>
                                                            {scan.status}
                                                        </span>
                                                    </td>
                                                    <td>{scan.devices_found || 0}</td>
                                                    <td>{scan.devices_reachable || 0}</td>
                                                    <td>{scan.started_at ? new Date(scan.started_at).toLocaleString() : '-'}</td>
                                                    <td>{scan.completed_at ? new Date(scan.completed_at).toLocaleString() : '-'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}

                            {activeTab === 'devices' && (
                                <div className="devices-section">
                                    {rescanning && (
                                        <div className="rescan-status">
                                            <span>⏳ Rescanning devices... Results will update shortly.</span>
                                        </div>
                                    )}
                                    <div className="devices-actions">
                                        <button
                                            onClick={importDevices}
                                            disabled={selectedDevices.length === 0 || loading}
                                        >
                                            Import Selected ({selectedDevices.length})
                                        </button>
                                        <button
                                            onClick={rescanDevices}
                                            disabled={selectedDevices.length === 0 || loading}
                                            className="rescan-btn"
                                        >
                                            {loading ? 'Rescanning...' : `Rescan Selected (${selectedDevices.length})`}
                                        </button>
                                    </div>

                                    <div className="devices-table">
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>
                                                        <input
                                                            type="checkbox"
                                                            onChange={(e) => {
                                                                if (e.target.checked) {
                                                                    setSelectedDevices(
                                                                        devices
                                                                            .filter(d => (d.discovery_status === 'reachable' || d.discovery_status === 'online') && !d.imported)
                                                                            .map(d => d.ip)
                                                                    );
                                                                } else {
                                                                    setSelectedDevices([]);
                                                                }
                                                            }}
                                                        />
                                                    </th>
                                                    <th>IP Address</th>
                                                    <th>Vendor</th>
                                                    <th>Status</th>
                                                    <th>Ping</th>
                                                    <th>SSH</th>
                                                    <th>SNMP</th>
                                                    <th>HTTPS</th>
                                                    <th>Discovered</th>
                                                    <th>Imported</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {devices.map(device => (
                                                    <tr key={device.ip} className={device.imported ? 'imported' : device.discovery_status === 'reachable' ? 'device-reachable' : device.discovery_status === 'online' ? 'device-online' : ''}>
                                                        <td>
                                                            <input
                                                                type="checkbox"
                                                                checked={selectedDevices.includes(device.ip)}
                                                                onChange={() => toggleDeviceSelection(device.ip)}
                                                                disabled={device.imported || (device.discovery_status !== 'reachable' && device.discovery_status !== 'online')}
                                                            />
                                                        </td>
                                                        <td>{device.ip}</td>
                                                        <td>{device.vendor || '-'}</td>
                                                        <td>
                                                            <span className={`status-badge status-${device.discovery_status}`}>
                                                                {device.discovery_status}
                                                            </span>
                                                        </td>
                                                        <td>{device.ping_reachable ? '✓' : '✗'}</td>
                                                        <td>{device.ssh_reachable ? '✓' : '✗'}</td>
                                                        <td>{device.snmp_reachable ? '✓' : '✗'}</td>
                                                        <td>{device.https_reachable ? '✓' : '✗'}</td>
                                                        <td>{device.discovered_at ? new Date(device.discovered_at).toLocaleString() : '-'}</td>
                                                        <td>{device.imported ? '✓' : ''}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default Discovery;
