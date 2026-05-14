#!/bin/bash
# probe_health.sh - Check service health endpoints and readiness
# Output: JSON with health check results

set -euo pipefail

PROJECT_DIR="${1:-.}"
TIMEOUT="${EVAL_BENCH_TIMEOUT:-30}"

# Detect service type and port
detect_service_config() {
  local dir="$1"
  local port="8000"
  local host="localhost"
  
  # Check for FastAPI app configuration
  if grep -r "uvicorn" "$dir" --include="*.py" &>/dev/null; then
    port=$(grep -r "port=" "$dir" --include="*.py" -h | head -1 | grep -oE "[0-9]{4,5}" || echo "8000")
  fi
  
  # Check for Flask
  if grep -r "Flask" "$dir" --include="*.py" &>/dev/null; then
    port="5000"
  fi
  
  echo "$host:$port"
}

# Check if service is running
is_service_running() {
  local endpoint="$1"
  local timeout="$2"
  
  # Try to connect to service
  if timeout "$timeout" bash -c "echo > /dev/tcp/${endpoint%:*}/${endpoint##*:}" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# Probe health endpoint
probe_health_endpoint() {
  local endpoint="$1"
  local timeout="$2"
  
  # Try /health endpoint
  local health=$(curl -s -m "$timeout" "http://${endpoint}/health" 2>/dev/null || echo "{\"status\": \"unreachable\"}")
  echo "$health"
}

# Probe readiness endpoint
probe_ready_endpoint() {
  local endpoint="$1"
  local timeout="$2"
  
  # Try /ready endpoint
  local ready=$(curl -s -m "$timeout" "http://${endpoint}/ready" 2>/dev/null || echo "{\"ready\": false}")
  echo "$ready"
}

# Generate health report
generate_health_report() {
  local dir="$1"
  local config=$(detect_service_config "$dir")
  local running=false
  local health_status="unknown"
  local ready_status="unknown"
  
  # Check if service is running
  if is_service_running "$config" "$TIMEOUT"; then
    running=true
    health_status=$(probe_health_endpoint "$config" "$TIMEOUT")
    ready_status=$(probe_ready_endpoint "$config" "$TIMEOUT")
  fi
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "service_endpoint": "$config",
  "service_running": $running,
  "health_endpoint": {
    "reachable": $running,
    "response": $health_status
  },
  "ready_endpoint": {
    "reachable": $running,
    "response": $ready_status
  },
  "recommendations": [
    {
      "severity": "High",
      "description": "Ensure /health endpoint is implemented and responds quickly",
      "action": "Add health check to service (< 100ms response time)"
    },
    {
      "severity": "High",
      "description": "Ensure /ready endpoint indicates startup completion",
      "action": "Add readiness probe for orchestration platforms"
    },
    {
      "severity": "Medium",
      "description": "Set up monitoring and alerting for endpoint availability",
      "action": "Configure monitoring dashboard (Prometheus, CloudWatch, etc.)"
    }
  ]
}
EOF
}

# Main execution
generate_health_report "$PROJECT_DIR"
