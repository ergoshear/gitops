# CrewAI API

Self-hosted CrewAI multi-agent workflow endpoint at `https://crew.ergoshear.dev`.

## Architecture

A FastAPI wrapper around [CrewAI](https://github.com/crewAIInc/crewAI) that
exposes crew execution via REST API. Integrates with the in-cluster Olla model
gateway for LLM inference.

## Endpoints

### Health
- `GET /health` — Service status with LLM configuration and active task count

### Crew Execution
- `POST /kickoff` — Execute a crew synchronously (blocking)
- `POST /kickoff/async` — Submit a crew for async execution
- `GET /tasks/{task_id}` — Poll async task status
- `DELETE /tasks/{task_id}` — Remove completed task
- `GET /tasks` — List all tasks

### Pre-built Crews
- `GET /crews` — List available crew templates
- `POST /crews/{crew_id}/run` — Run a pre-built crew template

Available templates: `research`, `code-review`, `content`

## Configuration

| Environment Variable     | Default                                  | Description                          |
|--------------------------|------------------------------------------|--------------------------------------|
| `CREWAI_LLM_PROVIDER`    | `olla`                                   | LLM provider name                    |
| `CREWAI_LLM_BASE_URL`    | `http://olla:40114/olla/openai/v1`      | LLM API base URL                     |
| `CREWAI_LLM_MODEL`       | `qwen2.5-coder-32b-instruct`             | Model name/alias                     |
| `CREWAI_LLM_API_KEY`     | `olla`                                   | API key for the LLM provider         |
| `CREWAI_MAX_WORKERS`     | `4`                                      | Max concurrent crew executions       |
| `CREWAI_TIMEOUT`         | `300`                                    | Timeout per execution (seconds)      |

## Example: Custom Crew

```bash
curl -X POST https://crew.ergoshear.dev/kickoff \
  -H "Content-Type: application/json" \
  -d '{
    "agents": [
      {
        "role": "Researcher",
        "goal": "Find information about the topic",
        "backstory": "You are an expert researcher."
      },
      {
        "role": "Writer",
        "goal": "Write a clear summary",
        "backstory": "You are a skilled technical writer."
      }
    ],
    "tasks": [
      {
        "description": "Research quantum computing advances in 2025",
        "expected_output": "A research brief with key findings",
        "agent": "Researcher"
      },
      {
        "description": "Summarize the research findings",
        "expected_output": "A clear summary report",
        "agent": "Writer"
      }
    ],
    "process": "sequential"
  }'
```

## Example: Pre-built Crew

```bash
curl -X POST https://crew.ergoshear.dev/crews/research/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "Rust programming language"}'
```

## Building and Publishing

```bash
# Build the Docker image
docker build -t ghcr.io/ergoshear/crewai:latest .

# Push to GHCR
docker push ghcr.io/ergoshear/crewai:latest

# Deploy via ArgoCD (already configured)
kubectl kustomize apps/crewai --enable-helm | kubectl apply -f -
```

## Dependencies

- **Olla** (`olla.ergoshear.dev`) — Model gateway for LLM inference
- **cert-manager** — TLS certificate for `crew.ergoshear.dev`
- **ExternalDNS** — Route 53 A record for `crew.ergoshear.dev`
- **Traefik** — Ingress controller with TLS termination
