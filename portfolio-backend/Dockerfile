FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (add curl for health checks)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r portfolio && useradd -r -g portfolio portfolio

# Copy requirements first for better caching
COPY portfolio-backend/backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY portfolio-backend/backend/ ./backend/

# Copy frontend files
COPY portfolio-frontend/ ./frontend/

# Create data directory and set permissions
RUN mkdir -p /var/lib/portfolio && \
    chown -R portfolio:portfolio /app /var/lib/portfolio

# Set Python path
ENV PYTHONPATH=/app

# Default environment variables
ENV PORT=8080

# Switch to non-root user
USER portfolio

# Expose port
EXPOSE 8080

# Run the application
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]