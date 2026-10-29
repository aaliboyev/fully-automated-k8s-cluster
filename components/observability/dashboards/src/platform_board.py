from grammar import (CRIT, MUTED, SERIES, WARN, Board, bars, column, fixed, gauge, stat, steps, table,
                     timeseries)

BACKUP = 'cronjob=~"backup-.*"'
# Age as a share of the gap BackupStale allows: 36 h for daily jobs, 8 days for the weekly export.
BACKUP_AGE = ('100 * (time() - kube_cronjob_status_last_successful_time{cronjob=~"backup-.*",cronjob!~".*-export"}) / (36 * 3600)'
              ' or 100 * (time() - kube_cronjob_status_last_successful_time{cronjob=~"backup-.*-export"}) / (8 * 86400)')


def build():
    b = Board("platform", "Platform",
              "The machinery under the apps: scheduling room, the control plane, storage "
              "redundancy, backups, deploys and the monitoring itself.")

    b.put(stat("Targets down", "count(up == 0) or vector(0)", thresholds=steps(crit=1),
               sparkline=False, desc="Scrape targets that did not answer. Grey dashboards are only "
                                     "reassuring when this is zero."), 4, 5)
    b.put(stat("Argo apps unhealthy", 'count(argocd_app_info{health_status!="Healthy"}) or vector(0)',
               thresholds=steps(1, 3), sparkline=False,
               desc="Applications Progressing, Degraded or Missing."), 4, 5)
    b.put(stat("Argo apps out of sync", 'count(argocd_app_info{sync_status!="Synced"}) or vector(0)',
               thresholds=steps(1), sparkline=False,
               desc="Applications whose live state differs from git. The manual-sync parents sit "
                    "here until synced by hand."), 4, 5)
    b.put(stat("Stale backups",
               f"count(({BACKUP_AGE}) >= 100) or vector(0)",
               thresholds=steps(crit=1), sparkline=False,
               desc="Backup jobs past their allowed gap, the BackupStale alert line."), 4, 5)
    b.put(stat("etcd leader changes, 24h", "sum(increase(etcd_server_leader_changes_seen_total[24h])) or vector(0)",
               thresholds=steps(1, 3), decimals=0, sparkline=False,
               desc="A single control plane should never change leader; any change is a restart."), 4, 5)
    b.put(stat("etcd database", "max(etcd_mvcc_db_total_size_in_bytes)", "bytes", decimals=0,
               thresholds=steps(4 * 2**30, 7 * 2**30),
               desc="etcd refuses writes at its 8 GiB quota."), 4, 5)

    b.row("Room to schedule")
    alloc = 'kube_node_status_allocatable{{resource="{r}"}}'
    req = ('sum by (node) (kube_pod_container_resource_requests{{resource="{r}"}}'
           ' * on (namespace, pod) group_left () (kube_pod_status_phase{{phase=~"Running|Pending"}} == 1))')
    for r, title in (("cpu", "CPU requested"), ("memory", "Memory requested")):
        b.put(gauge(title, [(f'sort_by_label(100 * {req.format(r=r)} / sum by (node) ({alloc.format(r=r)}), "node")',
                             "{{node}}")],
                    thresholds=steps(80, 95),
                    desc=f"{title.split()[0]} promised to pods against what each node can give. A node "
                         "at 100% refuses new pods however idle it looks."), 12, 6)

    b.row("Backups")
    b.put(bars("Backup age, share of allowed gap",
               [(f"sort_desc({BACKUP_AGE})", "{{namespace}} / {{cronjob}}")],
               "percent", thresholds=steps(75, 100), maximum=100, decimals=0,
               desc="How far each backup is into the gap BackupStale allows: 36 hours for daily "
                    "jobs, 8 days for weekly ones. At 100% the alert fires."), 24, 10)

    b.row("Control plane")
    b.put(timeseries("etcd disk sync, p99",
                     [("histogram_quantile(0.99, sum by (le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[$__rate_interval])))",
                       "fsync p99")],
                     "s", thresholds=steps(0.01, 0.025),
                     desc="How long etcd waits for its log to reach disk. Past 10 ms the whole API slows."),
          8, 8)
    classes = {"2xx": SERIES[0], "4xx": SERIES[3], "5xx": CRIT}
    b.put(timeseries("API server requests",
                     [('sum by (class) (label_replace(rate(apiserver_request_total{code=~"[245].."}[$__rate_interval]),'
                       ' "class", "${1}xx", "code", "([245]).."))', "{{class}}")],
                     "reqps", stack=True, overrides=fixed(classes),
                     desc="Every call to the Kubernetes API, by status class."), 8, 8)
    b.put(timeseries("API server latency, p99",
                     [('histogram_quantile(0.99, sum by (le, verb) (rate(apiserver_request_duration_seconds_bucket{verb!~"WATCH|CONNECT"}[$__rate_interval])))',
                       "{{verb}}")],
                     "s", thresholds=steps(1, 3), legend="table",
                     desc="Slowest one percent of API calls per verb; watches excluded."), 8, 8)

    b.row("Deploys")
    b.put(table("Argo applications",
                [("argocd_app_info", "info")],
                [column("name", rename="Application"),
                 column("dest_namespace", rename="Namespace", width=180),
                 column("sync_status", rename="Sync", width=120,
                        colors={"Synced": MUTED, "OutOfSync": WARN, "Unknown": WARN}),
                 column("health_status", rename="Health", width=130,
                        colors={"Healthy": MUTED, "Progressing": WARN, "Degraded": CRIT,
                                "Missing": CRIT, "Suspended": WARN}),
                 column("autosync_enabled", rename="Auto sync", width=110)],
                keep=["name", "dest_namespace", "sync_status", "health_status", "autosync_enabled"],
                sort=("health_status", False),
                desc="Every Argo CD application with its sync and health."), 12, 12)
    b.put(timeseries("Syncs",
                     [("sum by (name) (increase(argocd_app_sync_total[$__interval])) > 0", "{{name}}")],
                     "short", legend="table",
                     desc="Sync operations per application: when each one last changed."), 12, 12)
    b.panels[-1]["fieldConfig"]["defaults"]["custom"].update({"drawStyle": "bars", "fillOpacity": 85,
                                                             "lineWidth": 0})
    b.panels[-1]["interval"] = "10m"

    b.row("Monitoring")
    b.put(timeseries("Samples stored",
                     [("sum(rate(vm_rows_inserted_total[$__rate_interval]))", "metrics"),
                      ("sum(rate(vl_rows_ingested_total[$__rate_interval]))", "log lines")],
                     "short", overrides=fixed({"metrics": SERIES[0], "log lines": SERIES[1]}),
                     desc="Rows per second written into VictoriaMetrics and VictoriaLogs."), 8, 8)
    b.put(stat("Logs on disk", "sum(vl_data_size_bytes)", "bytes", decimals=1,
               thresholds=steps(40 * 2**30, 48 * 2**30),
               desc="Compressed log storage. At the 50 GiB cap the oldest days are dropped."), 8, 8)
    b.put(table("Targets down",
                [("up == 0", "up")],
                [column("job", rename="Job"), column("instance", rename="Instance", width=220),
                 column("namespace", rename="Namespace", width=160)],
                keep=["job", "instance", "namespace"],
                desc="Every scrape target not answering right now."), 8, 8)
    return b
