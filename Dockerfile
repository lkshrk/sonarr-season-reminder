FROM python:3.15-slim

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy source code
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package
RUN pip install --no-cache-dir .

# Run as non-root user
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["new-seasons-reminder"]
