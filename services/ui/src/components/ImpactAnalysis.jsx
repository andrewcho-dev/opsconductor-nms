import React, { useState, useEffect } from 'react'
import './ImpactAnalysis.css'

const ImpactAnalysis = ({ selectedNode, onClose }) => {
  const [impactData, setImpactData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!selectedNode) {
      setImpactData(null)
      return
    }

    const fetchImpact = async () => {
      try {
        setLoading(true)
        setError(null)
        
        const response = await fetch(`/api/topology/impact?node=${encodeURIComponent(selectedNode.id)}`)
        
        if (!response.ok) {
          throw new Error('Failed to fetch impact analysis')
        }

        const data = await response.json()
        setImpactData(data)
        setLoading(false)
      } catch (err) {
        console.error('Error fetching impact:', err)
        setError(err.message)
        setLoading(false)
      }
    }

    fetchImpact()
  }, [selectedNode])

  if (!selectedNode) return null

  return (
    <div className="impact-analysis">
      <div className="impact-header">
        <h3>Impact Analysis</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="impact-device">
        <label>Device:</label>
        <span>{selectedNode.id}</span>
      </div>

      {loading ? (
        <div className="impact-loading">Analyzing impact...</div>
      ) : error ? (
        <div className="impact-error">
          <p>Error: {error}</p>
        </div>
      ) : impactData ? (
        <div className="impact-content">
          <section className="impact-section">
            <h4>Affected Devices</h4>
            {impactData.affected_devices && impactData.affected_devices.length > 0 ? (
              <div className="device-list">
                {impactData.affected_devices.map((device, index) => (
                  <div key={index} className="device-item">
                    <div className="device-icon">🖥️</div>
                    <div className="device-info">
                      <div className="device-name">{device}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-data">No affected devices found</div>
            )}
          </section>

          <section className="impact-section">
            <h4>Summary</h4>
            <div className="impact-summary">
              <div className="summary-item">
                <div className="summary-label">Total Affected Devices:</div>
                <div className="summary-value">
                  {impactData.affected_count || 0}
                </div>
              </div>
            </div>
          </section>
        </div>
      ) : (
        <div className="no-data">No impact data available</div>
      )}
    </div>
  )
}

export default ImpactAnalysis
