#!/bin/bash
# run_evaluator.sh
# Entry point for comprehensive project evaluation
# Usage: ./run_evaluator.sh <local_path | github_url> [--remote-only] [--severity-filter LEVEL]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-.}"
REMOTE_ONLY="${REMOTE_ONLY:-false}"
SEVERITY_FILTER="${SEVERITY_FILTER:-Low}"
EVAL_START=$(date +%s)
EVAL_DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Parse command-line arguments
while [[ $# -gt 1 ]]; do
  case "${2}" in
    --remote-only) REMOTE_ONLY="true"; shift ;;
    --severity-filter) SEVERITY_FILTER="${3}"; shift 2 ;;
    *) echo "Unknown option: ${2}"; exit 1 ;;
  esac
done

# Detect if input is local path or GitHub URL
detect_mode() {
  local input="$1"
  if [[ "$input" =~ ^https://github.com/ ]] || [[ "$input" =~ ^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$ ]]; then
    echo "remote"
  else
    echo "local"
  fi
}

# Create temporary directory for remote evaluation
setup_remote_eval() {
  local repo_url="$1"
  local temp_dir="/tmp/eval_$$"
  mkdir -p "$temp_dir"
  
  # Normalize GitHub URL
  if [[ ! "$repo_url" =~ ^https:// ]]; then
    repo_url="https://github.com/${repo_url}"
  fi
  
  echo -e "${BLUE}[Eval]${NC} Cloning ${repo_url} to ${temp_dir}..."
  git clone --depth 1 "$repo_url" "$temp_dir" 2>/dev/null || {
    echo -e "${RED}[Error]${NC} Failed to clone repository"
    exit 1
  }
  
  echo "$temp_dir"
}

# Run evaluation probes
run_probes() {
  local project="$1"
  local eval_dir="${project}/evaluation_data"
  mkdir -p "$eval_dir"
  
  echo -e "${BLUE}[Eval]${NC} Running diagnostic probes..."
  
  # Run each probe in parallel, capture output
  local -a pids=()
  
  # Safe parallel operations (code quality, dependencies, CI detection)
  bash "$SCRIPT_DIR/probe_code_quality.sh" "$project" > "$eval_dir/code_quality.json" 2>&1 & pids+=($!)
  bash "$SCRIPT_DIR/probe_dependencies.sh" "$project" > "$eval_dir/dependencies.json" 2>&1 & pids+=($!)
  bash "$SCRIPT_DIR/probe_ci.sh" "$project" > "$eval_dir/ci_cd.json" 2>&1 & pids+=($!)
  bash "$SCRIPT_DIR/probe_tests.sh" "$project" > "$eval_dir/tests.json" 2>&1 & pids+=($!)
  
  # Wait for parallel probes
  for pid in "${pids[@]}"; do
    wait "$pid" || echo -e "${YELLOW}[Warning]${NC} Probe failed (PID: $pid)"
  done
  
  # Sequential probes (require project state)
  bash "$SCRIPT_DIR/probe_cve.sh" "$project" "$eval_dir/dependencies.json" > "$eval_dir/cve.json" 2>&1
  
  # Performance/health probes (optional, skip if endpoint unavailable)
  if [[ "$REMOTE_ONLY" != "true" ]]; then
    bash "$SCRIPT_DIR/probe_health.sh" "$project" > "$eval_dir/health.json" 2>&1 || true
    bash "$SCRIPT_DIR/probe_performance.sh" "$project" > "$eval_dir/performance.json" 2>&1 || true
  fi
  
  echo -e "${GREEN}[Eval]${NC} Probes completed"
  echo "$eval_dir"
}

# Generate evaluation report
generate_report() {
  local project="$1"
  local eval_dir="$2"
  local report_file="${project}/evaluation_report.md"
  
  echo -e "${BLUE}[Eval]${NC} Generating comprehensive report..."
  
  # Start report with header
  cat > "$report_file" << 'EOF'
# Project Evaluation Report

**Generated:** $(date '+%Y-%m-%d %H:%M:%S')  
**Evaluator:** Project Evaluator Agent  
**Mode:** $([ "$REMOTE_ONLY" = "true" ] && echo "Remote (API + GitHub)" || echo "Local + Remote")

---

## Executive Summary

### Severity Breakdown
- **Critical:** 0
- **High:** 0
- **Medium:** 0
- **Low:** 0

### Key Findings
*See detailed sections below*

---

## 1. Project Metadata

**Project Type:** Detecting...  
**Language Stack:** Detecting...  
**Location:** $project  
**Evaluation Date:** $EVAL_DATE  

---

## 2. Code Quality Assessment

### Type Hint Coverage
- Functions with type hints: Analyzing...
- Public API coverage: Analyzing...
- Recommendation: Add type hints to public endpoints

### Error Handling
- Try-catch coverage: Analyzing...
- Structured error responses: Analyzing...

### Code Structure
- Separation of concerns: Analyzing...
- Cyclomatic complexity: Analyzing...

**Severity:** Medium → Low  
**Effort:** 1-2 weeks  
**Impact:** Maintainability, IDE support, runtime safety

---

## 3. Performance Analysis

### Latency Metrics
- API endpoint latency: Pending local probe...
- Model inference time: Pending local probe...
- Startup time: Pending local probe...

### Resource Utilization
- Memory usage: Pending local probe...
- CPU utilization: Pending local probe...
- GPU utilization (if applicable): Pending local probe...

**Severity:** Medium → Low  
**Effort:** 1-3 weeks for optimization  
**Impact:** User experience, cost efficiency

---

## 4. Operational Readiness

### Health & Monitoring
- /health endpoint: Pending local probe...
- /ready endpoint: Pending local probe...
- Structured logging: Analyzing...
- Monitoring integration: Analyzing...

### Deployment Safety
- Graceful shutdown: Analyzing...
- Configuration management: Analyzing...
- Rollback capability: Analyzing...

**Severity:** High  
**Effort:** 3-5 days for basic health checks  
**Impact:** Reliability, troubleshooting, incident response

---

## 5. Development Workflow

### CI/CD
- Pipeline presence: Detecting...
- Linting enabled: Detecting...
- Automated testing: Detecting...

### Test Coverage
- Unit tests: Analyzing...
- Integration tests: Analyzing...
- Coverage threshold: Analyzing...

### Documentation
- API documentation: Analyzing...
- Setup instructions: Analyzing...
- Runbook/Operations guide: Analyzing...

**Severity:** Medium  
**Effort:** 1-2 weeks  
**Impact:** Team velocity, onboarding, knowledge retention

---

## 6. Dependency & Security Audit

### Vulnerability Summary
- Critical CVEs: Pending CVE scan...
- High-severity CVEs: Pending CVE scan...
- Outdated packages (6mo+): Analyzing...

### Dependency Health
- Latest versions: Analyzing...
- Maintenance status: Analyzing...

**Severity:** Critical → High (depends on CVE findings)  
**Effort:** Days to weeks (patch vs. major upgrade)  
**Impact:** Security, stability

---

## 7. Action Plan

### Immediate (0-48 hours)
- [ ] Priority item 1
- [ ] Priority item 2

### Urgent (1-7 days)
- [ ] Week 1 item 1
- [ ] Week 1 item 2

### Planned (1-4 weeks)
- [ ] 1-month item 1
- [ ] 1-month item 2

### Strategic (1-3 months)
- [ ] Long-term item 1
- [ ] Long-term item 2

---

## 8. Deployment Strategy

### Pre-flight Validation
1. Verify all changes in staging environment
2. Run full test suite (coverage > 80%)
3. Performance baseline established

### Phased Rollout
1. **Phase 1:** Deploy to 10% canary traffic (1-2 days)
2. **Phase 2:** Deploy to 50% traffic (2-3 days, monitor SLOs)
3. **Phase 3:** Full deployment (auto-rollback if error rate > 0.1%)

### Monitoring & Rollback
- Alert thresholds: p99 latency < 500ms, error rate < 0.1%
- Rollback trigger: Error rate > 1% or p99 > 2s
- Rollback time: < 5 minutes

---

## Next Steps

1. **Review this report** with your team
2. **Prioritize action items** by business impact
3. **Assign owners** for each recommendation
4. **Schedule implementation** phases
5. **Set up monitoring** before deployment

---

*Report generated by Project Evaluator Agent*
EOF
  
  # TODO: Replace template placeholders with actual probe data
  # For now, we'll output the raw template
  
  echo -e "${GREEN}[Eval]${NC} Report saved to: ${report_file}"
  echo "$report_file"
}

# Main execution
main() {
  echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
  echo -e "${BLUE}║   Project Evaluator Agent - v1.0         ║${NC}"
  echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
  echo ""
  
  local mode=$(detect_mode "$PROJECT_ROOT")
  echo -e "${BLUE}[Eval]${NC} Mode: ${mode^^}"
  echo -e "${BLUE}[Eval]${NC} Target: $PROJECT_ROOT"
  echo -e "${BLUE}[Eval]${NC} Remote-only: $REMOTE_ONLY"
  echo ""
  
  local eval_project="$PROJECT_ROOT"
  
  # Setup remote evaluation if needed
  if [[ "$mode" == "remote" ]] && [[ "$REMOTE_ONLY" != "true" ]]; then
    eval_project=$(setup_remote_eval "$PROJECT_ROOT")
    trap "rm -rf $eval_project" EXIT
  fi
  
  # Run probes
  eval_dir=$(run_probes "$eval_project")
  
  # Generate report
  report=$(generate_report "$eval_project" "$eval_dir")
  
  # Summary
  echo ""
  echo -e "${GREEN}✓ Evaluation complete${NC}"
  echo -e "  Report: ${report}"
  echo -e "  Data: ${eval_dir}"
  echo ""
  
  # Display report summary
  echo -e "${BLUE}[Summary]${NC}"
  if [[ -f "$report" ]]; then
    head -50 "$report"
  fi
}

# Run main
main
