FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Docling PDF processing
RUN apt-get update && apt-get install -y \
    curl \
    libxcb1 \
    libxrender1 \
    libxext6 \
    libsm6 \
    libice6 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .

# Install uv and dependencies
RUN pip install uv && \
    uv pip install --system -e .

# Copy application code
COPY backend/app/ ./app/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
