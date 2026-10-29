# Ansible

Ansible manages the nodes and everything ArgoCD depends on: Kubernetes,
containerd, the Cilium CNI, local-path storage and ArgoCD itself. Everything
above that is an Argo app.

Run playbooks from this directory: `ansible.cfg` sets `inventory.ini`, the
root SSH user and the key. Variables are in `group_vars/all.yml`; Cilium's Helm
values are in `cilium/`.

The order for a new cluster is in [../BOOTSTRAP.md](../BOOTSTRAP.md#phase-1-nodes-and-base-layer).

## Playbooks

### Cluster lifecycle

| Playbook | Purpose |
|----------|---------|
| `install-k8s.yml` | kubeadm, kubelet, kubectl (held) and kernel headers |
| `init-cluster.yml` | `kubeadm init` on the first control plane, without kube-proxy |
| `join-workers.yml` | Join workers |
| `promote-controlplane.yml` | Join additional control planes |
| `upgrade-cluster.yml` | Rolling Kubernetes upgrade, one node at a time |
| `remove-workers.yml` | Drain, delete and clean workers |

### Node configuration

| Playbook | Purpose |
|----------|---------|
| `upgrade-containerd.yml` | Install the pinned `containerd.io`, one node at a time |
| `update-kernel.yml` | Latest kernel and headers (and optionally `apt upgrade`), rolling reboot with storage gates |
| `configure-sysctl.yml` | inotify and conntrack limits |
| `configure-firewall.yml` | nftables guard for cluster-internal ports |
| `configure-registry-mirrors.yml` | containerd pulls `ghcr.io` and `docker.io` through Harbor |
| `install-tailscale.yml` | Enroll nodes in the tailnet ([../TAILSCALE.md](../TAILSCALE.md)) |

### Cluster add-ons

| Playbook | Purpose |
|----------|---------|
| `install-cilium.yml` | Install or upgrade Cilium (`-e cilium_routing=tunnel` for VXLAN) |
| `install-local-path.yml` | local-path-provisioner (`local-path`, `local-fast`) |
| `install-argocd.yml` | ArgoCD |

Details per playbook: [playbooks/README.md](playbooks/README.md). Kubeconfig
handling: [KUBECONFIG.md](KUBECONFIG.md).

## Examples

```bash
ansible-playbook playbooks/install-k8s.yml --limit node5
ansible-playbook playbooks/install-cilium.yml
ansible-playbook playbooks/update-kernel.yml --limit node3
ansible-playbook playbooks/upgrade-cluster.yml -e kubernetes_version=v1.35
```
