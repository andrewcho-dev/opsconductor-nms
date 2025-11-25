import { useState } from "react";
import InventoryGrid from "./InventoryGrid";
import Admin from "./Admin";
import TopologyMap from "./TopologyMap";
import DiscoveryPage from "./DiscoveryPage";
import RoutingTable from "./RoutingTable";
import RouterInventory from "./RouterInventory";

// NOTE: For this docker-compose setup the API is served by network-discovery on port 8000.
// We hardcode apiBase here to avoid any ambiguity with Vite env vars.
const apiBase = "http://10.120.0.18:8000";

type Page = "inventory" | "admin" | "topology" | "discovery" | "routing" | "router-inventory";

function App() {
  const [currentPage, setCurrentPage] = useState<Page>("inventory");

  const contentClass = `content${currentPage === "discovery" ? " content--discovery" : ""}`;

  return (
    <div className="app">
      <div className={contentClass}>
        {currentPage === "inventory" && (
          <InventoryGrid 
            apiBase={apiBase} 
            onNavigateToAdmin={() => setCurrentPage("admin")}
            onNavigateToTopology={() => setCurrentPage("topology")}
            onNavigateToDiscovery={() => setCurrentPage("discovery")}
            onNavigateToRouting={() => setCurrentPage("routing")}
            onNavigateToRouterInventory={() => setCurrentPage("router-inventory")}
          />
        )}
        {currentPage === "admin" && (
          <Admin apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
        {currentPage === "topology" && (
          <TopologyMap apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
        {currentPage === "discovery" && (
          <DiscoveryPage apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
        {currentPage === "routing" && (
          <RoutingTable apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
        {currentPage === "router-inventory" && (
          <RouterInventory apiBase={apiBase} onBack={() => setCurrentPage("inventory")} />
        )}
      </div>
    </div>
  );
}

export default App;
