FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create a non-root user (UID/GID 1000) so bind-mounted output files on Linux
# are owned by a regular user rather than root.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --no-create-home app

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements change.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source. Generated artifacts (data-*.json, reports/, etc.) are excluded
# by .dockerignore and will be written to the bind-mounted host directory at run time.
COPY . .

RUN chown -R app:app /app

USER app

CMD ["python", "main.py"]
