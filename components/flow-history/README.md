# Flow history

Cilium writes each node's flows to `/var/run/cilium/hubble/events.log` (static exporter, field mask in `ansible/cilium/values.yaml`). The Vector DaemonSet tails that file into `hubble.flows` on a single ClickHouse pinned to one node. Parts move to S3 bucket `example-hubble-flows` after `hotDays` and are dropped after `retentionDays` (`values.yaml`). Grafana reads through datasource `ClickHouse-Flows`. The route also puts Hubble UI on the private gateway.

## Setup

`./create-secrets.sh` (AWS credentials in the environment) before the first sync. Pods wait for the secrets.

## Querying

```bash
kubectl -n flow-history exec -it clickhouse-0 -- clickhouse-client -d hubble
```

```sql
-- drops in the last hour by pair
SELECT src_namespace, src_workload, dst_namespace, dst_workload, dst_port, drop_reason, count()
FROM flows WHERE verdict = 'DROPPED' AND time > now() - INTERVAL 1 HOUR
GROUP BY ALL ORDER BY count() DESC LIMIT 20;
```

Empty strings mean the field wasn't set on the flow (no pod: host, world or remote node). `is_reply` is NULL when Cilium couldn't tell.

## Schema changes

`flows.sql` runs on every start with `IF NOT EXISTS`, so it creates a missing table but never changes an existing one. Run the matching `ALTER TABLE hubble.flows …` by hand as well as editing the file.
