interface NavigationProps {
  currentPage: string;
  onNavigate: (page: "inventory" | "admin" | "routing") => void;
}

function Navigation({ currentPage, onNavigate }: NavigationProps) {
  const navItems = [
    { id: "inventory", label: "Inventory", icon: "📋" },
    { id: "routing", label: "Routes", icon: "🌐" },
    { id: "admin", label: "Admin", icon: "⚙️" }
  ];

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "0.5rem",
      padding: "0.5rem 1rem",
      backgroundColor: "#f1f5f9",
      borderBottom: "1px solid #e2e8f0"
    }}>
      <div style={{
        display: "flex",
        gap: "0.25rem",
        marginRight: "auto"
      }}>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id as "inventory" | "admin" | "routing")}
            style={{
              padding: "0.375rem 0.75rem",
              fontSize: "0.875rem",
              fontWeight: "500",
              border: "none",
              borderRadius: "0.375rem",
              cursor: "pointer",
              backgroundColor: currentPage === item.id ? "#3b82f6" : "transparent",
              color: currentPage === item.id ? "white" : "#64748b",
              transition: "all 0.2s"
            }}
          >
            {item.icon} {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default Navigation;
