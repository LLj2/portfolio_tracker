# Portfolio Tracker - Production Deployment Guide

## Overview

This guide covers deploying the Portfolio Tracker application to production using a security-hardened, single-container architecture designed for the provided Hetzner + Tailscale infrastructure.

## Architecture Changes

The application has been updated from the original 3-service architecture to a production-ready single-container deployment:

- **Before**: db + api:8000 + nginx:8080 (3 services)
- **After**: Single hardened container serving both API and frontend on port 8080
- **Database**: Optional PostgreSQL container or external database via `DATABASE_URL`
- **Security**: Non-root user, read-only filesystem, no-new-privileges

## Key Features Added

✅ **Health endpoint** (`/health`) for Docker healthchecks and monitoring
✅ **Environment-based configuration** (`.env` file with secrets management)
✅ **Multi-provider pricing**: Alpha Vantage → IEX Cloud → Yahoo Finance fallback
✅ **Robust error handling** with timeouts and retries for all external APIs
✅ **Structured JSON logging** for production monitoring and debugging
✅ **CORS restriction** from environment variables (no wildcards)
✅ **Container security hardening** (non-root, read-only, tmpfs)
✅ **Versioned image deployment** with rollback capability

## Container Registry Setup

### Option 1: GitHub Container Registry (Recommended)

1. **Create Personal Access Token**:
   - Go to GitHub → Settings → Developer settings → Personal access tokens
   - Create token with `write:packages` and `read:packages` permissions

2. **Login to Registry**:
   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin
   ```

3. **Update Image Reference**:
   Edit `docker-compose.prod.yml`:
   ```yaml
   image: ghcr.io/your-username/portfolio-tracker:1.0.0
   ```

### Option 2: Docker Hub

1. **Login**: `docker login`
2. **Update Image Reference**:
   ```yaml
   image: your-dockerhub-username/portfolio-tracker:1.0.0
   ```

## Deployment Steps

### 1. Prepare Environment

```bash
# On your server (as ops user)
mkdir -p ~/portfolio/{data,pgdata,backups}
cd ~/portfolio

# Copy the production files (adjust paths as needed)
cp /path/to/docker-compose.prod.yml ./docker-compose.yml
cp /path/to/.env.example ./.env
```

### 2. Configure Environment

Edit `.env` file with your settings:

```bash
# Required: Set your API keys
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
IEX_CLOUD_TOKEN=your_iex_cloud_token

# Required: Database configuration
DATABASE_URL=postgresql://user:pass@host:5432/portfolio

# Optional: Customize other settings
BASE_CURRENCY=EUR
SCHED_WINDOWS=12:00,20:00
ALLOWED_ORIGINS=http://your-tailscale-ip:8080
```

### 3. Deploy Application

```bash
# Login to your container registry (if private)
echo $GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin

# Pull the specific version
docker compose pull

# Start services
docker compose up -d

# Check status
docker compose ps
docker compose logs -f portfolio --tail 50
```

### 4. Verify Deployment

```bash
# Health check
curl -f http://localhost:8080/health && echo " ✓ Health check passed"

# Check structured logs
docker compose logs portfolio | tail -5 | jq '.'

# API documentation (optional)
curl -s http://localhost:8080/docs | grep -q "swagger" && echo " ✓ API docs accessible"
```

### 5. Access via Tailscale

From any Tailscale-connected device:
```
http://<your-server-tailscale-ip>:8080
```

**Note**: Add your actual Tailscale URL to `ALLOWED_ORIGINS` in `.env`

## Rollback Procedures

### Quick Rollback to Previous Version

1. **Update image tag** in `docker-compose.yml`:
   ```yaml
   image: ghcr.io/your-username/portfolio-tracker:1.0.0  # change version
   ```

2. **Deploy previous version**:
   ```bash
   docker compose pull
   docker compose up -d
   docker compose logs -f portfolio --tail 20
   ```

3. **Verify rollback**:
   ```bash
   curl -f http://localhost:8080/health && echo " ✓ Rollback successful"
   ```

### Emergency Rollback (keeps data)

```bash
# Stop current version
docker compose down

# Quick restore to last known good version
sed -i 's/:1\.1\.0/:1.0.0/' docker-compose.yml  # example version change
docker compose pull
docker compose up -d

# Verify
curl -f http://localhost:8080/health
```

### Version Management Best Practices

- **Always use specific version tags** (never `latest`)
- **Keep previous version tag** in comments for quick rollback:
  ```yaml
  image: ghcr.io/your-username/portfolio-tracker:1.1.0
  # Previous: ghcr.io/your-username/portfolio-tracker:1.0.0
  ```
- **Test health check** before considering deployment complete
- **Monitor structured logs** for errors during deployment

## API Providers Configuration

### Alpha Vantage (Primary)
- Sign up at: https://www.alphavantage.co/
- Free tier: 5 requests/minute, 500 requests/day
- Set `ALPHAVANTAGE_API_KEY` in `.env`

### IEX Cloud (Secondary)
- Sign up at: https://iexcloud.io/
- Free tier: 50,000 requests/month
- Set `IEX_CLOUD_TOKEN` in `.env`

### Yahoo Finance (Fallback)
- No API key required
- Rate limited, used as last resort

## Monitoring

### Health Checks
```bash
# Container health
docker compose ps

# Application health
curl http://localhost:8080/health
```

### Logs
```bash
# View logs
docker compose logs -f portfolio

# Structured JSON logs
docker compose logs portfolio | jq '.'
```

### Manual Operations
```bash
# Manual price refresh
curl -X POST http://localhost:8080/admin/refresh/prices

# Upload CSV files via web UI or API
# POST /upload/holdings
# POST /upload/nav
```

## Troubleshooting

### Common Issues

1. **Container won't start**
   ```bash
   docker compose logs portfolio
   # Check .env file configuration
   ```

2. **Database connection fails**
   ```bash
   # Verify DATABASE_URL format
   # Check database is accessible
   ```

3. **API pricing fails**
   ```bash
   # Check API keys in .env
   # Verify API quotas/limits
   # Check logs for specific errors
   ```

4. **Frontend not loading**
   ```bash
   # Verify ALLOWED_ORIGINS includes your access URL
   # Check if /health endpoint responds
   ```

## Backup & Recovery

The infrastructure includes automated backup scripts for both database and file-based data. Refer to the server setup documentation for details.

## Updates & Image Management

### Deploying New Versions

1. **Build and push new image** (see CI/CD section):
   ```bash
   # Tag with new version
   docker build -t ghcr.io/your-username/portfolio-tracker:1.1.0 ./portfolio-backend
   docker push ghcr.io/your-username/portfolio-tracker:1.1.0
   ```

2. **Update production**:
   ```bash
   # Update image tag in docker-compose.yml
   sed -i 's/:1\.0\.0/:1.1.0/' docker-compose.yml

   # Deploy
   docker compose pull
   docker compose up -d

   # Verify
   curl -f http://localhost:8080/health && echo " ✓ Update successful"
   ```

### Security Updates

For security patches and dependency updates:

```bash
# Pull base image updates
docker compose pull
docker compose up -d --force-recreate

# Verify system health
curl -f http://localhost:8080/health
docker compose logs portfolio --tail 20
```