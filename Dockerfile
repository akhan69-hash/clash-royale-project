# Royale IQ -- single-service production image: builds the React frontend,
# then serves it (as static files) AND the FastAPI backend from one Python
# process on one port. Same-origin, no CORS needed in production, one
# dedicated IP to register with the Clash Royale API (see fly.toml).

# ---- Stage 1: build the React frontend ----
FROM node:22-alpine AS frontend-builder
WORKDIR /app/cr_platform/frontend
COPY cr_platform/frontend/package*.json ./
RUN npm ci
COPY cr_platform/frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend, serving the built frontend ----
FROM python:3.13-slim
WORKDIR /app

# Non-root container user -- UID/GID 1001 matches the deploy host's `ubuntu`
# user (see the docker-compose.yml bind mount of ./data), so files the app
# writes to the host-mounted data/ directory come out owned correctly
# instead of as root, and a compromised app process doesn't get root inside
# its own container either.
RUN groupadd -g 1001 appuser && useradd -u 1001 -g appuser -m appuser

# pandas/numpy/xgboost all ship prebuilt manylinux wheels for this platform,
# so no apt-get build toolchain is needed here.
COPY cr_platform/backend/requirements.txt cr_platform/backend/requirements.txt
RUN pip install --no-cache-dir -r cr_platform/backend/requirements.txt

COPY --chown=appuser:appuser cr_platform/backend cr_platform/backend
COPY --chown=appuser:appuser utils utils
COPY --chown=appuser:appuser scripts scripts
# Small derived CSVs only (see .dockerignore) -- the big collected_battles.csv
# and crawl_state.json are gitignored and live on the persistent volume
# instead (mounted over this same path at deploy time), not baked into the
# image. This copy just means the image still runs sensibly on its own
# (e.g. a quick local `docker run` with no volume attached).
COPY --chown=appuser:appuser data data
# The frontend's build output -- backend/main.py serves this directly
# whenever cr_platform/frontend/dist exists (see FRONTEND_DIST there).
COPY --chown=appuser:appuser --from=frontend-builder /app/cr_platform/frontend/dist cr_platform/frontend/dist

USER appuser
WORKDIR /app/cr_platform/backend
EXPOSE 8080
# --proxy-headers + --forwarded-allow-ips: trusts X-Forwarded-For from Caddy
# (the only thing that talks to this container -- see docker-compose.yml) so
# request.client.host resolves to the real visitor IP, not Caddy's container
# IP. Needed for main.py's per-IP rate limiter to actually rate-limit by
# visitor rather than accidentally limiting all traffic as if from one source.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
