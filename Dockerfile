FROM python:3.11-slim

WORKDIR /app

# Install git and ssh for GitHub integration
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client gosu && rm -rf /var/lib/apt/lists/*

# Create cactus user with same UID/GID as host (files created will belong to cactus)
RUN groupadd -g 1000 cactus && useradd -u 1000 -g 1000 -m cactus

# SSH config for GitHub + git safe directory (for cactus user)
RUN mkdir -p /home/cactus/.ssh && \
    printf "Host github.com\n  IdentityFile /home/cactus/.ssh/github_key\n  StrictHostKeyChecking accept-new\n" > /home/cactus/.ssh/config && \
    chmod 700 /home/cactus/.ssh && chmod 600 /home/cactus/.ssh/config && \
    chown -R cactus:cactus /home/cactus/.ssh && \
    su -c "git config --global --add safe.directory '*'" cactus

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY config.py .
COPY cactus_secrets_client.py .
COPY index.html .
COPY chromium/ ./chromium/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create data directory for preferences (owned by cactus)
RUN mkdir -p /data && chown cactus:cactus /data

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost/health', timeout=5)" || exit 1

# Entrypoint fixes /data ownership then drops to cactus via gosu
ENTRYPOINT ["./entrypoint.sh"]

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "server:app"]
