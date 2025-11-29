import { useEffect, useMemo, useState } from "react";
import DataTable, { TableColumnMeta } from "./components/DataTable";
import { useErrorHandler, ErrorDisplay, LoadingSpinner } from "./utils/errorHandling";

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
  { id: "networks", label: "Networks" },
  { id: "topology_links", label: "Topology Links" },
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

  const { error, isLoading, clearError, wrapAsync } = useErrorHandler();

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    fetchRuns();
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [selectedTable, selectedRun, debouncedSearch, limit]);

  useEffect(() => {
    fetchTable();
  }, [selectedTable, selectedRun, debouncedSearch, limit, offset]);

  const fetchRuns = async () => {
    await wrapAsync(async () => {
      const data = await apiCall<DiscoveryRunSummary[]>(`${apiBase}/api/discover`);
      setRuns(data || []);
    }, false); // Don't show loading for background fetch
  };

  const fetchTable = async () => {
    const params = new URLSearchParams({
      table: selectedTable,
      limit: String(limit),
      offset: String(offset),
    });

    if (selectedRun) params.set('run_id', selectedRun);
    if (debouncedSearch) params.set('search', debouncedSearch);

    await wrapAsync(async () => {
      const data = await apiCall<TableResponse>(`${apiBase}/api/tables?${params}`);
      setTableData(data);
    });
  };

  const totalPages = useMemo(() => {
    if (!tableData) return 1;
    return Math.max(1, Math.ceil(tableData.total / limit));
  }, [tableData, limit]);

  const currentPage = Math.floor(offset / limit) + 1;

  return (
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
        <DataTable
          columns={tableData.columns}
          rows={tableData.rows}
          density="compact"
        />
      )}
    </div>
  );
};

export default TableExplorer;
