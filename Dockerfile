FROM python:3.12-slim
# uv pinned so a rebuild resolves the same tool (latest release on 2026-10-26)
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY dugout ./dugout
COPY scenarios ./scenarios
# The MCP server's tools read the recorded demo match.
COPY data/demo-rfc-cas-0073.jsonl ./data/
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# Both apps only read files at run time, so they run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home dugout
USER dugout
EXPOSE 8000
CMD ["uvicorn", "dugout.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
