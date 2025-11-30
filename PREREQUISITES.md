# Prerequisites

This document outlines all requirements and preparatory steps needed before deploying the Kubernetes infrastructure.

## Table of Contents

- [Infrastructure Requirements](#infrastructure-requirements)
- [SSH Configuration](#ssh-configuration)
- [Required Software](#required-software)
- [Domain and DNS Setup](#domain-and-dns-setup)
- [Service Accounts and API Keys](#service-accounts-and-api-keys)

## Infrastructure Requirements

### VPS/Bare Metal Servers

This setup is designed for **bare metal or VPS deployments** where you don't have access to cloud load balancers (unlike AWS ELB, GCP Load Balancer, etc.).

#### Minimum Requirements

**Control Plane Nodes** (1-3 nodes):
- 2 vCPU cores
- 4 GB RAM
- 50 GB disk space
- Ubuntu 22.04 LTS or later
- Public IP address (at least one node for ingress)

**Worker Nodes** (3+ recommended):
- 4 vCPU cores
- 8 GB RAM
- 100 GB disk space
- Additional disk/partition for Longhorn storage (recommended)
- Ubuntu 22.04 LTS or later

**Important**: You need VPS or bare metal servers with direct root access and public IPs. Managed Kubernetes services (EKS, GKE, AKS) are not compatible with this setup.

### Network Requirements

- All nodes must be able to communicate with each other
- At least one node must have a public IP for ingress traffic
- Ports required:
  - **80/443** (HTTP/HTTPS) - For Traefik ingress
  - **6443** - Kubernetes API server
  - **2379-2380** - etcd
  - **10250** - Kubelet API
  - **30000-32767** - NodePort services (if needed)

## SSH Configuration

### Why Use SSH Config?

Using SSH config keeps your Ansible inventory clean and maintainable. Instead of hardcoding IPs and connection details in the inventory, you define them once in your SSH config.

### Setting Up SSH Config

#### Step 1: Create/Edit SSH Config

Edit or create `~/.ssh/config` on your local machine:

```bash
vim ~/.ssh/config
```

#### Step 2: Define Server Connections

Add your server configurations:

```ssh-config
# Kubernetes Control Plane Nodes
Host n1
    HostName 192.168.1.10
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

Host n2
    HostName 192.168.1.11
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

Host n3
    HostName 192.168.1.12
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

# Kubernetes Worker Nodes
Host n4
    HostName 192.168.1.21
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

Host n5
    HostName 192.168.1.22
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

Host n6
    HostName 192.168.1.23
    User root
    IdentityFile ~/.ssh/id_rsa
    Port 22

# Optional: Wildcard config for all nodes
Host n*
    ServerAliveInterval 60
    ServerAliveCountMax 3
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

**Configuration Options Explained:**
- `HostName` - The actual IP address or hostname of the server
- `User` - SSH user (typically `root` for initial setup)
- `IdentityFile` - Path to your SSH private key
- `Port` - SSH port (default 22)
- `ServerAliveInterval` - Keeps SSH connection alive
- `StrictHostKeyChecking` - Disable for automated deployments (optional)

#### Step 3: Set Correct Permissions

```bash
chmod 600 ~/.ssh/config
```

#### Step 4: Test SSH Connections

```bash
# Test each node
ssh n1 'hostname'
ssh n2 'hostname'
ssh n3 'hostname'
ssh n4 'hostname'
ssh n5 'hostname'
ssh n6 'hostname'
```

All commands should connect without prompting for passwords or confirmations.

### Configuring Ansible Inventory

With SSH config in place, your `ansible/inventory.ini` becomes clean and simple:

```ini
[control_plane]
n1
n2
n3

[workers]
n4
n5
n6

[k8s:children]
control_plane
workers
```

**Benefits of this approach:**
- Clean, readable inventory
- Centralized SSH configuration
- Easy to add/remove nodes
- No hardcoded IPs in multiple places
- Consistent across all tools (Ansible, kubectl, ssh, scp)

### SSH Key Setup

If you haven't set up SSH key authentication yet:

```bash
# Generate SSH key pair (if needed)
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Copy SSH key to each server
ssh-copy-id -i ~/.ssh/id_rsa.pub root@192.168.1.10
ssh-copy-id -i ~/.ssh/id_rsa.pub root@192.168.1.11
# ... repeat for all servers

# Or manually copy
cat ~/.ssh/id_rsa.pub | ssh root@192.168.1.10 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## Required Software

### Local Machine (Control Machine)

#### 1. Ansible

**Version**: 2.10 or later

**Installation:**

```bash
# macOS
brew install ansible

# Ubuntu/Debian
sudo apt update
sudo apt install ansible

# RHEL/CentOS
sudo yum install ansible

# Python pip
pip3 install ansible
```

**Verify installation:**
```bash
ansible --version
```

#### 2. kubectl

**Version**: Compatible with your Kubernetes version (v1.34 in this setup)

**Installation:**

```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Verify
kubectl version --client
```

#### 3. Helm (Optional)

**Version**: 3.x

Useful for debugging Helm charts locally.

```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify
helm version
```

#### 4. Git

Required for cloning and managing this repository.

```bash
# macOS
brew install git

# Ubuntu/Debian
sudo apt install git

# Verify
git --version
```

#### 5. ArgoCD CLI (Optional)

Useful for managing ArgoCD applications from the command line.

```bash
# macOS
brew install argocd

# Linux
curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x /usr/local/bin/argocd

# Verify
argocd version --client
```

### Target Servers

The `scripts/server-init.sh` script will install all required software on target servers:
- containerd (container runtime)
- Kubernetes components (kubeadm, kubelet, kubectl)
- CNI plugins
- Required kernel modules
- iscsi tools (for Longhorn)

## Domain and DNS Setup

### Domain Registration

You need a **registered domain name** that you control.

### Cloudflare DNS Management

This setup requires **Cloudflare** for DNS management because:
- We use `external-dns` with Cloudflare provider for automatic DNS record creation
- We use `cert-manager` with Cloudflare DNS-01 challenge for Let's Encrypt certificates

#### Setting Up Cloudflare DNS

1. **Create a Cloudflare Account** (if you don't have one)
   - Go to https://cloudflare.com and sign up

2. **Add Your Domain to Cloudflare**
   - Click "Add a Site"
   - Enter your domain name
   - Choose a plan (Free plan is sufficient)
   - Update nameservers at your domain registrar to point to Cloudflare

3. **Verify DNS is Working**
   ```bash
   dig yourdomain.com
   # Should show Cloudflare nameservers
   ```

#### Create DNS Records

Before deployment, create a wildcard A record pointing to your ingress node:

```
Type: A
Name: *
Content: <PUBLIC_IP_OF_INGRESS_NODE>
Proxy: Disabled (DNS only)
TTL: Auto
```

This allows `*.yourdomain.com` to route to your cluster.

**Note**: `external-dns` will automatically create additional records (like `argocd.yourdomain.com`, `grafana.yourdomain.com`) after deployment.

## Service Accounts and API Keys

### Cloudflare API Token

Required for `cert-manager` and `external-dns`.

#### Create API Token

1. Log into Cloudflare Dashboard
2. Go to **My Profile** → **API Tokens**
3. Click **Create Token**
4. Use the **Edit zone DNS** template or create custom with:
   - Permissions:
     - Zone / DNS / Edit
     - Zone / Zone / Read
   - Zone Resources:
     - Include / Specific zone / yourdomain.com
5. Copy the token (you'll only see it once)

**Save this token securely** - you'll need it during Phase 2 deployment.

#### Token Verification

Test your token:

```bash
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer YOUR_TOKEN_HERE" \
     -H "Content-Type:application/json"
```

Should return:
```json
{
  "success": true,
  "messages": [],
  "result": {
    "id": "...",
    "status": "active"
  }
}
```

### Twingate Service Keys (Optional)

If using Twingate for zero-trust network access to private services:

1. Log into your Twingate Admin Console
2. Navigate to **Settings** → **Connectors**
3. Create a new Connector
4. Generate service key tokens:
   - `TWINGATE_ACCESS_TOKEN`
   - `TWINGATE_REFRESH_TOKEN`
5. Copy both tokens

**Save these tokens securely** - you'll need them during Phase 2 deployment.

If you're not using Twingate, you can:
- Remove Twingate from the network stack
- Use a different VPN solution
- Expose services publicly (not recommended for production)

### GitHub SSH Key (for GitOps)

ArgoCD needs access to your Git repository.

#### Generate Deploy Key

```bash
ssh-keygen -t rsa -b 4096 -C "argocd@yourdomain.com" -f ~/.ssh/argocd_deploy_key
```

#### Add to GitHub

1. Go to your repository → **Settings** → **Deploy keys**
2. Click **Add deploy key**
3. Title: `ArgoCD Deploy Key`
4. Key: Paste contents of `~/.ssh/argocd_deploy_key.pub`
5. Check **Allow write access** if you want ArgoCD to sync back (optional)

#### Configure ArgoCD

After ArgoCD is installed, add the private key:

```bash
kubectl create secret generic argocd-repo-key \
  --namespace=argocd \
  --from-file=sshPrivateKey=$HOME/.ssh/argocd_deploy_key
```

Then configure the repository in ArgoCD (via UI or CLI).

## Pre-Deployment Checklist

Before starting deployment, ensure you have:

- [ ] VPS/bare metal servers provisioned with Ubuntu 22.04+
- [ ] SSH key-based authentication configured to all servers
- [ ] SSH config file created with short aliases (n1, n2, etc.)
- [ ] Ansible installed on local machine
- [ ] kubectl installed on local machine
- [ ] Domain registered and DNS pointing to Cloudflare
- [ ] Cloudflare API token created with DNS edit permissions
- [ ] Wildcard DNS record (*.yourdomain.com) created
- [ ] Twingate connector and tokens (if using)
- [ ] GitHub deploy key configured (if using private repo)
- [ ] Ansible inventory configured with SSH aliases
- [ ] Customized `components/*/root.yaml` files with your domain

## Next Steps

Once all prerequisites are met, proceed to:
1. **BOOTSTRAP.md** - Detailed deployment guide
2. **README.md** - Overview and quick start

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH connection
ssh -v n1

# Check SSH config syntax
ssh -G n1

# Verify SSH key permissions
ls -la ~/.ssh/id_rsa
# Should be 600 or 400
```

### Ansible Connection Issues

```bash
# Test Ansible connectivity
ansible all -i ansible/inventory.ini -m ping

# Run with verbose output
ansible all -i ansible/inventory.ini -m ping -vvv

# Test with specific user
ansible all -i ansible/inventory.ini -m ping -u root
```

### Domain/DNS Issues

```bash
# Verify nameservers
dig NS yourdomain.com

# Verify A record
dig A yourdomain.com

# Verify wildcard
dig test.yourdomain.com

# Check Cloudflare API access
curl -X GET "https://api.cloudflare.com/client/v4/zones" \
     -H "Authorization: Bearer YOUR_TOKEN" | jq .
```

### Firewall Issues

Ensure these ports are open on all nodes:

```bash
# Check if ports are listening
sudo ss -tulnp | grep -E ':(80|443|6443|2379|2380|10250)'

# Check firewall rules (Ubuntu/Debian)
sudo ufw status

# Check firewall rules (RHEL/CentOS)
sudo firewall-cmd --list-all
```

## Support

For questions or issues with prerequisites:
- Review this document thoroughly
- Check Ansible documentation: https://docs.ansible.com/
- Check Kubernetes documentation: https://kubernetes.io/docs/
- Review Cloudflare API docs: https://developers.cloudflare.com/api/
