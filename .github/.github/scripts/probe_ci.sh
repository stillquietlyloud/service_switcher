#!/bin/bash
# probe_ci.sh - Detect CI/CD pipeline configuration
# Output: JSON with CI/CD status and recommendations

set -euo pipefail

PROJECT_DIR="${1:-.}"

# Detect CI/CD platforms
detect_ci_platforms() {
  local dir="$1"
  local platforms=()
  
  # GitHub Actions
  [[ -d "$dir/.github/workflows" ]] && platforms+=("github_actions")
  
  # GitLab CI
  [[ -f "$dir/.gitlab-ci.yml" ]] && platforms+=("gitlab_ci")
  
  # CircleCI
  [[ -d "$dir/.circleci" ]] && platforms+=("circleci")
  
  # Jenkins
  [[ -f "$dir/Jenkinsfile" ]] && platforms+=("jenkins")
  
  # Travis CI
  [[ -f "$dir/.travis.yml" ]] && platforms+=("travis_ci")
  
  # Azure Pipelines
  [[ -f "$dir/azure-pipelines.yml" ]] && platforms+=("azure_pipelines")
  
  echo "[$(IFS=,; echo \"${platforms[*]}\")]"
}

# Detect automated checks
detect_automated_checks() {
  local dir="$1"
  local checks=()
  
  # Linting
  if grep -r "pylint\|flake8\|black\|isort" "$dir" --include="*.py" --include="*.txt" --include="*.toml" --include="*.yml" &>/dev/null; then
    checks+=("\"linting\"")
  fi
  
  # Type checking
  if grep -r "mypy\|pyright" "$dir" --include="*.py" --include="*.txt" --include="*.toml" --include="*.yml" &>/dev/null; then
    checks+=("\"type_checking\"")
  fi
  
  # Testing
  if grep -r "pytest\|unittest" "$dir" --include="*.py" --include="*.txt" --include="*.toml" --include="*.yml" &>/dev/null; then
    checks+=("\"testing\"")
  fi
  
  # Security scanning
  if grep -r "bandit\|safety\|semgrep" "$dir" --include="*.txt" --include="*.toml" --include="*.yml" &>/dev/null; then
    checks+=("\"security\"")
  fi
  
  echo "[$(IFS=,; echo "${checks[*]}")]"
}

# Generate CI report
generate_ci_report() {
  local dir="$1"
  local platforms=$(detect_ci_platforms "$dir")
  local checks=$(detect_automated_checks "$dir")
  local has_ci=false
  
  if [[ "$platforms" != "[]" ]]; then
    has_ci=true
  fi
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "ci_present": $has_ci,
  "ci_platforms": $platforms,
  "automated_checks": $checks,
  "ci_status": {
    "workflows": "pending_analysis",
    "build_success_rate": "pending_analysis",
    "average_build_time": "pending_analysis"
  },
  "recommendations": [
    {
      "severity": "High",
      "priority": 1,
      "description": "Set up basic CI/CD pipeline if not present",
      "action": "Create .github/workflows/test.yml for GitHub Actions"
    },
    {
      "severity": "High",
      "priority": 2,
      "description": "Enable automatic linting and formatting checks",
      "action": "Add flake8/black/isort to CI workflow"
    },
    {
      "severity": "High",
      "priority": 3,
      "description": "Enable automated testing on every push",
      "action": "Add 'pytest' step with coverage reporting"
    },
    {
      "severity": "Medium",
      "priority": 4,
      "description": "Enable type checking (mypy) for static analysis",
      "action": "Add mypy check step to CI workflow"
    },
    {
      "severity": "Medium",
      "priority": 5,
      "description": "Set up security scanning in CI/CD",
      "action": "Add bandit or safety checks to workflow"
    },
    {
      "severity": "Low",
      "priority": 6,
      "description": "Set up deployment automation from CI/CD",
      "action": "Configure auto-deploy on main branch after passing tests"
    }
  ]
}
EOF
}

# Main execution
generate_ci_report "$PROJECT_DIR"
