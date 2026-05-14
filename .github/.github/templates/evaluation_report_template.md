# Evaluation Report Template

**Generated:** {DATE}  
**Evaluator:** Project Evaluator Agent  
**Project:** {PROJECT_NAME}  
**Mode:** {MODE} (Local + Remote / Remote Only)  
**Location:** {PROJECT_PATH}

---

## Executive Summary

### Severity Breakdown
- **🔴 Critical:** {CRITICAL_COUNT}
- **🟠 High:** {HIGH_COUNT}
- **🟡 Medium:** {MEDIUM_COUNT}
- **🟢 Low:** {LOW_COUNT}

**Total Findings:** {TOTAL_COUNT}  
**Risk Level:** {OVERALL_RISK}

### Key Metrics
| Metric | Status |
|--------|--------|
| Code Quality (Type Hints) | {TYPE_HINT_PCT}% |
| Test Coverage | {TEST_COVERAGE_PCT}% |
| CVE Vulnerabilities | {CVE_COUNT} |
| CI/CD Pipeline | {CI_STATUS} |
| Operational Readiness | {OPS_READY} |

### Critical Issues (Require Immediate Action)
{CRITICAL_LIST}

---

## 1. Project Metadata

**Project Type:** {PROJECT_TYPE}  
**Primary Language:** Python  
**Framework(s):** {FRAMEWORKS}  
**Location:** {PROJECT_PATH}  
**Repository:** {REPO_URL}  
**Git Branch:** {BRANCH}  
**Last Commit:** {LAST_COMMIT}  
**Python Version Required:** {PYTHON_VERSION}

**Key Dependencies:**
{DEPENDENCY_TABLE}

---

## 2. Code Quality & Architecture Assessment

### Type Hint Coverage
- **Functions Analyzed:** {TOTAL_FUNCTIONS}
- **Functions with Type Hints:** {FUNCTIONS_WITH_HINTS}
- **Coverage:** {TYPE_HINT_PCT}%
- **Target:** 80%+ for public APIs

**Finding:** {TYPE_HINT_FINDING}

**Severity:** {TYPE_HINT_SEVERITY}  
**Effort:** {TYPE_HINT_EFFORT}  
**Impact:** IDE support, static type checking, runtime safety

---

### Error Handling & Robustness
- **Try-Catch Blocks:** {TRY_CATCH_COUNT}
- **Exception Handlers:** {EXCEPTION_HANDLERS}
- **Coverage Ratio:** {ERROR_HANDLING_RATIO}

**Finding:** {ERROR_HANDLING_FINDING}

**Severity:** {ERROR_HANDLING_SEVERITY}  
**Effort:** {ERROR_HANDLING_EFFORT}  
**Impact:** Production reliability, troubleshooting capability

---

### Code Structure & Organization
- **Lines of Code:** {LOC}
- **Files Count:** {FILE_COUNT}
- **Main Components:** {COMPONENTS}
- **Cyclomatic Complexity:** {COMPLEXITY_SCORE}

**Finding:** {STRUCTURE_FINDING}

**Severity:** {STRUCTURE_SEVERITY}  
**Effort:** {STRUCTURE_EFFORT}  
**Impact:** Maintainability, team velocity

---

## 3. Performance & Scalability Analysis

### Latency Metrics
- **API Endpoint (p50):** {LATENCY_P50}ms
- **API Endpoint (p99):** {LATENCY_P99}ms
- **Target (FastAPI):** < 100ms (p99)

**Finding:** {LATENCY_FINDING}

### Resource Utilization
- **Memory Usage (baseline):** {MEMORY_MB}MB
- **CPU Utilization:** {CPU_PERCENT}%
- **GPU Utilization (if applicable):** {GPU_PERCENT}%

**Finding:** {RESOURCE_FINDING}

### Bottleneck Analysis
{BOTTLENECK_LIST}

**Severity:** {PERFORMANCE_SEVERITY}  
**Effort:** {PERFORMANCE_EFFORT}  
**Impact:** User experience, infrastructure cost, scalability

---

## 4. Operational Readiness

### Health & Monitoring Endpoints
- **`/health` Endpoint:** {HEALTH_ENDPOINT_STATUS}
- **`/ready` Endpoint:** {READY_ENDPOINT_STATUS}
- **Response Time:** {ENDPOINT_LATENCY}ms
- **Success Rate:** {ENDPOINT_SUCCESS_RATE}%

**Finding:** {HEALTH_FINDING}

### Structured Logging
- **Logging Framework:** {LOGGING_FRAMEWORK}
- **Log Levels Configured:** {LOG_LEVELS}
- **Structured Format:** {STRUCTURED_LOGGING_STATUS}

**Finding:** {LOGGING_FINDING}

### Monitoring & Observability
- **Metrics Endpoint:** {METRICS_ENDPOINT_STATUS}
- **Tracing Integration:** {TRACING_STATUS}
- **Alerting Rules:** {ALERTING_STATUS}

**Finding:** {MONITORING_FINDING}

### Deployment Safety
- **Configuration Management:** {CONFIG_MANAGEMENT}
- **Graceful Shutdown:** {GRACEFUL_SHUTDOWN}
- **Rollback Capability:** {ROLLBACK_CAPABILITY}

**Finding:** {DEPLOYMENT_SAFETY_FINDING}

**Severity:** {OPS_SEVERITY}  
**Effort:** {OPS_EFFORT}  
**Impact:** Reliability, incident response time, zero-downtime deployments

---

## 5. Development Workflow & Automation

### CI/CD Pipeline
- **Platform:** {CI_PLATFORM}
- **Pipelines:** {PIPELINE_COUNT}
- **Build Success Rate:** {BUILD_SUCCESS_RATE}%
- **Average Build Time:** {AVG_BUILD_TIME}min

**Finding:** {CI_FINDING}

### Automated Checks
| Check | Status | Coverage |
|-------|--------|----------|
| Linting | {LINTING_STATUS} | - |
| Type Checking | {TYPE_CHECKING_STATUS} | - |
| Testing | {TESTING_STATUS} | {TEST_COVERAGE_PCT}% |
| Security Scanning | {SECURITY_SCAN_STATUS} | - |

**Finding:** {AUTOMATED_CHECKS_FINDING}

### Test Coverage
- **Unit Tests:** {UNIT_TEST_COUNT}
- **Integration Tests:** {INTEGRATION_TEST_COUNT}
- **Coverage %:** {TEST_COVERAGE_PCT}%
- **Target:** 80%+

**Finding:** {TEST_COVERAGE_FINDING}

### Documentation
- **API Documentation:** {API_DOCS_STATUS}
- **Setup Instructions:** {SETUP_DOCS_STATUS}
- **Runbook/Operations Guide:** {RUNBOOK_STATUS}

**Finding:** {DOCUMENTATION_FINDING}

**Severity:** {WORKFLOW_SEVERITY}  
**Effort:** {WORKFLOW_EFFORT}  
**Impact:** Team velocity, onboarding, knowledge retention

---

## 6. Dependency & Security Audit

### Vulnerability Summary
- **Critical CVEs (CVSS 9.0+):** {CVE_CRITICAL}
- **High CVEs (CVSS 7-8.9):** {CVE_HIGH}
- **Medium CVEs (CVSS 4-6.9):** {CVE_MEDIUM}
- **Low CVEs (CVSS 0-3.9):** {CVE_LOW}

### Outdated Dependencies
| Package | Current | Latest | Age |
|---------|---------|--------|-----|
{OUTDATED_PACKAGES_TABLE}

### Vulnerability Details
{CVE_DETAILS_LIST}

**Severity:** {SECURITY_SEVERITY}  
**Effort:** {SECURITY_EFFORT}  
**Impact:** Security posture, compliance, production stability

---

## 7. Action Plan

### 🔴 Critical (0-48 hours)
- [ ] **Item 1:** {CRITICAL_ITEM_1}
  - **Owner:** TBD
  - **Effort:** {EFFORT_HOURS}h
  - **Impact:** {IMPACT}
  - **Deployment:** {DEPLOYMENT_STRATEGY}

{CRITICAL_ITEMS}

### 🟠 High (1-7 days)
{HIGH_PRIORITY_ITEMS}

### 🟡 Medium (1-4 weeks)
{MEDIUM_PRIORITY_ITEMS}

### 🟢 Low (1-3 months)
{LOW_PRIORITY_ITEMS}

---

## 8. Deployment Strategy

### Pre-flight Validation Checklist
- [ ] All changes reviewed and tested in staging
- [ ] Test suite runs with > 80% coverage passing
- [ ] Performance baseline established and compared
- [ ] CVE scan passed (no critical/high vulnerabilities)
- [ ] Linting and type checks passing (clean build)
- [ ] Health/ready endpoints responding < 100ms
- [ ] Monitoring/alerting configured and tested

### Phased Rollout Plan

#### Phase 1: Canary (10% traffic, 1-2 days)
1. Deploy to 10% of production traffic
2. Monitor error rate, latency, resource usage
3. Set alert thresholds:
   - Error rate: alert > 0.1%, auto-rollback > 1%
   - Latency (p99): alert > 2x baseline, auto-rollback > 5x
4. Validate health checks passing
5. Decision point: proceed or rollback

#### Phase 2: Progressive (50% traffic, 2-3 days)
1. Roll out to 50% of traffic
2. Continue monitoring against thresholds
3. Gather performance data and user feedback
4. Document any anomalies

#### Phase 3: Full Deployment (100% traffic, 1 day)
1. Roll out to remaining 50% of traffic
2. Monitor for 24h minimum
3. Confirm no issues in full production load

### Rollback Procedure
- **Trigger:** Error rate > 1% OR p99 latency > 5x baseline OR health checks failing
- **Time to rollback:** < 5 minutes
- **Verification:** Health checks green, error rate < 0.1%, latency normalized

### Monitoring & Alerting
**Critical Alerts (PagerDuty/Slack):**
- Error rate > 1%
- p99 latency > 2s
- Health check failures > 10% of instances

**Warning Alerts (Slack only):**
- Error rate > 0.5%
- p99 latency > 1s
- Memory usage > 80% available

---

## Next Steps

1. **Immediate (today):**
   - [ ] Share report with engineering team
   - [ ] Identify critical blockers
   - [ ] Assign owners for Critical items

2. **This week:**
   - [ ] Schedule implementation kickoff
   - [ ] Create tickets for each action item
   - [ ] Establish review/approval process

3. **Ongoing:**
   - [ ] Weekly status updates on action items
   - [ ] Re-run evaluation after each major release
   - [ ] Track trend in severity counts over time

---

## Appendix: Evaluation Methodology

**Evaluation Date:** {DATE}  
**Evaluator Agent:** Project Evaluator v1.0  
**Mode:** {MODE}  
**Probes Run:** {PROBES_EXECUTED}  
**Total Runtime:** {RUNTIME_SECONDS}s

**Data Sources:**
- Local filesystem analysis (code inspection)
- PyPI API (dependency metadata)
- CVE databases (vulnerability scanning)
- Performance benchmarks (latency, resource usage)
- CI/CD platform APIs (pipeline status)
- GitHub API (repo metadata)

**Severity Classification:**
- **Critical:** Breaks deployability or production
- **High:** Production risk or compliance issue
- **Medium:** Best practice gap or tech debt
- **Low:** Code quality or style issue

**Report limitations:**
- Performance metrics captured at evaluation time (may vary with load)
- CVE data depends on available scanning tools
- Recommendations are guidance; adjust based on business context

---

*Generated by Project Evaluator Agent*  
*Evaluation Report v1.0*
