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

interface DiscoveryRunSummary {
  id: number;
  status: string;
  root_ip: string;
  started_at: string;
}

const TABLE_OPTIONS = [
  { id: "discovery_runs", label: "Discovery Runs" },
  { id: "routers", label: "Routers" },
  { id: "routes", label: "Routes" },
  { id: "network_topology", label: "Network Topology" },
  { id: "topology_links", label: "Topology Links" },
  { id: "networks", label: "Networks" },
  { id: "network_links", label: "Persistent Links" },
];

const TableExplorer = ({ apiBase }: TableExplorerProps) => {
  const [selectedTable, setSelectedTable] = useState<string>(TABLE_OPTIONS[1].id);
  const [runs, setRuns] = useState<DiscoveryRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>("");
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
    fetchRuns();
  }, []);

  useEffect(() => {
    if (runs.length > 0) {
      // Auto-select the latest run if none is selected and viewing topology links
      if (!selectedRun && (selectedTable === 'topology_links' || selectedTable === 'routers' || selectedTable === 'routes')) {
        const latestRun = runs[0]; // runs are already sorted by ID desc
        setSelectedRun(latestRun.id.toString());
      }
    }
  }, [runs, selectedTable, selectedRun]);

  useEffect(() => {
    fetchRouters();
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [selectedTable, selectedRun, debouncedSearch, limit]);

  useEffect(() => {
    fetchTable();
  }, [selectedTable, selectedRun, debouncedSearch, limit, offset]);

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

  const enhanceTopologyLinkData = (data: TableResponse): TableResponse => {
    if (data.table !== 'topology_links') return data;
    
    // Remove discovery_run_id column and enhance router columns
    const enhancedColumns = data.columns
      .filter(col => col.id !== 'discovery_run_id')
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

  const enhanceRoutesData = (data: TableResponse): TableResponse => {
    if (data.table !== 'routes') return data;
    
    // Remove discovery_run_id column and enhance router column
    const enhancedColumns = data.columns
      .filter(col => col.id !== 'discovery_run_id')
      .map((col) => {
        if (col.id === 'router_id') {
          return { ...col, id: 'router_ip', label: 'Router IP' };
        }
        return col;
      });

    // Add router hostname column after router IP
    const columnsWithHostname = [
      ...enhancedColumns.slice(0, 1),
      { id: 'router_hostname', label: 'Hostname', type: 'text' },
      ...enhancedColumns.slice(1)
    ];
    
    return {
      ...data,
      columns: columnsWithHostname,
      rows: data.rows.map((row) => ({
        ...row,
        router_ip: routers[row.router_id]?.ip_address || `Router ${row.router_id}`,
        router_hostname: routers[row.router_id]?.hostname || 'Unknown',
      }))
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

  const fetchRuns = async () => {
    await wrapAsync(async () => {
      const data = await apiCall<DiscoveryRunSummary[]>(`${apiBase}/api/discover`);
      const sortedRuns = (data || []).sort((a, b) => b.id - a.id);
      setRuns(sortedRuns);
      
      // Auto-select the latest run if none is selected and viewing topology links
      if (sortedRuns.length > 0 && !selectedRun && (selectedTable === 'topology_links' || selectedTable === 'routers' || selectedTable === 'routes')) {
        setSelectedRun(sortedRuns[0].id.toString());
      }
    }, false); // Don't show loading for background fetch
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

    const params = new URLSearchParams({
      table: selectedTable,
      limit: String(limit),
      offset: String(offset),
    });

    if (selectedRun) params.set('run_id', selectedRun);
    if (debouncedSearch) params.set('search', debouncedSearch);

    await wrapAsync(async () => {
      const data = await apiCall<TableResponse>(`${apiBase}/api/tables?${params}`);
      let enhancedData = data;
      
      if (data.table === 'topology_links') {
        enhancedData = enhanceTopologyLinkData(data);
      } else if (data.table === 'routes') {
        enhancedData = enhanceRoutesData(data);
      }
      
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
        <select
          value={selectedRun}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedRun(e.target.value)}
        >
          <option value="">All runs</option>
          {runs.map((run) => (
            <option key={run.id} value={run.id}>
              #{run.id} – {run.root_ip} ({run.status})
            </option>
          ))}
        </select>
        <input
          type="search"
          value={search}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
          placeholder="Filter rows..."
        />
        <select value={limit} onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setLimit(Number(e.target.value))}>
          {[50, 100, 250, 500].map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
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
