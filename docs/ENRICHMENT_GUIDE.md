# KAI Platform - Agent Enrichment Guide

## Overview

The KAI platform has been significantly enriched with advanced tools, specialized prompts, and comprehensive safety policies to enable secure, capability-rich operations across multiple teams and use cases.

## What's New

### 1. Expanded Tool Catalog (30+ Tools)

#### **Troubleshooting & Root Cause Analysis**
- **`trace_pod_dependencies`**: Map service connections, environment references, and upstream/downstream calls
- **`analyze_crash_loop`**: Deep dive into pod failures with exit codes, termination messages, and recent events
- **`event_history`**: Build outage timelines with filtered events, reason summaries, and severity tracking
- **`cluster_health_summary`**: Quick cluster status check (nodes, pods, running vs failed)

#### **Cost Optimization & FinOps**
- **`cost_breakdown_by_namespace`**: Daily cost estimates by namespace (CPU, memory, storage)
- **`resource_efficiency_analysis`**: Identify over-provisioned workloads, single-replicas, idle StatefulSets
- **`cost_anomaly_detection`**: Flag unusual resource requests and storage outliers
- **`identify_resource_bottlenecks`**: Find over-constrained workloads hitting limits

#### **Security & Compliance**
- **`analyze_rbac`**: Audit ClusterRoles, roles, role bindings, and service accounts
- **`check_network_policies`**: Scan network segmentation and identify unprotected pods
- **`analyze_pod_security`**: Flag root users, privileged containers, writable filesystems
- **`list_secrets_audit`**: Read-only Secret audit (names/references only, NEVER values)
- **`analyze_image_security`**: Detect :latest images, non-IfNotPresent pull policies
- **`check_pod_disruption_budgets`**: Verify HA coverage during maintenance
- **`audit_cluster_policies`**: Executive compliance summary (Pod Security, NetworkPolicy, RBAC, etc.)

#### **Performance & Observation**
- **`analyze_pod_performance`**: CPU/memory trends, network I/O, latency percentiles
- **`find_slow_queries`**: Database/service query analysis from Prometheus
- **`cluster_health_summary`**: Node readiness, system component health, API responsiveness

#### **GitOps & Deployment Management**
- **`analyze_argocd_sync_status`**: GitOps health, sync state, drift detection
- **`get_deployment_history`**: Rollout history, rollback candidates, revision tracking

#### **Multi-Cluster & Federation** (Placeholder for future expansion)
- **`list_clusters`**: Available clusters in context
- **`switch_cluster_context`**: Change active cluster for multi-cluster operations

---

## Team-Specialized Prompt Modes

### Available Modes

Each mode is a user-selectable focus that biases tool selection and response format to a specific team's priority:

#### **`reliability`** (SRE/Troubleshooting)
- **Priority**: Incident root causes, operational runbooks
- **Key Tools**: `event_history`, `analyze_crash_loop`, `trace_pod_dependencies`, `cluster_health_summary`
- **Output**: Actionable diagnostics, SLO/SLI impact quantification, escalation paths

#### **`sre`** (Site Reliability Engineering)
- **Priority**: Operational excellence, incident response, runbook automation
- **Key Tools**: SRE-specific tools, performance analysis, recovery procedures
- **Output**: Runbook steps, escalation procedures, recovery guidance

#### **`security`** (Security & Compliance)
- **Priority**: Risk assessment, vulnerability scanning, policy enforcement
- **Key Tools**: `analyze_rbac`, `check_network_policies`, `analyze_pod_security`, `audit_cluster_policies`
- **Output**: Compliance reports, policy violations, remediation steps

#### **`compliance`** (Audit & Governance)
- **Priority**: Policy adherence, audit trails, regulatory mapping
- **Key Tools**: `audit_cluster_policies`, `check_resource_quotas_compliance`, `analyze_pod_security`
- **Output**: Evidence-based audit trails, CIS/PCI-DSS/SOC2/ISO27001 mapping

#### **`cost`** (FinOps & Budget)
- **Priority**: Cost optimization, resource efficiency, spend awareness
- **Key Tools**: `cost_breakdown_by_namespace`, `resource_efficiency_analysis`, `finops_cluster_signals`
- **Output**: Quantified savings in $/day, rightsizing recommendations, waste identification

#### **`devops`** (Infrastructure & Platform)
- **Priority**: Platform reliability, deployment automation, infrastructure-as-code
- **Key Tools**: GitOps tools, HPA analysis, cluster health, policy compliance
- **Output**: Infrastructure recommendations, policy-as-code guidance, automation readiness

#### **`general`** (Default)
- **Priority**: Balanced across all concerns
- **Output**: Comprehensive cluster overview with actionable insights

---

## Multi-Step Reasoning Framework

KAI now supports structured, multi-step analysis for complex troubleshooting scenarios:

### The 5-Step Methodology

1. **Information Gathering Phase**
   - Collect baseline state across pods, deployments, services, events, metrics
   - Tools: `cluster_health_summary`, `list_events`, `list_pods`

2. **Root Cause Analysis Phase**
   - Synthesize data to identify failure patterns, dependencies, cascading effects
   - Tools: `analyze_crash_loop`, `trace_pod_dependencies`, `event_history`

3. **Impact Assessment Phase**
   - Quantify SLO/SLI impact, affected users, data loss risk
   - Tools: `get_pod_details`, `get_logs`, `analyze_pod_performance`

4. **Resolution Recommendation Phase**
   - Provide specific, actionable steps with safety checks
   - Tools: Observability and configuration tools (read-only)

5. **Historical Context Phase**
   - Use rollback candidates, deployment history, GitOps status
   - Tools: `get_deployment_history`, `analyze_argocd_sync_status`

### Invoking Multi-Step Analysis

The orchestrator automatically detects complex scenarios and applies multi-step reasoning. No explicit action needed by users - just describe your problem in detail.

---

## Safety & Security Features

### Security-First Design

**Read-Only Operation (Enforced)**
- No write operations possible: `kubectl apply`, `patch`, `delete`
- No port-forwarding for modifications
- No `exec` for state changes
- All sandbox operations are audited and logged

**Secret Protection (Enforced)**
- `list_secrets_audit` returns only names/references - NEVER values
- No decoding of base64-encoded Secret values
- Secure handling of sensitive ConfigMap data

**Rate Limiting & Quota**
- List operations paginated with max result enforcement
- Prometheus queries: 10-second timeout
- Log reads: 2500 lines max per query
- ConfigMap data: 64KB per value max

**Compliance & Audit**
- All tool calls logged with timestamp and context
- Policy violation auto-detection (Pod Security, NetworkPolicy, RBAC, image policies)
- Automatic risk flagging (CrashLoopBackOff > 30 min, NotReady nodes, secret mounting, etc.)

**PII & Data Protection**
- Long values truncated to 600-1000 chars
- Logs scrubbed of potential sensitive data
- Data retention policies enforced (events: 24h default, logs: 7d)
- Safe error reporting without stack traces

---

## How to Use

### Via CLI/API

**Get Available Modes**:
```bash
curl http://agent-controller/chat
```
Returns: `"prompt_modes": ["general", "sre", "security", "compliance", "cost", "devops", ...]`

**Query with Specific Mode**:
```bash
curl http://agent-controller/chat \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Why are my pods in CrashLoopBackOff?",
    "prompt_mode": "sre"
  }'
```

**With Screenshots** (for visual analysis):
```bash
curl http://agent-controller/chat \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Is this dashboard showing issues?",
    "prompt_mode": "security",
    "images": ["data:image/png;base64,..."]
  }'
```

### Response Format

All responses include:
- **mode**: "conversation" or "tools"
- **response**: Human-readable analysis
- **tool_calls** (if used): Which tools were executed
- **tool_results** (if used): Raw data collected

---

## Examples by Team

### SRE Team - Debugging a Deployment Failure

**Query**:
```json
{
  "message": "Production deployment hung at 3/5 ready replicas for 20 minutes",
  "prompt_mode": "sre"
}
```

**Process**:
1. Orchestrator selects SRE mode → biases toward incident tools
2. Planner runs: `list_deployments` → `get_deployment_rollout_status` → `analyze_crash_loop` → `get_logs`
3. Multi-step analysis: Gathers baseline → analyzes pod failures → checks events → identifies root cause
4. Response includes runbook steps, escalation guidance, recovery procedures

---

### Finance Team - Optimization Opportunities

**Query**:
```json
{
  "message": "Show me the biggest cost drivers and optimization opportunities",
  "prompt_mode": "cost"
}
```

**Process**:
1. Orchestrator selects Cost mode → biases toward FinOps tools
2. Planner runs: `cost_breakdown_by_namespace` → `resource_efficiency_analysis` → `cost_anomaly_detection` → `identify_resource_bottlenecks`
3. Response includes:
   - Cost per namespace ($/day)
   - Over-provisioned workloads (projected savings)
   - Anomalies and outliers
   - Specific rightsizing recommendations

---

### Security Team - Compliance Audit

**Query**:
```json
{
  "message": "Run a compliance audit against CIS Kubernetes Benchmark",
  "prompt_mode": "compliance"
}
```

**Process**:
1. Orchestrator selects Compliance mode → biases toward security/audit tools
2. Planner runs: `audit_cluster_policies` → `analyze_rbac` → `check_network_policies` → `analyze_pod_security` → `check_resource_quotas_compliance`
3. Response includes:
   - Policy violations with severity
   - Compliance gaps mapped to CIS/PCI-DSS/SOC2
   - Evidence-based audit trail
   - Remediation steps

---

## Extending the Platform

### Adding New Tools

1. **Define** the tool in `shared/tools.yaml`:
   ```yaml
   - name: my_tool
     arguments:
       param1: required description
       param2: optional description
     detail: What this tool returns and when to use it
   ```

2. **Implement** in `agent_sandbox/tool_dispatch.py`:
   ```python
   elif tool == "my_tool":
       param1 = arguments.get("param1")
       # Your tool logic
       return {"tool": "my_tool", "result": ...}
   ```

3. **Test** via API:
   ```bash
   curl http://agent-sandbox/execute \
     -X POST \
     -H "Content-Type: application/json" \
     -d '{"tool": "my_tool", "arguments": {"param1": "value"}}'
   ```

### Adding New Prompt Modes

1. **Create** `agent_controller/prompt_modes/{mode_name}.txt`
2. **Write** tool selection instructions (see existing modes for format)
3. **Done** - mode automatically loads and appears in `/chat` metadata

### Custom Analysis Templates

Add new templates to `agent_controller/prompt_templates/`:
- `multistep_analysis.txt` - Already added for complex troubleshooting
- Create custom templates for specific workflows

---

## Architecture & Performance

### Tool Execution Flow

```
User Query
  ↓
[Orchestrator] Load mode, images
  ↓
[Planner] Decide which tools needed (Gemini)
  ↓
[Sandbox] Execute tools in parallel (read-only)
  ↓
[Summarizer] Digest tool results
  ↓
[Analyzer] Generate response (Gemini + tools data)
  ↓
User Response
```

### Performance Characteristics

- **Tool Execution**: Parallel where possible; typically 2-5 seconds for 5-10 tools
- **Prometheus Queries**: 10-second timeout, cached for 60 seconds
- **API Calls**: Batched where possible; respects Kubernetes API rate limits
- **Response Size**: Tool results capped at `max_tool_context_chars` (default 128KB)

### Scalability

- Tools run read-only: No state changes, safe to parallelize
- Rate limiting per tool: Prevents cluster overload
- Paginated results: No memory exhaustion on large clusters
- Configurable timeouts: Graceful degradation on slow queries

---

## Troubleshooting

### Tool Not Found

**Issue**: `Unknown tool: my_tool`

**Solution**: Verify tool name in `shared/tools.yaml` and `tool_dispatch.py` - must match exactly

### Timeout on Cluster Query

**Issue**: Response takes > 30 seconds

**Solution**: 
- Reduce cluster size or narrow query scope
- Use specific namespaces instead of cluster-wide
- Check Prometheus server responsiveness

### Secret Values Displayed

**Issue**: Secret contents in response

**Solution**: This is a security violation - immediately rotate affected Secrets

---

## Next Steps & Roadmap

### Phase 1 (Completed)
- ✅ 30+ tools for troubleshooting, cost, security, compliance
- ✅ Team-specialized prompt modes
- ✅ Multi-step reasoning framework
- ✅ Safety policies and guardrails

### Phase 2 (Recommended)
- [ ] Multi-cluster federation tools
- [ ] ML-powered anomaly detection
- [ ] Custom alert integration (PagerDuty, Slack)
- [ ] Trend analysis over time (capacity planning)
- [ ] Policy-as-code generators (OPA/Kyverno)

### Phase 3 (Future)
- [ ] Write operations (with approval workflows)
- [ ] Integration with ChatOps platforms
- [ ] Custom team role plugins
- [ ] Advanced visualization dashboards
- [ ] Predictive health scoring

---

## Support & Resources

- **Documentation**: See `docs/` directory
- **Architecture**: See [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Deployment**: See [DEPLOYMENT.md](../DEPLOYMENT.md)
- **Safety Policies**: See [SAFETY_POLICIES.md](./SAFETY_POLICIES.md)
- **Issues**: Escalate security concerns to platform team immediately

---

## Summary

KAI is now a comprehensive, secure, and extensible Kubernetes intelligence platform that serves multiple teams with specialized prompts, rich tool catalog, and enterprise-grade safety controls. All operations remain read-only and fully auditable, making it safe for production use across organizations.
