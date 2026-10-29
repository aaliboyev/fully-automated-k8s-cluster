# local-path-provisioner

Rancher's [local-path-provisioner](https://github.com/rancher/local-path-provisioner) provides fast, single-node local storage for Kubernetes via dynamically-provisioned hostPath volumes.

## Why it exists alongside `replicated`

The default `replicated` class (see [../storage/README.md](../storage/README.md)) writes every block to two nodes over the network. Rebuildable data (ML model caches, build artefacts, large append-mostly archives) and hot write paths (SQLite, mail stores) don't need that and benefit from direct disk throughput. `local-path` provisions on whichever node the pod lands on, so the workload pins itself; `local-fast` is the same provisioner restricted to node5's 3TB disk.

## Node coverage

Cluster-wide: any node can host a local-path PV at `/opt/local-path-data` (configured via `DEFAULT_PATH_FOR_NON_LISTED_NODES` in the provisioner's ConfigMap). Add a per-node entry to `nodePathMap` only when a particular node has an unusual mount layout.

The Ansible playbook ensures `/opt/local-path-data` exists on every node before the provisioner starts.

## StorageClasses

Names: `local-path` (any node), `local-fast` (node5 only)  
Provisioner: `rancher.io/local-path`  
Reclaim policy: `Retain` (data survives PVC deletion — clean up manually)  
Volume binding: `WaitForFirstConsumer`

## Installation

The chart is installed directly from the [rancher/local-path-provisioner](https://github.com/rancher/local-path-provisioner) GitHub master branch (no third-party Helm repo). The Ansible playbook clones the repo at run time, installs the chart from `deploy/chart/local-path-provisioner/`, and removes the clone when done.

## How to use

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-cache
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-fast
  resources:
    requests:
      storage: 50Gi
```

## Warning

A local-path PV is bound to whichever node the consuming pod first scheduled on; **losing that node means losing the PVC**. Use `local-fast` only for rebuildable data, or pin the consuming workload to a node you treat as durable.
