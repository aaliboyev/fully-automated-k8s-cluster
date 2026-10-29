# BuildKit Helm Chart

A Helm chart for deploying BuildKit on Kubernetes with Harbor registry integration.

## Features

- StatefulSet deployment with persistent storage for build cache
- Configurable registry authentication (Harbor, Docker Hub, etc.)
- Support for registry mirrors and proxies
- Health checks and resource management
- BuildKit configuration via `buildkitd.toml`

## Configuration

### Registry Authentication

To use BuildKit with Harbor or any container registry:

1. **Using internal cluster service** (recommended for in-cluster Harbor):
```yaml
registry:
  enabled: true
  useInternalService: true
  internalService:
    name: "harbor-registry"  # Use registry service, not core
    namespace: "argocd"
    port: 5000  # Registry port, not 80
  insecure: true  # Required for HTTP (no TLS)
  auth:
    existingSecret: "harbor-registry-credentials"
```

2. **Using external domain with HTTPS**:
```yaml
registry:
  enabled: true
  url: "harbor.example.com"
  auth:
    existingSecret: "harbor-registry-credentials"
```

3. **Using username/password** (chart will create secret):
```yaml
registry:
  enabled: true
  url: "harbor.example.com"
  auth:
    username: "admin"
    password: "your-password"
```

**Note:** Internal service communication uses plain HTTP (port 80) without TLS. Kubernetes does NOT automatically provide SSL for `.svc.cluster.local` domains. This is faster and more efficient for in-cluster communication since traffic never leaves the cluster network.

### Registry Mirrors

Configure Docker Hub mirror through Harbor:

```yaml
registry:
  enabled: true
  url: "harbor.example.com"
  mirrors:
    - registry: docker.io
      mirrors:
        - "https://harbor.example.com/v2/dockerhub"
```

### Custom BuildKit Configuration

Override the entire `buildkitd.toml` configuration:

```yaml
buildkitConfig: |
  debug = true
  
  [worker.oci]
    enabled = true
    platforms = [ "linux/amd64", "linux/arm64" ]
  
  [registry."harbor.example.com"]
    http = false
    insecure = false
```

### Self-Signed Certificates

If using self-signed certificates with Harbor:

```yaml
registry:
  enabled: true
  url: "harbor.example.com"
  ca: |
    -----BEGIN CERTIFICATE-----
    ... your CA certificate ...
    -----END CERTIFICATE-----
```

### Resources

Adjust CPU and memory limits:

```yaml
resources:
  limits:
    cpu: 4000m
    memory: 8Gi
  requests:
    cpu: 1000m
    memory: 2Gi
```

### Persistence

Configure persistent storage for build cache:

```yaml
persistence:
  enabled: true
  storageClass: "fast-ssd"
  size: 100Gi
  accessMode: ReadWriteOnce
```

## Usage Examples

### Building with buildctl

Connect to BuildKit from a pod in the cluster:

```bash
# Using internal Harbor service (no SSL)
buildctl --addr tcp://buildkit:1234 build \
  --frontend dockerfile.v0 \
  --local context=. \
  --local dockerfile=. \
  --output type=image,name=harbor-registry.harbor.svc.cluster.local:5000/library/myapp:latest,push=true

# Or using external domain (with HTTPS)
buildctl --addr tcp://buildkit:1234 build \
  --frontend dockerfile.v0 \
  --local context=. \
  --local dockerfile=. \
  --output type=image,name=harbor.example.com/library/myapp:latest,push=true
```

### Building with Docker Buildx

Add BuildKit as a remote builder:

```bash
docker buildx create \
  --name k8s-buildkit \
  --driver remote \
  tcp://buildkit.buildkit.svc.cluster.local:1234
  
docker buildx use k8s-buildkit
docker buildx build --push -t harbor.example.com/library/myapp:latest .
```

## Creating Registry Secret

If using `existingSecret`, create it before deploying:

```bash
kubectl create secret docker-registry harbor-registry-credentials \
  --namespace=buildkit \
  --docker-server=harbor.example.com \
  --docker-username=admin \
  --docker-password=YOUR_PASSWORD
```

Or use SealedSecrets/ExternalSecrets for GitOps workflows.
