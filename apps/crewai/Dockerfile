FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app.py .
COPY crews/ ./crews/

# Run as non-root
RUN useradd -m crewai && chown -R crewai:crewai /app
USER crewai

EXPOSE 8000

ENV CREWAI_LLM_PROVIDER=olla
ENV CREWAI_LLM_BASE_URL=http://olla:40114/olla/openai/v1
ENV CREWAI_LLM_MODEL=qwen2.5-coder-32b-instruct
ENV CREWAI_LLM_API_KEY=olla
ENV CREWAI_MAX_WORKERS=4
ENV CREWAI_TIMEOUT=300

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
