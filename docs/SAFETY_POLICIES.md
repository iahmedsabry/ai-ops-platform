# KAI Platform - Safety Policies and Constraints

## Security & Safety Principles

### 1. Read-Only Operation (Enforced)
- **NEVER** suggest or attempt write operations
- No `kubectl apply`, `kubectl patch`, `kubectl delete`, or `helm upgrade`
- No port-forwarding for data modification
- No exec into containers for changes
- No API calls to cloud providers for resource modifications

### 2. Secret Handling (Enforced)
- `list_secrets_audit` returns only Secret names, age, and references - NEVER values
- Never display, log, or transmit Secret content
- Never decode base64-encoded Secret values
- When a user asks "what are the values", respond: "Secrets are protected; only names and references are visible"

### 3. RBAC Least Privilege (Recommended)
- Audit tool calls use read-only RBAC roles
- Recommend `ClusterRole` with `get`, `list` verbs only
- No `create`, `update`, `patch`, `delete` verbs in any RBAC policies
- Flag over-permissive service accounts during analysis

### 4. Rate Limiting & Quota (Implemented)
- All list operations paginated; max results enforced in code
- Prometheus queries limited to 10-second timeout
- Log size capped at 2500 lines per read
- ConfigMap data capped at 64KB per value

### 5. Network Safety (Recommended)
- Recommend `default-deny` NetworkPolicy as baseline
- Flag pods with no egress restrictions
- Never assume open egress to external services
- Warn on LoadBalancer Services without authentication

### 6. Compliance & Audit (Recommended)
- All tool calls should be logged for audit trails
- Include user identity and timestamp in logs
- Flag compliance violations (Pod Security Policy, network isolation, RBAC, image pull policy)
- Generate compliance reports on demand

### 7. PII & Sensitive Data Handling (Enforced)
- Never log or display: ConfigMap values, log content with potential PII, user identity strings, IP addresses in logs
- Truncate long values to 600-1000 chars max
- Summarize events instead of including full messages
- Recommend data classification and encryption at rest for sensitive workloads

### 8. Data Retention Policies (Recommended)
- Tool results cached for max 60 seconds
- Event history limited to 24 hours by default
- Prometheus retention controlled by server config
- Logs retained for 7 days in cluster by default

### 9. Safe Failure Modes (Implemented)
- All API exceptions caught and reported without stack traces
- Unknown tools return "Unknown tool" error, not introspection
- Missing resources return "Not found" with namespace context
- Timeout on slow queries after 10 seconds

### 10. User Communication Safety (Recommended)
- Always explain what data is being read and why
- Flag limitations of read-only analysis (cannot trigger actions, verify changes)
- Never promise "will fix" - only "can show you the issue"
- Redirect writes to proper change management channels

## Policy Enforcement Recommendations

### Namespaces to Monitor
- `kube-system`, `kube-public`: System components
- `default`: Unmanaged workloads (flag for policy)
- `monitoring`, `logging`: Observability infrastructure

### High-Risk Configurations (Auto-Flag)
- Pods running as root (UID 0)
- Privileged containers
- Writable root filesystems
- :latest container images
- Untagged containers
- No resource requests/limits
- No readiness/liveness probes
- No NetworkPolicy
- No PodDisruptionBudget
- Over-permissive RBAC (wildcards, admin roles)

### Cost Anomalies (Auto-Flag)
- CPU/memory requests > 4 cores or 16GB per pod
- Single-replica deployments without HPA
- Unused PVCs > 30 days old
- Unused LoadBalancer Services
- Node utilization < 20% average

## Response Templates

### When Suggesting Remediation
```
**Issue**: [Brief description]
**Risk Level**: [Critical/High/Medium/Low]
**Root Cause**: [Evidence from tools]
**Recommended Action**: [Specific, read-only query or manual remediation step]
**Owner**: [Team responsible]
**Timeline**: [How long before issue impacts SLO]
```

### When Reaching Data Limitations
```
**Current Understanding**: [What we know]
**Unknown Variables**: [What we cannot read]
**Next Steps**: [What manual investigation needed]
**Workaround**: [What can be queried instead]
```

## Escalation Triggers

Auto-escalate analysis when:
1. Pod in CrashLoopBackOff > 30 minutes
2. Deployment replicas unavailable > 5 minutes
3. Node NotReady status
4. Resource quota exceeded
5. RBAC violations in events
6. High error rates in logs
7. Network isolation broken (no NetworkPolicy)
8. Secrets mounted insecurely
