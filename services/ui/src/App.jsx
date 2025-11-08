import React, { useState, useCallback } from 'react'
import TopologyMap from './components/TopologyMap'
import PortDrillDown from './components/PortDrillDown'
import PathQuery from './components/PathQuery'
import ImpactAnalysis from './components/ImpactAnalysis'
import './App.css'

function App() {
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [activePanel, setActivePanel] = useState('topology')

  const handleEdgeSelect = useCallback((edge) => {
    setSelectedEdge(edge)
    setSelectedNode(null)
  }, [])

  const handleNodeSelect = useCallback((node) => {
    setSelectedNode(node)
    setSelectedEdge(null)
  }, [])

  const handleClosePanel = () => {
    setSelectedEdge(null)
    setSelectedNode(null)
  }

  return (
    <div className="app">
      <header className="header">
        <h1>OpsConductor NMS</h1>
        <p>Network Topology & Troubleshooting</p>
        <nav className="nav-tabs">
          <button 
            className={activePanel === 'topology' ? 'active' : ''} 
            onClick={() => setActivePanel('topology')}
          >
            Topology
          </button>
          <button 
            className={activePanel === 'path' ? 'active' : ''} 
            onClick={() => setActivePanel('path')}
          >
            Path Query
          </button>
        </nav>
      </header>
      <main className="main">
        {activePanel === 'topology' && (
          <>
            <TopologyMap 
              onEdgeSelect={handleEdgeSelect}
              onNodeSelect={handleNodeSelect}
            />
            {selectedEdge && (
              <PortDrillDown 
                edge={selectedEdge} 
                onClose={handleClosePanel} 
              />
            )}
            {selectedNode && (
              <ImpactAnalysis 
                selectedNode={selectedNode} 
                onClose={handleClosePanel} 
              />
            )}
          </>
        )}
        {activePanel === 'path' && (
          <div className="panel-container">
            <PathQuery />
          </div>
        )}
      </main>
    </div>
  )
}

export default App
