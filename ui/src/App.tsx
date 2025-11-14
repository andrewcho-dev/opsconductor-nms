import { useState } from "react";
import InventoryGrid from "./InventoryGrid";
import Admin from "./Admin";

const apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

type Page = "inventory" | "admin";

function App() {
  const [currentPage, setCurrentPage] = useState<Page>("inventory");

  return (
    <div className="app">
      <div className="content">
        {currentPage === "inventory" && (
          <InventoryGrid apiBase={apiBase} onNavigateToAdmin={() => setCurrentPage("admin")} />
        )}
        {currentPage === "admin" && (
          <Admin apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
      </div>
    </div>
  );
}

export default App;
