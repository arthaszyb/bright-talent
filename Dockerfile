# Demo image: builds the reference instance and can run any component.
# Used by docker-compose.yml (mock Change Gateway + governance console) and
# verified by the repo-ci docker-demo job on every push.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# git: skills-lock commit resolution + console draft-MR branches; make: repo entry points
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Compile the reference instance and pre-sync the console venv so container
# startup is instant instead of resolving dependencies on first request.
RUN cd instances/acme-checkout-sre \
    && ../../scaffold/de validate . \
    && ../../scaffold/de build . \
    && cd ../.. \
    && uv sync --project console

EXPOSE 8801 8900

# Default: governance console. The compose file overrides command per service.
CMD ["uv", "run", "--project", "console", "python", "-m", "console.app", \
     "--repo", ".", "--host", "0.0.0.0", "--port", "8900"]
