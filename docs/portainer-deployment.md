# Portainer Deployment

This guide deploys `zygo-dataX` as a containerized web service.

## What The Container Runs

- Web app: `zygo_datax.web.app:app`
- Internal port: `8000`
- Default host port in `docker-compose.yml`: `8017`
- Persistent output folder inside the container: `/app/runs`
- Health check: `GET /health`

## Build Locally

From the project directory:

```bash
docker compose build
docker compose up -d
```

Open:

```text
http://SERVER_IP:8017
```

Check health:

```bash
curl http://SERVER_IP:8017/health
```

## Portainer Stack

In Portainer:

1. Go to Stacks.
2. Click Add stack.
3. Name it `zygo-datax`.
4. Use this stack file:

```yaml
services:
  zygo-datax:
    image: zygo-datax:latest
    container_name: zygo-datax
    restart: unless-stopped
    ports:
      - "8017:8000"
    environment:
      ZYGO_DATAX_RUN_ROOT: /app/runs
      MPLBACKEND: Agg
    volumes:
      - zygo-datax-runs:/app/runs

volumes:
  zygo-datax-runs:
```

5. Deploy the stack.

If Portainer cannot see a locally built `zygo-datax:latest` image, either build it on the Docker host first or use the GHCR image:

```yaml
services:
  zygo-datax:
    image: ghcr.io/yonggangg/zygo-datax:latest
    container_name: zygo-datax
    restart: unless-stopped
    ports:
      - "8017:8000"
    environment:
      ZYGO_DATAX_RUN_ROOT: /app/runs
      MPLBACKEND: Agg
    volumes:
      - zygo-datax-runs:/app/runs

volumes:
  zygo-datax-runs:
```

## Portainer Git Repository Deployment

If the project is in a Git repository accessible from the Docker host:

1. Create a new Stack.
2. Choose Repository.
3. Set the repository URL and branch.
4. Set compose path:

```text
docker-compose.yml
```

5. Deploy.

Portainer will build the image from the included `Dockerfile` when using the compose file in this repository.

## Data Persistence

Analysis runs are written to:

```text
/app/runs
```

The compose file stores this in a named Docker volume:

```text
zygo-datax-runs
```

Each upload creates a run folder containing:

- input DATX
- structure summary JSON
- web result JSON
- wavefront/fringe/Zernike analysis files
- Zemax Grid Sag DAT
- full ZIP bundle

## Change External Port

To expose the app on a different host port, change:

```yaml
ports:
  - "8017:8000"
```

For example:

```yaml
ports:
  - "8088:8000"
```

## Resource Notes

DATX files can be tens of MB. A practical minimum container allocation:

- CPU: 2 cores
- RAM: 2 GB
- Disk: enough for uploaded DATX files and generated ZIP reports

For large batches, increase RAM and periodically clean old run folders or rotate the Docker volume.
