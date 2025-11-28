import { useMemo, useState } from "react";
import {
  ColumnDef,
  ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
  VisibilityState,
} from "@tanstack/react-table";

export interface TableColumnMeta {
  id: string;
  label: string;
  type?: string;
}

interface DataTableProps {
  columns: TableColumnMeta[];
  rows: Record<string, any>[];
  density?: "comfortable" | "compact";
}

const typeToAlign: Record<string, "left" | "right" | "center"> = {
  number: "right",
  mono: "left",
  boolean: "center",
  badge: "center",
};

const typeToWidth: Record<string, number> = {
  mono: 180,
  number: 120,
  badge: 120,
  datetime: 200,
};

function formatValue(value: any, type?: string): string {
  if (value === null || value === undefined) {
    return "";
  }

  if (type === "datetime") {
    try {
      return new Date(value).toLocaleString();
    } catch {
      return String(value);
    }
  }

  if (type === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

function getBadgeClass(value: any): string {
  if (typeof value !== "string") return "badge";
  const val = value.toLowerCase();
  if (val.includes("fail") || val.includes("down")) return "badge badge--danger";
  if (val.includes("up") || val.includes("active")) return "badge badge--success";
  return "badge";
}

const DataTable = ({ columns, rows, density = "comfortable" }: DataTableProps) => {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});

  const columnDefs: ColumnDef<Record<string, any>>[] = useMemo(() => {
    return columns.map((col) => ({
      id: col.id,
      accessorKey: col.id,
      header: col.label,
      enableSorting: true,
      size: typeToWidth[col.type || ""] || 160,
      cell: (info) => {
        const raw = info.getValue();
        if (col.type === "badge") {
          return <span className={getBadgeClass(raw)}>{formatValue(raw, col.type)}</span>;
        }
        if (col.type === "boolean") {
          return <span className="badge badge--boolean">{formatValue(raw, col.type)}</span>;
        }
        return <span className={col.type === "mono" ? "mono" : undefined}>{formatValue(raw, col.type)}</span>;
      },
      meta: {
        align: typeToAlign[col.type || ""] || "left",
      },
    }));
  }, [columns]);

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    state: {
      sorting,
      columnFilters,
      globalFilter,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    autoResetPageIndex: false,
    enableColumnResizing: true,
    columnResizeMode: "onChange",
  });

  return (
    <div className={`data-table data-table--${density}`}>
      <div className="data-table__toolbar">
        <input
          type="search"
          placeholder="Quick filter..."
          value={globalFilter ?? ""}
          onChange={(e) => setGlobalFilter(e.target.value)}
        />
        <details>
          <summary>Columns</summary>
          <div className="column-toggle-list">
            {table.getAllLeafColumns().map((column) => (
              <label key={column.id}>
                <input
                  type="checkbox"
                  checked={column.getIsVisible()}
                  onChange={(e) => column.toggleVisibility(e.target.checked)}
                />
                {column.columnDef.header as string}
              </label>
            ))}
          </div>
        </details>
      </div>

      <div className="data-table__viewport">
        <table>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    colSpan={header.colSpan}
                    style={{
                      width: header.getSize(),
                      textAlign: (header.column.columnDef.meta as any)?.align || "left",
                    }}
                  >
                    {header.isPlaceholder ? null : (
                      <div
                        className={header.column.getCanSort() ? "sortable" : undefined}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {header.column.columnDef.header as string}
                        {{
                          asc: " ▲",
                          desc: " ▼",
                        }[header.column.getIsSorted() as string] ?? null}
                      </div>
                    )}
                    {header.column.getCanResize() && (
                      <div
                        onMouseDown={header.getResizeHandler()}
                        onTouchStart={header.getResizeHandler()}
                        className={`resizer ${header.column.getIsResizing() ? "is-resizing" : ""}`}
                      />
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    style={{
                      textAlign: (cell.column.columnDef.meta as any)?.align || "left",
                    }}
                  >
                    {cell.getValue() === undefined || cell.getValue() === null ? (
                      <span className="muted">—</span>
                    ) : (
                      flexRender(cell.column.columnDef.cell, cell.getContext())
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="data-table__footer">
        <div className="pagination">
          <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            Prev
          </button>
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount() || 1}
          </span>
          <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            Next
          </button>
        </div>
        <select
          value={table.getState().pagination.pageSize}
          onChange={(e) => table.setPageSize(Number(e.target.value))}
        >
          {[10, 25, 50, 100].map((pageSize) => (
            <option key={pageSize} value={pageSize}>
              Show {pageSize}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};

export default DataTable;
