FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy civiphrases source code (copied by deployment script)
COPY civiphrases/ ./civiphrases/
COPY pyproject.toml .

# Install civiphrases from source
RUN pip install -e .

# Copy application files
COPY app.py .
COPY templates/ templates/
COPY version.json .

# Create output directory and logs subdirectory
RUN mkdir -p /output/logs

# Set up Unraid-compatible user (nobody/users)
RUN chown -R nobody:users /app /output
USER nobody

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV OUT_DIR=/output

# Run the application with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "300", "app:app"]
