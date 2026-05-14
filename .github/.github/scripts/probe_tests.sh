#!/bin/bash
# probe_tests.sh - Analyze test coverage and test infrastructure
# Output: JSON with test metrics

set -euo pipefail

PROJECT_DIR="${1:-.}"

# Detect test framework
detect_test_framework() {
  local dir="$1"
  
  if grep -r "pytest" "$dir" --include="*.txt" --include="*.toml" --include="*.cfg" &>/dev/null; then
    echo "pytest"
  elif grep -r "unittest" "$dir" --include="*.py" &>/dev/null; then
    echo "unittest"
  elif grep -r "nose" "$dir" --include="*.txt" --include="*.toml" &>/dev/null; then
    echo "nose"
  else
    echo "none"
  fi
}

# Count test files
count_tests() {
  local dir="$1"
  local test_count=$(find "$dir" -name "test_*.py" -o -name "*_test.py" 2>/dev/null | wc -l)
  echo "$test_count"
}

# Check for coverage configuration
has_coverage_config() {
  local dir="$1"
  
  if [[ -f "$dir/.coveragerc" ]] || [[ -f "$dir/pyproject.toml" ]]; then
    if grep -q "coverage\|pytest-cov" "$dir/pyproject.toml" 2>/dev/null || [[ -f "$dir/.coveragerc" ]]; then
      echo "true"
    else
      echo "false"
    fi
  else
    echo "false"
  fi
}

# Generate test report
generate_test_report() {
  local dir="$1"
  local framework=$(detect_test_framework "$dir")
  local test_count=$(count_tests "$dir")
  local has_coverage=$(has_coverage_config "$dir")
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "test_framework": "$framework",
  "test_files_found": $test_count,
  "coverage_configured": $has_coverage,
  "test_statistics": {
    "unit_tests": "pending_execution",
    "integration_tests": "pending_execution",
    "coverage_percent": "pending_execution"
  },
  "recommendations": [
    {
      "severity": "High",
      "description": "Implement test suite if not present",
      "action": "Create test_*.py files in tests/ directory"
    },
    {
      "severity": "High",
      "description": "Set up code coverage tracking",
      "action": "Use pytest-cov; aim for > 80% coverage on main modules"
    },
    {
      "severity": "Medium",
      "description": "Add integration tests for API endpoints",
      "action": "Test health, ready, and main API endpoints"
    },
    {
      "severity": "Medium",
      "description": "Set up test execution in CI/CD",
      "action": "Add 'pytest' step to GitHub Actions or CI workflow"
    }
  ]
}
EOF
}

# Main execution
generate_test_report "$PROJECT_DIR"
