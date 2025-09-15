# Portfolio Tracker - CI/CD Guide

## Overview

This guide provides CI/CD setup for automated building, testing, and publishing of the Portfolio Tracker Docker images using GitHub Actions.

## GitHub Actions Workflow

### `.github/workflows/build-and-publish.yml`

```yaml
name: Build and Publish Docker Image

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-test:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        cd portfolio-backend
        pip install -r backend/requirements.txt
        pip install pytest pytest-cov

    - name: Run tests
      run: |
        cd portfolio-backend
        # Add your test commands here when you have tests
        # pytest tests/
        echo "Tests would run here"

    - name: Lint code
      run: |
        cd portfolio-backend
        pip install flake8
        flake8 backend/ --count --select=E9,F63,F7,F82 --show-source --statistics

  build-and-publish:
    needs: build-and-test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ${{ env.REGISTRY }}
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Extract metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=sha,prefix={{branch}}-

    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        file: ./portfolio-backend/Dockerfile
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max

    - name: Generate deployment summary
      run: |
        echo "## 🚀 Deployment Summary" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        echo "**Image:** \`${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}\`" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        echo "**Tags:**" >> $GITHUB_STEP_SUMMARY
        echo "\`\`\`" >> $GITHUB_STEP_SUMMARY
        echo "${{ steps.meta.outputs.tags }}" >> $GITHUB_STEP_SUMMARY
        echo "\`\`\`" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        echo "**Deployment Command:**" >> $GITHUB_STEP_SUMMARY
        echo "\`\`\`bash" >> $GITHUB_STEP_SUMMARY
        echo "# Update docker-compose.yml with new image tag" >> $GITHUB_STEP_SUMMARY
        echo "# Then run:" >> $GITHUB_STEP_SUMMARY
        echo "docker compose pull" >> $GITHUB_STEP_SUMMARY
        echo "docker compose up -d" >> $GITHUB_STEP_SUMMARY
        echo "\`\`\`" >> $GITHUB_STEP_SUMMARY
```

## Setup Instructions

### 1. Create GitHub Repository

1. Push your code to a GitHub repository
2. Ensure the repository is public or you have GitHub Pro/Organization for private container registry

### 2. Repository Settings

1. Go to repository **Settings** → **Actions** → **General**
2. Enable "Allow GitHub Actions to create and approve pull requests"
3. Set **Workflow permissions** to "Read and write permissions"

### 3. Container Registry Permissions

The workflow uses `GITHUB_TOKEN` automatically. No additional secrets needed for GitHub Container Registry.

### 4. Create Workflow File

Create `.github/workflows/build-and-publish.yml` with the content above.

## Usage Patterns

### Development Workflow

```bash
# Create feature branch
git checkout -b feature/new-api-endpoint

# Make changes
# ... edit code ...

# Push changes (triggers CI build, no publish)
git push origin feature/new-api-endpoint

# Create PR (triggers CI build and test)
# After review and merge to main, image is built and published
```

### Release Workflow

```bash
# Create and push version tag
git tag v1.0.0
git push origin v1.0.0

# This triggers:
# - Build and test
# - Publish image with tags: v1.0.0, 1.0, latest
```

### Hotfix Workflow

```bash
# Create hotfix branch
git checkout -b hotfix/security-patch

# Make critical changes
# ... fix security issue ...

# Push and merge quickly
git push origin hotfix/security-patch
# Merge to main

# Tag hotfix version
git tag v1.0.1
git push origin v1.0.1
```

## Image Tagging Strategy

The workflow creates multiple tags for flexibility:

- **Branch builds**: `main`, `feature-xyz`
- **PR builds**: `pr-123`
- **Version tags**: `v1.0.0`, `1.0`, `latest`
- **Commit SHA**: `main-abc1234`

## Deployment Integration

### Automatic Deployment (Advanced)

For automatic deployments, add this job to the workflow:

```yaml
deploy:
  needs: build-and-publish
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'

  steps:
  - name: Deploy to production
    run: |
      # SSH to your server and update
      # This requires setting up SSH keys as repository secrets
      echo "Would deploy to production server here"
```

### Manual Deployment (Recommended)

1. **Monitor the GitHub Actions**:
   - Check the workflow completion
   - Note the published image tags

2. **Update production**:
   ```bash
   # SSH to your server
   cd ~/portfolio

   # Update docker-compose.yml with new tag
   sed -i 's/:v1\.0\.0/:v1.0.1/' docker-compose.yml

   # Deploy
   docker compose pull
   docker compose up -d

   # Verify
   curl -f http://localhost:8080/health
   ```

## Local Development

### Build locally

```bash
# Build image locally
docker build -t portfolio-tracker:dev ./portfolio-backend

# Test locally
docker run -p 8080:8080 --env-file .env portfolio-tracker:dev
```

### Test container security

```bash
# Test as non-root user
docker run --rm portfolio-tracker:dev whoami
# Should output: portfolio

# Test read-only filesystem
docker run --rm --read-only --tmpfs /tmp portfolio-tracker:dev
# Should start successfully
```

## Security Considerations

### Image Scanning

Add vulnerability scanning to your workflow:

```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.meta.outputs.version }}
    format: 'sarif'
    output: 'trivy-results.sarif'

- name: Upload Trivy scan results
  uses: github/codeql-action/upload-sarif@v2
  with:
    sarif_file: 'trivy-results.sarif'
```

### Secrets Management

- Never commit API keys or secrets to code
- Use GitHub repository secrets for sensitive data
- Environment variables in `.env` should be managed separately

## Troubleshooting

### Build Failures

1. **Docker build fails**:
   ```bash
   # Test build locally first
   docker build -t test ./portfolio-backend
   ```

2. **Registry push fails**:
   - Check repository permissions
   - Verify GITHUB_TOKEN has package write permissions

3. **Image too large**:
   - Use multi-stage builds
   - Add `.dockerignore` file
   - Remove unnecessary files

### Deployment Issues

1. **Image pull fails**:
   ```bash
   # Login to registry manually
   echo $GITHUB_TOKEN | docker login ghcr.io -u username --password-stdin
   ```

2. **Container won't start**:
   ```bash
   # Check logs
   docker compose logs portfolio

   # Test locally with same config
   docker run --env-file .env your-image:tag
   ```

## Best Practices

1. **Always use specific version tags** in production
2. **Test images locally** before pushing
3. **Monitor build times** and optimize if needed
4. **Keep images small** with minimal dependencies
5. **Scan for vulnerabilities** regularly
6. **Use semantic versioning** for releases
7. **Document breaking changes** in release notes