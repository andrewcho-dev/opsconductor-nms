import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models import DiscoveryRun, Router
from datetime import datetime, timezone

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_health_check():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "router-discovery"


def test_start_discovery_invalid_ip():
    """Test start discovery with invalid IP."""
    response = client.post(
        "/api/router-discovery/start",
        json={
            "root_ip": "invalid_ip",
            "snmp_community": "public",
            "snmp_version": "2c",
        },
    )
    assert response.status_code == 422


def test_start_discovery_invalid_snmp_version():
    """Test start discovery with invalid SNMP version."""
    response = client.post(
        "/api/router-discovery/start",
        json={
            "root_ip": "10.0.0.1",
            "snmp_community": "public",
            "snmp_version": "1",
        },
    )
    assert response.status_code == 422


def test_get_run_state_not_found():
    """Test getting state for non-existent run."""
    response = client.get("/api/router-discovery/runs/999/state")
    assert response.status_code == 404


def test_get_topology_not_found():
    """Test getting topology for non-existent run."""
    response = client.get("/api/router-discovery/runs/999/topology")
    assert response.status_code == 404


def test_get_topology_empty():
    """Test getting topology for run with no routers."""
    db = TestingSessionLocal()
    
    run = DiscoveryRun(
        status="COMPLETED",
        root_ip="10.0.0.1",
        snmp_community="public",
        snmp_version="2c",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    run_id = run.id
    
    db.close()
    
    response = client.get(f"/api/router-discovery/runs/{run_id}/topology")
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == []
    assert data["edges"] == []


def test_get_run_state():
    """Test getting state for existing run."""
    db = TestingSessionLocal()
    
    run = DiscoveryRun(
        status="COMPLETED",
        root_ip="10.0.0.1",
        snmp_community="public",
        snmp_version="2c",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    run_id = run.id
    
    db.close()
    
    response = client.get(f"/api/router-discovery/runs/{run_id}/state")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] == "COMPLETED"
    assert data["root_ip"] == "10.0.0.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
