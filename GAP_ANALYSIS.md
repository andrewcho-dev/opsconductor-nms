# Gap Analysis: LLM-Powered Network Topology Discovery System

**Date**: 2025-11-12  
**Status**: ⚠️ Partially Functional - Core Issues Identified

---

## Critical Issues

### 🔴 **PRIMARY PROBLEM: Minimal Network Discovery**

**Expected**: Rich "spaghetti" network visualization with 40+ devices from 192.168.10.0/24 network
**Actual**: Only 5 nodes with 77 duplicate edges (8 unique relationships)

**Root Causes**:

1. **Switched Network Visibility Limitation**
   - Passive packet capture on switched network only sees:
     - Traffic to/from capture host (192.168.10.50)
     - Broadcast/multicast traffic
   - CANNOT see unicast traffic between other devices
   - **Impact**: 95% of network topology is invisible

2. **Insufficient Active Discovery**
   - No ping sweep being performed
   - No ARP probing
   - Relying purely on passive observation of existing traffic
   - **Impact**: Silent/idle devices never discovered

3. **Edge Duplication Problem**
   - 77 total edges but only 8 unique pairs
   - LLM generating duplicate edges with different evidence
   - State server not deduplicating edges
   - **Impact**: Graph bloat, poor visualization performance

4. **Missing Node Auto-Creation**
   - Edges reference IPs not in nodes dict (e.g., 192.168.10.1)
   - vis-network cannot render edges without both endpoints
   - **Impact**: Invisible relationships even when discovered

---

## Current System State

### ✅ What's Working

- ✅ Packet collector capturing ARP + flows
- ✅ LLM analyst generating patches
- ✅ State server applying patches
- ✅ UI rendering nodes and edges
- ✅ WebSocket real-time updates
- ✅ All Docker services healthy

### 🔴 What's Broken/Missing

#### 1. **Network Discovery Scope** (CRITICAL)
   - **Problem**: Only discovering 5 nodes from 40+ device network
   - **Cause**: Switched network + passive-only capture
   - **Solution Required**: Active discovery (ping sweep, ARP scan)

#### 2. **Edge Management** (HIGH PRIORITY)
   - **Problem**: Massive edge duplication (77 edges, 8 unique)
   - **Cause**: LLM re-adding same edges with different evidence timestamps
   - **Solution Required**: Edge deduplication logic in state server

#### 3. **Node Creation** (HIGH PRIORITY)
   - **Problem**: Edges reference non-existent nodes
   - **Cause**: LLM creates edges but forgets to create nodes first
   - **Solution Required**: Auto-create missing nodes (partially implemented)

#### 4. **LLM Token Limitations** (MEDIUM)
   - **Problem**: JSON truncation at max_tokens limit
   - **Cause**: 4096 context model with large evidence windows
   - **Current Workaround**: Reduced max_evidence_items to 80
   - **Proper Solution**: Upgrade to 8k or 32k context model

#### 5. **Visualization** (MEDIUM)
   - **Problem**: No "spaghetti" network - minimal graph
   - **Cause**: Only 5 nodes discovered
   - **Dependency**: Blocked by network discovery issues

---

## Architecture Review

### Designed vs Actual

```
DESIGNED FLOW                          ACTUAL FLOW
─────────────────                      ──────────────
Network (40+ devices)                  Network (40+ devices)
         ↓                                     ↓
Packet Capture ✅                      Packet Capture ✅ (limited visibility)
   (all traffic)                          (only host + broadcast)
         ↓                                     ↓
Evidence Window ✅                     Evidence Window ✅ (2-5 hosts)
  (250ms batch)                          (250ms batch)
         ↓                                     ↓
LLM Analyst ✅                         LLM Analyst ⚠️ (truncation issues)
  (topology patches)                     (duplicate edges)
         ↓                                     ↓
State Server ✅                        State Server ⚠️ (no dedup)
  (graph storage)                        (77 duplicate edges)
         ↓                                     ↓
UI Visualization ✅                    UI Visualization ⚠️ (5 nodes)
  (spaghetti network)                    (minimal graph)
```

---

## Required Fixes

### Priority 0 (Blocking)

1. **Implement Active Discovery**
   ```python
   # Add to packet-collector service
   async def active_discovery_loop():
       while True:
           # ARP scan entire subnet
           for ip in subnet_ips():
               send_arp_request(ip)
           # ICMP ping sweep
           for ip in subnet_ips():
               send_icmp_ping(ip)
           await asyncio.sleep(30)  # Every 30 seconds
   ```

2. **Fix Edge Deduplication**
   ```python
   # Add to state-server service.py
   def deduplicate_edges(edges):
       seen = {}
       for edge in edges:
           key = (edge['src'], edge['dst'], edge['type'])
           if key not in seen or edge['confidence'] > seen[key]['confidence']:
               seen[key] = edge
       return list(seen.values())
   ```

3. **Ensure Node Auto-Creation**
   - ✅ Partially implemented
   - Need to verify it's working correctly

### Priority 1 (High)

4. **Reduce LLM Patch Complexity**
   - Limit patches to 3-5 operations max
   - Focus on highest-confidence discoveries
   - Update system prompt

5. **Add Graph Cleanup**
   - Remove low-confidence edges after N minutes
   - Prune inactive nodes
   - Limit total edge count per node pair

6. **Improve Evidence Window Quality**
   - Prioritize new discoveries over repeated observations
   - Deduplicate flows before sending to LLM
   - Include node/edge counts in prompt

### Priority 2 (Medium)

7. **Upgrade LLM Model**
   - Switch to Phi-3-medium-4k-instruct (better reasoning)
   - Or use Phi-3-mini-128k-instruct (massive context)
   - Or use Llama-3-8B-Instruct

8. **Add UI Features**
   - Node search/filter
   - Edge thickness based on confidence
   - Color coding by node type
   - Time-travel (view graph history)
   - Export to GraphML/JSON

---

## Network Discovery Strategy

### Current Limitations

**Switched Network Reality**:
```
Switch Port Mirroring: NO
Promiscuous Mode: YES (but ineffective on switched network)
SPAN/TAP: NO

Visible Traffic:
├─ ✅ Traffic to/from 192.168.10.50 (capture host)
├─ ✅ ARP broadcasts
├─ ✅ Multicast traffic (MDNS, SSDP, etc.)
└─ ❌ Unicast traffic between other devices (95% of network)
```

### Required Approach

**Active + Passive Hybrid**:
```python
# Passive: Observe what we can see
- ARP replies
- Flows to/from this host
- Broadcast/multicast announcements

# Active: Probe for what we can't see
- ARP scan: Probe every IP in subnet
- ICMP ping: Verify liveness
- TCP SYN scan: Discover services (optional)
- DNS queries: Map hostnames
```

---

## Immediate Action Items

1. **Add ARP Sweep to Packet Collector**
   - Scan 192.168.10.0/24 every 30 seconds
   - Generate ARP requests for all IPs
   - Capture responses to discover devices

2. **Implement Edge Deduplication**
   - Modify state-server to merge duplicate edges
   - Keep highest confidence + merge evidence arrays

3. **Update System Prompt**
   - Limit to 3-5 operations per patch
   - Prioritize NEW discoveries
   - Explain edge/node creation atomicity

4. **Add Graph Stats Endpoint**
   - `/stats` showing node count, edge count, duplicates
   - Help debug what LLM is producing

5. **Create Active Discovery Service** (NEW)
   - Separate service for active scanning
   - Configurable scan intervals
   - Feeds discovered IPs to packet collector

---

## Success Metrics

### Current State
- ❌ Nodes discovered: 5 / 40+ (12%)
- ❌ Edge quality: 77 total / 8 unique (90% duplication)
- ❌ Visualization: Minimal graph (not "spaghetti")
- ✅ Services: All running
- ⚠️ LLM: Generating patches but with issues

### Target State
- ✅ Nodes discovered: 35+ / 40+ (85%+)
- ✅ Edge quality: <10% duplication
- ✅ Visualization: Complex "spaghetti" network
- ✅ Discovery rate: New nodes every 30-60 seconds
- ✅ LLM: Clean, atomic patches

---

## Updated Architecture Diagram

```
┌─────────────────────────────────────┐
│       Network (192.168.10.0/24)     │
│         40+ devices (target)        │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        │             │
  [Passive]      [Active]  ← NEW COMPONENT NEEDED
        │             │
        │      ┌──────┴──────┐
        │      │ ARP Sweeper │
        │      │ Ping Sweep  │
        │      └──────┬──────┘
        │             │
        └──────┬──────┘
               ▼
    ┌──────────────────┐
    │ Packet Collector │ ✅ Working
    │   (Scapy/BPF)    │    (visibility limited)
    └────────┬─────────┘
             │ 250ms batches
             ▼
    ┌──────────────────┐
    │  LLM Analyst     │ ⚠️ Truncation + Duplication
    │  (Phi-3-4k)      │    (needs prompt tuning)
    └────────┬─────────┘
             │ JSON Patch
             ▼
    ┌──────────────────┐
    │  State Server    │ ⚠️ No Edge Deduplication
    │  (PostgreSQL)    │    (needs dedup logic)
    └────────┬─────────┘
             │ WebSocket
             ▼
    ┌──────────────────┐
    │  UI (React)      │ ✅ Rendering OK
    │  (vis-network)   │    (but limited data)
    └──────────────────┘
```

---

## Conclusion

The system **architecture is sound** but **implementation has critical gaps**:

1. **Network visibility**: Passive-only approach cannot see most network activity
2. **Edge quality**: Massive duplication due to lack of deduplication logic
3. **Node discovery**: Only seeing 5 of 40+ devices due to switched network

**Next Steps**:
1. Add active discovery (ARP sweep, ping sweep)
2. Implement edge deduplication
3. Tune LLM prompts to reduce patch complexity
4. Add graph statistics/monitoring

**ETA to "Spaghetti Network"**: 1-2 days with active discovery + deduplication
