import pytest

from snmp_routing import parse_inet_cidr_index, inet_address_to_string


@pytest.mark.parametrize(
    "index_suffix, dest_ip, prefix_len, next_ip",
    [
        # IPv4 dest 10.10.0.0/24, next hop 192.0.2.1
        ([1, 4, 10, 10, 0, 0, 24, 1, 4, 192, 0, 2, 1], "10.10.0.0", 24, "192.0.2.1"),
        # IPv6 dest 2001:db8::/32, next hop 2001:db8::1
        ([2, 16,
          0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 32,
          2, 16,
          0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
         "2001:db8:0:0:0:0:0:0", 32, "2001:db8:0:0:0:0:0:1"),
        # IPv6 dest 2001:db8::/32, local route (no nexthop octets)
        ([2, 16,
          0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 32,
          2, 0],
         "2001:db8:0:0:0:0:0:0", 32, None),
    ],
)
def test_parse_inet_cidr_index_basic(index_suffix, dest_ip, prefix_len, next_ip):
    idx = parse_inet_cidr_index(index_suffix)

    dest_addr = inet_address_to_string(idx["dest_type"], idx["dest_octets"])
    nh_addr = inet_address_to_string(idx["next_type"], idx["next_octets"])

    assert dest_addr == dest_ip
    assert idx["prefix_len"] == prefix_len
    assert nh_addr == next_ip


def test_parse_inet_cidr_index_invalid_short():
    with pytest.raises(ValueError):
        parse_inet_cidr_index([1, 0, 0])
