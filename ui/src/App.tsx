import InventoryGrid from "./InventoryGrid";

const apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

function App() {
  return (
    <div className="app">
      <div className="content">
        <InventoryGrid apiBase={apiBase} />
      </div>
    </div>
  );
}

export default App;
