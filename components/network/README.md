# Network

HAProxy Unified Gateway (public edge), Traefik (private gateway),
cert-manager, external-dns and the Tailscale operator, as Argo apps rendered
from this chart.

## Gateways

`templates/21-gateways.yaml` defines the two shared Gateways, both serving
`*.example.com` with the wildcard certificate `public-wildcard-tls`:

- `public` (class `public-v2`): HAProxy Unified Gateway, a host-network
  DaemonSet on the nodes in the affinity of `values/haproxy-public.yaml`,
  binding 80 and 443. external-dns points its hosts at `publicEdgeHostname`,
  which has one A record per edge node. The port-80 listener has no hostname
  and accepts only routes from this namespace; `https-redirect` sends every
  host to HTTPS.
- `private` (class `private`): Traefik on the ClusterIP `10.111.111.111`,
  reached over Tailscale ([../../TAILSCALE.md](../../TAILSCALE.md#private-gateway)).
  external-dns points its hosts at `internal.example.com`.

Hosts outside `example.com` get a Gateway of class `public-v2` in their own
namespace.

## Gateway API CRDs

Installed by hand from the upstream release, not by any app here: bundle
**v1.6.2, experimental channel** (HAProxy Unified Gateway 1.0.9 watches
TLSRoute `v1alpha2`, which the standard channel doesn't serve).

The bundle also carries the `safe-upgrades` admission policy, which refuses
experimental CRDs over standard ones, so a channel change removes it first:

```sh
url=https://github.com/kubernetes-sigs/gateway-api/releases/download/<version>/experimental-install.yaml
curl -sL "$url" > bundle.yaml
yq 'select(.kind=="CustomResourceDefinition")' bundle.yaml > crds.yaml
yq 'select(.kind!="CustomResourceDefinition")' bundle.yaml > policy.yaml
kubectl delete validatingadmissionpolicybinding,validatingadmissionpolicy safe-upgrades.gateway.networking.k8s.io
kubectl apply --server-side --force-conflicts -f crds.yaml
kubectl apply --server-side -f policy.yaml
```

Server-side apply because the experimental CRDs outgrow the client-side
last-applied annotation. Never delete these CRDs: that deletes every Gateway
and route of that kind.
