from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque


class STPTopologyCalculator:
    """Calculates spanning tree topology from LLDP and STP data."""
    
    def __init__(self, devices: Dict, edges: List):
        """
        Initialize calculator with devices and edges.
        
        Args:
            devices: Dict mapping IP to device info
            edges: List of edge dicts with 'from', 'to' keys and optional 'stp_state'
        """
        self.devices = devices
        self.edges = edges
        self.root_bridge = self._find_root_bridge()
        
    def _find_root_bridge(self) -> Optional[str]:
        """Identify root bridge from device STP data."""
        devices_by_cost = []
        
        for device in self.devices.values():
            root_cost = device.get("root_cost")
            ip = device.get("id")
            
            if root_cost is not None:
                try:
                    cost = int(root_cost) if isinstance(root_cost, str) else root_cost
                    devices_by_cost.append((cost, ip))
                except (ValueError, TypeError):
                    continue
        
        if not devices_by_cost:
            return None
            
        devices_by_cost.sort()
        return devices_by_cost[0][1]
    
    def _build_adjacency(self) -> Dict[str, List[str]]:
        """Build undirected adjacency list from edges."""
        adj = defaultdict(list)
        for edge in self.edges:
            from_ip = edge.get("from")
            to_ip = edge.get("to")
            if from_ip and to_ip:
                adj[from_ip].append(to_ip)
                adj[to_ip].append(from_ip)
        return adj
    
    def _calculate_distances_from_root(self, adj: Dict[str, List[str]]) -> Dict[str, int]:
        """Calculate hop distance from root bridge to each device using BFS."""
        if not self.root_bridge:
            return {}
        
        distances = {self.root_bridge: 0}
        queue = deque([self.root_bridge])
        
        while queue:
            current = queue.popleft()
            current_dist = distances[current]
            
            for neighbor in adj.get(current, []):
                if neighbor not in distances:
                    distances[neighbor] = current_dist + 1
                    queue.append(neighbor)
        
        return distances
    
    def _build_spanning_tree_edges(self, adj: Dict[str, List[str]], 
                                   distances: Dict[str, int]) -> Set[Tuple[str, str]]:
        """Build spanning tree by keeping only edges that move closer to root."""
        tree_edges = set()
        
        if not self.root_bridge:
            return tree_edges
        
        visited = set()
        queue = deque([self.root_bridge])
        visited.add(self.root_bridge)
        
        while queue:
            current = queue.popleft()
            current_dist = distances.get(current, float('inf'))
            
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    neighbor_dist = distances.get(neighbor, float('inf'))
                    if neighbor_dist == current_dist + 1:
                        tree_edges.add(tuple(sorted([current, neighbor])))
                        visited.add(neighbor)
                        queue.append(neighbor)
        
        return tree_edges
    
    def calculate_tree_topology(self) -> Tuple[List[Dict], List[Dict], Optional[str]]:
        """
        Calculate spanning tree topology.
        
        Returns:
            Tuple of (filtered_nodes, filtered_edges, root_bridge_ip)
        """
        if not self.root_bridge:
            return self._add_device_hierarchy([]), self.edges, None
        
        adj = self._build_adjacency()
        distances = self._calculate_distances_from_root(adj)
        
        if not distances or len(distances) < len(self.devices):
            tree_edges = self._build_spanning_tree_edges_with_costs()
        else:
            tree_edges = self._build_spanning_tree_edges(adj, distances)
        
        filtered_edges = []
        seen = set()
        for edge in self.edges:
            from_ip = edge.get("from")
            to_ip = edge.get("to")
            edge_key = tuple(sorted([from_ip, to_ip]))
            
            if edge_key in tree_edges:
                if edge_key not in seen:
                    filtered_edges.append(edge)
                    seen.add(edge_key)
                    edge["stp_state"] = "forwarding"
        
        filtered_nodes = self._add_device_hierarchy(self.devices, distances)
        
        return filtered_nodes, filtered_edges, self.root_bridge
    
    def _build_spanning_tree_edges_with_costs(self) -> Set[Tuple[str, str]]:
        """Build spanning tree using STP cost information."""
        tree_edges = set()
        
        if not self.root_bridge:
            return tree_edges
        
        visited = {self.root_bridge}
        queue = deque([self.root_bridge])
        
        while queue:
            current = queue.popleft()
            current_cost = self._get_device_root_cost(current)
            
            for edge in self.edges:
                from_ip = edge.get("from")
                to_ip = edge.get("to")
                
                if not from_ip or not to_ip:
                    continue
                
                if from_ip == current and to_ip not in visited:
                    neighbor_cost = self._get_device_root_cost(to_ip)
                    if neighbor_cost is not None and neighbor_cost > current_cost:
                        tree_edges.add(tuple(sorted([from_ip, to_ip])))
                        visited.add(to_ip)
                        queue.append(to_ip)
                elif to_ip == current and from_ip not in visited:
                    neighbor_cost = self._get_device_root_cost(from_ip)
                    if neighbor_cost is not None and neighbor_cost > current_cost:
                        tree_edges.add(tuple(sorted([from_ip, to_ip])))
                        visited.add(from_ip)
                        queue.append(from_ip)
        
        return tree_edges
    
    def _get_device_root_cost(self, device_ip: str) -> Optional[int]:
        """Get root cost for a device."""
        device = self.devices.get(device_ip, {})
        root_cost = device.get("root_cost")
        
        if root_cost is None:
            return None
        
        try:
            return int(root_cost) if isinstance(root_cost, str) else root_cost
        except (ValueError, TypeError):
            return None
    
    def _add_device_hierarchy(self, devices, distances: Dict[str, int] = None) -> List[Dict]:
        """Add hierarchy level to devices for visualization."""
        if not devices:
            return []
        
        if not distances:
            distances = {}
        
        result = []
        for device in (devices if isinstance(devices, list) else devices.values()):
            device_copy = dict(device)
            device_ip = device_copy.get("id")
            
            if device_ip == self.root_bridge:
                device_copy["hierarchy_level"] = 0
            else:
                distance = distances.get(device_ip, -1)
                if distance > 0:
                    device_copy["hierarchy_level"] = distance
                else:
                    cost = self._get_device_root_cost(device_ip)
                    if cost is not None:
                        device_copy["hierarchy_level"] = min(cost // 100 + 1, 10)
                    else:
                        device_copy["hierarchy_level"] = 10
            
            result.append(device_copy)
        
        return result
