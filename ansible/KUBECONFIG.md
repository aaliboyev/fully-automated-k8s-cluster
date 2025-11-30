# Kubeconfig Management

## Overview
The playbooks automatically manage your kubeconfig by:
- Merging new cluster configs into a single `~/.kube/config`
- Creating automatic backups before any changes
- Ensuring no duplicate contexts in Lens IDE

## Directory Structure

```
~/.kube/
├── config                    # Single merged config (used by kubectl and Lens)
└── config.backup.*           # Automatic timestamped backups
```

## Usage

### Accessing Clusters

```bash
# List available contexts
kubectl config get-contexts

# Switch to on-prem cluster
kubectl config use-context kubernetes-admin@kubernetes

# Switch to GKE cluster
kubectl config use-context gke_codevalet_us-east5_dev-cluster

# Use specific config directly
kubectl --kubeconfig ~/.kube/.configs/k8s-onprem get nodes
```

### Adding New Clusters

When you run the init-cluster playbook:
1. It fetches the kubeconfig temporarily to `/tmp`
2. It merges the new config into `~/.kube/config`
3. It creates a backup of the existing config
4. It cleans up the temporary file

To manually add a cluster:
```bash
# Backup current config
cp ~/.kube/config ~/.kube/config.backup.manual

# Merge new config
KUBECONFIG="$HOME/.kube/config:/path/to/new-cluster-config" \
  kubectl config view --flatten > ~/.kube/config.tmp && \
  mv ~/.kube/config.tmp ~/.kube/config && \
  chmod 600 ~/.kube/config
```

## Why Single Config?

Lens IDE automatically discovers kubeconfig files in `~/.kube/`. To prevent duplicates:
- We maintain only ONE config file: `~/.kube/config`
- All clusters are merged into this single file
- Lens sees each context only once
- Backups are kept for safety

## Restoring from Backup

Backups are created with timestamps:
```bash
# List backups
ls -lt ~/.kube/config.backup.*

# Restore from backup
cp ~/.kube/config.backup.20251127_103000 ~/.kube/config
```
