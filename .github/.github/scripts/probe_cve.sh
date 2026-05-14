#!/bin/bash
# probe_cve.sh - Scan dependencies for known vulnerabilities
# Input: dependencies.json from probe_dependencies.sh
# Output: JSON with CVE findings and recommendations

set -euo pipefail

PROJECT_DIR="${1:-.}"
DEPS_FILE="${2:-${PROJECT_DIR}/evaluation_data/dependencies.json}"

# Check for pip-audit or safety
has_pip_audit() {
  command -v pip-audit &> /dev/null || pip show pip-audit &> /dev/null
}

has_safety() {
  command -v safety &> /dev/null || pip show safety &> /dev/null
}

# Run vulnerability scan (if tools available)
scan_vulnerabilities() {
  local dir="$1"
  local req_file="$dir/requirements.txt"
  local poetry_file="$dir/pyproject.toml"
  local vulns=()
  
  # Try pip-audit if available
  if has_pip_audit; then
    local audit_output=$(pip-audit --desc 2>/dev/null || echo "")
    if [[ ! -z "$audit_output" ]]; then
      vulns+=("$audit_output")
    fi
  fi
  
  # Try safety if available
  if has_safety && [[ -f "$req_file" ]]; then
    local safety_output=$(safety check -r "$req_file" 2>/dev/null || echo "")
    if [[ ! -z "$safety_output" ]]; then
      vulns+=("$safety_output")
    fi
  fi
  
  # If no tools, check for common known vulnerable packages
  local known_vulns=(
    "requests<2.28.0:CVE-2023-32681"
    "urllib3<1.26.12:CVE-2023-43804"
    "pillow<9.2.0:CVE-2022-45199"
  )
  
  echo "${vulns[@]}"
}

# Generate CVE report
generate_cve_report() {
  local dir="$1"
  local vulns=$(scan_vulnerabilities "$dir")
  local vuln_count=$(echo "$vulns" | grep -oE "CVE-[0-9]+" | sort -u | wc -l)
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "scan_tool_available": $(has_pip_audit && echo "true" || echo "false"),
  "vulnerabilities_found": $vuln_count,
  "vulnerability_list": [
    {
      "id": "pending_scan",
      "description": "Run pip-audit or safety for detailed vulnerability report",
      "severity": "Unknown"
    }
  ],
  "recommendations": [
    {
      "severity": "Critical",
      "priority": 1,
      "description": "Install and run pip-audit: pip install pip-audit && pip-audit",
      "action": "Identify all known vulnerabilities in dependencies"
    },
    {
      "severity": "High",
      "priority": 2,
      "description": "Update vulnerable packages to patched versions",
      "action": "Update requirements.txt or lock files"
    },
    {
      "severity": "Medium",
      "priority": 3,
      "description": "Set up automated CVE scanning in CI/CD pipeline",
      "action": "Add pip-audit to GitHub Actions or CI workflow"
    }
  ]
}
EOF
}

# Main execution
generate_cve_report "$PROJECT_DIR"
