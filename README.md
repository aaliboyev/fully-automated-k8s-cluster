# Fully Automated Kubernetes Cluster

A complete Kubernetes cluster infrastructure automation framework for self-managed (on-premises) clusters. This project provides everything needed to deploy, manage, and maintain production-ready Kubernetes clusters using Ansible.

## Overview

This repository contains:
- **Ansible Playbooks** - Full cluster lifecycle automation (install, upgrade, scale, remove)
- **Cluster Components** - Helm value configurations for essential cluster add-ons
- **Server Scripts** - Cloud-init and server initialization scripts

## Why This Setup?

### Cost-Effective Self-Hosting

**VPS servers are dramatically cheaper than cloud-managed Kubernetes:**

| Setup | Monthly Cost | Resources                          |
|-------|--------------|------------------------------------|
| **VPS (10 nodes)** | ~$200 | 100 vCPU, 200GB RAM                | 
| **Cloud K8s (similar)** | ~$2,000+ | Managed control plane + worker nodes |

**Real-world example:** This complete setup running on 9 nodes uses:
- **CPU**: <2 cores (out of 110 available) 
- **RAM**: ~18GB (out of 266GB available)
- **Leaves plenty of resources** for your actual workloads

### Perfect For

- **Self-hosting enthusiasts** - Run multiple projects on your own infrastructure
- **Small SaaS platforms** - Production-ready with proper networking and observability
- **Learning & development** - Full Kubernetes experience without cloud costs
- **Data sovereignty** - Complete control over your infrastructure and data
- **Scalable architecture** - Easily add more nodes as you grow

### What You Get

✅ **Production-ready backbone**: Network stack (Traefik, cert-manager, external-dns) + Observability (Victoria Metrics, Grafana)

✅ **GitOps workflow**: ArgoCD manages all components with automatic sync

✅ **Distributed storage**: Longhorn provides persistent volumes with replication

✅ **Secure access**: Twingate zero-trust access to internal services

✅ **Automatic TLS**: Let's Encrypt certificates with DNS-01 validation

✅ **Highly scalable**: Tested with 9 nodes, can scale to much larger clusters

### Minimum Recommended Specs

⚠️ **Important**: This setup includes production components (ArgoCD, Victoria Metrics, Longhorn) that consume resources.

**Minimum viable cluster:**
- **3 worker nodes** (1 control plane + 3 workers recommended)
- **16GB RAM per node** (48GB total for workers)
- **4 CPU cores per node** (12 cores total for workers)

**Why these specs?**
- Core infrastructure uses ~6-8GB RAM total
- Leaves 40GB+ for your actual applications
- CPU usage is minimal (<2 cores for infrastructure)

**Not suitable for:**
- Single-node setups or very small servers (<8GB RAM)
- Development laptops (use k3s, minikube, or kind instead)
- Extremely resource-constrained environments

**This setup is overkill if:**
- You only need to run 1-2 simple applications
- You have less than 3 nodes
- Each node has less than 12GB RAM

For smaller setups, consider simplified alternatives like k3s or single-node Kubernetes.

## Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Orchestration | Kubernetes | v1.34 |
| Container Runtime | containerd | Latest |
| CNI (Networking) | Calico (Tigera Operator) | v3.31.2 |
| Storage | Longhorn | v1.10.1 |
| GitOps | ArgoCD | v7.7.12 |
| Automation | Ansible | Latest |
| Package Manager | Helm | v3 |

## Project Structure

```
.
├── PREREQUISITES.md              # Infrastructure and tooling requirements
├── BOOTSTRAP.md                  # Step-by-step deployment guide
├── README.md                     # This file: overview and quick reference
├── Makefile                      # Task automation shortcuts
├── ansible/                      # Ansible automation (Phase 1)
│   ├── inventory.ini             # Cluster node inventory
│   ├── group_vars/all.yml        # Centralized variables
│   └── playbooks/                # Cluster lifecycle playbooks
├── components/                   # Component stacks
│   ├── network/                  # Network stack (Phase 2: ArgoCD-managed)
│   │   ├── root.yaml             # ArgoCD root application
│   │   ├── values.yaml           # Parameterized configuration
│   │   ├── templates/            # ArgoCD apps, gateways, routes
│   │   └── values/               # Child app Helm values
│   ├── observability/            # Observability stack (Phase 2: ArgoCD-managed)
│   │   ├── root.yaml             # ArgoCD root application
│   │   ├── values.yaml           # Parameterized configuration
│   │   └── templates/            # Victoria Metrics apps
│   ├── argocd/values.yaml        # ArgoCD Helm values (Phase 1)
│   └── longhorn/values.yaml      # Longhorn Helm values (Phase 1)
├── apps/                         # Your application deployments
└── scripts/server-init.sh        # Server initialization script
```

## Quick Start

### Prerequisites

**Before you begin, review [PREREQUISITES.md](PREREQUISITES.md) for:**
- VPS/bare metal server requirements
- SSH configuration with clean inventory setup
- Required software installation (Ansible, kubectl, etc.)
- Domain and Cloudflare DNS setup
- API keys and service accounts

**Quick checklist:**
- Ansible installed on your local machine
- SSH key-based access configured to all target nodes (as root)
- SSH config with node aliases (n1, n2, etc.) for clean inventory
- Ubuntu/Debian-based nodes (tested on Ubuntu 22.04+)
- Domain with Cloudflare DNS management
- Cloudflare API token ready

### 1. Server Initialization

Run the initialization script on each node to prepare the base OS:

```bash
# On each server node
bash scripts/server-init.sh
```

This script:
- Installs required packages and dependencies
- Disables swap (required for Kubernetes)
- Loads kernel modules (overlay, br_netfilter, iscsi_tcp)
- Installs and configures containerd runtime
- Sets up networking prerequisites

### 2. Configure Inventory

Edit `ansible/inventory.ini` to define your cluster nodes:

```ini
[control_plane]
master1 ansible_host=192.168.1.10

[workers]
worker1 ansible_host=192.168.1.11
worker2 ansible_host=192.168.1.12
worker3 ansible_host=192.168.1.13

[k8s:children]
control_plane
workers
```

### 3. Deploy Cluster

```bash
# Install Kubernetes components on all nodes
make ansible-init

# Or run playbooks manually:
cd ansible
ansible-playbook playbooks/install-k8s.yml
ansible-playbook playbooks/init-cluster.yml
ansible-playbook playbooks/install-calico.yml
ansible-playbook playbooks/install-longhorn.yml
ansible-playbook playbooks/join-workers.yml
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make ansible-ping` | Test connectivity to all nodes |
| `make ansible-init` | Initialize a new cluster |
| `make ansible-join` | Join worker nodes to cluster |
| `make ansible-promote` | Add additional control planes (HA) |
| `make ansible-upgrade` | Upgrade cluster to target version |
| `make ansible-check` | Dry-run cluster initialization |

## Ansible Playbooks

### Cluster Lifecycle

| Playbook | Purpose |
|----------|---------|
| `install-k8s.yml` | Install kubeadm, kubelet, kubectl on all nodes |
| `init-cluster.yml` | Initialize the first control plane node |
| `join-workers.yml` | Join worker nodes to the cluster |
| `promote-controlplane.yml` | Add control planes for HA setup |
| `upgrade-cluster.yml` | Rolling upgrade (one node at a time) |
| `remove-workers.yml` | Drain and remove worker nodes |

### Cluster Components

| Playbook | Purpose |
|----------|---------|
| `install-calico.yml` | Install Calico CNI with Tigera Operator |
| `install-longhorn.yml` | Install Longhorn distributed storage |
| `install-argocd.yml` | Install ArgoCD GitOps controller |

## Cluster Components

### Calico CNI
- Tigera Operator deployment
- eBPF dataplane support
- Pod network CIDR: `192.168.0.0/16`

### Longhorn Storage
- Distributed block storage
- Default replica count: 3
- Auto-balance with least-effort scheduling
- Accessible at `longhorn.example.com` (via private gateway)

### ArgoCD
- GitOps continuous delivery
- Manages all post-bootstrap components via App of Apps pattern
- ApplicationSet support for multi-app management
- Accessible at `argocd.example.com` (via private gateway)

```bash
# Get ArgoCD admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Traefik Ingress
- Two separate Traefik instances:
  - **Public Gateway** (port 80/443) - Public internet access
  - **Private Gateway** (port 8000/8443) - Twingate-protected internal services
- Runs in **host network mode** with direct port binding
- Gateway API implementation (v1) for routing
- Automatic TLS via cert-manager integration

## Configuration

### Global Variables (`ansible/group_vars/all.yml`)

```yaml
kubernetes_version: "v1.34"
pod_network_cidr: "192.168.0.0/16"
calico_version: "v3.31.2"
longhorn_cli_version: "v1.10.1"
longhorn_chart_version: "1.10.1"
argocd_chart_version: "7.7.12"
```

### Override Versions

```bash
# Upgrade to specific version
ansible-playbook playbooks/upgrade-cluster.yml -e "kubernetes_version=v1.35"

# Install specific Calico version
ansible-playbook playbooks/install-calico.yml -e "calico_version=v3.32.0"
```

## Infrastructure Architecture

This infrastructure follows a two-phase deployment model:

### Phase 1: Ansible-Managed Base Infrastructure
Ansible handles the foundational cluster setup:
- **Kubernetes cluster** - Control plane and worker nodes
- **Calico CNI** - Pod networking via Tigera Operator
- **Longhorn** - Distributed block storage
- **ArgoCD** - GitOps controller for application management

### Phase 2: ArgoCD-Managed Application Stack
Once ArgoCD is running, it manages all additional components via GitOps:
- **Network Stack** - Traefik ingress, cert-manager, external-dns, Twingate
- **Observability Stack** - Victoria Metrics operator and monitoring
- **Application Routes** - HTTPRoutes for ArgoCD, Longhorn, and Grafana UIs

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   KUBERNETES CLUSTER (v1.34)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  ANSIBLE-MANAGED INFRASTRUCTURE (Phase 1)                 │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │  • Kubernetes (kubeadm, kubelet, kubectl)                 │ │
│  │  • Calico CNI (Tigera Operator + eBPF)                    │ │
│  │  • Longhorn Storage (distributed, 3 replicas)             │ │
│  │  • ArgoCD (GitOps controller)                             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                             ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  ARGOCD-MANAGED COMPONENTS (Phase 2)                      │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │  Network Stack (components/network/):                     │ │
│  │    • Traefik (public & private gateways)                  │ │
│  │    • cert-manager (Let's Encrypt DNS-01)                  │ │
│  │    • external-dns (Cloudflare integration)                │ │
│  │    • Twingate (zero-trust network access)                 │ │
│  │    • Gateway API (*.example.com routing)                 │ │
│  │                                                            │ │
│  │  Observability Stack (components/observability/):         │ │
│  │    • Victoria Metrics Operator                            │ │
│  │    • VM K8s Stack (metrics + alerting)                    │ │
│  │    • Grafana (grafana.example.com)                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Networking: Pod CIDR 192.168.0.0/16 | Gateway API + HTTPRoute │
└─────────────────────────────────────────────────────────────────┘
```

## Bootstrap Sequence

The cluster follows this exact boot sequence:

### Step 1: Base Infrastructure via Ansible
```bash
# 1. Install K8s components on all nodes
ansible-playbook ansible/playbooks/install-k8s.yml

# 2. Initialize the first control plane
ansible-playbook ansible/playbooks/init-cluster.yml

# 3. Install Calico CNI
ansible-playbook ansible/playbooks/install-calico.yml

# 4. Install Longhorn storage
ansible-playbook ansible/playbooks/install-longhorn.yml

# 5. Join worker nodes
ansible-playbook ansible/playbooks/join-workers.yml

# 6. Install ArgoCD
ansible-playbook ansible/playbooks/install-argocd.yml
```

Or use the Makefile shortcut:
```bash
make ansible-init
```

### Step 2: Deploy Root Applications to ArgoCD

Once the base infrastructure is running, bootstrap the ArgoCD-managed stacks:

```bash
# Apply the network stack root application
kubectl apply -f components/network/root.yaml

# Apply the observability stack root application
kubectl apply -f components/observability/root.yaml
```

ArgoCD will automatically:
1. Sync the root applications
2. Deploy all child Application resources
3. Install Helm charts with appropriate values
4. Create HTTPRoutes and configure DNS
5. Issue TLS certificates via Let's Encrypt

### Step 3: Verify Deployment

```bash
# Check ArgoCD applications
kubectl get applications -n argocd

# Watch components come online
kubectl get pods -n network
kubectl get pods -n observability

# Verify gateways and routes
kubectl get gateway,httproute -A
```

## Operations

### Cluster Upgrade

The upgrade playbook performs rolling upgrades one node at a time:

```bash
# Upgrade to target version
make ansible-upgrade

# Or with custom version
ansible-playbook ansible/playbooks/upgrade-cluster.yml -e "kubernetes_version=v1.35"
```

### Add Worker Nodes

1. Update `inventory.ini` with new nodes
2. Run server initialization on new nodes
3. Install Kubernetes components and join:

```bash
ansible-playbook ansible/playbooks/install-k8s.yml --limit new_worker
ansible-playbook ansible/playbooks/join-workers.yml --limit new_worker
```

### Remove Worker Nodes

```bash
# Remove specific workers
ansible-playbook ansible/playbooks/remove-workers.yml --limit worker_to_remove
```

### High Availability Setup

Add additional control planes for HA:

```bash
ansible-playbook ansible/playbooks/promote-controlplane.yml
```

## Network Architecture

### Ingress Strategy: Host Network Mode

This setup uses **Traefik in host network mode** to handle ingress traffic. This approach is necessary for VPS/bare metal deployments.

#### Why Host Network?

Unlike cloud providers (AWS, GCP, Azure) that offer LoadBalancer services, VPS and bare metal environments require direct port binding:

**Cloud Providers:**
```
Internet → Cloud Load Balancer → Service (type: LoadBalancer) → Ingress → Pods
```

**VPS/Bare Metal (This Setup):**
```
Internet → Public IP → Host Network → Traefik (ports 80/443) → Pods
```

#### Traefik Configuration

Two separate Traefik instances handle different traffic types:

**Public Gateway** (`traefik-public`):
- Binds to ports **80** and **443** on the host
- Handles public internet traffic
- Uses `hostNetwork: true`
- Configured in `components/network/values/traefik-public.yaml`

**Private Gateway** (`traefik-private`):
- Binds to ports **8000** and **8443** on the host
- Handles internal/management traffic
- Requires Twingate authentication
- Configured in `components/network/values/traefik-private.yaml`

#### Privileged Ports

Ports below 1024 (like 80 and 443) are privileged. Traefik handles this through:
- `NET_BIND_SERVICE` capability
- Kubernetes node configuration allowing privileged port binding

#### Gateway API

This setup uses Kubernetes **Gateway API v1** instead of traditional Ingress resources:
- `Gateway` resources define listeners and TLS configuration
- `HTTPRoute` resources define routing rules
- Better multi-tenancy and role separation
- Native support in Traefik v3+

#### Security Considerations

- Only one Traefik pod per node (DaemonSet with node selector)
- TLS termination with automatic certificate renewal
- Private gateway isolated via Twingate zero-trust access
- Public gateway protected by application-level authentication

## Scripts

### server-init.sh

Base server initialization script for cloud-init or manual setup:

- Updates system packages
- Installs containerd runtime with SystemdCgroup
- Configures kernel modules and sysctl parameters
- Disables swap
- Installs CNI plugins and networking tools

```bash
# Run on each node before Ansible playbooks
bash scripts/server-init.sh
```

## Accessing Services

After full deployment, the following services are available via HTTPRoutes:

| Service | URL | Gateway | Description |
|---------|-----|---------|-------------|
| ArgoCD | `https://argocd.example.com` | Private | GitOps UI |
| Longhorn | `https://longhorn.example.com` | Private | Storage management |
| Grafana | `https://grafana.example.com` | Private | Metrics & dashboards |

**Note:** All services use the private gateway and require Twingate access or VPN connectivity.

TLS certificates are automatically issued and renewed by cert-manager using Let's Encrypt DNS-01 challenges.

## Customization

To customize domain names, emails, or repository URLs, edit the `valuesObject` section in:
- `components/network/root.yaml` - Network stack configuration
- `components/observability/root.yaml` - Observability configuration

Example:
```yaml
valuesObject:
  domain: yourdomain.com
  email: admin@yourdomain.com
  repoURL: git@github.com:yourorg/your-repo.git
```

After changes, reapply the root applications:
```bash
kubectl apply -f components/network/root.yaml
kubectl apply -f components/observability/root.yaml
```

## Documentation

Complete documentation is available:

### Getting Started
- **[PREREQUISITES.md](PREREQUISITES.md)** - Required infrastructure, SSH setup, tools, and API keys
- **[BOOTSTRAP.md](BOOTSTRAP.md)** - Step-by-step deployment guide from bare metal to production
- **[README.md](README.md)** - This file: overview, architecture, and quick reference

### Component Guides
- **[TWINGATE.md](TWINGATE.md)** - Twingate setup, VPN-like vs true ZTNA approaches

### Ansible Guides
- `ansible/README.md` - Ansible workflow and playbook overview
- `ansible/KUBECONFIG.md` - Kubeconfig management and access
- `ansible/playbooks/README.md` - Detailed playbook reference
- `ansible/playbooks/README-calico.md` - Calico CNI configuration
- `ansible/playbooks/README-longhorn.md` - Longhorn storage setup

## License

MIT License

## Author

Abror Aliboyev
