# Twingate Zero-Trust Access Setup

This document explains how Twingate is configured in this cluster and how to set it up for secure access to internal services.

## Overview

In this setup, **Twingate is used as a VPN-like gateway** to provide secure access to the private Traefik ingress controller. This is a simplified approach that works well for small to medium clusters.

**Important Note**: This configuration does not utilize Twingate's full Zero-Trust Network Access (ZTNA) capabilities. For true ZTNA, services would be exposed individually with granular access controls (see [Advanced: True ZTNA Setup](#advanced-true-ztna-setup) below).

## How It Works

### Architecture

```
User → Twingate Client → Twingate Network → Connector Pod → Private Gateway (10.111.111.111) → Services
```

1. **Private Gateway**: Traefik private instance runs on ports 8000/8443
2. **ClusterIP Service**: `traefik-private` service has ClusterIP `10.111.111.111`
3. **Twingate Resource**: Single resource pointing to `10.111.111.111`
4. **HTTPRoutes**: All private services route through this gateway (ArgoCD, Longhorn, Grafana)

### What This Gives You

- **Single Access Point**: One Twingate resource controls access to all private services
- **TLS Termination**: HTTPS works properly via cert-manager certificates
- **Domain-based Routing**: Access services via their proper domains (argocd.example.com, etc.)
- **Simple Management**: No need to add individual services to Twingate

### Trade-offs

**Pros:**
- Simple setup and management
- Works with existing Traefik routing
- Proper TLS certificates and HTTPS
- No changes needed when adding new services

**Cons:**
- All-or-nothing access (if user has Twingate access, they can reach all private services)
- No service-level granular access control
- Not true zero-trust architecture

## Setup Instructions

### Step 1: Create Twingate Account and Network

1. Sign up at [Twingate](https://www.twingate.com/)
2. Create a new **Network** (e.g., "k8s-cluster")
3. Note your network name - you'll need it for the connector

### Step 2: Create Connector

1. In Twingate dashboard, go to **Settings** → **Connectors**
2. Click **Add Connector**
3. Name it (e.g., "k8s-connector")
4. Click **Generate Tokens**
5. Copy the tokens:
   - `TWINGATE_ACCESS_TOKEN`
   - `TWINGATE_REFRESH_TOKEN`

**Important**: Save these tokens securely - you won't be able to see them again.

### Step 3: Create Kubernetes Secrets

Create the secret in the network namespace:

```bash
kubectl create namespace network

kubectl create secret generic twingate-service-key \
  --namespace=network \
  --from-literal=TWINGATE_ACCESS_TOKEN='your_access_token_here' \
  --from-literal=TWINGATE_REFRESH_TOKEN='your_refresh_token_here'
```

### Step 4: Create Twingate Resource

In the Twingate dashboard:

1. Go to **Resources** → **Add Resource**
2. Configure the resource:
   - **Name**: `Private Gateway`
   - **Address**: `10.111.111.111`
   - **Ports**: 
     - Option 1: No restrictions (allows all ports)
     - Option 2: Restrict to `8000,8443` only
   - **Protocols**: TCP

3. **Assign Access**:
   - Add users or groups who should have access
   - These users can access all services behind the private gateway

4. Click **Save**

### Step 5: Deploy Network Stack

Apply the network stack root application (which includes Twingate connector):

```bash
kubectl apply -f components/network/root.yaml
```

Verify the connector is running:

```bash
kubectl get pods -n network -l app.kubernetes.io/name=connector

# Check logs
kubectl logs -n network -l app.kubernetes.io/name=connector
```

The connector should show as **online** in the Twingate dashboard.

### Step 6: Connect and Test

1. **Install Twingate Client** on your device:
   - macOS: Download from Twingate dashboard or App Store
   - Windows: Download from Twingate dashboard
   - Linux: [Installation guide](https://docs.twingate.com/docs/linux)
   - Mobile: iOS/Android apps available

2. **Sign in** to Twingate client with your account

3. **Enable the connection** to your network

4. **Test access**:
   ```bash
   # Test connectivity to private gateway
   curl -k https://10.111.111.111:8443
   
   # Access services via domains
   curl https://argocd.example.com
   curl https://longhorn.example.com
   curl https://grafana.example.com
   ```

5. **Open in browser**: Navigate to any private service domain

## How Services are Accessed

With this setup, all private services are accessed via their domains through the single Twingate resource:

### Service Flow

```
https://argocd.example.com
  ↓
Twingate Client (local machine)
  ↓
Twingate Network
  ↓
Connector Pod (in cluster)
  ↓
10.111.111.111:8443 (traefik-private ClusterIP)
  ↓
HTTPRoute (argocd.example.com)
  ↓
argocd-server Service
  ↓
ArgoCD Pod
```

### Adding New Services

When you add a new private service:

1. Create an HTTPRoute pointing to the `private` gateway
2. Add the `external-dns.alpha.kubernetes.io/hostname` annotation
3. No Twingate changes needed - it automatically works

Example:
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-new-service
  namespace: my-namespace
  annotations:
    external-dns.alpha.kubernetes.io/hostname: myservice.example.com
spec:
  hostnames:
    - myservice.example.com
  parentRefs:
    - name: private
      namespace: network
  rules:
    - backendRefs:
        - name: my-service
          port: 80
```

The service is now accessible at `https://myservice.example.com` for anyone with Twingate access.

## Advanced: True ZTNA Setup

For **true Zero-Trust Network Access** with service-level granular control:

### Approach

Instead of routing through Traefik, expose services directly via their Kubernetes ClusterIP or service name.

### Steps

#### 1. Create Individual Twingate Resources

For each service you want to expose:

**Example: ArgoCD**
- **Name**: `ArgoCD`
- **Address**: `argocd-server.argocd.svc` (or `10.96.x.x` ClusterIP)
- **Port**: `80` or `443`
- **Access**: Grant to specific users/groups

**Example: Longhorn**
- **Name**: `Longhorn`
- **Address**: `longhorn-frontend.longhorn-system.svc`
- **Port**: `80`
- **Access**: Grant to admin users only

#### 2. Remove from Traefik Private Gateway

To prevent bypass via Traefik, either:
- Don't create HTTPRoute for the service
- Use NetworkPolicy to restrict access to Traefik

#### 3. Access Services Directly

Users connect to services using Kubernetes DNS names:

```bash
# Access ArgoCD directly (no TLS, HTTP only)
http://argocd-server.argocd.svc

# Or using shorter name
http://argocd-server.argocd

# Or just service name (if in same namespace)
http://argocd-server
```

### Benefits of True ZTNA

- **Granular Access Control**: Different users can access different services
- **Service-level Auditing**: Know exactly who accessed what
- **Principle of Least Privilege**: Users only see services they need
- **No Gateway Bypass**: Direct service access, can't route through Traefik

### Limitations of True ZTNA

- **No TLS/HTTPS**: Direct ClusterIP access doesn't support TLS termination
  - Services must handle TLS themselves or accept HTTP
- **More Complex**: Each service needs a Twingate resource
- **DNS Names**: Users must use cluster DNS names (not friendly domains)
- **Certificate Warnings**: If services use self-signed certs

### Alternative Approaches

#### Option 1: DNS-Based Access (Advanced)

You can create DNS records or CoreDNS entries pointing to ClusterIPs/service names:

**Public DNS Approach:**
```bash
# Create DNS record
dbadmin.example.com → 10.96.50.100 (service ClusterIP)
```

**CoreDNS Approach:**
Add custom domain to CoreDNS for internal resolution:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns-custom
  namespace: kube-system
data:
  example.server: |
    example.com {
      hosts {
        10.96.50.100 dbadmin.example.com
        fallthrough
      }
    }
```

**TLS Considerations:**
- If service supports TLS and cert-manager certificates → Configure directly
- If service needs TLS termination → Use dedicated private Traefik (see Option 2)

#### Option 2: Service-Specific Private Traefik (Recommended for Granular ZTNA)

Create **dedicated Traefik instances** for services requiring granular access control with proper TLS termination.

**When to Use:**
- Service needs HTTPS/TLS but doesn't support it natively
- Requires granular per-service access control
- Service should be isolated from main private gateway
- Want proper domain names with valid certificates

**Architecture:**
```
User → Twingate → Service-Specific Traefik → Backend Service
```

**Steps:**

1. **Create dedicated Traefik instance** (very lightweight):

```yaml
# components/my-app/traefik-values.yaml
service:
  type: ClusterIP
  spec:
    clusterIP: 10.111.222.222  # Choose unique ClusterIP

ports:
  web:
    port: 8000
  websecure:
    port: 8443

# Use label selector to avoid gateway conflicts
kubernetesGateway:
  enabled: true
  gateway:
    labelselector: "gateway-class=my-app-private"

# Or disable Gateway API and use IngressRoute (simpler)
kubernetesGateway:
  enabled: false

providers:
  kubernetesCRD:
    enabled: true
    namespaces: ["my-app-namespace"]
```

2. **Deploy Traefik instance**:

```bash
helm install my-app-traefik traefik/traefik \
  --namespace my-app-namespace \
  --values traefik-values.yaml
```

3. **Create routing configuration**:

**Option A: Using IngressRoute** (Simpler):
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: my-app
  namespace: my-app-namespace
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`myapp.example.com`)
      kind: Rule
      services:
        - name: my-app-service
          port: 80
  tls:
    secretName: myapp-tls
```

**Option B: Using Gateway API** (if multiple Traefik instances):
```yaml
# Gateway with unique label
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: my-app-gateway
  namespace: my-app-namespace
  labels:
    gateway-class: my-app-private
spec:
  gatewayClassName: my-app-private
  listeners:
    - name: websecure
      protocol: HTTPS
      port: 8443
      hostname: "myapp.example.com"
      tls:
        mode: Terminate
        certificateRefs:
          - name: myapp-tls
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app
  namespace: my-app-namespace
spec:
  hostnames:
    - myapp.example.com
  parentRefs:
    - name: my-app-gateway
  rules:
    - backendRefs:
        - name: my-app-service
          port: 80
```

4. **Create TLS certificate**:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: myapp-tls
  namespace: my-app-namespace
spec:
  secretName: myapp-tls
  issuerRef:
    name: letsencrypt-dns
    kind: ClusterIssuer
  dnsNames:
    - myapp.example.com
```

5. **Add Twingate resource** for this specific Traefik:

- **Name**: `My App`
- **Address**: `10.111.222.222` (service-specific Traefik ClusterIP)
- **Ports**: `8000,8443`
- **Access**: Grant to specific users/groups (e.g., DBA only)

6. **Access the service**:

```bash
# With Twingate connected
curl https://myapp.example.com
```

**Benefits of Service-Specific Traefik:**
- ✅ Granular access control per service
- ✅ Proper HTTPS/TLS with valid certificates
- ✅ Friendly domain names
- ✅ Isolated from main private gateway
- ✅ Can't bypass via main Traefik
- ✅ Traefik is lightweight (minimal resource overhead)

**Considerations:**
- Each Traefik instance needs unique ClusterIP
- Gateway API: Use label selectors to avoid conflicts
- IngressRoute: Simpler, no gateway conflicts
- More Twingate resources to manage

### Comparison: Which Approach?

| Approach | TLS/HTTPS | Domain Names | Granular Access | Complexity | Best For |
|----------|-----------|--------------|-----------------|------------|----------|
| **Shared Private Gateway** | ✅ | ✅ | ❌ All-or-nothing | Low | Small teams, trusted users |
| **Direct Service Access** | ❌ HTTP only | ❌ DNS names | ✅ Per-service | Low | Simple services, no TLS needed |
| **DNS + CoreDNS** | ⚠️ If service supports | ✅ | ✅ Per-service | Medium | Services with native TLS |
| **Service-Specific Traefik** | ✅ | ✅ | ✅ Per-service | Medium | Production, compliance, HTTPS required |

### Hybrid Approach (Recommended)

Combine approaches based on needs:

1. **Most Services**: Shared private Traefik gateway (current setup)
   - ArgoCD, Longhorn, Grafana
   - All administrators have access
   - Simple management

2. **Database/Admin Tools**: Service-specific private Traefik
   - pgAdmin, phpMyAdmin, etc.
   - DBA-only access via dedicated Twingate resource
   - Proper HTTPS with certificates

3. **Internal APIs**: Direct service access
   - No TLS needed (internal only)
   - Developer access to specific APIs
   - Use Kubernetes service DNS names

**Example Setup:**
```
Shared Private Gateway (10.111.111.111):
  ├─ ArgoCD (all admins)
  ├─ Longhorn (all admins)
  └─ Grafana (all admins)

Database Traefik (10.111.222.222):
  ├─ pgAdmin (DBA group only)
  └─ Database UI (DBA group only)

Kubernetes Dashboard Traefik (10.111.333.333):
  └─ K8s Dashboard (cluster-admin group only)

Direct Service Access:
  ├─ Internal API (developers)
  └─ Monitoring endpoints (SRE team)
```

## Troubleshooting

### Connector Not Online

```bash
# Check connector pod
kubectl get pods -n network -l app.kubernetes.io/name=connector

# Check logs
kubectl logs -n network -l app.kubernetes.io/name=connector

# Common issues:
# - Invalid tokens (recreate secret with correct tokens)
# - Network connectivity from cluster
# - Wrong network URL
```

### Can't Access Services

```bash
# 1. Verify Twingate connection is active (check client status)

# 2. Test direct connectivity to ClusterIP
kubectl run -it --rm debug --image=curlimages/curl --restart=Never \
  -- curl -v http://10.111.111.111:8000

# 3. Check traefik-private service
kubectl get svc -n network traefik-private
# Should show ClusterIP 10.111.111.111

# 4. Verify HTTPRoute exists
kubectl get httproute -A

# 5. Check DNS resolution
nslookup argocd.example.com
```

### Wrong ClusterIP

If `traefik-private` service doesn't have ClusterIP `10.111.111.111`:

1. Update Twingate resource address to match actual ClusterIP
2. Or delete and recreate service with desired ClusterIP:

```bash
kubectl delete svc -n network traefik-private
# Edit components/network/values/traefik-private.yaml to set clusterIP
kubectl apply -f components/network/root.yaml
```

### Access Denied

- Verify you're assigned to the Private Gateway resource in Twingate dashboard
- Check that Twingate client is connected and shows the resource as available
- Ensure you're connected to the correct Twingate network

## Security Considerations

### Current Setup (VPN-like)

- **Access Control**: Managed at Twingate resource level
- **All-or-nothing**: Access to gateway = access to all services
- **Suitable for**: Small teams, trusted users, simple deployments

### Recommendations

1. **User Management**: 
   - Only grant access to trusted administrators
   - Use groups for easier management
   - Regularly audit access

2. **Additional Security**:
   - Enable MFA in Twingate
   - Use short-lived sessions
   - Monitor Twingate access logs

3. **Service-level Security**:
   - Enable authentication on services (ArgoCD, Grafana)
   - Use RBAC within Kubernetes
   - Implement NetworkPolicies

4. **Consider True ZTNA** for:
   - Larger teams with different access needs
   - Compliance requirements
   - Services with different security levels

## References

- [Twingate Documentation](https://docs.twingate.com/)
- [Twingate Connector Helm Chart](https://github.com/Twingate/helm-charts)
- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/)
- [Zero Trust Architecture (NIST)](https://www.nist.gov/publications/zero-trust-architecture)
