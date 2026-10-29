# Ansible Playbooks

## init-cluster.yml

Initializes a fresh Kubernetes cluster from scratch.

**What it does:**
1. Writes `/root/kubeadm-init.yaml` (`cluster_name`, `pod_network_cidr`) and runs `kubeadm init --skip-phases=addon/kube-proxy`: Cilium replaces kube-proxy
2. Sets up kubectl for root user
3. Fetches the admin kubeconfig and merges it into the local `~/.kube/config`

Install the CNI next (`install-cilium.yml`). A different `pod_network_cidr` also needs `ipv4NativeRoutingCIDR` changed in `ansible/cilium/values.yaml`.

**Usage:**
```bash
ansible-playbook playbooks/init-cluster.yml
```

---

## install-cilium.yml

Installs or upgrades Cilium (`cilium_version` in `group_vars/all.yml`) with Helm from the first control plane, using `ansible/cilium/values.yaml`, then waits for the operator and agents. `-e cilium_routing=tunnel` adds `values-tunnel.yaml`: VXLAN between nodes, WireGuard for pod traffic only.

It also installs `cilium-proxy-rpcheck.service` on every node. tailscaled sets `src_valid_mark=1`, so the source check of a packet Cilium marks for its L7/DNS proxy sees a local source and drops it; the unit's `ip rule` sends those checks to the main table. It depends on Cilium's mark layout, so check it after Cilium upgrades.

There is no Argo app for the CNI; this playbook is the only way it changes.

**Usage:**
```bash
ansible-playbook -i inventory.ini playbooks/install-cilium.yml
ansible-playbook -i inventory.ini playbooks/install-cilium.yml -e cilium_routing=tunnel
```

---

## update-kernel.yml

Installs `linux-image-amd64` and `linux-headers-amd64`; if the newest kernel isn't running, drains, reboots, waits Ready and uncordons. One node at a time. Run it before a node joins replicated storage: the LINSTOR satellite builds DRBD against the running kernel's headers.

Before draining it refuses to continue if any volume with a disk on the node has no other `UpToDate` replica, so a reboot never removes the last good copy. After uncordon it waits for the node's satellite to be `ONLINE`, the node's replicas to resync (`files/check-replicas.py`), Harbor's deployments and statefulsets to be available (nodes can't pull images while Harbor is down) and each URL in `node_health_urls` (`group_vars/all.yml`) to return 200. A gate that times out stops the run before the next node.

**Usage:**
With `-e upgrade_packages=true` it first runs `apt upgrade` (held packages such as `containerd.io` and `kubelet` stay put; changed config files keep the local version) and reboots when anything changed, even if the kernel was already current.

```bash
ansible-playbook playbooks/update-kernel.yml --limit node3
ansible-playbook playbooks/update-kernel.yml --limit node3 -e upgrade_packages=true
```

---

## configure-sysctl.yml

Writes `/etc/sysctl.d/90-k8s-node.conf` and applies it live: `fs.inotify.max_user_instances=8192` and `fs.inotify.max_user_watches=524288`. The kernel default of 128 instances per user is shared by kubelet, every containerd shim and the LINSTOR satellite; after a reboot the satellite can lose the race for one, crash-loop, and leave the node's replicated volumes unattachable. Run it on every node, including new ones before they join replicated storage.

It also raises `net.netfilter.nf_conntrack_max` and the hash table (`nf_conntrack_buckets`, and `hashsize` at module load) from 262,144 to 1,048,576, and loads `nf_conntrack` at boot so the keys exist when systemd-sysctl runs. A full table drops new connections on the whole node. Connection storms fill it: each new connection's DNS lookup adds a UDP entry on the node running CoreDNS. At about 320 bytes per entry, a full table is ~320 MiB.

**Usage:**
```bash
ansible-playbook -i inventory.ini playbooks/configure-sysctl.yml
```

---

## configure-firewall.yml

Loads nftables table `inet node_firewall` from `/etc/node-firewall.nft` (unit `node-firewall.service`). Ports in `firewall_guarded_tcp_ports` / `firewall_guarded_udp_ports` (`group_vars/all.yml`) accept only node addresses, the pod CIDR, loopback and `tailscale0`; everything else, including IPv6, is dropped. Public ports (SSH, ingress, mail hostPorts, WireGuard, Tailscale) aren't listed and stay open. Workstations reach the API server over Tailscale: kubeconfig `server` set to the control plane's Tailscale address with `tls-server-name` set to the API endpoint name.

When the rules change or the table isn't loaded, it arms a 5-minute `systemd-run` timer that deletes the table, loads the rules, and cancels the timer only after the node is Ready, its Cilium agent is ready, the node reaches the API server and `node_health_urls` answer. One node at a time. Debian's `nftables.service` stays disabled: its config starts with `flush ruleset`, which would wipe Cilium's and Tailscale's tables.

Every node's address goes into each node's trusted set, so after adding a node run it on all nodes.

**Usage:**
```bash
ansible-playbook -i inventory.ini playbooks/configure-firewall.yml --limit node1
```

---

## configure-registry-mirrors.yml

Makes containerd pull `ghcr.io` and `docker.io` images through Harbor's proxy caches (`ghcr-proxy`, `docker-proxy`) and fall back to the upstream registry when Harbor is unreachable. Manifests keep plain `ghcr.io/...` / `docker.io/...` names. Harbor's projects are private, so the hosts files (including one for `harbor.example.com` itself) carry the cluster-pull robot's credentials, read from secret `harbor/cluster-pull-robot` at run time. Pods need no `imagePullSecrets`; while Harbor is down, private images can't be pulled (public ones fall back to upstream).

**Usage:**
```bash
ansible-playbook -i inventory.ini playbooks/configure-registry-mirrors.yml --limit node1
```

---

## join-workers.yml

Joins worker nodes to an existing cluster.

**Prerequisites:**
- Control plane must be initialized (run `init-cluster.yml` first)

**Usage:**
```bash
ansible-playbook playbooks/join-workers.yml
```

---

## promote-controlplane.yml

Adds additional control plane nodes for high availability (HA) setup.

**Prerequisites:**
- Primary control plane must be initialized
- Additional nodes must be in the `control_plane` group in inventory

**Usage:**
```bash
ansible-playbook playbooks/promote-controlplane.yml
```

---

## upgrade-cluster.yml

Upgrades Kubernetes cluster to a target version with proper rolling upgrade procedure.

**What it does:**
1. Upgrades control plane nodes one at a time (serial: 1)
   - Upgrades kubeadm
   - Runs `kubeadm upgrade apply` (first CP) or `kubeadm upgrade node` (additional CPs), with `--skip-phases=addon/kube-proxy` so kubeadm doesn't bring kube-proxy back
   - Drains the node
   - Upgrades kubelet and kubectl
   - Restarts kubelet
   - Uncordons the node
2. Upgrades worker nodes one at a time (serial: 1)
   - Drains the node
   - Upgrades kubeadm, kubelet, kubectl
   - Runs `kubeadm upgrade node --skip-phases=addon/kube-proxy`
   - Restarts kubelet
   - Uncordons the node
3. Verifies all nodes are Ready after upgrade

**Prerequisites:**
- Cluster must be running
- Target version must be set in `group_vars/all.yml` or passed as extra var

**Usage:**
```bash
# Upgrade to version in group_vars/all.yml
ansible-playbook playbooks/upgrade-cluster.yml

# Upgrade to specific version
ansible-playbook playbooks/upgrade-cluster.yml -e "kubernetes_version=v1.35.0"
```

**Notes:**
- Nodes already at target version are skipped
- Upgrades are done one node at a time to maintain cluster availability
- The playbook holds/unholds apt packages to prevent accidental upgrades
- Cilium is upgraded separately with `install-cilium.yml`
