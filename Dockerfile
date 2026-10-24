FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure data and config directories exist
RUN mkdir -p data config

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000
ENV SCHEDULER_ENABLED=true
ENV COLLECTION_TIME_IST=01:00

CMD ["python", "main.py", "run-server", "--host", "0.0.0.0"]
