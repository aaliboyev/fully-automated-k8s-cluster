from grammar import (CRIT, WARN, Board, column, gauge, node_colors, stat, state_timeline, states, steps, table,
                     timeseries)
from home import DISK

POOL = 'storage_pool="data"'
USED = "kubelet_volume_stats_used_bytes"
CAP = "kubelet_volume_stats_capacity_bytes"


def build():
    b = Board("storage", "Storage",
              "Will a disk fill, and is every replicated volume really holding two copies?")

    b.put(stat("Volumes out of sync",
               'count(drbd_device_state{drbd_device_state!~"UpToDate|Diskless"} == 1) or vector(0)',
               thresholds=steps(crit=1), sparkline=False,
               desc="DRBD devices not UpToDate. A replicated volume keeps working on one copy, so "
                    "this is the only place a lost replica shows."), 4, 5)
    b.put(stat("Broken links",
               'count(drbd_connection_state{drbd_connection_state!="Connected"} == 1) or vector(0)',
               thresholds=steps(crit=1), sparkline=False,
               desc="DRBD peer connections not Connected."), 4, 5)
    b.put(stat("Nodes offline", 'count(linstor_node_state != 2) or vector(0)',
               thresholds=steps(crit=1), sparkline=False,
               desc="LINSTOR satellites not ONLINE."), 4, 5)
    b.put(gauge("LINSTOR pool fill",
                [(f"sort_by_label(100 * (1 - linstor_storage_pool_capacity_free_bytes{{{POOL}}}"
                  f' / linstor_storage_pool_capacity_total_bytes{{{POOL}}}), "node")', "{{node}}")],
                thresholds=DISK, desc="The thin pool replicated volumes live in, per node."), 12, 5)

    days_left = (f"(max by (namespace, persistentvolumeclaim) ({CAP} - {USED}))"
                 f" / (max by (namespace, persistentvolumeclaim) (deriv({USED}[24h])) > 0) / 86400")
    b.put(table("Volumes",
                [(f"max by (namespace, persistentvolumeclaim) ({USED})", "Used"),
                 (f"max by (namespace, persistentvolumeclaim) ({CAP})", "Size"),
                 (f"100 * max by (namespace, persistentvolumeclaim) ({USED} / {CAP})", "Fill"),
                 (days_left, "Days until full")],
                [column("namespace", rename="Namespace", width=170),
                 column("persistentvolumeclaim", rename="Volume"),
                 column("Used", "bytes", decimals=1, width=110),
                 column("Size", "bytes", decimals=0, width=100),
                 column("Fill", "percent", DISK, "gauge", decimals=0, gauge_max=100),
                 column("Days until full", "d", {"mode": "absolute", "steps": [
                     {"color": CRIT, "value": None}, {"color": WARN, "value": 3},
                     {"color": "text", "value": 14}]}, "color-text", decimals=0, width=150)],
                keep=["namespace", "persistentvolumeclaim", "Used", "Size", "Fill", "Days until full"],
                sort=("Fill", True),
                desc="Replicated volumes. Days until full extrapolates the last day of growth; "
                     "a dash means the volume is not growing."), 24, 9)

    root = 'mountpoint="/"'
    b.put(timeseries("Node disk fill",
                     [(f'sort_by_label(100 * (1 - node_filesystem_avail_bytes{{{root}}} / node_filesystem_size_bytes{{{root}}}), "node")',
                       "{{node}}")],
                     "percent", thresholds=DISK, maximum=100,
                     overrides=node_colors(),
                     desc="Root disk per node; local-path volumes, images and logs all live here."),
          12, 8)
    b.put(timeseries("Days until a node disk fills",
                     [(f'(node_filesystem_avail_bytes{{{root}}} / (-deriv(node_filesystem_avail_bytes{{{root}}}[24h]) > 0) / 86400) < 365',
                       "{{node}}")],
                     "d", thresholds={"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                     overrides=node_colors(),
                     desc="Free space divided by the last day of growth, shown under a year. Missing "
                          "lines are nodes whose disk is not filling."), 12, 8)

    b.put(timeseries("Replication traffic",
                     [("sum by (node) (rate(drbd_peerdevice_sent_bytes[$__rate_interval]))", "{{node}}")],
                     "Bps", overrides=node_colors(),
                     desc="Bytes each node sends to its DRBD peers: every write to a replicated volume, "
                          "plus resyncs."), 12, 8)
    b.put(state_timeline("Volumes degraded",
                         [('max by (name) (drbd_device_state{drbd_device_state!~"UpToDate|Diskless"} == 1)'
                           ' or label_replace(vector(0), "name", "all volumes", "", "")',
                           "{{name}}")],
                         *states((1, "not in sync", CRIT)),
                         desc="When each DRBD volume was not UpToDate on some node. Empty is good."),
          12, 8)
    return b
