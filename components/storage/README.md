# Storage

Replicated block storage: LINSTOR/DRBD via the [Piraeus operator](https://piraeus.io/docs/). ArgoCD app `storage`, namespace `piraeus-datastore`.

## Choosing a class

| Class | Backing | Use for |
|-------|---------|---------|
| `replicated` (default) | 2 diskful DRBD replicas + automatic diskless tiebreaker, thin files in pool `data` on each node's root fs | Data that must survive a node loss |
| `local-path` | Directory on the node the pod first lands on; the workload pins itself with a nodeSelector | Rebuildable data, hot write paths (SQLite, mail stores) |
| `local-fast` | `local-path` restricted to node5 | Large rebuildable data on node5's disk |

All three are `Retain` and `WaitForFirstConsumer`: deleting a claim leaves the volume, clean it up by hand.

## Joining a node

1. `ansible-playbook -i inventory.ini playbooks/update-kernel.yml --limit <node>` — latest kernel + matching headers, drain, reboot. The satellite's `drbd-module-loader` compiles DRBD 9 against those headers.
2. Add the node to `nodes` in `values.yaml` and push.
3. Check it shows `ONLINE` in `linstor node list` and has pool `data` in `linstor storage-pool list`.

Debian 13 headers link into `/usr/lib/linux-kbuild-*`, so the loader mounts the host `/usr` as an overlay (`templates/10-linstor-cluster.yaml`).

## Moving a volume between classes

For an existing StatefulSet:

1. Pause the app's automated sync in ArgoCD.
2. Scale the workload to 0.
3. Create a claim in the target class, copy the data with a one-off pod mounting both claims, and compare checksums.
4. Re-bind the new PV under the original claim name (delete both claims, clear the new PV's `claimRef`, recreate the original claim with `volumeName` set to it), or point the chart at the new claim via `existingClaim`.
5. Change `storageClass` in the app values, then `kubectl delete sts <name> --cascade=orphan` (volumeClaimTemplates are immutable).
6. Sync the app once explicitly and check the pod mounts the new volume.
7. Re-enable automated sync.

With `Retain`, the old PV stays until deleted by hand; keep it until the app is verified.

## Checking health

```bash
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor node list
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor storage-pool list
kubectl -n piraeus-datastore exec deploy/linstor-controller -- linstor resource list
```

Every resource should be `UpToDate` on two nodes, plus `TieBreaker` or `Diskless` on a third.
