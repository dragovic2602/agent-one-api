FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install uv && uv sync --no-install-project
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
