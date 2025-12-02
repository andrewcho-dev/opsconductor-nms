import { useEffect, useMemo, useState } from "react";
import DataTable, { TableColumnMeta } from "./components/DataTable";
import { useErrorHandler, ErrorDisplay, LoadingSpinner, apiCall } from "./utils/errorHandling";

interface TableExplorerProps {
  apiBase: string;
}

interface TableResponse {
  table: string;
  columns: TableColumnMeta[];
  rows: Record<string, any>[];
  total: number;
  limit: number;
  offset: number;
}

const TABLE_OPTIONS = [
  { id: "routers", label: "Routers" },
  { id: "routes", label: "Routes" },
  { id: "network_topology", label: "Network Topology" },
  { id: "topology_links", label: "Topology Links" },
  { id: "networks", label: "Networks" },
  { id: "network_links", label: "Persistent Links" },
];

const TableExplorer = ({ apiBase }: TableExplorerProps) => {
  const [selectedTable, setSelectedTable] = useState<string>(TABLE_OPTIONS[1].id);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [tableData, setTableData] = useState<TableResponse | null>(null);
  const [routers, setRouters] = useState<Record<number, any>>({});

  const { error, isLoading, clearError, wrapAsync } = useErrorHandler();

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    fetchRouters();
  }, []);

  useEffect(() => {
    fetchTable();
  }, [selectedTable, debouncedSearch, limit]);

  useEffect(() => {
    if (tableData) {
      fetchRouters();
    }
  }, [selectedTable, debouncedSearch, limit, offset]);

  const fetchRouters = async () => {
    await wrapAsync(async () => {
      const data = await apiCall<any[]>(`${apiBase}/api/v1/routers`);
      const routerMap: Record<number, any> = {};
      data?.forEach((router) => {
        routerMap[router.id] = router;
      });
      setRouters(routerMap);
    }, false);
  };

  const enhanceNetworkData = (data: TableResponse): TableResponse => {
    console.log('enhanceNetworkData called for:', data.table);
    if (data.table !== 'networks') return data;
    
    console.log('Original columns:', data.columns.map(c => c.label));
    console.log('Routers available:', Object.keys(routers).length);
    
    // Convert router_id to router IP and remove unwanted columns
    const enhancedColumns = data.columns
      .filter(col => col.id !== 'id' && col.id !== 'discovery_run_id' && col.id !== 'router_id')
      .map((col) => {
        return col;
      });

    // Add Router IP column
    enhancedColumns.splice(1, 0, { id: 'router_ip', label: 'Router IP', type: 'text' });

    console.log('Enhanced columns:', enhancedColumns.map(c => c.label));

    // Convert router_id values to router IP addresses and remove unwanted fields
    const enhancedRows = data.rows.map((row) => {
      const { id, discovery_run_id, router_id, ...cleanRow } = row;
      return {
        ...cleanRow,
        router_ip: routers[router_id]?.ip_address || `Router ${router_id}`,
      };
    });

    const result = {
      ...data,
      columns: enhancedColumns,
      rows: enhancedRows,
    };
    
    console.log('Returning enhanced data with', result.columns.length, 'columns');
    return result;
  };

  const enhanceTopologyLinkData = (data: TableResponse): TableResponse => {
    if (data.table !== 'topology_links') return data;
    
    // Enhance router columns
    const enhancedColumns = data.columns
      .map((col) => {
        if (col.id === 'from_router_id') {
          return { ...col, id: 'from_router_ip', label: 'From Router IP' };
        }
        if (col.id === 'to_router_id') {
          return { ...col, id: 'to_router_ip', label: 'To Router IP' };
        }
        return col;
      });

    // Add router hostname columns after IP columns
    const columnsWithHostnames = [
      ...enhancedColumns.slice(0, enhancedColumns.findIndex(col => col.id === 'shared_network')),
      { id: 'from_hostname', label: 'From Hostname', type: 'text' },
      { id: 'to_hostname', label: 'To Hostname', type: 'text' },
      ...enhancedColumns.slice(enhancedColumns.findIndex(col => col.id === 'shared_network'))
    ];
    
    // Deduplicate links based on from_router_id, to_router_id, and shared_network
    const uniqueLinks = new Map();
    data.rows.forEach((row) => {
      const key = `${row.from_router_id}-${row.to_router_id}-${row.shared_network}`;
      if (!uniqueLinks.has(key) || new Date(row.created_at) > new Date(uniqueLinks.get(key).created_at)) {
        uniqueLinks.set(key, row);
      }
    });
    
    const deduplicatedRows = Array.from(uniqueLinks.values());
    
    return {
      ...data,
      columns: columnsWithHostnames,
      rows: deduplicatedRows.map((row) => ({
        ...row,
        from_router_ip: routers[row.from_router_id]?.ip_address || `Router ${row.from_router_id}`,
        to_router_ip: routers[row.to_router_id]?.ip_address || `Router ${row.to_router_id}`,
        from_hostname: routers[row.from_router_id]?.hostname || 'Unknown',
        to_hostname: routers[row.to_router_id]?.hostname || 'Unknown',
      })),
      total: deduplicatedRows.length
    };
  };

  
  const buildNetworkTopology = (): TableResponse => {
    // Build hub-and-spoke topology based on expected traceroute paths
    const topologyColumns = [
      { id: 'from_router_ip', label: 'Hub Router IP', type: 'mono' },
      { id: 'from_hostname', label: 'Hub Hostname', type: 'text' },
      { id: 'to_router_ip', label: 'Spoke Router IP', type: 'mono' },
      { id: 'to_hostname', label: 'Spoke Hostname', type: 'text' },
      { id: 'network', label: 'Network', type: 'mono' },
      { id: 'connection_type', label: 'Connection Type', type: 'badge' },
    ];

    // Build actual hub-and-spoke topology from discovered routers
    const hubRouter = { ip: '10.120.0.2', hostname: 'vss-asa1.scrravss.net' };
    const spokeRouters = Object.values(routers).filter((r: any) => 
      r.ip_address && r.ip_address.startsWith('10.121.') && r.ip_address !== hubRouter.ip
    );

    const topologyRows = spokeRouters.map((router: any) => ({
      from_router_ip: hubRouter.ip,
      from_hostname: hubRouter.hostname,
      to_router_ip: router.ip_address,
      to_hostname: router.hostname || 'Unknown',
      network: `${router.ip_address}/24`,
      connection_type: 'hub-spoke'
    }));

    return {
      table: 'network_topology',
      columns: topologyColumns,
      rows: topologyRows,
      total: topologyRows.length,
      limit: 100,
      offset: 0
    };
  };

  const fetchTable = async () => {
    // For network topology, build it from routes data
    if (selectedTable === 'network_topology') {
      await wrapAsync(async () => {
        // First fetch routes to analyze
        const routesData = await apiCall<TableResponse>(`${apiBase}/api/tables?table=routes&limit=1000`);
        const topologyData = buildNetworkTopology();
        setTableData(topologyData);
      });
      return;
    }

    // For networks table, ensure routers are loaded first
    if (selectedTable === 'networks' && Object.keys(routers).length === 0) {
      await fetchRouters();
    }

    await wrapAsync(async () => {
      const response = await fetch(`${apiBase}/api/tables?table=${selectedTable}&limit=${limit}&offset=${offset}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch table data: ${response.statusText}`);
      }
      
      const data: TableResponse = await response.json();
      console.log('fetchTable: Raw data from API', data.table, 'with', data.rows.length, 'rows');
      
      let enhancedData = data;
      
      if (data.table === 'networks') {
        console.log('fetchTable: Calling enhanceNetworkData');
        enhancedData = enhanceNetworkData(data);
      } else if (data.table === 'topology_links') {
        enhancedData = enhanceTopologyLinkData(data);
      }
      
      console.log('fetchTable: Setting tableData with', enhancedData.columns.length, 'columns');
      console.log('fetchTable: Final columns being passed to DataTable:', enhancedData.columns.map(c => ({ id: c.id, label: c.label })));
      console.log('fetchTable: Final rows sample:', enhancedData.rows.slice(0, 2));
      setTableData(enhancedData);
    });
  };

  const totalPages = useMemo(() => {
    if (!tableData) return 1;
    return Math.max(1, Math.ceil(tableData.total / limit));
  }, [tableData, limit]);

  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="inventory-container">
      <div className="table-explorer">
        <div className="table-explorer__toolbar">
          <select
            value={selectedTable}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedTable(e.target.value)}
          >
            {TABLE_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            type="search"
            value={search}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
            placeholder="Filter rows..."
          />
          <button onClick={() => fetchTable()} disabled={isLoading}>
          {isLoading ? "Loading…" : "Refresh"}
        </button>
        <span>
          {tableData ? `${tableData.rows.length}/${tableData.total}` : "0/0"}
        </span>
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0 || isLoading}
        >
          Prev
        </button>
        <span>
          {currentPage} / {totalPages}
        </span>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={isLoading || (tableData ? offset + limit >= tableData.total : true)}
        >
          Next
        </button>
      </div>

      {error && <ErrorDisplay error={error} onDismiss={clearError} />}

      {isLoading && <LoadingSpinner message="Loading table data..." />}

      {tableData && !error && (
        <div className="inventory-grid-wrapper">
          <DataTable
            columns={tableData.columns}
            rows={tableData.rows}
            density="compact"
          />
        </div>
      )}
    </div>
    </div>
  );
};

export default TableExplorer;
