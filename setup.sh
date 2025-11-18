#!/bin/bash
set -e

echo "============================================"
echo "  OpsConductor NMS - Setup Script"
echo "============================================"
echo

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  Please do not run this script as root"
   exit 1
fi

# Detect GPU
echo "🔍 Detecting hardware..."
HAS_GPU=false
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi &> /dev/null; then
        HAS_GPU=true
        GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
        echo "✅ NVIDIA GPU detected: $GPU_INFO"
    fi
fi

if [ "$HAS_GPU" = false ]; then
    echo "ℹ️  No NVIDIA GPU detected - will configure CPU-only mode"
fi

# Detect network interfaces
echo
echo "🔍 Detecting network interfaces..."
INTERFACES=$(ip -o link show | awk -F': ' '{print $2}' | grep -v "lo" | grep -v "docker" | grep -v "br-")
echo "Available interfaces:"
select IFACE in $INTERFACES; do
    if [ -n "$IFACE" ]; then
        PCAP_IFACE=$IFACE
        break
    fi
done

# Detect default gateway
echo
echo "🔍 Detecting network configuration..."
DEFAULT_GATEWAY=$(ip route | grep default | awk '{print $3}' | head -1)
if [ -n "$DEFAULT_GATEWAY" ]; then
    echo "Detected gateway: $DEFAULT_GATEWAY"
    read -p "Use this gateway IP? [Y/n]: " USE_GATEWAY
    if [[ $USE_GATEWAY =~ ^[Nn] ]]; then
        read -p "Enter gateway IP: " GATEWAY_IP
    else
        GATEWAY_IP=$DEFAULT_GATEWAY
    fi
else
    read -p "Enter gateway IP (e.g., 192.168.1.1): " GATEWAY_IP
fi

read -p "Enter firewall IP (press Enter to skip): " FIREWALL_IP

# Detect server IP
echo
echo "🔍 Detecting server IP address..."
SERVER_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -1)
if [ -n "$SERVER_IP" ]; then
    echo "Detected server IP: $SERVER_IP"
    read -p "Use this IP for UI access? [Y/n]: " USE_SERVER_IP
    if [[ $USE_SERVER_IP =~ ^[Nn] ]]; then
        read -p "Enter server IP: " SERVER_IP
    fi
else
    read -p "Enter server IP address: " SERVER_IP
fi

# LLM Configuration
# LLM Configuration
echo
if [ "$HAS_GPU" = true ]; then
    echo "📝 LLM Configuration (GPU mode)"
    echo "Select model:"
    echo "  1) Qwen/Qwen2-7B-Instruct (7GB VRAM, recommended)"
    echo "  2) microsoft/Phi-3-mini-4k-instruct (4GB VRAM, faster)"
    echo "  3) Custom model"
    read -p "Choice [1]: " MODEL_CHOICE
    MODEL_CHOICE=${MODEL_CHOICE:-1}
    
    case $MODEL_CHOICE in
        1)
            MODEL_NAME="Qwen/Qwen2-7B-Instruct"
            VLLM_MAX_CONTEXT_LEN=4096
            ;;
        2)
            MODEL_NAME="microsoft/Phi-3-mini-4k-instruct"
            VLLM_MAX_CONTEXT_LEN=4096
            ;;
        3)
            read -p "Enter model name: " MODEL_NAME
            read -p "Max context length [4096]: " VLLM_MAX_CONTEXT_LEN
            VLLM_MAX_CONTEXT_LEN=${VLLM_MAX_CONTEXT_LEN:-4096}
            ;;
    esac
    
    read -p "HuggingFace token (press Enter to skip): " HF_TOKEN
else
    echo "📝 CPU-only mode - AI classification will be disabled"
    MODEL_NAME="none"
    VLLM_MAX_CONTEXT_LEN=4096
    HF_TOKEN=""
fi

# Create .env file
echo
echo "📝 Creating .env file..."
cat > .env <<EOF
# LLM Configuration
MODEL_NAME=$MODEL_NAME
VLLM_MAX_CONTEXT_LEN=$VLLM_MAX_CONTEXT_LEN
HF_TOKEN=$HF_TOKEN

# Network Configuration
PCAP_IFACE=$PCAP_IFACE
FILTER_BPF=arp or ip or ip6
ANALYST_URL=http://127.0.0.1:8100/tick
STATE_SERVER_URL=http://127.0.0.1:8080
GATEWAY_IP=$GATEWAY_IP
SERVER_IP=$SERVER_IP
FIREWALL_IP=$FIREWALL_IP

# LLM Response Format
RESPONSE_FORMAT=json_object

# Scanning Configuration (optional overrides)
# SCAN_INTERVAL_SECONDS=300
# SNMP_SCAN_INTERVAL_SECONDS=300
# SNMP_COMMUNITY=public
# MAC_SCAN_INTERVAL_SECONDS=3600
# MIB_ASSIGN_INTERVAL_SECONDS=600
# MIB_WALK_INTERVAL_SECONDS=1800
EOF

echo "✅ Created .env file"

# Create docker-compose.override.yml for CPU mode
if [ "$HAS_GPU" = false ]; then
    echo
    echo "📝 Creating docker-compose.override.yml for CPU-only mode..."
    cat > docker-compose.override.yml <<EOF
# CPU-only mode - disables GPU-dependent services
services:
  vllm:
    deploy:
      resources:
        reservations: {}
    profiles:
      - disabled
    
  analyst:
    profiles:
      - disabled
  
EOF
    echo "✅ Created docker-compose.override.yml (AI services disabled)"
fi

# Summary
echo
echo "============================================"
echo "  ✅ Setup Complete!"
echo "============================================"
echo
echo "Configuration Summary:"
echo "  • Mode: $([ "$HAS_GPU" = true ] && echo "GPU-accelerated" || echo "CPU-only (no AI)")"
echo "  • Network Interface: $PCAP_IFACE"
echo "  • Gateway IP: $GATEWAY_IP"
[ -n "$FIREWALL_IP" ] && echo "  • Firewall IP: $FIREWALL_IP"
[ "$HAS_GPU" = true ] && echo "  • LLM Model: $MODEL_NAME"
echo

echo "Next steps:"
echo "  1. Review configuration: cat .env"
echo "  2. Start services: docker compose up -d"
echo "  3. View logs: docker compose logs -f"
echo "  4. Access UI: http://localhost:3000"
echo
echo "For troubleshooting, see: README.md"
echo
