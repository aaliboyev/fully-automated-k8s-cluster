# Longhorn Installation Playbook

## Overview
This playbook installs Longhorn distributed storage on a Kubernetes cluster using Helm.

## Prerequisites
- Kubernetes cluster with at least one worker node (Longhorn should run on workers, not control plane)
- Nodes must have the required packages (installed automatically by preflight)

## What it does

1. **Installs Helm** (if not already installed)
   - Downloads and installs Helm 3 from the official script

2. **Installs longhornctl CLI**
   - Architecture-aware (ARM64/AMD64)
   - Used for preflight checks

3. **Runs Preflight Checks**
   - Creates longhorn-system namespace
   - Installs required packages (open-iscsi, nfs-common, jq)
   - Validates system requirements
   - Probes kernel modules (iscsi_tcp)
   - Starts required services (iscsid)

4. **Installs Longhorn via Helm**
   - Adds Longhorn Helm repository
   - Installs using custom values from `../../components/longhorn/values.yaml`
   - Waits for all deployments to be ready

5. **Verifies Installation**
   - Displays pod status
   - Shows storage classes
   - Provides UI access instructions

## Configuration

Edit `../../components/longhorn/values.yaml` to customize:
- `defaultClassReplicaCount`: Number of replicas for volumes (default: 3)
- `defaultDataLocality`: Data locality setting (default: disabled)

Configuration variables in `group_vars/all.yml`:
- `longhorn_cli_version`: longhornctl CLI version
- `longhorn_chart_version`: Longhorn Helm chart version

## Usage

```bash
# Install Longhorn
ansible-playbook -i inventory.ini playbooks/install-longhorn.yml

# Access Longhorn UI
kubectl port-forward -n longhorn-system svc/longhorn-frontend 8080:80
# Then open: http://localhost:8080
```

## Post-Installation

After installation:
- Storage class `longhorn` will be available (set as default)
- Volumes can be provisioned using the `longhorn` storage class
- Longhorn UI accessible via port-forward

## Notes

- The playbook is idempotent - safe to run multiple times
- Preflight checks validate all nodes in the cluster
- Installation runs from the first control plane node
- Default replica count is set to 3 (requires at least 3 nodes with storage)
