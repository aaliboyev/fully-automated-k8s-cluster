# Bootstrapping the Cluster

How to build the cluster from bare servers. Requirements, SSH setup and
credentials are in [PREREQUISITES.md](PREREQUISITES.md); how the result is laid
out is in [README.md](README.md).

## Table of Contents

- [Phase 1: Nodes and Base Layer](#phase-1-nodes-and-base-layer)
- [Phase 2: ArgoCD-Managed Components](#phase-2-argocd-managed-components)
- [Phase 3: Verification](#phase-3-verification)
- [Customization](#customization)
- [Scaling the Cluster](#scaling-the-cluster)
- [Troubleshooting](#troubleshooting)

## Phase 1: Nodes and Base Layer

Playbooks run from `ansible/`; `ansible.cfg` sets the inventory and the root
SSH user.

### Step 1: Prepare Server Nodes

Run the initialization script on each node:

```bash
scp scripts/server-init.sh root@<node>:/tmp/
ssh root@<node> 'bash /tmp/server-init.sh'
```

It installs base packages and containerd, loads `overlay` and `br_netfilter`,
sets the forwarding sysctls and disables swap.

### Step 2: Configure the Inventory

`ansible/inventory.ini` lists SSH aliases (see
[PREREQUISITES.md](PREREQUISITES.md#ssh-configuration)):

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

```bash
cd ansible
ansible all -m ping
```

### Step 3: Review Variables

- `ansible/group_vars/all.yml`: `kubernetes_version`, `containerd_version`,
  `cluster_name`, `pod_network_cidr`, `cilium_version`, `local_path_version`,
  `argocd_chart_version`, firewall port lists, `node_health_urls`.
- `ansible/cilium/values.yaml`: `k8sServiceHost` / `k8sServicePort` are how
  Cilium agents reach the API server. With kube-proxy replaced there is no
  `kubernetes` Service translation until Cilium runs, so this must be a name
  that resolves to the control plane and is in the API server certificate
  (kubeadm `controlPlaneEndpoint`). `devices` names the node interfaces.

### Step 4: Deploy the Base Layer

```bash
ansible-playbook playbooks/install-k8s.yml
ansible-playbook playbooks/configure-sysctl.yml
ansible-playbook playbooks/init-cluster.yml
ansible-playbook playbooks/install-cilium.yml
ansible-playbook playbooks/join-workers.yml
ansible-playbook playbooks/install-local-path.yml
ansible-playbook playbooks/install-argocd.yml
```

- `install-k8s.yml` installs and holds kubeadm, kubelet and kubectl, plus
  kernel headers for DRBD.
- `configure-sysctl.yml` raises inotify and conntrack limits; see
  [ansible/playbooks/README.md](ansible/playbooks/README.md#configure-sysctlyml).
- `init-cluster.yml` runs `kubeadm init` without the kube-proxy addon and
  merges the admin kubeconfig into the local `~/.kube/config`. Nodes stay
  `NotReady` until Cilium is installed.
- `install-cilium.yml` installs or upgrades Cilium from `ansible/cilium/` and
  adds `cilium-proxy-rpcheck.service` on every node (Tailscale sets
  `src_valid_mark`, which otherwise drops traffic Cilium hands to its proxy).
- `install-local-path.yml` deploys `local-path` and `local-fast` (see
  [components/local-path/README.md](components/local-path/README.md)).

`make ansible-init` runs only `init-cluster.yml`.

Then move every node to the pinned `containerd.io` (drains one node at a time):

```bash
ansible-playbook playbooks/upgrade-containerd.yml
```

### Step 5: Prepare Replicated Storage Nodes

Run `update-kernel.yml` on every node listed in `components/storage/values.yaml`.
It installs the latest kernel with matching headers and reboots one node at a
time; the LINSTOR satellite compiles DRBD 9 against those headers.

```bash
ansible-playbook playbooks/update-kernel.yml --limit <node>
```

### Step 6: Verify the Base Layer

```bash
kubectl get nodes
kubectl -n kube-system get pods -l k8s-app=cilium
kubectl -n kube-system exec ds/cilium -- cilium-dbg status --brief
kubectl -n local-path-storage get pods
kubectl -n argocd get pods
```

## Phase 2: ArgoCD-Managed Components

### Step 1: Enroll Nodes in the Tailnet

Host enrollment is Ansible's job (see [TAILSCALE.md](TAILSCALE.md)):

```bash
ansible-playbook playbooks/install-tailscale.yml -e tailscale_authkey=tskey-auth-...
```

### Step 2: Create Credential Secrets

Credentials are never in git. Create them before the apps that read them sync:

```bash
kubectl create namespace network
kubectl -n network create secret generic cloudflare-api-token \
  --from-literal=api-token='<CLOUDFLARE_API_TOKEN>'

kubectl create namespace tailscale
kubectl -n tailscale create secret generic operator-oauth \
  --from-literal=client_id=... --from-literal=client_secret=...
```

`components/flow-history/create-secrets.sh` creates the S3 credentials; apps
with a `create-secrets.sh` in their directory need it run once. ArgoCD needs
read access to the repository (see
[PREREQUISITES.md](PREREQUISITES.md#github-ssh-key-for-gitops)).

### Step 3: Install the Gateway API CRDs

No app installs them; follow
[components/network/README.md](components/network/README.md#gateway-api-crds).

### Step 4: Apply the Root Application

```bash
kubectl apply -f bootstrap/root.yaml
```

The `root` Application applies every `apps/*/root.yaml` and
`components/*/root.yaml`, and from then on applies any pushed change to them.
It never prunes: to remove an app, delete its Application explicitly.

```bash
kubectl -n argocd get applications
```

### Step 5: Node Settings That Depend on Cluster Services

If a Harbor registry with proxy-cache projects runs in the cluster, route
image pulls through it:

```bash
ansible-playbook playbooks/configure-registry-mirrors.yml
```

Once kubectl works over the tailnet, close the cluster-internal ports:

```bash
ansible-playbook playbooks/configure-firewall.yml
```

Both are described in [ansible/playbooks/README.md](ansible/playbooks/README.md).

## Phase 3: Verification

```bash
# All applications Synced and Healthy
kubectl -n argocd get applications

# Gateways Programmed, routes attached
kubectl get gateway,httproute -A

# Certificates Ready
kubectl get certificate -A

# Edge pods on the edge nodes
kubectl -n network get pods -o wide
```

Private services (ArgoCD, Grafana, Hubble UI) answer only over the tailnet.
The ArgoCD admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

## Customization

- Domains, hostnames, the ACME email, the external-dns owner ID and the edge
  DNS name: `components/network/values.yaml`.
- Grafana hostname: `components/observability/values.yaml`.
- OIDC issuer and client IDs: `components/argocd/values.yaml` and
  `components/observability/values/stack.yaml`.
- Edge nodes: the node affinity in `components/network/values/haproxy-public.yaml`,
  plus one A record per edge node under `publicEdgeHostname`.
- Repository URL: `repoURL` in `bootstrap/root.yaml`, every `root.yaml` and the
  component `values.yaml` files.

Push the change; the `root` Application and the component apps apply it.

### Adding an Application

Create `apps/<name>/root.yaml` holding an ArgoCD Application and push; `root`
applies it. Public hosts use a Gateway of class `public-v2` with
`external-dns.alpha.kubernetes.io/target: dns.example.com`; internal
`*.example.com` hosts attach an HTTPRoute to `network/private`.

## Scaling the Cluster

### Add Worker Nodes

1. Run `scripts/server-init.sh` on the node and add it to `ansible/inventory.ini`
   under `[workers]`.
2. Install, tune and join it:

   ```bash
   ansible-playbook playbooks/install-k8s.yml --limit <node>
   ansible-playbook playbooks/configure-sysctl.yml --limit <node>
   ansible-playbook playbooks/join-workers.yml --limit <node>
   ansible-playbook playbooks/upgrade-containerd.yml --limit <node>
   ansible-playbook playbooks/configure-registry-mirrors.yml --limit <node>
   ansible-playbook playbooks/install-tailscale.yml --limit <node> -e tailscale_authkey=tskey-auth-...
   ```

3. Run `configure-firewall.yml` on all nodes, not just the new one: every
   node's address is in each node's trusted set.
4. For replicated storage, follow
   [components/storage/README.md](components/storage/README.md#joining-a-node).

### Add Control Plane Nodes

Add the node under `[control_plane]` and run
`ansible-playbook playbooks/promote-controlplane.yml`.

## Troubleshooting

### ArgoCD Applications Not Syncing

```bash
kubectl -n argocd describe application <app>
kubectl -n argocd logs -l app.kubernetes.io/name=argocd-application-controller
```

### DNS Records Not Created

```bash
kubectl -n network logs -l app.kubernetes.io/name=external-dns
kubectl -n network get secret cloudflare-api-token
```

external-dns publishes about a minute after a route appears; lookups made
before that may cache NXDOMAIN.

### TLS Certificates Not Issued

```bash
kubectl -n network logs -l app.kubernetes.io/name=cert-manager
kubectl get certificate,certificaterequest -A
kubectl get challenge -A
```

### Pods Not Starting

```bash
kubectl -n <namespace> describe pod <pod>
kubectl -n <namespace> logs <pod>
kubectl -n <namespace> get events --sort-by='.lastTimestamp'
```

### Storage Issues

```bash
# Piraeus operator, controller, satellites, CSI
kubectl get pods -n piraeus-datastore

# LINSTOR view of nodes, pools and volumes
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor node list
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor storage-pool list
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor resource list
```

A satellite stuck in init usually means the DRBD module failed to build: check
the `drbd-module-loader` init container logs and that the node has run
`update-kernel.yml`.

### Network Connectivity Issues

```bash
# Agent health and recent drops on one node
kubectl -n kube-system get pods -l k8s-app=cilium -o wide
kubectl -n kube-system exec <cilium-pod> -- cilium-dbg status
kubectl -n kube-system exec <cilium-pod> -- hubble observe --verdict DROPPED --last 50

kubectl get networkpolicy,ciliumnetworkpolicy -A
```

A node whose agent can't start loses contact with the others (they keep
WireGuard peering to it); `kubectl delete ciliumnode <node>` clears that.
Historical drops are in ClickHouse
([components/flow-history/README.md](components/flow-history/README.md)).

## References

- [Kubernetes](https://kubernetes.io/docs/)
- [ArgoCD](https://argo-cd.readthedocs.io/)
- [Cilium](https://docs.cilium.io/)
- [Piraeus Datastore](https://piraeus.io/docs/)
- [LINSTOR User Guide](https://linbit.com/drbd-user-guide/linstor-guide-1_0-en/)
- [Traefik](https://doc.traefik.io/traefik/)
- [cert-manager](https://cert-manager.io/docs/)
