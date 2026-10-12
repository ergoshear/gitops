"""
CrewAI API Server - REST endpoint for CrewAI multi-agent workflows.

Exposes crews via a REST API. Supports synchronous kickoff and
asynchronous task submission with status polling.

Environment variables:
  CREWAI_LLM_PROVIDER   - LLM provider: "olla" (default), "openai", "anthropic"
  CREWAI_LLM_BASE_URL   - Base URL for the LLM API
  CREWAI_LLM_MODEL      - Model name/alias to use
  CREWAI_LLM_API_KEY    - API key for the LLM provider
  CREWAI_MAX_WORKERS    - Max concurrent crew executions
  CREWAI_TIMEOUT        - Timeout per crew execution (seconds)
"""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from crewai import Agent, Crew, Task
from crewai.llm import LLM

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("CREWAI_LLM_PROVIDER", "olla")
LLM_BASE_URL = os.getenv("CREWAI_LLM_BASE_URL", "http://olla:40114/olla/openai/v1")
LLM_MODEL = os.getenv("CREWAI_LLM_MODEL", "qwen2.5-coder-32b-instruct")
LLM_API_KEY = os.getenv("CREWAI_LLM_API_KEY", "olla")
MAX_WORKERS = int(os.getenv("CREWAI_MAX_WORKERS", "4"))
TIMEOUT = int(os.getenv("CREWAI_TIMEOUT", "300"))


def get_llm():
    """Create an LLM instance based on environment configuration."""
    return LLM(
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
    )


# ---------------------------------------------------------------------------
# In-memory task store for async execution
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


active_tasks: dict[str, ExecutionResult] = {}
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Configuration for a single agent in the crew."""
    role: str = Field(..., description="The role/identity of the agent")
    goal: str = Field(..., description="What the agent is trying to achieve")
    backstory: str = Field(..., description="Context and personality for the agent")
    tools: list[str] = Field(default_factory=list, description="Tool names to equip")


class TaskConfig(BaseModel):
    """Configuration for a task in the crew."""
    description: str = Field(..., description="What the task should accomplish")
    expected_output: str = Field(..., description="Description of the expected output format")
    agent: str = Field(..., description="Role of the agent assigned to this task")


class KickoffRequest(BaseModel):
    """Request to execute a crew."""
    agents: list[AgentConfig] = Field(..., description="Agents in the crew")
    tasks: list[TaskConfig] = Field(..., description="Tasks to execute")
    process: str = Field(
        default="sequential",
        description="Execution process: sequential, hierarchical, or consensual"
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Context variables available to tasks"
    )
    max_iter: int = Field(default=10, description="Max iterations per task")
    max_rpm: Optional[int] = Field(
        default=None,
        description="Max requests per minute (rate limiting)"
    )


class KickoffResponse(BaseModel):
    """Response from a crew execution."""
    output: str = Field(..., description="Final output from the crew")
    task_id: str = Field(..., description="Unique task identifier")
    elapsed_seconds: float = Field(..., description="Execution time in seconds")


class TaskStatusResponse(BaseModel):
    """Response for task status polling."""
    task_id: str
    status: TaskStatus
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    active_tasks: int
    max_workers: int


# ---------------------------------------------------------------------------
# Crew execution logic
# ---------------------------------------------------------------------------

def build_crew(request: KickoffRequest) -> Crew:
    """Build a Crew from the request configuration."""
    llm = get_llm()

    agents = {}
    for agent_cfg in request.agents:
        agent = Agent(
            role=agent_cfg.role,
            goal=agent_cfg.goal,
            backstory=agent_cfg.backstory,
            llm=llm,
            max_iter=request.max_iter,
            verbose=True,
        )
        agents[agent_cfg.role] = agent

    tasks = []
    for task_cfg in request.tasks:
        agent = agents.get(task_cfg.agent)
        if not agent:
            raise ValueError(f"Unknown agent role: {task_cfg.agent}")
        task = Task(
            description=task_cfg.description,
            expected_output=task_cfg.expected_output,
            agent=agent,
        )
        tasks.append(task)

    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=request.process,
        max_rpm=request.max_rpm,
    )


def execute_crew(task_id: str, request: KickoffRequest) -> str:
    """Execute a crew and return the output."""
    result = active_tasks[task_id]
    result.status = TaskStatus.RUNNING
    result.started_at = time.time()

    try:
        crew = build_crew(request)
        result = crew.kickoff(inputs=request.input)

        # Crew.kickoff returns a CrewOutput or str depending on version
        if hasattr(result, "raw"):
            output = result.raw
        elif hasattr(result, "output"):
            output = result.output
        else:
            output = str(result)

        active_tasks[task_id].status = TaskStatus.COMPLETED
        active_tasks[task_id].output = output
        active_tasks[task_id].completed_at = time.time()
        return output

    except Exception as e:
        active_tasks[task_id].status = TaskStatus.FAILED
        active_tasks[task_id].error = str(e)
        active_tasks[task_id].completed_at = time.time()
        raise


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CrewAI API",
    description="REST API for executing CrewAI multi-agent workflows",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        llm_provider=LLM_PROVIDER,
        llm_model=LLM_MODEL,
        active_tasks=sum(1 for r in active_tasks.values() if r.status == TaskStatus.RUNNING),
        max_workers=MAX_WORKERS,
    )


@app.post("/kickoff", response_model=KickoffResponse)
def kickoff(request: KickoffRequest):
    """Execute a crew synchronously and return the result."""
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = ExecutionResult(task_id=task_id)

    start = time.time()
    try:
        output = execute_crew(task_id, request)
        elapsed = time.time() - start

        # Clean up after completion
        del active_tasks[task_id]

        return KickoffResponse(
            output=output,
            task_id=task_id,
            elapsed_seconds=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = time.time() - start
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/kickoff/async", response_model=TaskStatusResponse)
def kickoff_async(request: KickoffRequest):
    """Submit a crew for asynchronous execution."""
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = ExecutionResult(task_id=task_id)

    future = executor.submit(execute_crew, task_id, request)
    future.add_done_callback(
        lambda f: _on_future_done(task_id, f)
    )

    return TaskStatusResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """Get the status of an async crew execution."""
    result = active_tasks.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**result.__dict__)


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Remove a completed task from the store."""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    result = active_tasks.pop(task_id)
    return {"deleted": task_id, "status": result.status}


@app.get("/tasks")
def list_tasks():
    """List all active and recent tasks."""
    return {
        "tasks": [
            {"task_id": r.task_id, "status": r.status}
            for r in active_tasks.values()
        ],
        "total": len(active_tasks),
    }


def _on_future_done(task_id: str, future: Future):
    """Callback when an async crew execution completes."""
    if future.exception() and active_tasks[task_id].status == TaskStatus.RUNNING:
        active_tasks[task_id].status = TaskStatus.FAILED
        active_tasks[task_id].error = str(future.exception())
        active_tasks[task_id].completed_at = time.time()


# ---------------------------------------------------------------------------
# Pre-built demo crews
# ---------------------------------------------------------------------------

@app.get("/crews")
def list_crews():
    """List available pre-built crew templates."""
    return {
        "crews": [
            {
                "id": "research",
                "name": "Research Crew",
                "description": "Web research and summary crew with a researcher and writer agent",
            },
            {
                "id": "code-review",
                "name": "Code Review Crew",
                "description": "Code analysis and review crew with reviewer and suggester agents",
            },
            {
                "id": "content",
                "name": "Content Creator Crew",
                "description": "Content creation crew with researcher, writer, and editor agents",
            },
        ]
    }


@app.post("/crews/{crew_id}/run")
def run_crew(crew_id: str, input: dict[str, Any] = Field(default_factory=dict)):
    """Run a pre-built crew template."""
    request = KickoffRequest(
        agents=[],
        tasks=[],
        input=input,
    )

    if crew_id == "research":
        request.agents = [
            AgentConfig(
                role="Researcher",
                goal="Find accurate and relevant information from available sources",
                backstory="You are an expert researcher skilled at finding and synthesizing information from multiple sources.",
            ),
            AgentConfig(
                role="Writer",
                goal="Produce clear, well-structured summaries and reports",
                backstory="You are a skilled technical writer who excels at distilling complex information into clear, actionable summaries.",
            ),
        ]
        request.tasks = [
            TaskConfig(
                description="Research the topic and gather relevant information. Focus on accuracy and comprehensiveness.",
                expected_output="A comprehensive research brief with key findings, sources, and notable insights.",
                agent="Researcher",
            ),
            TaskConfig(
                description="Transform the research findings into a clear, well-structured summary.",
                expected_output="A polished summary report with key takeaways and actionable insights.",
                agent="Writer",
            ),
        ]
    elif crew_id == "code-review":
        request.agents = [
            AgentConfig(
                role="Reviewer",
                goal="Identify bugs, security issues, and code quality problems",
                backstory="You are a senior software engineer with expertise in code review, security, and best practices.",
            ),
            AgentConfig(
                role="Suggester",
                goal="Propose concrete improvements and refactoring suggestions",
                backstory="You are an experienced developer who excels at suggesting practical, actionable code improvements.",
            ),
        ]
        request.tasks = [
            TaskConfig(
                description="Review the provided code for bugs, security vulnerabilities, and quality issues.",
                expected_output="A detailed review listing issues found, severity levels, and locations.",
                agent="Reviewer",
            ),
            TaskConfig(
                description="Based on the review findings, suggest concrete improvements and refactoring.",
                expected_output="Specific improvement suggestions with code examples and rationale.",
                agent="Suggester",
            ),
        ]
    elif crew_id == "content":
        request.agents = [
            AgentConfig(
                role="Researcher",
                goal="Gather relevant facts, data, and context for the content topic",
                backstory="You are an expert researcher who finds the most relevant and engaging information.",
            ),
            AgentConfig(
                role="Writer",
                goal="Create engaging, well-structured content based on research",
                backstory="You are a creative writer who transforms research into compelling content.",
            ),
            AgentConfig(
                role="Editor",
                goal="Review and refine content for clarity, accuracy, and style",
                backstory="You are a meticulous editor who ensures content is polished and error-free.",
            ),
        ]
        request.tasks = [
            TaskConfig(
                description="Research the content topic and gather relevant information.",
                expected_output="Research notes with key facts, data points, and context.",
                agent="Researcher",
            ),
            TaskConfig(
                description="Write the content based on the research findings.",
                expected_output="A complete draft of the content piece.",
                agent="Writer",
            ),
            TaskConfig(
                description="Review the draft for clarity, accuracy, tone, and style. Make improvements.",
                expected_output="A polished final version of the content with editorial notes.",
                agent="Editor",
            ),
        ]
    else:
        raise HTTPException(status_code=404, detail=f"Unknown crew template: {crew_id}")

    task_id = str(uuid.uuid4())
    active_tasks[task_id] = ExecutionResult(task_id=task_id)

    start = time.time()
    try:
        output = execute_crew(task_id, request)
        elapsed = time.time() - start
        del active_tasks[task_id]

        return KickoffResponse(
            output=output,
            task_id=task_id,
            elapsed_seconds=round(elapsed, 2),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
