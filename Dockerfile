FROM python:3.12-slim
WORKDIR /app

# System deps some Python packages may need (psycopg2-binary is self-contained,
# but keep this minimal image lean).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application packages (needed by collector, web app, and alerting).
COPY collector/ collector/
COPY inference/ inference/
COPY interface/ interface/
COPY api/ api/

# Default command is the collector; the compose file overrides it per service.
CMD ["python", "-m", "collector.main"]