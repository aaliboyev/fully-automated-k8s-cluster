# Kubernetes Cluster Management with Ansible

Complete Ansible automation for deploying and managing Kubernetes clusters.

## Overview

This setup separates concerns into:
1. **Server initialization** (`server-init.sh`) - Base OS setup, containerd, networking
2. **Kubernetes installation** (`install-k8s.yml`) - Install kubeadm, kubelet, kubectl  
3. **Cluster management** (various playbooks) - Initialize, join nodes, install storage

## Quick Start

```bash
# 1. Initialize servers (run on each node)
sudo bash /path/to/server-init.sh

# 2. Install Kubernetes
ansible-playbook -i inventory.ini playbooks/install-k8s.yml

# 3. Initialize cluster
ansible-playbook -i inventory.ini playbooks/init-cluster.yml

# 4. Join workers
ansible-playbook -i inventory.ini playbooks/join-workers.yml

# 5. Install storage (optional)
ansible-playbook -i inventory.ini playbooks/install-longhorn.yml
```

## Playbooks

### install-k8s.yml
Install Kubernetes components (kubeadm, kubelet, kubectl)

```bash
ansible-playbook -i inventory.ini playbooks/install-k8s.yml
ansible-playbook -i inventory.ini playbooks/install-k8s.yml --limit n1
```

### init-cluster.yml  
Initialize Kubernetes cluster on first control plane

```bash
ansible-playbook -i inventory.ini playbooks/init-cluster.yml
```

### join-workers.yml
Join worker nodes to cluster

```bash
ansible-playbook -i inventory.ini playbooks/join-workers.yml
ansible-playbook -i inventory.ini playbooks/join-workers.yml --limit n1,n3
```

### remove-workers.yml
Remove and clean worker nodes

```bash
ansible-playbook -i inventory.ini playbooks/remove-workers.yml --limit n1
```

### install-longhorn.yml
Install Longhorn distributed storage

```bash
ansible-playbook -i inventory.ini playbooks/install-longhorn.yml
```

## Configuration

Edit `group_vars/all.yml`:
- `kubernetes_version`: "v1.34"
- `calico_version`: "v3.31.2"
- `longhorn_cli_version`: "v1.10.1"

See individual playbook README files for details.
