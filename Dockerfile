FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create application user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create necessary directories
RUN mkdir -p data logs config temp && \
    chown -R appuser:appuser /app

# Copy project files
COPY --chown=appuser:appuser . .

# Create default configuration files
RUN echo "# SiliconFlow Key Scanner Search Queries" > config/queries.txt && \
    echo "sk- in:file" >> config/queries.txt && \
    echo "siliconflow in:file" >> config/queries.txt && \
    echo "\"sk-\" filetype:py" >> config/queries.txt && \
    echo "\"sk-\" filetype:js" >> config/queries.txt && \
    echo "\"sk-\" filetype:env" >> config/queries.txt && \
    chown appuser:appuser config/queries.txt

# Switch to non-root user
USER appuser

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Add metadata labels
LABEL maintainer="SiliconFlow Key Scanner Team" \
      version="0.0.1" \
      description="Automated scanner for SiliconFlow API keys in GitHub repositories" \
      org.opencontainers.image.title="SiliconFlow Key Scanner" \
      org.opencontainers.image.description="Automated scanner for SiliconFlow API keys in GitHub repositories" \
      org.opencontainers.image.version="0.0.1" \
      org.opencontainers.image.source="https://github.com/yourusername/siliconflow-key-scanner"

# Expose port (optional - if you add web interface later)
# EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
