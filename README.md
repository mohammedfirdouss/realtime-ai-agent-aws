## Building a Realtime Agentic API with AWS CDK, AWS Lambda, AWS Step Functions, AWS EventBridge, Strands Agent

A serverless, event-driven platform for deploying and managing AI agents. Built with Python, AWS CDK, Lambda, Step Functions, EventBridge, and DynamoDB.

## Prerequisites
- Python >= 3.11
- AWS CLI (configured)
- AWS CDK CLI (`npm install -g aws-cdk`)
- Docker (for bundling Lambda layers)

## Quick Start

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

# Run tests
pytest tests/ -v

# Lint
ruff check .

# Synthesize CloudFormation (dev environment)
cdk synth -c env=dev

# Deploy (dev environment)
cdk deploy -c env=dev
```

## Environments

| Environment | NAT Gateways | AZs | Notes |
|-------------|-------------|-----|-------|
| dev         | 0           | 2   | Isolated subnets, secrets auto-deleted |
| staging     | 1           | 2   | Private subnets with egress, VPC flow logs |
| prod        | 2           | 3   | Full HA, secrets retained on delete |
