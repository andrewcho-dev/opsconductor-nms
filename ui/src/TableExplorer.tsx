import { useEffect, useMemo, useState } from "react";
import DataTable, { TableColumnMeta } from "./components/DataTable";

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const response = await fetch(`${apiBase}/api/discover`);
      if (!response.ok) return;
      const data = await response.json();
      setRuns(data || []);
    } catch (err) {
      console.error("Failed to load discovery runs", err);
    }
  };

  const fetchTable = async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      table: selectedTable,
      limit: String(limit),
      offset: String(offset),
    });
    if (selectedRun) {
      params.append("run_id", selectedRun);
    }
    if (debouncedSearch) {
      params.append("search", debouncedSearch);
    }

    try {
      const response = await fetch(`${apiBase}/api/tables?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Failed to load table data");
      }
      const data: TableResponse = await response.json();
      setTableData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setTableData(null);
    } finally {
      setLoading(false);
    }
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
        <button onClick={() => fetchTable()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        <span>
          {tableData ? `${tableData.rows.length}/${tableData.total}` : "0/0"}
        </span>
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0 || loading}
        >
          Prev
        </button>
        <span>
          {currentPage} / {totalPages}
        </span>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={loading || (tableData ? offset + limit >= tableData.total : true)}
        >
          Next
        </button>
      </div>

      {error && <div className="table-explorer__error">{error}</div>}

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
