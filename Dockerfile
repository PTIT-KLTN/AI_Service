FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory (for worker mode)
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Pipeline configuration (default: optimized)
ENV USE_OPTIMIZED_PIPELINE=true
ENV RECIPE_CACHE_TTL=3600
ENV RECIPE_CACHE_MAXSIZE=1000
ENV OPTIMIZED_MAX_WORKERS=3

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

# Expose port for FastAPI application
EXPOSE 8000

# Default command - run FastAPI app with optimized pipeline
# Override this in docker-compose.yml for different modes
CMD ["uvicorn", "app.main_optimized:app", "--host", "0.0.0.0", "--port", "8000"]
