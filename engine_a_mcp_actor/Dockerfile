# Apify Actor & Hosted MCP Server Dockerfile (Zero pip dependencies — Python stdlib only)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Keep /app as parent root so ../shared_data/models_live.json and ../config.json paths resolve cleanly
WORKDIR /app/engine_a_mcp_actor

COPY . /app/engine_a_mcp_actor/

# Stage config.json if present and pre-populate live OpenRouter + Mainland China model catalog for <50ms cold starts
RUN mkdir -p /app/shared_data && \
    if [ -f /app/engine_a_mcp_actor/config.json ]; then cp /app/engine_a_mcp_actor/config.json /app/config.json; fi && \
    python3 fetch_and_enrich.py || true

EXPOSE 4321 8787

CMD ["python3", "apify_main.py"]
