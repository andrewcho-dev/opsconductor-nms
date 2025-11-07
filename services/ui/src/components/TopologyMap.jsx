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

const elkOptions = {
  'elk.algorithm': 'layered',
  'elk.layered.spacing.nodeNodeBetweenLayers': '100',
  'elk.spacing.nodeNode': '80',
  'elk.direction': 'DOWN',
}

const getLayoutedElements = async (nodes, edges) => {
  const graph = {
    id: 'root',
    layoutOptions: elkOptions,
    children: nodes.map((node) => ({
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

  const layoutedNodes = nodes.map((node) => {
    const layoutedNode = layoutedGraph.children.find((n) => n.id === node.id)
    return {
      ...node,
      position: { x: layoutedNode.x, y: layoutedNode.y },
    }
  })

  return { nodes: layoutedNodes, edges }
}

const TopologyMap = ({ onEdgeSelect, onNodeSelect }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

      const flowNodes = devices.map((device) => ({
        id: device.name,
        type: 'default',
        data: {
          label: (
            <div className="node-content">
              <div className="node-name">{device.name}</div>
              <div className="node-details">
                {device.vendor && <span>{device.vendor}</span>}
                {device.model && <span>{device.model}</span>}
              </div>
            </div>
          ),
        },
        position: { x: 0, y: 0 },
      }))

      const flowEdges = topologyEdges.map((edge) => {
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
          type: 'smoothstep',
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
        flowEdges
      )

      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
      setLoading(false)
    } catch (err) {
      console.error('Error fetching topology:', err)
      setError(err.message)
      setLoading(false)
    }
  }, [setNodes, setEdges])

  useEffect(() => {
    fetchTopology()
    const interval = setInterval(fetchTopology, 60000)
    return () => clearInterval(interval)
  }, [fetchTopology])

  const getEdgeColor = (confidence) => {
    if (confidence >= 0.9) return '#22c55e'
    if (confidence >= 0.75) return '#eab308'
    if (confidence >= 0.6) return '#f97316'
    return '#ef4444'
  }

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

  return (
    <div className="topology-map">
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
