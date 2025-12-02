import { useState, useEffect } from "react";
import InventoryGrid from "./InventoryGrid";
import Admin from "./Admin";
import Navigation from "./Navigation";
import TableExplorer from "./TableExplorer";
import ErrorBoundary from "./components/ErrorBoundary";

// NOTE: For this docker-compose setup the API is served by network-discovery on port 8000.
// We hardcode apiBase here to avoid any ambiguity with Vite env vars.
const apiBase = "http://10.120.0.18:8000";

type Page = "inventory" | "admin" | "tables";

function App() {
  const [currentPage, setCurrentPage] = useState<Page>("inventory");

  const contentClass = `content${currentPage === "inventory" ? " content--inventory" : currentPage === "tables" ? " content--tables" : ""}`;

  // Handle browser back/forward buttons
  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      if (event.state) {
        setCurrentPage(event.state.page);
      } else {
        // If no state, default to inventory
        setCurrentPage("inventory");
      }
    };

    window.addEventListener('popstate', handlePopState);
    
    // Set initial state
    window.history.replaceState({ page: currentPage }, '', `/${currentPage}`);

    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  // Update history when page changes
  useEffect(() => {
    window.history.pushState({ page: currentPage }, '', `/${currentPage}`);
  }, [currentPage]);

  return (
    <ErrorBoundary
      onError={(error, errorInfo) => {
        // Send to monitoring service if available
        console.error('Application Error:', { error, errorInfo });
      }}
      fallback={
        <div style={{
          padding: '2rem',
          textAlign: 'center',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <h1 style={{ color: '#dc2626', marginBottom: '1rem' }}>Application Error</h1>
          <p style={{ color: '#6b7280', marginBottom: '2rem' }}>
            Something went wrong with the application. Please refresh the page.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              fontSize: '1rem',
              fontWeight: '500'
            }}
          >
            Reload Application
          </button>
        </div>
      }
    >
      <div className="app">
        <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
        <div className={contentClass}>
          {currentPage === "inventory" && (
            <InventoryGrid
              apiBase={apiBase}
              onNavigateToAdmin={() => setCurrentPage("admin")}
            />
          )}
          {currentPage === "admin" && (
            <Admin apiBase={apiBase} />
          )}
          {currentPage === "tables" && (
            <TableExplorer apiBase={apiBase} />
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}

export default App;
