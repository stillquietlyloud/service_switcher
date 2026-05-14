# Project Evaluation Framework

## Overview

This framework defines the evaluation criteria, severity levels, and scoring methodology used by the Project Evaluator Agent to assess AI service projects across multiple dimensions.

---

## Severity Classification

### Critical (🔴) - Breaks Deployability
Fixes are **mandatory before production deployment**. These issues prevent safe operation or violate security/compliance requirements.

**Examples:**
- Missing health check endpoints (`/health`, `/ready`)
- Hardcoded secrets, API keys, or credentials in source code
- No error handling in main request paths (will crash on error)
- Unpatched critical CVEs (CVSS 9.0+)
- No graceful shutdown mechanism
- Data corruption risk or data loss on restart

**Action Timeline:** 0-48 hours  
**Effort:** Variable (hours to days)  
**Risk if Delayed:** Production incidents, security breach, compliance violation

---

### High (🟠) - Production Risk
Issues that **significantly impact reliability, security, or user experience** but can be deployed with workarounds/monitoring.

**Examples:**
- No centralized logging or error tracking
- Missing structured error responses (unhandled exceptions)
- Known high-severity CVEs (CVSS 7-8.9)
- Single point of failure (no redundancy, no failover)
- Dependencies unmaintained (2+ years without updates)
- No monitoring/alerting for critical metrics
- Manual deployment process (no automation)

**Action Timeline:** 1-7 days  
**Effort:** Days to weeks  
**Risk if Delayed:** Incidents harder to debug, security vulnerabilities exploited, operational burden

---

### Medium (🟡) - Best Practice Gap
Issues that represent **common tech debt or misalignment with industry standards**, affecting maintainability and team velocity.

**Examples:**
- Incomplete type hints (< 80% of public functions)
- Low test coverage (< 50% code coverage)
- No CI/CD pipeline
- Dependencies 6+ months outdated (not critical CVE)
- Missing API documentation
- Inconsistent code style
- No linting/formatting automation

**Action Timeline:** 1-4 weeks  
**Effort:** Weeks to months  
**Risk if Delayed:** Technical debt accumulates, team velocity decreases, onboarding slower

---

### Low (🟢) - Code Quality / Style
**Minor improvements** that enhance readability, consistency, or minor efficiency. Can be batched with other changes.

**Examples:**
- Code style inconsistencies (spacing, naming)
- Inefficient algorithms in non-critical paths
- Missing docstrings/comments
- Incomplete setup instructions
- Minor refactoring opportunities

**Action Timeline:** 1-3 months (can batch with other work)  
**Effort:** Hours to days  
**Risk if Delayed:** Minimal; code still works correctly

---

## Evaluation Dimensions

### 1. Code Quality & Architecture

#### Metric: Type Hint Coverage
- **Excellent (90-100%):** All public functions have type hints; private functions mostly typed
- **Good (70-89%):** Public API fully typed; internal functions mostly typed
- **Fair (50-69%):** ~50% of functions typed; some API endpoints lacking hints
- **Poor (0-49%):** Few or no type hints; IDE support compromised
- **Severity Mapping:**
  - Poor → High (if public API)
  - Fair → Medium
  - Good → Low (nice-to-have)
  - Excellent → ✓ (Pass)

#### Metric: Error Handling
- **Excellent:** All endpoints have try-catch; structured error responses with codes
- **Good:** Most endpoints handle errors; some structured responses
- **Fair:** Error handling present but inconsistent
- **Poor:** No error handling; exceptions propagate to client
- **Severity Mapping:**
  - Poor → Critical (will crash in production)
  - Fair → High (unreliable error messages)
  - Good → Medium (some edge cases uncovered)
  - Excellent → ✓ (Pass)

#### Metric: Code Structure
- **Excellent:** Clean separation: API routes → business logic → data layer; no circular imports
- **Good:** Mostly separated; some tight coupling
- **Fair:** Mixed concerns; basic structure present
- **Poor:** Monolithic or chaotic; hard to follow
- **Severity Mapping:**
  - Poor → Medium (hard to maintain/test)
  - Fair → Medium (refactor recommended)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

---

### 2. Performance & Scalability

#### Metric: Latency (p99)
- **Excellent:** < 100ms (FastAPI service)
- **Good:** 100-500ms
- **Fair:** 500ms-2s
- **Poor:** > 2s
- **Severity Mapping:**
  - Poor → High (user-facing impact)
  - Fair → Medium (acceptable but slow)
  - Good → Low (minor optimization opportunity)
  - Excellent → ✓ (Pass)

#### Metric: Resource Efficiency
- **Excellent:** Memory < 500MB, CPU avg < 30%, GPU well-utilized (if applicable)
- **Good:** Memory < 1GB, CPU avg < 50%
- **Fair:** Memory < 2GB, CPU avg < 70%
- **Poor:** Memory > 2GB or CPU > 70% or memory leaks detected
- **Severity Mapping:**
  - Poor → High (scalability risk, cost overruns)
  - Fair → Medium (optimization recommended)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Bottleneck Identification
- **Finding bottlenecks:** Profiler analysis identifies top 3 time consumers
- **Severity:** Medium-High if main path not optimized
- **Action:** Profile and optimize top 1-2 bottlenecks (usually 20% effort for 80% gain)

---

### 3. Operational Readiness

#### Metric: Health Check Endpoints
- **Excellent:** `/health` (< 50ms), `/ready` (< 100ms), both return valid JSON
- **Good:** Both endpoints present; response times acceptable
- **Fair:** One endpoint missing or slow (> 500ms)
- **Poor:** No health endpoints
- **Severity Mapping:**
  - Poor → Critical (cannot orchestrate)
  - Fair → High (incomplete health model)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Structured Logging
- **Excellent:** JSON logs with level/timestamp/component/trace_id; log aggregation configured
- **Good:** Structured JSON logs; basic levels set
- **Fair:** Logging present but not structured; hardcoded strings
- **Poor:** Minimal or no logging
- **Severity Mapping:**
  - Poor → High (hard to debug production issues)
  - Fair → Medium (log parsing painful)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Monitoring & Alerting
- **Excellent:** Prometheus/CloudWatch integration; dashboards and alert rules
- **Good:** Some metrics collected; basic dashboards
- **Fair:** Metrics available but not actively monitored
- **Poor:** No monitoring setup
- **Severity Mapping:**
  - Poor → High (blind in production)
  - Fair → Medium (reactive troubleshooting)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Graceful Shutdown
- **Excellent:** Service drains connections; completes in-flight requests
- **Good:** Service responds to SIGTERM; logs shutdown
- **Fair:** Service stops but may leave connections open
- **Poor:** Force kill only; data loss risk
- **Severity Mapping:**
  - Poor → Critical (data loss, inconsistent state)
  - Fair → High (connection leaks)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

---

### 4. Development Workflow & Automation

#### Metric: CI/CD Pipeline
- **Excellent:** GitHub Actions/GitLab CI with auto-test, auto-lint, auto-deploy
- **Good:** CI runs tests and linting; manual approval before deploy
- **Fair:** CI runs tests only; no linting or deployment automation
- **Poor:** No CI/CD; manual testing and deployment
- **Severity Mapping:**
  - Poor → High (error-prone, slow deployments)
  - Fair → Medium (incomplete automation)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Automated Checks
- **Excellent:** Linting + type checking + tests + security scan in CI
- **Good:** Linting + tests in CI
- **Fair:** Tests only in CI
- **Poor:** No automated checks
- **Severity Mapping:**
  - Poor → Medium (manual reviews needed)
  - Fair → Medium (missing checks)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Test Coverage
- **Excellent:** > 80% code coverage; unit + integration tests
- **Good:** 60-80% coverage; mostly unit tests
- **Fair:** 30-60% coverage; some tests
- **Poor:** < 30% or no tests
- **Severity Mapping:**
  - Poor → High (regression risk, difficult refactoring)
  - Fair → Medium (some test coverage, but gaps)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Documentation
- **Excellent:** API docs (OpenAPI/Swagger), setup instructions, runbook/operations guide
- **Good:** API docs + setup instructions
- **Fair:** Basic README; no API docs
- **Poor:** Minimal or no documentation
- **Severity Mapping:**
  - Poor → Medium (hard to onboard, ops difficult)
  - Fair → Medium (gaps in coverage)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

---

### 5. Dependency & Security

#### Metric: CVE Vulnerability Count
- **Excellent:** 0 CVEs
- **Good:** < 5 CVEs (all low/medium)
- **Fair:** 5-20 CVEs (mix of levels)
- **Poor:** > 20 CVEs or any critical/high
- **Severity Mapping:**
  - Any Critical → Critical severity
  - Any High (CVSS 7-8.9) → High severity
  - Any Medium (CVSS 4-6.9) → Medium severity
  - Low only → Low severity

#### Metric: Dependency Freshness
- **Excellent:** All dependencies within 6 months of latest
- **Good:** 80%+ within 6 months
- **Fair:** 50-80% within 6 months; some 1-2 years old
- **Poor:** Major dependencies 2+ years old
- **Severity Mapping:**
  - Poor → High (missing features, security patches)
  - Fair → Medium (some outdated)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

#### Metric: Maintenance Status
- **Excellent:** Main dependencies actively maintained (releases in last 3 months)
- **Good:** Most dependencies maintained (last 6-12 months)
- **Fair:** Some unmaintained dependencies (> 1 year)
- **Poor:** Key dependencies appear abandoned
- **Severity Mapping:**
  - Poor → High (risk of dead-end upgrade path)
  - Fair → Medium (may need migration path)
  - Good → Low (acceptable)
  - Excellent → ✓ (Pass)

---

## Effort Estimation

### Time Estimates for Common Improvements

| Item | Effort | Timeline |
|------|--------|----------|
| Add `/health` endpoint | 2-4h | Same day |
| Add `/ready` endpoint | 2-4h | Same day |
| Set up structured logging | 4-8h | 1 day |
| Add basic type hints to API | 4-8h | 1 day |
| Set up health checks monitoring | 4-8h | 1-2 days |
| Enable GitHub Actions CI | 4-8h | 1 day |
| Add pytest + coverage | 8-16h | 1-2 days |
| Update all dependencies | 4-12h | 1-2 days |
| Add integration tests | 16-24h | 2-3 days |
| Full type hint coverage (80%+) | 16-32h | 2-4 days |
| Implement graceful shutdown | 4-8h | 1-2 days |
| Set up security scanning in CI | 4-8h | 1 day |
| Comprehensive documentation | 8-16h | 1-2 days |

**Effort levels:**
- **Quick win:** < 4h (can do same day)
- **Short:** 4-8h (1-2 days)
- **Medium:** 8-16h (2-3 days)
- **Large:** 16-32h (1 week)
- **Epic:** > 32h (1+ months)

---

## Impact Scoring

### How to Estimate Business Impact

1. **Reliability:** Does this issue cause outages or incidents?
   - Critical impact: Incidents occur weekly or more
   - High impact: Incidents occur monthly
   - Medium impact: Incidents occur quarterly
   - Low impact: No known incidents

2. **Security:** Does this issue create a vulnerability?
   - Critical impact: Can expose secrets or cause data loss
   - High impact: Can be exploited by attackers
   - Medium impact: Increases attack surface
   - Low impact: Reduces defense-in-depth

3. **User Experience:** Does this impact end users?
   - Critical impact: Service is unavailable
   - High impact: Latency > 1s or frequent errors
   - Medium impact: Minor performance issues
   - Low impact: Cosmetic or rare issues

4. **Developer Velocity:** Does this slow down development?
   - Critical impact: Blocks all development
   - High impact: Slows team significantly (2+ hours/week)
   - Medium impact: Minor friction (< 1 hour/week)
   - Low impact: Negligible

5. **Compliance:** Does this violate regulations?
   - Critical impact: Audit failure, legal risk
   - High impact: Audit findings, compliance gaps
   - Medium impact: Best practice not followed
   - Low impact: No compliance requirement

---

## Evaluation Workflow

1. **Detect Project Type** (FastAPI, PyTorch, TensorFlow, general Python)
2. **Run Parallel Probes** (code quality, dependencies, CI detection, tests)
3. **Sequential Analysis** (CVE scan, health checks, performance)
4. **Classify Findings** by severity (Critical → Low)
5. **Estimate Effort** for each recommendation
6. **Prioritize by Impact** (business value per effort)
7. **Generate Report** with executive summary + detailed findings + action plan
8. **Output Deployment Strategy** (pre-flight checks, phased rollout, rollback plan)

---

## Report Quality Checklist

- [ ] All 5 dimensions evaluated (code quality, performance, ops, workflow, security)
- [ ] At least 3-5 findings per dimension
- [ ] Each finding has severity, effort, and impact estimate
- [ ] Action plan is time-phased (immediate, urgent, planned)
- [ ] Deployment strategy includes pre-flight checklist and rollback procedure
- [ ] No secrets/credentials exposed in report
- [ ] Recommendations are actionable (not vague)
- [ ] Report file is standalone and shareable

---

*Evaluation Framework v1.0*  
*Used by Project Evaluator Agent*
