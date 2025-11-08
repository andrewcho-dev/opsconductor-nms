import React, { useState, useEffect } from 'react'
import '../styles/Settings.css'

function Settings() {
  const [config, setConfig] = useState({
    poll_networks: '',
    skip_networks: '',
    poll_enabled: true
  })
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/settings/polling')
      if (!response.ok) throw new Error('Failed to fetch config')
      const data = await response.json()
      setConfig(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setConfig(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }))
    setSaved(false)
  }

  const handleSave = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/settings/polling', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      if (!response.ok) throw new Error('Failed to save config')
      const data = await response.json()
      setConfig(data)
      setSaved(true)
      setError(null)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="settings-panel">
      <h2>Polling Configuration</h2>
      
      {error && <div className="error-message">{error}</div>}
      {saved && <div className="success-message">Configuration saved successfully</div>}
      
      <div className="settings-form">
        <div className="form-group">
          <label htmlFor="poll_enabled">
            <input
              type="checkbox"
              id="poll_enabled"
              name="poll_enabled"
              checked={config.poll_enabled}
              onChange={handleChange}
              disabled={loading}
            />
            Enable Polling
          </label>
          <p className="help-text">Enable or disable all SNMP polling</p>
        </div>

        <div className="form-group">
          <label htmlFor="poll_networks">Poll Networks</label>
          <textarea
            id="poll_networks"
            name="poll_networks"
            value={config.poll_networks}
            onChange={handleChange}
            disabled={loading}
            placeholder="10.121.40.0/24&#10;10.121.50.0/24"
            rows="4"
          />
          <p className="help-text">
            Comma-separated or line-separated CIDR networks to include in polling.
            If empty, all networks will be polled (except those in Skip Networks).
          </p>
          <p className="help-text">Example: 10.121.40.0/24,10.121.50.0/24</p>
        </div>

        <div className="form-group">
          <label htmlFor="skip_networks">Skip Networks</label>
          <textarea
            id="skip_networks"
            name="skip_networks"
            value={config.skip_networks}
            onChange={handleChange}
            disabled={loading}
            placeholder="10.121.19.0/24"
            rows="4"
          />
          <p className="help-text">
            Comma-separated or line-separated CIDR networks to exclude from polling.
          </p>
          <p className="help-text">Example: 10.121.19.0/24,10.121.100.0/24</p>
        </div>

        <div className="form-actions">
          <button
            onClick={handleSave}
            disabled={loading}
            className="save-button"
          >
            {loading ? 'Saving...' : 'Save Configuration'}
          </button>
          <button
            onClick={fetchConfig}
            disabled={loading}
            className="reload-button"
          >
            {loading ? 'Loading...' : 'Reload'}
          </button>
        </div>

        <div className="info-box">
          <h3>How it works:</h3>
          <ul>
            <li>If <strong>Poll Networks</strong> is set, only devices in those networks will be polled</li>
            <li>If <strong>Skip Networks</strong> is set, devices in those networks will be excluded</li>
            <li>Devices must have <code>polling_enabled=TRUE</code> and <code>snmp_polling_enabled=TRUE</code> in the database</li>
            <li>Changes take effect on the next polling cycle</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default Settings
