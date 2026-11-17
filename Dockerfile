# Same Python version as the development virtual environment (3.13.3).
# Bump this together with the venv and the pins in requirements.txt.
FROM python:3.13.3-slim

# No .pyc files in the image; log output goes straight to the container log.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only: pytest, httpx and ruff live in
# requirements-dev.txt and never reach the image. Copied first so this layer
# is cached until the pins change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user. It needs a home directory: yfinance writes a
# timezone cache under the user's cache directory and logs errors when it
# cannot.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

# Copy only what the service needs. Tests, scripts, CI config and docs stay
# out of the image; .dockerignore backs this up by keeping them out of the
# build context.
COPY --chown=app:app main.py ./
COPY --chown=app:app routes ./routes
COPY --chown=app:app schemas ./schemas
COPY --chown=app:app services ./services
# The daily paper-trading run. The image's default command serves the API;
# `python -m pipeline SYMBOL ...` runs this instead.
COPY --chown=app:app pipeline ./pipeline

USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
