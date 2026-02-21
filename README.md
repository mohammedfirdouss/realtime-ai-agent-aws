## Realtime Agentic API

A serverless, event-driven platform for deploying and managing AI agents. Built with Python, AWS CDK, Lambda, Step Functions, EventBridge, and DynamoDB.

## Architecture

```
┌──────────┐    ┌──────────────────┐    ┌────────────┐
│API Gateway│───▶│  Lambda Handlers │───▶│  DynamoDB   │
└──────────┘    └──────┬───────────┘    └────────────┘
                       │
                ┌──────▼───────────┐    ┌────────────┐
                │   EventBridge    │───▶│ Step Funcs  │
                └──────────────────┘    └────────────┘
                       │
                ┌──────▼───────────┐
                │  LLM Providers   │
                │ (OpenAI/Anthropic)│
                └──────────────────┘
```

### CDK Stacks

| Stack | Description |
|-------|-------------|
| **Foundation** | VPC, subnets, security groups |
| **Database** | DynamoDB tables (Agents, Tasks, Context, Connections) |
| **Cache** | ElastiCache Redis cluster |
| **Events** | EventBridge bus, rules, and archive |
| **Auth** | Lambda authorizers (API key + JWT), Secrets Manager |
| **AgentManagement** | Agent CRUD Lambda with DynamoDB and EventBridge access |

### Runtime Modules

| Module | Description |
|--------|-------------|
| `runtime/handlers/` | Lambda handler entry points (agent management) |
| `runtime/repositories/` | DynamoDB repository layer (agents, tasks, context, connections) |
| `runtime/auth/` | API key and JWT authorizers, permission middleware |
| `runtime/shared/` | Config, constants, secrets, cache, event publisher, LLM providers |

### LLM Providers

The `runtime/shared/llm_provider.py` module provides a unified interface for LLM integrations:

- **OpenAI** — GPT models via `/v1/chat/completions`
- **Anthropic** — Claude models via `/v1/messages`
- Exponential backoff retry (configurable, default 3 attempts)
- Circuit breaker pattern to avoid hammering failing providers
- API keys resolved from AWS Secrets Manager or passed directly

## Prerequisites
- Python >= 3.11
- AWS CLI (configured)
- AWS CDK CLI (`npm install -g aws-cdk`)
- Node.js (for CDK synthesis)

## Quick Start

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check .

# Synthesize CloudFormation (dev environment)
cdk synth -c env=dev

# Deploy (dev environment)
cdk deploy --all -c env=dev
```

## Environments

| Environment | NAT Gateways | AZs | Notes |
|-------------|-------------|-----|-------|
| dev         | 0           | 2   | Isolated subnets, secrets auto-deleted |
| staging     | 1           | 2   | Private subnets with egress |
| prod        | 2           | 3   | Full HA, secrets retained on delete |
