# Tailscale — cluster access mesh

Tailscale carries host and admin access only, never pod traffic between
nodes. A CNI that takes `tailscale0` as its node interface moves the pod
underlay into userspace WireGuard, and magicsock's periodic endpoint
re-discovery then stalls node networking for seconds at a time. Cilium takes
node addresses from InternalIP (`eth0`) and encrypts node-to-node traffic with
its own kernel WireGuard; `tailscale0` is in its `devices` only so service IPs
reached from the tailnet get translated (`ansible/cilium/values.yaml`). Don't
make `tailscale0` a node address or routing device.

Two planes, three owners:

- **Ansible owns hosts** — `ansible/playbooks/install-tailscale.yml` installs
  `tailscaled` on every node in the `k8s` inventory group and enrolls it with
  a tagged pre-auth key. Re-runs are no-ops on enrolled nodes.
- **ArgoCD owns the cluster** — the Tailscale Kubernetes operator
  (`network-tailscale-operator` app, ns `tailscale`). The `operator-oauth`
  secret is created out-of-band (see
  `components/network/values/tailscale-operator.yaml`). The API-server proxy
  is enabled: kubectl over the tailnet with tailnet identity, which needs the
  impersonation grant in `tailscale/acl.hujson`. Services are exposed with the
  `tailscale.com/expose` annotation; no Connectors or ProxyGroups.
  Every proxy uses ProxyClass `datacenter`, which turns off the portmapper:
  its UPnP/NAT-PMP probes find no router in a datacenter and only show up as
  Cilium drops.
- **Git owns the ACL** — `tailscale/acl.hujson` is the tailnet policy source
  of truth. Paste it into the admin console ACL editor to apply.

## Private gateway

The private Traefik listens on the ClusterIP `10.111.111.111`
(`components/network/values/traefik-private.yaml`), and
`internal.example.com` resolves to it. `node3` advertises `10.111.111.111/32` to
the tailnet as a subnet route (`tailscale set --advertise-routes=...` on the
node, approved in the admin console); tailnet clients reach ArgoCD, Grafana
and the other private hosts through it. Clients must accept subnet routes
(`tailscale set --accept-routes` on Linux).

## Addressing

Devices are reached only via our own DNS, never `.ts.net`:

    <host>.net.example.com  →  tailnet 100.x IP   (A records, Cloudflare)

MagicDNS is not used for addressing; all enrollments pass `--accept-dns=false`
so tailscaled never touches resolv.conf.

Nodes are tagged `tag:node`; members' own devices stay untagged. Device names
are forced to inventory names so DNS maps 1:1.

## Enrolling a new node

1. Admin console → Settings → Keys → generate a reusable key tagged `tag:node`
2. Add the host to `ansible/inventory.ini`
3. `ansible-playbook -i inventory.ini playbooks/install-tailscale.yml \
     -e tailscale_authkey=tskey-auth-... --limit <host>`
4. Add `<host>.net.example.com` A record → its tailnet IP
5. Throw the key away (expiry is the cleanup; nothing running depends on it)

Tagged devices never expire their node keys. Personal devices: disable key
expiry per-device in the admin console (Machines → … → Disable key expiry).

## Exit nodes

Any node can offer full-tunnel egress: `tailscale set --advertise-exit-node`
on the node, approve in console, then per-client
`tailscale set --exit-node=<host>.net.example.com` (empty value to stop).

## Break-glass

SSH stays open on every node's public address. The API server is reachable
only from nodes and the tailnet (`configure-firewall.yml`); with the tailnet
down, SSH to the control plane and run kubectl there with
`KUBECONFIG=/etc/kubernetes/admin.conf`.
