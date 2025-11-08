import React, { useEffect, useState, useCallback } from 'react'
import ReactFlow, {
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  MiniMap,
} from 'reactflow'
import 'reactflow/dist/style.css'
import ELK from 'elkjs/lib/elk.bundled.js'
import './TopologyMap.css'

const elk = new ELK()

const getElkOptions = (algorithm, direction) => {
  const baseOptions = {
    'elk.algorithm': algorithm,
    'elk.spacing.nodeNode': '80',
    'elk.direction': direction,
  }

  if (algorithm === 'layered') {
    return {
      ...baseOptions,
      'elk.layered.spacing.nodeNodeBetweenLayers': '100',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
    }
  }

  return baseOptions
}

const sortNodes = (nodes, sortBy) => {
  if (sortBy === 'none') return nodes

  return [...nodes].sort((a, b) => {
    if (sortBy === 'ip') {
      const ipA = a.id.split('.').map(Number)
      const ipB = b.id.split('.').map(Number)
      for (let i = 0; i < 4; i++) {
        if (ipA[i] !== ipB[i]) return ipA[i] - ipB[i]
      }
      return 0
    }
    if (sortBy === 'name') {
      return a.id.localeCompare(b.id)
    }
    return 0
  })
}


const isIpInSubnet = (ip, subnet) => {
  if (!subnet || subnet.trim() === '') return true
  
  const [subnetIp, maskBits] = subnet.split('/')
  if (!maskBits) return true
  
  const ipParts = ip.split('.').map(Number)
  const subnetParts = subnetIp.split('.').map(Number)
  
  if (ipParts.length !== 4 || subnetParts.length !== 4) return false
  if (ipParts.some(isNaN) || subnetParts.some(isNaN)) return false
  
  const mask = parseInt(maskBits, 10)
  let bitsToCheck = mask
  
  for (let i = 0; i < 4; i++) {
    if (bitsToCheck >= 8) {
      if (ipParts[i] !== subnetParts[i]) return false
      bitsToCheck -= 8
    } else if (bitsToCheck > 0) {
      const maskValue = 256 - Math.pow(2, 8 - bitsToCheck)
      if ((ipParts[i] & maskValue) !== (subnetParts[i] & maskValue)) return false
      break
    }
  }
  return true
}

const getLayoutedElements = async (nodes, edges, algorithm, direction, sortBy) => {
  const sortedNodes = sortNodes(nodes, sortBy)
  
  const graph = {
    id: 'root',
    layoutOptions: getElkOptions(algorithm, direction),
    children: sortedNodes.map((node) => ({
      id: node.id,
      width: 180,
      height: 60,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  }

  const layoutedGraph = await elk.layout(graph)

  const layoutedNodes = sortedNodes.map((node) => {
    const layoutedNode = layoutedGraph.children.find((n) => n.id === node.id)
    return {
      ...node,
      position: { x: layoutedNode.x, y: layoutedNode.y },
    }
  })

  return { nodes: layoutedNodes, edges }
}

const getEdgeColor = (confidence) => {
  if (confidence >= 0.9) return '#22c55e'
  if (confidence >= 0.75) return '#eab308'
  if (confidence >= 0.6) return '#f97316'
  return '#ef4444'
}

const TopologyMap = ({ onEdgeSelect, onNodeSelect }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [layoutAlgorithm, setLayoutAlgorithm] = useState('layered')
  const [layoutDirection, setLayoutDirection] = useState('DOWN')
  const [nodeSorting, setNodeSorting] = useState('ip')
  const [subnetFilterInput, setSubnetFilterInput] = useState('')
  const [subnetFilter, setSubnetFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [theme, setTheme] = useState('light')

  const applySubnetFilter = () => {
    console.log('Applying subnet filter:', subnetFilterInput)
    setNodes([])
    setEdges([])
    setSubnetFilter(subnetFilterInput)
  }

  const handleFilterKeyPress = (e) => {
    if (e.key === 'Enter') {
      applySubnetFilter()
    }
  }

  const fetchTopology = useCallback(async () => {
    try {
      setLoading(true)
      
      const [devicesRes, edgesRes] = await Promise.all([
        fetch('/api/topology/nodes'),
        fetch('/api/topology/edges/enriched'),
      ])

      if (!devicesRes.ok || !edgesRes.ok) {
        throw new Error('Failed to fetch topology data')
      }

      const devices = await devicesRes.json()
      const topologyEdges = await edgesRes.json()

      console.log('Filtering devices with subnet:', subnetFilter)
      const filteredDevices = devices.filter(device => isIpInSubnet(device.name, subnetFilter))
      console.log('Filtered devices count:', filteredDevices.length, 'out of', devices.length)
      
      const flowNodes = filteredDevices.map((device) => ({
        id: device.name,
        type: 'simplebezier',
        data: {
          label: (
            <div className="node-content">
              <div className="node-name">{device.name}</div>
              <div className="node-details">
                {device.vendor && device.vendor !== 'Unknown' && device.vendor !== 'N/A' && <span>{device.vendor}</span>}
                {device.model && device.model !== 'Unknown' && device.model !== 'N/A' && <span>{device.model}</span>}
              </div>
            </div>
          ),
        },
        position: { x: 0, y: 0 },
      }))

      const visibleNodeIds = new Set(filteredDevices.map(d => d.name))
      const filteredEdges = topologyEdges.filter(edge => 
        visibleNodeIds.has(edge.a_dev) && visibleNodeIds.has(edge.b_dev)
      )
      
      const flowEdges = filteredEdges.map((edge) => {
        const hasFlow = edge.flow_detected || false
        const utilization = edge.utilization_bps || 0
        const utilizationMbps = (utilization / 1000000).toFixed(2)
        
        let edgeLabel = edge.method
        if (hasFlow && utilization > 0) {
          edgeLabel = `${edge.method} (${utilizationMbps} Mbps)`
        } else if (hasFlow) {
          edgeLabel = `${edge.method} ✓`
        }
        
        return {
          id: `${edge.edge_id}`,
          source: edge.a_dev,
          target: edge.b_dev,
          label: edgeLabel,
          type: 'simplebezier',
          style: {
            stroke: hasFlow ? '#22c55e' : getEdgeColor(edge.confidence),
            strokeWidth: hasFlow ? 3 : 2,
            strokeDasharray: hasFlow ? 'none' : '5, 5',
          },
          data: {
            confidence: edge.confidence,
            method: edge.method,
            a_if: edge.a_if,
            b_if: edge.b_if,
            flow_detected: hasFlow,
            utilization_bps: utilization,
            first_seen: edge.first_seen,
            last_seen: edge.last_seen,
            evidence: edge.evidence,
          },
        }
      })

      const { nodes: layoutedNodes, edges: layoutedEdges } = await getLayoutedElements(
        flowNodes,
        flowEdges,
        layoutAlgorithm,
        layoutDirection,
        nodeSorting
      )

      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
      setLoading(false)
    } catch (err) {
      console.error('Error fetching topology:', err)
      setError(err.message)
      setLoading(false)
    }
  }, [layoutAlgorithm, layoutDirection, nodeSorting, subnetFilter])

  useEffect(() => {
    fetchTopology()
  }, [fetchTopology])

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchTopology, 60000)
      return () => clearInterval(interval)
    }
  }, [fetchTopology, autoRefresh])

  const handleEdgeClick = useCallback((event, edge) => {
    if (onEdgeSelect) {
      onEdgeSelect(edge)
    }
  }, [onEdgeSelect])

  const handleNodeClick = useCallback((event, node) => {
    if (onNodeSelect) {
      onNodeSelect(node)
    }
  }, [onNodeSelect])

  if (loading) {
    return (
      <div className="topology-loading">
        <div className="spinner"></div>
        <p>Loading topology...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="topology-error">
        <p>Error loading topology: {error}</p>
        <button onClick={fetchTopology}>Retry</button>
      </div>
    )
  }

  if (nodes.length === 0) {
    return (
      <div className="topology-empty">
        <h3>No topology data available</h3>
        <p>Add devices to the inventory to start discovering topology</p>
      </div>
    )
  }

  return (
    <div className="topology-map" data-theme={theme}>
      <div className="topology-controls">
        <div className="control-group">
          <label>Theme:</label>
          <select value={theme} onChange={(e) => setTheme(e.target.value)}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="blue">Blue</option>
            <option value="forest">Forest</option>
            <option value="slate">Slate</option>
          </select>
        </div>
        <div className="control-group">
          <label>Layout:</label>
          <select value={layoutAlgorithm} onChange={(e) => setLayoutAlgorithm(e.target.value)}>
            <option value="layered">Layered (Hierarchical)</option>
            <option value="force">Force-Directed</option>
            <option value="stress">Stress Minimization</option>
            <option value="mrtree">Tree</option>
            <option value="radial">Radial</option>
          </select>
        </div>
        <div className="control-group">
          <label>Direction:</label>
          <select value={layoutDirection} onChange={(e) => setLayoutDirection(e.target.value)}>
            <option value="DOWN">Top to Bottom</option>
            <option value="UP">Bottom to Top</option>
            <option value="RIGHT">Left to Right</option>
            <option value="LEFT">Right to Left</option>
          </select>
        </div>
        <div className="control-group">
          <label>Sort By:</label>
          <select value={nodeSorting} onChange={(e) => setNodeSorting(e.target.value)}>
            <option value="ip">IP Address</option>
            <option value="name">Name</option>
            <option value="none">None</option>
          </select>
        </div>
        <div className="control-group">
          <label>Network Filter:</label>
          <input 
            type="text" 
            value={subnetFilterInput} 
            onChange={(e) => setSubnetFilterInput(e.target.value)}
            onKeyDown={handleFilterKeyPress}
            placeholder="e.g., 10.121.19.0/24"
          />
          <button onClick={applySubnetFilter} className="apply-filter-btn" title="Apply filter">↵</button>
        </div>
        <div className="control-group">
          <label>
            <input 
              type="checkbox" 
              checked={autoRefresh} 
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
        </div>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onEdgeClick={handleEdgeClick}
        onNodeClick={handleNodeClick}
        fitView
      >
        <Controls />
        <MiniMap />
        <Background variant="dots" gap={12} size={1} />
      </ReactFlow>
    </div>
  )
}

const TopologyMapWrapper = ({ onEdgeSelect, onNodeSelect }) => (
  <ReactFlowProvider>
    <TopologyMap onEdgeSelect={onEdgeSelect} onNodeSelect={onNodeSelect} />
  </ReactFlowProvider>
)

export default TopologyMapWrapper
