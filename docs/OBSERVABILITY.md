# Langfuse Observability

## Hosting Options

### Option A: Self-Host on S-1 with Docker

**Prerequisites:**
- VM with at least 4 cores and 16 GiB RAM (e.g., AWS t3.xlarge)
- Docker and Docker Compose installed
- Public IP if traces come from external sources
- ~100 GiB storage (observability data grows quickly)

**Deployment:**

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
# Edit docker-compose.yml secrets (marked # CHANGEME)
docker compose up
```

Wait ~3 minutes for containers to start. Open `http://<host-ip>:3000` and create your first user and project.

**Services in the stack:**
- `langfuse-web` (port 3000) - Web UI and API
- `langfuse-worker` (port 3030) - Background job processing
- `postgres` - Primary database
- `clickhouse` - Analytics and observability storage
- `redis` - Cache and queue
- `minio` (port 9090) - Media storage

**Security:** Restrict inbound traffic to ports 3000, 9090, and 3031 (AI Gateway). All other services bind to localhost only.

**Tradeoffs:**
- Full data ownership and control
- No usage limits
- Higher operational burden (backups, updates, scaling)
- No built-in high-availability in docker-compose
- Cost: VM + storage (~$300-500/mo for t3.xlarge)

### Option B: Langfuse Cloud Free Tier

Sign up at [cloud.langfuse.com](https://cloud.langfuse.com) or `us.cloud.langfuse.com` (US region).

**Tradeoffs:**
- Zero infrastructure to manage
- Free tier has usage limits (check [pricing page](https://langfuse.com/pricing) for current limits)
- Data stored in Langfuse's infrastructure
- Faster setup

**Current pricing note:** Verify pricing and limits on the Langfuse website — they change over time.

## Configuration

Set these environment variables in your `.env` file:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_BASE_URL=https://your-langfuse-instance.com
LANGFUSE_ENABLED=true
```

For Langfuse Cloud: use `https://cloud.langfuse.com` (EU) or `https://us.cloud.langfuse.com` (US) as `LANGFUSE_BASE_URL`.

## What Gets Traced

Each graph run creates a trace with the following structure:

```
triage-run (span)
  ├── input_guardrail (span)
  ├── classify (span + generation)
  ├── retrieve (span)
  ├── draft_fix (span + generation)
  ├── guardrail (span)
  ├── review (span)
  └── execute|reject (span)
```

- **Generations** (classify, draft_fix): Include prompt, completion, model ID, token usage, and latency
- **Spans** (retrieve, guardrail): Include inputs, outputs, and latency
- **Metadata**: run_id, thread_id, tags [provider, model]

## Token Cost Tracking

Bedrock token usage is automatically captured from response metadata. If Langfuse doesn't have pricing for your Bedrock model ID (e.g., `amazon.nova-micro-v1:0`), add a custom model definition:

1. Go to Project Settings → Models & Pricing
2. Click "Add custom model"
3. Enter model ID: `amazon.nova-micro-v1:0`
4. Enter pricing from the [Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/)
5. Local runs have $0 cost

## Eval Integration

Eval runs are tagged with the eval run name. Each case trace receives scores:

- `category_correct` (0 or 1)
- `guardrail_agree` (0 or 1)

Filter by tag in the Langfuse UI to view a specific eval run's traces.

## Alerts

Langfuse's native alerting features (as of 2026):
- **Slack notifications** on trace-level thresholds
- **Cost-based alerts** via Langfuse's alerting system
- **Webhook notifications** for custom integrations

See [Langfuse alerting docs](https://langfuse.com/docs/observability/features/alerts) for current capabilities.

### Fallback: Custom Cost/Latency Checker

`scripts/check_costs.py` reads daily cost and p95 latency from the Langfuse API and warns when thresholds are exceeded. Configure thresholds in `.env`:

```env
COST_DAILY_MAX=100.00
LATENCY_P95_MS=30000
```

Run as a cron job or add to CI/CD pipeline. Keep the AWS Budgets alarm as a hard backstop.

## Prompt Management

Prompts `triage-classify` and `triage-draft` are managed in Langfuse:

- Fetch the version labeled `production` at startup
- Fall back to local `prompts/*.txt` files if Langfuse is unreachable
- Prompt name and version are recorded in audit entries
- Update the `production` label to deploy new prompt versions

## Graceful Degradation

When `LANGFUSE_ENABLED=false` or the Langfuse instance is unreachable, the agent runs normally with no observability overhead. Callbacks are empty, spans are skipped, and prompt loading falls back to local files.