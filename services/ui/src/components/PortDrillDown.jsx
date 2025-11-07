import React, { useState, useEffect } from 'react'
import './PortDrillDown.css'

const PortDrillDown = ({ edge, onClose }) => {
  const [interfaceData, setInterfaceData] = useState(null)
  const [srcInterface, setSrcInterface] = useState(null)
  const [dstInterface, setDstInterface] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchInterfaceData = async () => {
      if (!edge) return

      try {
        setLoading(true)
        
        const srcDev = edge.source
        const srcIf = edge.data?.a_if
        const dstDev = edge.target
        const dstIf = edge.data?.b_if
        
        setInterfaceData(edge.data)
        
        if (srcDev && srcIf) {
          try {
            const srcResp = await fetch(`/api/topology/interface?device=${encodeURIComponent(srcDev)}&ifname=${encodeURIComponent(srcIf)}`)
            if (srcResp.ok) {
              const srcData = await srcResp.json()
              setSrcInterface(srcData)
            }
          } catch (err) {
            console.warn('Could not fetch source interface details:', err)
          }
        }
        
        if (dstDev && dstIf) {
          try {
            const dstResp = await fetch(`/api/topology/interface?device=${encodeURIComponent(dstDev)}&ifname=${encodeURIComponent(dstIf)}`)
            if (dstResp.ok) {
              const dstData = await dstResp.json()
              setDstInterface(dstData)
            }
          } catch (err) {
            console.warn('Could not fetch destination interface details:', err)
          }
        }
        
        setLoading(false)
      } catch (err) {
        console.error('Error fetching interface data:', err)
        setLoading(false)
      }
    }

    fetchInterfaceData()
  }, [edge])

  if (!edge) return null

  return (
    <div className="port-drilldown">
      <div className="drilldown-header">
        <h3>Port Details</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      {loading ? (
        <div className="drilldown-loading">Loading...</div>
      ) : (
        <div className="drilldown-content">
          <section className="drilldown-section">
            <h4>Connection</h4>
            <div className="info-grid">
              <div className="info-item">
                <label>Source Device:</label>
                <span>{edge.source}</span>
              </div>
              <div className="info-item">
                <label>Source Interface:</label>
                <span>{edge.data?.a_if || 'N/A'}</span>
              </div>
              <div className="info-item">
                <label>Target Device:</label>
                <span>{edge.target}</span>
              </div>
              <div className="info-item">
                <label>Target Interface:</label>
                <span>{edge.data?.b_if || 'N/A'}</span>
              </div>
            </div>
          </section>

          <section className="drilldown-section">
            <h4>Discovery Method</h4>
            <div className="info-grid">
              <div className="info-item">
                <label>Method:</label>
                <span className="method-badge">{edge.data?.method || 'N/A'}</span>
              </div>
              <div className="info-item">
                <label>Confidence:</label>
                <span className={`confidence-badge confidence-${getConfidenceLevel(edge.data?.confidence)}`}>
                  {edge.data?.confidence ? (edge.data.confidence * 100).toFixed(0) + '%' : 'N/A'}
                </span>
              </div>
            </div>
          </section>

          {srcInterface && (
            <section className="drilldown-section">
              <h4>Source Interface Details</h4>
              <div className="info-grid">
                <div className="info-item">
                  <label>Admin Status:</label>
                  <span className={srcInterface.admin_up ? 'status-up' : 'status-down'}>
                    {srcInterface.admin_up ? 'Up' : 'Down'}
                  </span>
                </div>
                <div className="info-item">
                  <label>Oper Status:</label>
                  <span className={srcInterface.oper_up ? 'status-up' : 'status-down'}>
                    {srcInterface.oper_up ? 'Up' : 'Down'}
                  </span>
                </div>
                {srcInterface.speed_mbps && (
                  <div className="info-item">
                    <label>Speed:</label>
                    <span>{srcInterface.speed_mbps} Mbps</span>
                  </div>
                )}
                {srcInterface.vlan && (
                  <div className="info-item">
                    <label>VLAN:</label>
                    <span>{srcInterface.vlan}</span>
                  </div>
                )}
                {srcInterface.l3_addr && (
                  <div className="info-item">
                    <label>IP Address:</label>
                    <span>{srcInterface.l3_addr}</span>
                  </div>
                )}
                {srcInterface.l2_mac && (
                  <div className="info-item">
                    <label>MAC Address:</label>
                    <span>{srcInterface.l2_mac}</span>
                  </div>
                )}
              </div>
            </section>
          )}

          {dstInterface && (
            <section className="drilldown-section">
              <h4>Target Interface Details</h4>
              <div className="info-grid">
                <div className="info-item">
                  <label>Admin Status:</label>
                  <span className={dstInterface.admin_up ? 'status-up' : 'status-down'}>
                    {dstInterface.admin_up ? 'Up' : 'Down'}
                  </span>
                </div>
                <div className="info-item">
                  <label>Oper Status:</label>
                  <span className={dstInterface.oper_up ? 'status-up' : 'status-down'}>
                    {dstInterface.oper_up ? 'Up' : 'Down'}
                  </span>
                </div>
                {dstInterface.speed_mbps && (
                  <div className="info-item">
                    <label>Speed:</label>
                    <span>{dstInterface.speed_mbps} Mbps</span>
                  </div>
                )}
                {dstInterface.vlan && (
                  <div className="info-item">
                    <label>VLAN:</label>
                    <span>{dstInterface.vlan}</span>
                  </div>
                )}
                {dstInterface.l3_addr && (
                  <div className="info-item">
                    <label>IP Address:</label>
                    <span>{dstInterface.l3_addr}</span>
                  </div>
                )}
                {dstInterface.l2_mac && (
                  <div className="info-item">
                    <label>MAC Address:</label>
                    <span>{dstInterface.l2_mac}</span>
                  </div>
                )}
              </div>
            </section>
          )}

          {interfaceData?.evidence && (
            <section className="drilldown-section">
              <h4>Evidence</h4>
              <pre className="evidence-json">
                {JSON.stringify(typeof interfaceData.evidence === 'string' 
                  ? JSON.parse(interfaceData.evidence) 
                  : interfaceData.evidence, null, 2)}
              </pre>
            </section>
          )}

          {interfaceData && (
            <section className="drilldown-section">
              <h4>Timestamps</h4>
              <div className="info-grid">
                <div className="info-item">
                  <label>First Seen:</label>
                  <span>{new Date(interfaceData.first_seen).toLocaleString()}</span>
                </div>
                <div className="info-item">
                  <label>Last Seen:</label>
                  <span>{new Date(interfaceData.last_seen).toLocaleString()}</span>
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}

const getConfidenceLevel = (confidence) => {
  if (!confidence) return 'unknown'
  if (confidence >= 0.9) return 'high'
  if (confidence >= 0.75) return 'medium'
  if (confidence >= 0.6) return 'low'
  return 'very-low'
}

export default PortDrillDown
