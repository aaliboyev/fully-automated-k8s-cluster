# Prerequisites

What has to exist before [BOOTSTRAP.md](BOOTSTRAP.md).

## Table of Contents

- [Infrastructure Requirements](#infrastructure-requirements)
- [SSH Configuration](#ssh-configuration)
- [Required Software](#required-software)
- [Domain and DNS Setup](#domain-and-dns-setup)
- [Service Accounts and API Keys](#service-accounts-and-api-keys)

## Infrastructure Requirements

### VPS/Bare Metal Servers

The cluster runs on VPS or bare metal servers with root access and public IPs.
There is no cloud load balancer: the public edge binds 80/443 on the edge
nodes' own addresses. Managed Kubernetes services (EKS, GKE, AKS) don't fit
this setup.

#### Minimum Requirements

**Control plane node**:
- 2 vCPU cores
- 4 GB RAM
- 50 GB disk space

**Worker nodes** (3 or more):
- 4 vCPU cores
- 8 GB RAM (16 GB leaves room for workloads next to the cluster services)
- 100 GB disk space
- Free space on the root filesystem for replicated volumes (thin files, no extra disk needed)

All nodes run **Debian 13**: the playbooks install `linux-image-amd64` and
`linux-headers-amd64`, and the Docker and Tailscale apt repositories are the
trixie ones.

### Network Requirements

- Every node has a public IP; nodes reach each other over those addresses.
  Node-to-node traffic is encrypted by Cilium's WireGuard, so nodes don't need
  a private network or shared L2.
- Open between nodes: UDP 51871 (Cilium WireGuard) and the cluster-internal
  ports in `firewall_guarded_tcp_ports` (`ansible/group_vars/all.yml`), among
  them 6443 (API server), 2379-2380 (etcd), 10250 (kubelet), 4240 (Cilium
  health) and 4244 (Hubble).
- Open to the internet on the edge nodes: 80 and 443.
- SSH (22) and Tailscale stay open to the internet on every node.

`configure-firewall.yml` restricts the guarded ports to nodes, pods, loopback
and `tailscale0`.

## SSH Configuration

### Why Use SSH Config?

Ansible's inventory holds only host aliases; addresses, users and keys live in
`~/.ssh/config`, so ssh, scp and Ansible use the same names.

### Setting Up SSH Config

#### Step 1: Define Server Connections

Add each node to `~/.ssh/config` on your workstation:

```ssh-config
Host n1
    HostName 192.0.2.10
    User root
    IdentityFile ~/.ssh/id_rsa

Host n2
    HostName 192.0.2.11
    User root
    IdentityFile ~/.ssh/id_rsa

Host n3
    HostName 192.0.2.12
    User root
    IdentityFile ~/.ssh/id_rsa

Host n4
    HostName 192.0.2.13
    User root
    IdentityFile ~/.ssh/id_rsa

Host n*
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

`ansible/ansible.cfg` already sets `remote_user = root`,
`private_key_file = ~/.ssh/id_rsa` and disables host key checking.

#### Step 2: Set Permissions and Test

```bash
chmod 600 ~/.ssh/config
for h in n1 n2 n3 n4; do ssh "$h" hostname; done
```

Every command should connect without a password prompt.

### Configuring Ansible Inventory

`ansible/inventory.ini` then lists only aliases:

```ini
[control_plane]
n1

[workers]
n2
n3
n4

[k8s:children]
control_plane
workers
```

### SSH Key Setup

```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id -i ~/.ssh/id_rsa.pub root@192.0.2.10
# ... repeat for all servers
```

## Required Software

### Workstation

| Tool | Why |
|------|-----|
| Ansible 2.10+ | All node and base-layer playbooks |
| kubectl | Matching `kubernetes_version` in `ansible/group_vars/all.yml` |
| Tailscale client | The API server and the private gateway are reachable only over the tailnet |
| git | This repository |
| yq | Splitting the Gateway API CRD bundle ([components/network/README.md](components/network/README.md)) |
| Helm 3 (optional) | Rendering charts locally; the playbooks install Helm on the control plane themselves |
| ArgoCD CLI (optional) | Managing applications from the command line |

```bash
# macOS
brew install ansible kubectl git yq helm argocd

# Debian
sudo apt install ansible git
```

### Target Servers

`scripts/server-init.sh` installs base packages and containerd, loads the
kernel modules and sets the sysctls. `install-k8s.yml` installs kubeadm,
kubelet, kubectl and `linux-headers-amd64`; `update-kernel.yml` keeps kernel
and headers matched, because the LINSTOR satellite compiles the DRBD module
against them. `upgrade-containerd.yml` replaces Debian's containerd with the
`containerd.io` version pinned in `group_vars/all.yml`.

## Domain and DNS Setup

### Cloudflare DNS Management

The domain's DNS must be on **Cloudflare**:
- `external-dns` (Cloudflare provider) creates a record for every route hostname
- `cert-manager` solves Let's Encrypt DNS-01 challenges through the Cloudflare API

Add the domain to Cloudflare and point the registrar's nameservers at it:

```bash
dig NS yourdomain.com
```

### Records Created by Hand

external-dns points public hostnames at the edge name (`publicEdgeHostname`
in `components/network/values.yaml`) and private hostnames at the private
gateway. The edge name itself is created by hand, one A record per edge node:

```
Type: A
Name: <edge name, e.g. dns>
Content: <public IP of an edge node>
Proxy: Disabled (DNS only)
```

Repeat for each edge node. Tailnet addresses (`<host>.net.<domain>`) are also
manual records; see [TAILSCALE.md](TAILSCALE.md#addressing).

## Service Accounts and API Keys

### Cloudflare API Token

Used by `cert-manager` and `external-dns`.

1. Cloudflare dashboard → **My Profile** → **API Tokens** → **Create Token**
2. Use the **Edit zone DNS** template or a custom token with:
   - Zone / DNS / Edit
   - Zone / Zone / Read
   - Zone resources: the domain(s) the cluster serves
3. Copy the token; it is shown once.

Verify it:

```bash
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer <TOKEN>" | jq .result.status
# "active"
```

### Tailscale

See [TAILSCALE.md](TAILSCALE.md):

1. Create a tailnet and apply `tailscale/acl.hujson` as the tailnet policy.
2. **Settings** → **Keys**: generate a **reusable** pre-auth key tagged
   `tag:node`. Pass it to `install-tailscale.yml` at runtime; never commit it.
3. **Settings** → **OAuth clients**: create a client for the Tailscale
   operator; its ID and secret go into the `operator-oauth` secret.

Auth keys are enrollment tickets, not runtime credentials: enrolled devices
are unaffected when the key expires.

### GitHub SSH Key (for GitOps)

ArgoCD reads this repository over SSH.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/argocd_deploy_key -N ''
```

Add `~/.ssh/argocd_deploy_key.pub` under the repository's **Settings** →
**Deploy keys** (read-only). After ArgoCD is installed, register it as a
repository secret:

```bash
kubectl -n argocd create secret generic repo-infra-k8s \
  --from-literal=type=git \
  --from-literal=url=git@github.com:<org>/<repo>.git \
  --from-file=sshPrivateKey=$HOME/.ssh/argocd_deploy_key
kubectl -n argocd label secret repo-infra-k8s argocd.argoproj.io/secret-type=repository
```

## Pre-Deployment Checklist

- [ ] Debian 13 servers with public IPs and root SSH access
- [ ] `~/.ssh/config` aliases and `ansible/inventory.ini`
- [ ] Ansible, kubectl and Tailscale on the workstation
- [ ] Domain on Cloudflare, API token with DNS edit permission
- [ ] Edge name with one A record per edge node
- [ ] Tailnet with the ACL applied, a tagged auth key and an operator OAuth client
- [ ] Deploy key on the repository
- [ ] Domains and `repoURL` set in `components/*/values.yaml` and the `root.yaml` files

## Troubleshooting

### SSH Connection Issues

```bash
ssh -v n1        # verbose connection
ssh -G n1        # resolved config for the alias
ls -la ~/.ssh/id_rsa   # must be 600 or 400
```

### Ansible Connection Issues

```bash
cd ansible
ansible all -m ping
ansible all -m ping -vvv
```

### Domain/DNS Issues

```bash
dig NS yourdomain.com
dig A <edge name>.yourdomain.com
curl -s "https://api.cloudflare.com/client/v4/zones" -H "Authorization: Bearer <TOKEN>" | jq '.result[].name'
```

### Firewall Issues

```bash
# Listening ports on a node
ss -tulnp | grep -E ':(80|443|6443|2379|2380|10250)'

# The node firewall table
nft list table inet node_firewall
```
