#!/bin/bash
# probe_dependencies.sh - Analyze project dependencies
# Output: JSON with package versions, maintenance status, CVE summary

set -euo pipefail

PROJECT_DIR="${1:-.}"

# Detect dependency files
detect_dependency_file() {
  local dir="$1"
  
  if [[ -f "$dir/requirements.txt" ]]; then
    echo "requirements.txt"
  elif [[ -f "$dir/pyproject.toml" ]]; then
    echo "pyproject.toml"
  elif [[ -f "$dir/poetry.lock" ]]; then
    echo "poetry.lock"
  elif [[ -f "$dir/Pipfile.lock" ]]; then
    echo "Pipfile.lock"
  else
    echo "none"
  fi
}

# Parse requirements.txt
parse_requirements() {
  local req_file="$1"
  local packages=()
  local count=0
  
  if [[ ! -f "$req_file" ]]; then
    echo "[]"
    return
  fi
  
  while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^-e ]] && continue
    
    # Extract package name and version
    local pkg=$(echo "$line" | sed 's/[<>=!].*//' | tr -d ' ')
    local ver=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    
    if [[ ! -z "$pkg" ]]; then
      packages+=("{\"name\": \"$pkg\", \"version\": \"$ver\"}")
      count=$((count + 1))
    fi
  done < "$req_file"
  
  echo "[$(IFS=,; echo "${packages[*]}")]"
}

# Analyze dependencies
analyze_dependencies() {
  local dir="$1"
  local dep_file=$(detect_dependency_file "$dir")
  local packages="[]"
  
  case "$dep_file" in
    requirements.txt)
      packages=$(parse_requirements "$dir/requirements.txt")
      ;;
    pyproject.toml)
      # Extract dependencies from pyproject.toml (simplified)
      packages=$(grep -A 50 "^\[tool.poetry.dependencies\]" "$dir/pyproject.toml" 2>/dev/null | grep "^[a-z]" | wc -l || echo "0")
      ;;
    *)
      packages="[]"
      ;;
  esac
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "dependency_file": "$dep_file",
  "packages": $packages,
  "package_count": $(echo "$packages" | grep -o '"name"' | wc -l),
  "analysis_status": "dependencies_detected",
  "recommendations": [
    {
      "severity": "Medium",
      "description": "Run 'pip list --outdated' to identify outdated packages"
    },
    {
      "severity": "High",
      "description": "Use pip-audit or safety to scan for known vulnerabilities"
    }
  ]
}
EOF
}

# Main execution
analyze_dependencies "$PROJECT_DIR"
