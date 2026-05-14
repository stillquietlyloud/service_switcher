# Project Evaluator Quick Start

## Overview

The Project Evaluator Agent is now deployed and ready to use. It comprehensively evaluates any AI service project across code quality, performance, operational readiness, and development workflow.

---

## Files Created

### Agent Definition
- **`/.github/agents/project-evaluator.agent.md`** — Standalone agent definition with 8-phase evaluation workflow

### Evaluation Scripts
- **`/.github/scripts/run_evaluator.sh`** — Main entry point (runs all probes and generates report)
- **`/.github/scripts/probe_code_quality.sh`** — Analyzes type hints, error handling, structure
- **`/.github/scripts/probe_dependencies.sh`** — Parses requirements and dependency files
- **`/.github/scripts/probe_cve.sh`** — Scans for known vulnerabilities
- **`/.github/scripts/probe_performance.sh`** — Measures latency and resource usage
- **`/.github/scripts/probe_health.sh`** — Checks /health and /ready endpoints
- **`/.github/scripts/probe_tests.sh`** — Detects test coverage and framework
- **`/.github/scripts/probe_ci.sh`** — Identifies CI/CD platforms and automation

### Templates & References
- **`/.github/templates/evaluation_report_template.md`** — Report structure and sections
- **`/.github/references/evaluation_framework.md`** — Severity levels, scoring rubric, effort estimates
- **`/.github/references/code_quality_patterns.md`** — Best practices for FastAPI, PyTorch, TensorFlow

---

## Usage

### Local Evaluation (on-target)
```bash
cd /path/to/project
/git/super_agent-new/.github/scripts/run_evaluator.sh .
```

**Output:** `evaluation_report.md` in the project root

### Evaluate from Another Location
```bash
/git/super_agent-new/.github/scripts/run_evaluator.sh /path/to/project
```

### Remote Evaluation (GitHub API + clone)
```bash
/git/super_agent-new/.github/scripts/run_evaluator.sh https://github.com/user/repo
# or
/git/super_agent-new/.github/scripts/run_evaluator.sh user/repo
```

**Output:** `evaluation_report.md` in temporary directory + summary to stdout

### Filter by Severity Level
```bash
# Only show Critical + High findings
/git/super_agent-new/.github/scripts/run_evaluator.sh /path/to/project --severity-filter High
```

### Remote API Only (no local probes)
```bash
# Use GitHub API for metadata, skip local filesystem
/git/super_agent-new/.github/scripts/run_evaluator.sh user/repo --remote-only
```

---

## Report Output

The evaluator generates `evaluation_report.md` with:

1. **Executive Summary** — severity breakdown, key metrics, critical issues
2. **Project Metadata** — type, stack, location, git info
3. **Code Quality** — type hints, error handling, structure analysis
4. **Performance** — latency, resource usage, bottlenecks
5. **Operational Readiness** — health checks, logging, monitoring, graceful shutdown
6. **Development Workflow** — CI/CD, tests, documentation, automation
7. **Security & Dependencies** — CVEs, outdated packages, vulnerability details
8. **Action Plan** — time-phased recommendations (immediate/urgent/planned)
9. **Deployment Strategy** — pre-flight checklist, phased rollout, rollback plan

---

## Severity Levels

### Critical 🔴 (0-48 hours)
- Missing or broken health checks
- Hardcoded secrets in code
- No error handling (will crash)
- Unpatched critical CVEs (CVSS 9+)
- Single point of failure

### High 🟠 (1-7 days)
- No structured logging
- Poor error handling
- High-severity CVEs (CVSS 7-8.9)
- Unmaintained dependencies
- No CI/CD pipeline

### Medium 🟡 (1-4 weeks)
- Incomplete type hints (< 80%)
- Low test coverage (< 50%)
- Outdated dependencies (6mo+)
- Missing documentation
- No linting/formatting

### Low 🟢 (1-3 months)
- Code style inconsistencies
- Minor refactoring opportunities
- Documentation gaps
- Efficiency improvements

---

## Example: Self-Evaluate super_agent-new

```bash
cd /git/super_agent-new
chmod +x .github/scripts/*.sh
./.github/scripts/run_evaluator.sh .
```

Expected output:
```
╔════════════════════════════════════════════╗
║   Project Evaluator Agent - v1.0         ║
╚════════════════════════════════════════════╝

[Eval] Mode: local
[Eval] Target: .
[Eval] Remote-only: false

[Eval] Running diagnostic probes...
[Eval] Probes completed
[Eval] Generating comprehensive report...
[Eval] ✓ Evaluation complete

Report: ./evaluation_report.md
Data: ./evaluation_data/
```

View the report:
```bash
cat evaluation_report.md
```

---

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Project Evaluation
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:  # Manual trigger

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Project Evaluator
        run: |
          bash .github/scripts/run_evaluator.sh .
      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: evaluation-report
          path: evaluation_report.md
```

### GitLab CI Example
```yaml
evaluate_project:
  script:
    - bash .github/scripts/run_evaluator.sh .
  artifacts:
    paths:
      - evaluation_report.md
  only:
    - schedules
```

---

## Customization

### Skip Certain Probes
Edit `run_evaluator.sh` to comment out probes:
```bash
# bash "$SCRIPT_DIR/probe_performance.sh" ...  # Skip performance
bash "$SCRIPT_DIR/probe_cve.sh" ...  # Keep CVE scan
```

### Add Custom Probes
Create `probe_custom.sh` following the pattern:
```bash
#!/bin/bash
# Output JSON format matching other probes
cat <<EOF
{
  "custom_metric": "value",
  "recommendations": []
}
EOF
```

Then add to `run_evaluator.sh`:
```bash
bash "$SCRIPT_DIR/probe_custom.sh" > "$eval_dir/custom.json"
```

### Configure Timeouts
Set environment variables:
```bash
export EVAL_BENCH_TIMEOUT=60  # Seconds for health/performance probes
./.github/scripts/run_evaluator.sh .
```

---

## Troubleshooting

### Scripts Not Executable
```bash
chmod +x .github/scripts/*.sh
```

### "No module named pip_audit"
Install pip-audit for enhanced CVE scanning:
```bash
pip install pip-audit
```

### "Repository not found" (Remote Evaluation)
Ensure GitHub repo is public or use a GitHub token:
```bash
export GITHUB_TOKEN="your_token"
```

### Performance Probes Timeout
Increase timeout:
```bash
export EVAL_BENCH_TIMEOUT=60
./.github/scripts/run_evaluator.sh .
```

### Health Check Failing
Ensure service is running:
```bash
# Start your service in another terminal
uvicorn app.main:app --reload

# Then run evaluator
./.github/scripts/run_evaluator.sh .
```

---

## Next Steps

1. **Test the evaluator:**
   ```bash
   cd /git/super_agent-new
   chmod +x .github/scripts/*.sh
   ./.github/scripts/run_evaluator.sh .
   cat evaluation_report.md
   ```

2. **Evaluate another project:**
   ```bash
   ./.github/scripts/run_evaluator.sh /path/to/another/project
   ```

3. **Integrate into CI/CD:**
   - Copy the `.github/` directory to your projects (deploy-agent.sh does this)
   - Add a GitHub Actions workflow to run evaluations weekly
   - Review reports in CI artifacts

4. **Customize for your needs:**
   - Adjust severity thresholds in `evaluation_framework.md`
   - Add custom probes for your infrastructure
   - Integrate with your internal tool stack

5. **Monitor trends:**
   - Run evaluator after each major release
   - Track severity counts over time
   - Celebrate improvements!

---

## Support

For issues or customizations, refer to:
- **Agent Definition:** `/.github/agents/project-evaluator.agent.md`
- **Evaluation Framework:** `/.github/references/evaluation_framework.md`
- **Code Patterns:** `/.github/references/code_quality_patterns.md`
- **Report Template:** `/.github/templates/evaluation_report_template.md`

---

*Project Evaluator Quick Start v1.0*
