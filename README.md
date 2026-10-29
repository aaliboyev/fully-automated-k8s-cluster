# Fully Automated Kubernetes Cluster

GitOps repository for a self-managed kubeadm cluster on VPS nodes. Ansible
builds the nodes and everything ArgoCD itself depends on (Kubernetes, the CNI,
local-path storage, ArgoCD). ArgoCD deploys everything else from `main`.

Domains, node names and repository URLs are placeholders (`example.com`,
`node1`…`node5`, `your-org/your-infra-repo`); replace them before bootstrapping.

To build a cluster from scratch: [PREREQUISITES.md](PREREQUISITES.md), then
[BOOTSTRAP.md](BOOTSTRAP.md).

## Cluster

| Role | Nodes |
|------|-------|
| Control plane | `node1` (API endpoint `k8s.example.com:6443`, kubeadm `controlPlaneEndpoint`) |
| Workers | `node2`, `node3`, `node4`, `node5` |
| Public edge | `node3`, `node4` |

Nodes run Debian 13. The inventory is `ansible/inventory.ini`; hosts resolve
through `~/.ssh/config` (see [PREREQUISITES.md](PREREQUISITES.md)).

## Components

| Layer | Component | Managed by | Configuration |
|-------|-----------|------------|---------------|
| Kubernetes | kubeadm, kubelet, containerd | Ansible | `ansible/group_vars/all.yml` |
| CNI | Cilium (kube-proxy replacement, WireGuard, Hubble) | Ansible: `install-cilium.yml` | `ansible/cilium/values.yaml` |
| Node-local storage | local-path-provisioner | Ansible: `install-local-path.yml` | `components/local-path/` |
| GitOps | ArgoCD | Ansible: `install-argocd.yml` | `components/argocd/values.yaml` |
| Public edge | HAProxy Unified Gateway | Argo app `network-haproxy-public` | `components/network/values/haproxy-public.yaml`, `charts/haproxy-unified-gateway/` |
| Private gateway | Traefik | Argo app `network-traefik-private` | `components/network/values/traefik-private.yaml` |
| TLS, DNS | cert-manager, external-dns (Cloudflare) | Argo app `network` | `components/network/` |
| Tailnet | Tailscale operator | Argo app `network-tailscale-operator` | [TAILSCALE.md](TAILSCALE.md) |
| Replicated storage | LINSTOR/DRBD (Piraeus operator) | Argo app `storage` | `components/storage/` |
| Metrics, dashboards | VictoriaMetrics, Grafana | Argo app `observability` | `components/observability/` |
| Flow history | Hubble flows to ClickHouse via Vector | Argo app `flow-history` | `components/flow-history/` |
| SSO | OIDC login for ArgoCD and Grafana (any provider; configured for Zitadel) | values files | `components/argocd/values.yaml`, `components/observability/values/stack.yaml` |

Versions are pinned in `ansible/group_vars/all.yml` (Ansible layer) and in
each Argo Application's `targetRevision`.

## Repository layout

- `ansible/` — inventory, variables, playbooks, Cilium values
- `bootstrap/root.yaml` — the `root` Application: applies every
  `apps/*/root.yaml` and `components/*/root.yaml`
- `components/` — cluster services, one Argo Application per directory
- `apps/` — your workloads, one Argo Application per directory
- `charts/` — charts maintained in this repo
- `tailscale/acl.hujson` — tailnet policy
- `scripts/server-init.sh` — base OS setup for a new node

## Networking

### CNI

Cilium replaces kube-proxy, so no kube-proxy DaemonSet runs: `init-cluster.yml`
and `upgrade-cluster.yml` pass `--skip-phases=addon/kube-proxy` to kubeadm. Pod
IPs come from each node's podCIDR inside `192.168.0.0/16`.

The nodes sit in three /22s with no shared L2, so native routing only works
with WireGuard node encryption: all node-to-node traffic (pod, host-to-pod,
DRBD, etcd) goes through it. `-e cilium_routing=tunnel` switches to VXLAN with
WireGuard for pod traffic only (`ansible/cilium/values-tunnel.yaml`).

The CNI is not an Argo app because ArgoCD runs on top of it. To change or
upgrade it, edit `ansible/cilium/values.yaml` or `cilium_version` and rerun
`install-cilium.yml`. A node whose agent can't start is cut off from the others
until its CiliumNode is deleted. DRBD replicates over the pod network, so a
CNI outage stalls writes on `replicated` volumes.

### Public edge

No cloud load balancer exists, so the edge binds the nodes' public IPs
directly. HAProxy Unified Gateway runs as a host-network DaemonSet on `node3` and
`node4` and serves every Gateway of class `public-v2` on ports 80 and 443.
`dns.example.com` has one A record per edge node; external-dns points public
hostnames at it.

- `network/public` serves `*.example.com` with the wildcard certificate
  `public-wildcard-tls`. Its port-80 listener accepts only the
  `network/https-redirect` route, so every host redirects to HTTPS.
- Other domains get their own Gateway (class `public-v2`) in the app's
  namespace, with a certificate from the `letsencrypt-dns` ClusterIssuer.
- The edge reaches pods on other nodes from the edge node's IP and pods on its
  own node from inside the pod CIDR. Apps that trust proxy headers list both;
  NetworkPolicies admit the edge with a CiliumNetworkPolicy
  `fromEntities: [host, remote-node]`.

### Private gateway

Traefik behind the ClusterIP `10.111.111.111`, Gateway `network/private`
(class `private`) on `*.example.com`. `internal.example.com` resolves to that
IP. It is reachable only over Tailscale: `node3` advertises the IP to the tailnet,
and Cilium translates it because `tailscale0` is in its `devices`. ArgoCD,
Grafana and Hubble UI are routed here. See [TAILSCALE.md](TAILSCALE.md).

Gateway API CRDs are installed by hand: [components/network/README.md](components/network/README.md).

### API server access

The host firewall (`configure-firewall.yml`) admits the API server, etcd and
kubelet ports only from nodes, pods, loopback and `tailscale0`. Workstations
set the kubeconfig `server` to the control plane's Tailscale address and
`tls-server-name` to `k8s.example.com`
([ansible/playbooks/README.md](ansible/playbooks/README.md#configure-firewallyml)).

## Storage

- `replicated` (default StorageClass): LINSTOR/DRBD via the Piraeus operator,
  2 diskful replicas + diskless tiebreaker, for data that must survive a node
  loss
- `local-path` / `local-fast`: node-local volumes for rebuildable data and hot
  write paths

See [components/storage/README.md](components/storage/README.md) and
[components/local-path/README.md](components/local-path/README.md).

## Operations

| Task | How |
|------|-----|
| Upgrade Kubernetes | `ansible-playbook playbooks/upgrade-cluster.yml -e kubernetes_version=v1.35` |
| Upgrade Cilium | bump `cilium_version`, `ansible-playbook playbooks/install-cilium.yml` |
| Upgrade containerd | bump `containerd_version`, `ansible-playbook playbooks/upgrade-containerd.yml --limit <node>` |
| Kernel and packages | `ansible-playbook playbooks/update-kernel.yml --limit <node>` |
| Add a worker | [BOOTSTRAP.md](BOOTSTRAP.md#add-worker-nodes) |
| Remove a worker | `ansible-playbook playbooks/remove-workers.yml --limit <node>` |
| Deploy an app | add `apps/<name>/root.yaml` and push; the `root` Application applies it |

Playbooks run from `ansible/`. Details: [ansible/playbooks/README.md](ansible/playbooks/README.md).

## Documentation

- [PREREQUISITES.md](PREREQUISITES.md) — servers, SSH, tools, DNS, credentials
- [BOOTSTRAP.md](BOOTSTRAP.md) — building the cluster from bare servers
- [TAILSCALE.md](TAILSCALE.md) — tailnet: node enrollment, ACL, addressing
- [ansible/README.md](ansible/README.md), [ansible/playbooks/README.md](ansible/playbooks/README.md) — playbooks
- [ansible/KUBECONFIG.md](ansible/KUBECONFIG.md) — kubeconfig merging and the admin identity
- [components/network/README.md](components/network/README.md) — network stack, Gateway API CRDs
- [components/storage/README.md](components/storage/README.md) — storage classes, joining nodes, moving volumes
- [components/flow-history/README.md](components/flow-history/README.md) — querying Hubble flows

## License

MIT License

## Author

Abror Aliboyev
