import { useState } from "react";
import InventoryGrid from "./InventoryGrid";
import Admin from "./Admin";
import RoutingTable from "./RoutingTable";
import Navigation from "./Navigation";

// NOTE: For this docker-compose setup the API is served by network-discovery on port 8000.
// We hardcode apiBase here to avoid any ambiguity with Vite env vars.
const apiBase = "http://10.120.0.18:8000";

type Page = "inventory" | "admin" | "routing";

function App() {
  const [currentPage, setCurrentPage] = useState<Page>("inventory");

  const contentClass = `content${currentPage === "inventory" ? " content--inventory" : ""}`;

  return (
    <div className="app">
      <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
      <div className={contentClass}>
        {currentPage === "inventory" && (
          <InventoryGrid 
            apiBase={apiBase} 
            onNavigateToAdmin={() => setCurrentPage("admin")}
            onNavigateToRouting={() => setCurrentPage("routing")}
          />
        )}
        {currentPage === "admin" && (
          <Admin apiBase={apiBase} />
        )}
        {currentPage === "routing" && (
          <RoutingTable apiBase={apiBase} />
        )}
      </div>
    </div>
  );
}

export default App;
