import React from 'react'
import TopologyMap from './components/TopologyMap'
import './App.css'

function App() {
  return (
    <div className="app">
      <header className="header">
        <h1>OpsConductor NMS</h1>
        <p>Network Topology & Troubleshooting</p>
      </header>
      <main className="main">
        <TopologyMap />
      </main>
    </div>
  )
}

export default App
