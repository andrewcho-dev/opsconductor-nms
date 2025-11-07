import React, { useState, useEffect } from 'react'
import './PathQuery.css'

const PathQuery = () => {
  const [devices, setDevices] = useState([])
  const [sourceDevice, setSourceDevice] = useState('')
  const [targetDevice, setTargetDevice] = useState('')
  const [pathResult, setPathResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const response = await fetch('/api/topology/nodes')
        const data = await response.json()
        setDevices(data)
      } catch (err) {
        console.error('Error fetching devices:', err)
      }
    }
    fetchDevices()
  }, [])

  const handleFindPath = async (e) => {
    e.preventDefault()
    
    if (!sourceDevice || !targetDevice) {
      setError('Please select both source and target devices')
      return
    }

    if (sourceDevice === targetDevice) {
      setError('Source and target devices must be different')
      return
    }

    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`/api/topology/path?src_dev=${encodeURIComponent(sourceDevice)}&dst_dev=${encodeURIComponent(targetDevice)}`)
      
      if (!response.ok) {
        throw new Error('Failed to find path')
      }

      const data = await response.json()
      setPathResult(data)
      setLoading(false)
    } catch (err) {
      console.error('Error finding path:', err)
      setError(err.message)
      setLoading(false)
    }
  }

  const handleClear = () => {
    setSourceDevice('')
    setTargetDevice('')
    setPathResult(null)
    setError(null)
  }

  return (
    <div className="path-query">
      <h3>Path Query</h3>
      
      <form onSubmit={handleFindPath} className="path-form">
        <div className="form-group">
          <label>Source Device:</label>
          <select 
            value={sourceDevice} 
            onChange={(e) => setSourceDevice(e.target.value)}
            disabled={loading}
          >
            <option value="">Select device...</option>
            {devices.map(device => (
              <option key={device.name} value={device.name}>
                {device.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Target Device:</label>
          <select 
            value={targetDevice} 
            onChange={(e) => setTargetDevice(e.target.value)}
            disabled={loading}
          >
            <option value="">Select device...</option>
            {devices.map(device => (
              <option key={device.name} value={device.name}>
                {device.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-actions">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Finding Path...' : 'Find Path'}
          </button>
          <button type="button" onClick={handleClear} disabled={loading} className="btn-secondary">
            Clear
          </button>
        </div>
      </form>

      {error && (
        <div className="path-error">
          {error}
        </div>
      )}

      {pathResult && (
        <div className="path-results">
          <h4>Path Found</h4>
          {pathResult.path && pathResult.path.length > 0 ? (
            <div className="path-hops">
              {pathResult.path.map((hop, index) => (
                <div key={index} className="path-hop">
                  <div className="hop-number">{index + 1}</div>
                  <div className="hop-details">
                    <div className="hop-device">{hop.device}</div>
                    {hop.interface && (
                      <div className="hop-interface">{hop.interface}</div>
                    )}
                    {hop.method && (
                      <div className="hop-metadata">
                        <span className="hop-method">{hop.method}</span>
                        {hop.confidence && (
                          <span className="hop-confidence">
                            {(hop.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  {index < pathResult.path.length - 1 && (
                    <div className="hop-arrow">→</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="no-path">
              No path found between selected devices
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default PathQuery
