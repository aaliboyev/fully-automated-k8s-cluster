from grammar import (LOG_ERRORS, SERIES, Board, column, fixed, gauge, logs, query_var, steps,
                     table, timeseries)
from home import CPU, DISK, MEM, PRESSURE, RES, nodes, restarts

N = 'node="$node"'


def build():
    b = Board("node", "Node", "One machine: how busy it is, what it waits on, and what runs on it.",
              variables=[query_var("node", "Node", "label_values(node_uname_info, node)")])

    b.put(nodes(), 24, 7)

    b.row("$node")
    for title, expr, th in (
        ("CPU", f'100 * (1 - avg(rate(node_cpu_seconds_total{{{N},mode="idle"}}[5m])))', CPU),
        ("Memory", f"100 * (1 - node_memory_MemAvailable_bytes{{{N}}} / node_memory_MemTotal_bytes{{{N}}})", MEM),
        ("Disk", f'100 * (1 - node_filesystem_avail_bytes{{{N},mountpoint="/"}}'
                 f' / node_filesystem_size_bytes{{{N},mountpoint="/"}})', DISK),
        ("Pressure", f'100 * max(rate({{__name__=~"node_pressure_(cpu|memory|io)_waiting_seconds_total",{N}}}[5m]))',
         PRESSURE),
    ):
        b.put(gauge(title, [(expr, title)], thresholds=th, maximum=50 if th is PRESSURE else 100,
                    desc=f"{title} on $node now; marks on the rim are warning and critical."), 6, 5)

    modes = {"user": SERIES[0], "system": SERIES[1], "iowait": SERIES[3], "steal": SERIES[4],
             "softirq": SERIES[2]}
    b.put(timeseries("CPU by mode",
                     [(f'100 * sum by (mode) (rate(node_cpu_seconds_total{{{N},mode=~"user|system|iowait|steal|softirq"}}[$__rate_interval]))'
                       f' / scalar(count(node_cpu_seconds_total{{{N},mode="idle"}}))', "{{mode}}")],
                     "percent", stack=True, overrides=fixed(modes), maximum=100,
                     desc="Where the CPU time goes. iowait is time stuck on disk; steal is time the "
                          "hypervisor gave to another tenant."), 12, 8)
    mem = {"used": SERIES[0], "page cache": SERIES[2], "free": "#383835"}
    b.put(timeseries("Memory",
                     [(f"node_memory_MemTotal_bytes{{{N}}} - node_memory_MemAvailable_bytes{{{N}}}", "used"),
                      (f"node_memory_Cached_bytes{{{N}}} + node_memory_Buffers_bytes{{{N}}}", "page cache"),
                      (f"node_memory_MemFree_bytes{{{N}}}", "free")],
                     "bytes", stack=True, overrides=fixed(mem),
                     desc="Used is memory no one can reclaim; page cache gives itself back under pressure."),
          12, 8)

    waits = {"cpu": SERIES[0], "memory": SERIES[1], "io": SERIES[3]}
    b.put(timeseries("Pressure stalls",
                     [(f'100 * rate(node_pressure_cpu_waiting_seconds_total{{{N}}}[$__rate_interval])', "cpu"),
                      (f'100 * rate(node_pressure_memory_waiting_seconds_total{{{N}}}[$__rate_interval])', "memory"),
                      (f'100 * rate(node_pressure_io_waiting_seconds_total{{{N}}}[$__rate_interval])', "io")],
                     "percent", thresholds=PRESSURE, overrides=fixed(waits),
                     desc="Share of time at least one task waited. The first sign a node is too small."),
          8, 8)
    b.put(timeseries("Disk throughput",
                     [(f'sum(rate(node_disk_read_bytes_total{{{N},device!~"dm-.*|loop.*"}}[$__rate_interval]))', "read"),
                      (f'-sum(rate(node_disk_written_bytes_total{{{N},device!~"dm-.*|loop.*"}}[$__rate_interval]))', "write")],
                     "Bps", minimum=None, overrides=fixed({"read": SERIES[0], "write": SERIES[1]}),
                     desc="Reads above the line, writes below."), 8, 8)
    b.put(timeseries("Network",
                     [(f'sum(rate(node_network_receive_bytes_total{{{N},device!~"lo|cali.*|vxlan.*|wireguard.*|bpf.*"}}[$__rate_interval]))', "in"),
                      (f'-sum(rate(node_network_transmit_bytes_total{{{N},device!~"lo|cali.*|vxlan.*|wireguard.*|bpf.*"}}[$__rate_interval]))', "out")],
                     "Bps", minimum=None, overrides=fixed({"in": SERIES[0], "out": SERIES[1]}),
                     desc="Physical interface traffic: in above the line, out below."), 8, 8)

    on_node = f'* on (namespace, pod) group_left () (kube_pod_info{{{N}}})'
    b.put(table("Pods on $node",
                [(f'sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{{{RES},container!=""}}[5m]) {on_node})', "CPU"),
                 (f'sum by (namespace, pod) (container_memory_working_set_bytes{{{RES},container!=""}} {on_node})', "Memory"),
                 (f'100 * sum by (namespace, pod) (container_memory_working_set_bytes{{{RES},container!=""}} {on_node})'
                  ' / sum by (namespace, pod) (kube_pod_container_resource_limits{resource="memory"})', "Memory of limit"),
                 (f'{restarts("namespace, pod")} {on_node}', "Restarts 1h")],
                [column("namespace", rename="Namespace", width=170,
                        link=("Workload", "/d/workload/workload?var-namespace=${__value.raw}")),
                 column("pod", rename="Pod"),
                 column("CPU", "cores", display="gauge", decimals=2),
                 column("Memory", "bytes", decimals=1, width=110),
                 column("Memory of limit", "percent", MEM, "gauge", decimals=0, gauge_max=100),
                 column("Restarts 1h", "short", steps(1, 5), "color-text", decimals=0, width=110)],
                keep=["namespace", "pod", "CPU", "Memory", "Memory of limit", "Restarts 1h"],
                sort=("CPU", True), desc="Everything scheduled on this node, busiest first."), 24, 10)

    b.put(logs("Errors on $node",
               f'kubernetes.pod_node_name:"$node" {LOG_ERRORS}',
               desc="Error-level log lines from every pod on this node, newest first."), 24, 10)
    return b
