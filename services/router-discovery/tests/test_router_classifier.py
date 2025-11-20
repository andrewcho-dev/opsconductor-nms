import pytest
from snmp_adapter import SystemInfo, InterfaceAddress, RouteEntry
from router_classifier import RouterClassifier


@pytest.fixture
def classifier():
    return RouterClassifier()


def test_classify_router_with_ip_forwarding(classifier):
    """Test classification of a clear router (IP forwarding enabled)."""
    system_info = SystemInfo(
        hostname="router1",
        sys_descr="Cisco ISR4431",
        sys_object_id="1.3.6.1.4.1.9.9.1"
    )
    interfaces = [
        InterfaceAddress(ip="10.0.0.1", netmask="255.255.255.0"),
        InterfaceAddress(ip="10.1.0.1", netmask="255.255.255.0"),
    ]
    routes = [
        RouteEntry(
            destination_ip="192.168.0.0",
            netmask="255.255.0.0",
            next_hop="10.0.0.254",
            protocol="BGP"
        ),
        RouteEntry(
            destination_ip="172.16.0.0",
            netmask="255.255.0.0",
            next_hop="10.1.0.254",
            protocol="static"
        ),
    ]
    
    result = classifier.classify_router(system_info, True, interfaces, routes)
    
    assert result.is_router is True
    assert result.score >= 3
    assert "ipForwarding=1" in result.reason


def test_classify_non_router_no_forwarding(classifier):
    """Test classification of a non-router (no IP forwarding)."""
    system_info = SystemInfo(
        hostname="workstation",
        sys_descr="Windows 10",
        sys_object_id="1.3.6.1.4.1.311"
    )
    interfaces = [
        InterfaceAddress(ip="192.168.1.100", netmask="255.255.255.0"),
    ]
    routes = []
    
    result = classifier.classify_router(system_info, False, interfaces, routes)
    
    assert result.is_router is False
    assert result.score < 3


def test_classify_router_multiple_networks(classifier):
    """Test that multiple networks contribute to router classification."""
    system_info = SystemInfo(hostname="device", sys_descr=None, sys_object_id=None)
    interfaces = [
        InterfaceAddress(ip="10.0.0.1", netmask="255.255.255.0"),
        InterfaceAddress(ip="10.1.0.1", netmask="255.255.255.0"),
        InterfaceAddress(ip="10.2.0.1", netmask="255.255.255.0"),
    ]
    routes = []
    
    result = classifier.classify_router(system_info, None, interfaces, routes)
    
    # 2 points for multiple networks
    assert result.score >= 2
    assert "3_networks" in result.reason


def test_classify_router_remote_routes(classifier):
    """Test that remote routes contribute to router classification."""
    system_info = SystemInfo(hostname="device", sys_descr=None, sys_object_id=None)
    interfaces = [
        InterfaceAddress(ip="10.0.0.1", netmask="255.255.255.0"),
    ]
    routes = [
        RouteEntry(
            destination_ip="192.168.0.0",
            netmask="255.255.0.0",
            next_hop="10.0.0.254",
            protocol="BGP"
        ),
    ]
    
    result = classifier.classify_router(system_info, None, interfaces, routes)
    
    # 3 points for at least one remote route
    assert result.score >= 3
    assert "1_remote_routes" in result.reason


def test_classify_router_vendor_keywords(classifier):
    """Test that vendor keywords contribute to classification."""
    system_info = SystemInfo(
        hostname="gateway",
        sys_descr="Cisco Router ISR 4431",
        sys_object_id="1.3.6.1.4.1.9"
    )
    interfaces = [
        InterfaceAddress(ip="10.0.0.1", netmask="255.255.255.0"),
    ]
    routes = []
    
    result = classifier.classify_router(system_info, None, interfaces, routes)
    
    # Should include keyword match
    assert "router_keywords" in result.reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
