#!/bin/bash
# probe_performance.sh - Benchmark inference latency and resource usage
# Output: JSON with performance metrics

set -euo pipefail

PROJECT_DIR="${1:-.}"
TIMEOUT="${EVAL_BENCH_TIMEOUT:-30}"

# Measure endpoint latency
measure_latency() {
  local endpoint="$1"
  local timeout="$2"
  local iterations=5
  local total_time=0
  local successful=0
  
  for i in $(seq 1 $iterations); do
    local start=$(date +%s%N | cut -b1-13)
    local response=$(curl -s -m "$timeout" "http://${endpoint}/health" 2>/dev/null || echo "")
    local end=$(date +%s%N | cut -b1-13)
    
    if [[ ! -z "$response" ]]; then
      local latency=$((end - start))
      total_time=$((total_time + latency))
      successful=$((successful + 1))
    fi
  done
  
  if [[ $successful -gt 0 ]]; then
    echo $((total_time / successful))
  else
    echo "0"
  fi
}

# Measure resource utilization
measure_resources() {
  local dir="$1"
  
  # Check memory usage of Python processes
  local mem=$(ps aux | grep python | grep -v grep | awk '{sum+=$6} END {print sum}')
  
  # Check CPU usage (simplified)
  local cpu=$(top -b -n 1 2>/dev/null | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 || echo "0")
  
  echo "{\"memory_kb\": ${mem:-0}, \"cpu_percent\": $cpu}"
}

# Generate performance report
generate_performance_report() {
  local dir="$1"
  local latency=$(measure_latency "localhost:8000" "$TIMEOUT" || echo "0")
  local resources=$(measure_resources "$dir")
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "inference_latency_ms": $latency,
  "resource_utilization": $resources,
  "performance_profile": {
    "baseline_latency": "pending_measurement",
    "memory_efficiency": "pending_measurement",
    "startup_time": "pending_measurement"
  },
  "recommendations": [
    {
      "severity": "Medium",
      "description": "Establish performance baseline metrics",
      "action": "Run benchmarks in isolated environment, document results"
    },
    {
      "severity": "Medium",
      "description": "Optimize hot paths if latency > 1s",
      "action": "Profile code to identify bottlenecks"
    },
    {
      "severity": "Low",
      "description": "Set up performance regression testing",
      "action": "Add latency checks to CI/CD pipeline"
    }
  ]
}
EOF
}

# Main execution
generate_performance_report "$PROJECT_DIR"
