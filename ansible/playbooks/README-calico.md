# Calico CNI Installation

This playbook installs Calico CNI with eBPF dataplane using the Tigera Operator (recommended method).

## Overview

The playbook follows the official Calico installation guide for self-managed on-premises Kubernetes clusters, using:
- **Tigera Operator**: Manages the installation, upgrade, and lifecycle of Calico
- **eBPF dataplane**: High-performance, kernel-native networking with automatic kube-proxy replacement

## Prerequisites

- Kubernetes cluster initialized (run `init-cluster.yml` first)
- kubectl configured on the control plane node
- Pod network CIDR configured (default: 192.168.0.0/16)

## Usage

Run the playbook after initializing your cluster:

```bash
ansible-playbook -i inventory.ini playbooks/install-calico.yml
```

## What it does

1. **Installs Tigera Operator CRDs**: Custom resource definitions for Calico operator
2. **Deploys Tigera Operator**: The operator that manages Calico lifecycle
3. **Applies eBPF custom resources**: Downloads and applies the official eBPF configuration
4. **Monitors deployment**: Waits for Calico to be fully available
5. **Displays status**: Shows TigeraStatus and pod status

## eBPF Mode Features

The eBPF dataplane provides:
- **Better performance**: Native kernel networking without iptables overhead
- **Kube-proxy replacement**: Automatically manages kube-proxy with `kubeProxyManagement: Enabled`
- **Network bootstrap**: Handles initial pod networking with `bpfNetworkBootstrap: Enabled`

## Configuration

The default configuration uses the official `custom-resources-bpf.yaml` from Calico repository.

Variables used (defined in `group_vars/all.yml`):
- `calico_version`: Calico version to install (default: v3.31.2)
- `pod_network_cidr`: Pod network CIDR (default: 192.168.0.0/16)

## Verification

After installation, verify Calico is running:

```bash
# Check TigeraStatus
kubectl get tigerastatus

# Check Calico pods
kubectl get pods -n calico-system

# Check node status
kubectl get nodes
```

## References

- [Calico on-premises installation guide](https://docs.tigera.io/calico/latest/getting-started/kubernetes/self-managed-onprem/onpremises)
- [Calico eBPF dataplane](https://docs.tigera.io/calico/latest/operations/ebpf/)
