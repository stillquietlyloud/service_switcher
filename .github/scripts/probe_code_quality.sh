#!/bin/bash
# probe_code_quality.sh - Analyze code quality metrics
# Output: JSON with type hints, error handling, complexity analysis

set -euo pipefail

PROJECT_DIR="${1:-.}"

# JSON output structure
cat > /tmp/code_quality_$$.json << 'EOJSON'
{
  "type_hints": {
    "python_files": 0,
    "functions_total": 0,
    "functions_with_hints": 0,
    "coverage_percent": 0,
    "files_analyzed": []
  },
  "error_handling": {
    "try_catch_blocks": 0,
    "unhandled_patterns": 0,
    "patterns_found": []
  },
  "code_structure": {
    "lines_of_code": 0,
    "files_count": 0,
    "languages": [],
    "main_components": []
  },
  "issues": [
    {
      "severity": "Low",
      "type": "pending_analysis",
      "description": "Code quality analysis in progress..."
    }
  ]
}
EOJSON

# Analyze Python files for type hints
analyze_type_hints() {
  local dir="$1"
  local total_funcs=0
  local funcs_with_hints=0
  local files=()
  
  if [[ ! -d "$dir" ]]; then
    echo "null"
    return 0
  fi
  
  # Count functions and type hints
  while IFS= read -r file; do
    files+=("$file")
    # Count 'def ' lines (functions)
    local defs=$(grep -c "^def " "$file" || true)
    total_funcs=$((total_funcs + defs))
    
    # Count lines with type hints (lines with ':' in function definitions)
    local hints=$(grep "^def .*->" "$file" 2>/dev/null | wc -l || true)
    funcs_with_hints=$((funcs_with_hints + hints))
  done < <(find "$dir" -name "*.py" -type f 2>/dev/null | head -20)
  
  local coverage=0
  if [[ $total_funcs -gt 0 ]]; then
    coverage=$((100 * funcs_with_hints / total_funcs))
  fi
  
  cat <<EOF
{
    "coverage_percent": $coverage,
    "functions_total": $total_funcs,
    "functions_with_hints": $funcs_with_hints,
    "files_analyzed": ${#files[@]}
}
EOF
}

# Analyze error handling patterns
analyze_error_handling() {
  local dir="$1"
  local try_blocks=0
  local exception_handlers=0
  
  if [[ ! -d "$dir" ]]; then
    echo "null"
    return 0
  fi
  
  try_blocks=$(grep -r "try:" "$dir" --include="*.py" 2>/dev/null | wc -l || echo 0)
  exception_handlers=$(grep -r "except" "$dir" --include="*.py" 2>/dev/null | wc -l || echo 0)
  
  cat <<EOF
{
    "try_catch_blocks": $try_blocks,
    "exception_handlers": $exception_handlers,
    "ratio": $([ $try_blocks -gt 0 ] && echo "scale=2; $exception_handlers / $try_blocks" | bc 2>/dev/null || echo "0")
}
EOF
}

# Analyze code structure
analyze_code_structure() {
  local dir="$1"
  
  if [[ ! -d "$dir" ]]; then
    echo "null"
    return 0
  fi
  
  local py_files=$(find "$dir" -name "*.py" -type f 2>/dev/null | wc -l)
  local loc=$(find "$dir" -name "*.py" -type f 2>/dev/null -exec wc -l {} + | tail -1 | awk '{print $1}' || echo "0")
  
  cat <<EOF
{
    "python_files": $py_files,
    "lines_of_code": $loc,
    "main_dirs": $(find "$dir" -maxdepth 2 -type d -name "src" -o -name "app" -o -name "service" 2>/dev/null | wc -l)
}
EOF
}

# Generate consolidated JSON report
generate_json_report() {
  local dir="$1"
  local type_hints=$(analyze_type_hints "$dir")
  local error_handling=$(analyze_error_handling "$dir")
  local structure=$(analyze_code_structure "$dir")
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project": "$dir",
  "type_hints": $type_hints,
  "error_handling": $error_handling,
  "code_structure": $structure,
  "recommendations": [
    {
      "severity": "Medium",
      "area": "Type Hints",
      "description": "Add type hints to improve IDE support and catch errors early"
    },
    {
      "severity": "High",
      "area": "Error Handling",
      "description": "Ensure all exceptions are caught and handled gracefully"
    }
  ]
}
EOF
}

# Main execution
generate_json_report "$PROJECT_DIR"
