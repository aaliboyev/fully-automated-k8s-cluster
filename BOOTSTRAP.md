# Kubernetes Cluster Bootstrap Guide

This guide provides step-by-step instructions for deploying a complete Kubernetes cluster from bare metal servers to a fully functional production environment.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Phase 1: Base Infrastructure Setup](#phase-1-base-infrastructure-setup)
- [Phase 2: ArgoCD-Managed Components](#phase-2-argocd-managed-components)
- [Phase 3: Verification](#phase-3-verification)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Hardware Requirements

- **Control Plane Nodes**: Minimum 1 node (3 recommended for HA)
  - 2 CPU cores
  - 4GB RAM
  - 50GB disk space

- **Worker Nodes**: Minimum 3 nodes recommended
  - 4 CPU cores
  - 8GB RAM
  - 100GB disk space
  - Additional disk for Longhorn storage

### Software Requirements

- **Operating System**: Ubuntu 22.04 LTS or later
- **Local Machine**: Ansible 2.10+ installed
- **Network**: SSH key-based access to all nodes as root
- **DNS**: Cloudflare-managed domain

### Required Secrets

Before deployment, you'll need to prepare the following credentials:

#### 1. Cloudflare API Token

Create a Cloudflare API token with the following permissions:
- Zone: DNS: Edit
- Zone: Zone: Read

This token is used by:
- `cert-manager` for Let's Encrypt DNS-01 challenges
- `external-dns` for automatic DNS record management

#### 2. Twingate Service Key

If using Twingate for zero-trust access:
- Create a connector in your Twingate dashboard
- Generate service key tokens

## Phase 1: Base Infrastructure Setup

### Step 1: Prepare Server Nodes

Run the initialization script on each bare metal node:

```bash
# SSH into each node and run:
bash <(curl -s https://raw.githubusercontent.com/yourusername/your-repo/main/scripts/server-init.sh)

# Or if you have the repository cloned locally:
scp scripts/server-init.sh root@node-ip:/tmp/
ssh root@node-ip 'bash /tmp/server-init.sh'
```

This script will:
- Update system packages
- Install and configure containerd runtime
- Load required kernel modules (overlay, br_netfilter, iscsi_tcp)
- Disable swap
- Configure sysctl parameters for Kubernetes

### Step 2: Configure Ansible Inventory

Edit `ansible/inventory.ini` to define your cluster topology:

```ini
[control_plane]
master1 ansible_host=192.168.1.10 ansible_user=root

# For HA setup, add additional control planes:
# master2 ansible_host=192.168.1.11 ansible_user=root
# master3 ansible_host=192.168.1.12 ansible_user=root

[workers]
worker1 ansible_host=192.168.1.21 ansible_user=root
worker2 ansible_host=192.168.1.22 ansible_user=root
worker3 ansible_host=192.168.1.23 ansible_user=root

[k8s:children]
control_plane
workers
```

### Step 3: Verify Ansible Connectivity

Test SSH connectivity to all nodes:

```bash
cd ansible
ansible all -m ping

# Expected output:
# master1 | SUCCESS => {...}
# worker1 | SUCCESS => {...}
# worker2 | SUCCESS => {...}
# worker3 | SUCCESS => {...}
```

### Step 4: Review Configuration Variables

Edit `ansible/group_vars/all.yml` if you need to customize versions:

```yaml
kubernetes_version: "v1.34"
pod_network_cidr: "192.168.0.0/16"
calico_version: "v3.31.2"
longhorn_cli_version: "v1.10.1"
longhorn_chart_version: "1.10.1"
argocd_chart_version: "7.7.12"
argocd_namespace: "argocd"
```

### Step 5: Deploy Base Infrastructure

Deploy the entire base infrastructure with a single command:

```bash
make ansible-init
```

This will execute the following playbooks in order:
1. `install-k8s.yml` - Install Kubernetes components
2. `init-cluster.yml` - Initialize the first control plane
3. `install-calico.yml` - Deploy Calico CNI
4. `install-longhorn.yml` - Deploy Longhorn storage
5. `join-workers.yml` - Join worker nodes
6. `install-argocd.yml` - Deploy ArgoCD

**Duration**: Approximately 15-20 minutes depending on your network and hardware.

### Step 6: Configure Kubeconfig

The kubeconfig file is automatically created on the first control plane node at `/root/.kube/config`.

Copy it to your local machine:

```bash
# From the control plane node
scp root@master1:/root/.kube/config ~/.kube/config

# Or use the helper script
scp root@master1:/etc/kubernetes/admin.conf ~/.kube/config
```

Test cluster access:

```bash
kubectl get nodes
kubectl get pods -A
```

### Step 7: Verify Base Components

Check that all base components are running:

```bash
# Verify nodes are Ready
kubectl get nodes

# Check Calico pods
kubectl get pods -n calico-system

# Check Longhorn
kubectl get pods -n longhorn-system

# Check ArgoCD
kubectl get pods -n argocd
```

### Step 8: Get ArgoCD Admin Password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

Save this password - you'll need it to access the ArgoCD UI.

## Phase 2: ArgoCD-Managed Components

### Step 1: Create Required Secrets

Before applying root applications, create the necessary secrets.

#### Create Cloudflare API Token Secret

```bash
kubectl create secret generic cloudflare-api-token \
  --namespace=network \
  --from-literal=api-token='YOUR_CLOUDFLARE_API_TOKEN'
```

**Note**: If the `network` namespace doesn't exist yet, create it first:

```bash
kubectl create namespace network
```

#### Create Twingate Service Key Secret

```bash
kubectl create secret generic twingate-service-key \
  --namespace=network \
  --from-literal=TWINGATE_ACCESS_TOKEN='YOUR_ACCESS_TOKEN' \
  --from-literal=TWINGATE_REFRESH_TOKEN='YOUR_REFRESH_TOKEN'
```

### Step 2: Customize Configuration (Optional)

If you want to use your own domain instead of `example.com`, edit the root application files:

#### Edit Network Stack Configuration

`components/network/root.yaml`:

```yaml
valuesObject:
  domain: yourdomain.com  # Change this
  email: admin@yourdomain.com  # Change this
  externalDns:
    txtOwnerId: your-infra  # Change this
  repoURL: git@github.com:yourorg/your-repo.git  # Change this
```

#### Edit Observability Stack Configuration

`components/observability/root.yaml`:

```yaml
valuesObject:
  domain: yourdomain.com  # Change this
  grafana:
    subdomain: grafana
  repoURL: git@github.com:yourorg/your-repo.git  # Change this
```

### Step 3: Apply Root Applications

Deploy the ArgoCD-managed stacks:

```bash
# Create namespaces if they don't exist
kubectl create namespace network --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

# Apply network stack
kubectl apply -f components/network/root.yaml

# Apply observability stack
kubectl apply -f components/observability/root.yaml
```

### Step 4: Monitor Deployment

Watch ArgoCD sync the applications:

```bash
# View all applications
kubectl get applications -n argocd

# Watch application status
watch kubectl get applications -n argocd

# View detailed application info
kubectl describe application network -n argocd
kubectl describe application observability -n argocd
```

You can also access the ArgoCD UI to monitor deployment progress visually.

## Phase 3: Verification

### Verify All Applications are Synced

```bash
kubectl get applications -n argocd

# All applications should show STATUS: Healthy and SYNC: Synced
```

### Verify Pods are Running

```bash
# Network stack
kubectl get pods -n network

# Observability stack
kubectl get pods -n observability
```

### Verify Gateways and Routes

```bash
# Check gateways
kubectl get gateway -A

# Check HTTP routes
kubectl get httproute -A

# Verify external-dns created records
kubectl logs -n network -l app.kubernetes.io/name=external-dns
```

### Verify TLS Certificates

```bash
# Check certificate resources
kubectl get certificate -A

# Check certificate status
kubectl describe certificate public-wildcard-tls -n network

# Certificates should show READY: True
```

### Access Services

After DNS propagation (may take a few minutes), access your services:

- **ArgoCD**: https://argocd.yourdomain.com
- **Longhorn**: https://longhorn.yourdomain.com
- **Grafana**: https://grafana.yourdomain.com

**Note**: These services use the private gateway and require Twingate access or VPN connectivity.

## Customization

### Changing Domain Names

1. Edit the `valuesObject` in `components/network/root.yaml` and `components/observability/root.yaml`
2. Update the domain field
3. Reapply the root applications:

```bash
kubectl apply -f components/network/root.yaml
kubectl apply -f components/observability/root.yaml
```

ArgoCD will automatically update all child resources with the new domain.

### Adding Custom Applications

To add your own applications managed by ArgoCD:

1. Create application manifests in the `apps/` directory
2. Create an ArgoCD Application resource pointing to your manifests
3. Apply the Application resource to the cluster

Example:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: git@github.com:yourorg/your-repo.git
    targetRevision: main
    path: apps/my-app
  destination:
    server: https://kubernetes.default.svc
    namespace: my-app
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Scaling the Cluster

#### Add Worker Nodes

1. Prepare new nodes with `scripts/server-init.sh`
2. Add nodes to `ansible/inventory.ini` under `[workers]`
3. Run playbooks:

```bash
ansible-playbook ansible/playbooks/install-k8s.yml --limit new_worker
ansible-playbook ansible/playbooks/join-workers.yml --limit new_worker
```

#### Add Control Plane Nodes (HA)

1. Prepare new nodes with `scripts/server-init.sh`
2. Add nodes to `ansible/inventory.ini` under `[control_plane]`
3. Run playbook:

```bash
ansible-playbook ansible/playbooks/promote-controlplane.yml
```

## Troubleshooting

### ArgoCD Applications Not Syncing

```bash
# Check application status
kubectl describe application network -n argocd

# Check ArgoCD controller logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller

# Force sync via CLI
argocd app sync network --force
```

### DNS Records Not Created

```bash
# Check external-dns logs
kubectl logs -n network -l app.kubernetes.io/name=external-dns

# Verify Cloudflare credentials
kubectl get secret cloudflare-api-token -n network -o yaml

# Check external-dns service
kubectl describe service external-dns -n network
```

### TLS Certificates Not Issued

```bash
# Check cert-manager logs
kubectl logs -n network -l app.kubernetes.io/name=cert-manager

# Check certificate status
kubectl describe certificate -n network

# Check certificate request
kubectl get certificaterequest -n network

# Check challenge status
kubectl get challenge -A
```

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -A

# Describe problematic pod
kubectl describe pod <pod-name> -n <namespace>

# Check pod logs
kubectl logs <pod-name> -n <namespace>

# Check events
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### Longhorn Issues

```bash
# Check Longhorn system pods
kubectl get pods -n longhorn-system

# Check Longhorn volumes
kubectl get volumes -n longhorn-system

# Run Longhorn preflight check
longhornctl check preflight

# Check node disk space
kubectl get nodes -o wide
```

### Network Connectivity Issues

```bash
# Check Calico status
kubectl get pods -n calico-system

# Check Calico node status
kubectl get caliconodestatus -A

# Test pod-to-pod connectivity
kubectl run test-pod --image=busybox --rm -it -- sh
# Inside pod: ping <other-pod-ip>

# Check network policies
kubectl get networkpolicy -A
```

## Next Steps

After successful bootstrap:

1. **Configure Backups**: Set up Longhorn snapshot schedules
2. **Enable Monitoring Alerts**: Configure alert rules in Victoria Metrics
3. **Set Up CI/CD**: Configure GitHub Actions or GitLab CI to deploy to ArgoCD
4. **Review Security**: Implement pod security policies, network policies
5. **Document Runbooks**: Create operational procedures for your team

## Support

For issues or questions:
- Check existing documentation in `ansible/playbooks/README*.md`
- Review ArgoCD application status and logs
- Check GitHub issues in the repository

## References

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Calico Documentation](https://docs.tigera.io/calico/)
- [Longhorn Documentation](https://longhorn.io/docs/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [cert-manager Documentation](https://cert-manager.io/docs/)
