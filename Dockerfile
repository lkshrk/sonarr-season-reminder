FROM python:3.14-slim

WORKDIR /app

ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Install build dependencies
RUN pip install --no-cache-dir hatchling hatch-vcs

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
