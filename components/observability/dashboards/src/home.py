from grammar import (CRIT, MUTED, SERIES, VL, WARN, Board, column, donut, fixed, gauge,
                     histogram_bars, log_table, state_timeline, states, steps, table, timeseries,
                     vl)

# Thresholds shared with the drill-downs and, later, the alert rules.
CPU = steps(70, 90)
MEM = steps(80, 92)
DISK = steps(80, 90)
PRESSURE = steps(10, 25)
ERRORS = steps(5, 20)

RES = 'metrics_path="/metrics/resource"'

# The public HAProxy edge. Listener frontends only; stats, healthz and
# health_check_socket are HUG's own.
EDGE_JOB = 'job="network/haproxy-public"'
EDGE_FE = f'{EDGE_JOB},proxy=~"hug_.+"'
EDGE_LOGS = ('_stream:{kubernetes.pod_namespace="network",kubernetes.container_name="hug"}'
             " kubernetes.pod_name:haproxy-public-*")
EDGE_ACCESS = f"{EDGE_LOGS} status:* -frontend:stats"
EDGE_LINK = {"title": "HAProxy edge", "url": "/d/edge/haproxy-edge"}
# Status classes only: "other" is a non-standard code, not a class.
EDGE_RESPONSES = f'haproxy_frontend_http_responses_total{{{EDGE_FE},code=~"[1-5]xx"}}'


def edge_linked(panel):
    """Public-edge summary panels link to the edge board for the detail."""
    return dict(panel, links=[EDGE_LINK])


def restarts(by, window="1h", match=""):
    """Container restarts in the window. increase() would count a series that
    appears mid-window (e.g. after kube-state-metrics restarts) from zero."""
    inner = f"max by ({by}, container) (kube_pod_container_status_restarts_total{{{match}}})"
    return (f"sum by ({by}) (max_over_time({inner}[{window}:1m]) - min_over_time({inner}[{window}:1m]))")

# Deployment, Job and DaemonSet pods end in -<hash>-<5 chars>, StatefulSet pods
# in -<ordinal>; anything else (static pods) keeps its name.
WORKLOAD = '"workload", "$1$2$3", "pod", "(.+?)(?:-[0-9a-f]{6,10})?-[0-9a-z]{5}|(.+)-[0-9]+|(.+)"'


def by_workload(expr):
    return f"sum by (namespace, workload) (label_replace({expr}, {WORKLOAD}))"


def nodes():
    q = [
        ('100 * (1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m])))', "CPU"),
        ("100 * (1 - max by (node) (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
         "Memory"),
        ('100 * (1 - max by (node) (node_filesystem_avail_bytes{mountpoint="/"}'
         ' / node_filesystem_size_bytes{mountpoint="/"}))', "Disk"),
        ('100 * max by (node) (rate({__name__=~"node_pressure_(cpu|memory|io)_waiting_seconds_total"}[5m]))',
         "Pressure"),
        ('count by (node) (kube_pod_info{node!=""} * on (namespace, pod) group_left ()'
         ' (kube_pod_status_phase{phase="Running"} == 1))', "Pods"),
        ('max by (node) (node_load15) / count by (node) (node_cpu_seconds_total{mode="idle"})',
         "Load per core"),
    ]
    cols = [
        column("node", rename="Node", width=90, link=("Node", "/d/node/node?var-node=${__value.raw}")),
        column("CPU", "percent", CPU, "gauge", decimals=0, gauge_max=100),
        column("Memory", "percent", MEM, "gauge", decimals=0, gauge_max=100),
        column("Disk", "percent", DISK, "gauge", decimals=0, gauge_max=100),
        column("Pressure", "percent", PRESSURE, "color-text", decimals=1, width=110),
        column("Pods", "short", width=80),
        column("Load per core", "short", steps(1, 2), "color-text", decimals=2, width=130),
    ]
    return table("Nodes", q, cols, keep=["node", "CPU", "Memory", "Disk", "Pressure", "Pods",
                                          "Load per core"], sort=("node", False),
                 desc="Now, per node. Pressure is the share of time tasks waited on CPU, memory or "
                      "IO, the worst of the three. Click a node for its drill-down.")


HOSTS = ('limitk(1, label_join(gateway_httproute_hostname_info, "route", "-", "namespace", "httproute"))'
         " by (route)")


def with_host(expr):
    """Traefik's route label joined to the HTTPRoute's name and first hostname."""
    return f"({expr}) * on (route) group_left (namespace, httproute, hostname) {HOSTS}"


def traffic():
    total = "sum by (route) (rate(traefik_service_requests_total[5m]))"
    zero = f"or on (route) (0 * {total})"

    def share(codes):
        return (f'100 * sum by (route) (rate(traefik_service_requests_total{{code=~"{codes}"}}[5m]))'
                f" / {total} {zero}")

    q = [
        (with_host(total), "Req/s"),
        (with_host(f"100 * {total} / scalar(sum(rate(traefik_service_requests_total[5m])))"), "Share"),
        (with_host(share("4..")), "4xx"),
        (with_host(share("5..")), "5xx"),
        (with_host("histogram_quantile(0.95, sum by (le, route)"
                   " (rate(traefik_service_request_duration_seconds_bucket[5m])))"), "p95"),
    ]
    cols = [
        column("httproute", rename="Service", width=200,
               link=("Private gateway", "/d/private-gateway/private-gateway?var-route=${__data.fields.route}")),
        column("hostname", rename="Domain"),
        column("Req/s", "reqps", decimals=2, width=110),
        column("Share", "percent", display="gauge", decimals=0, gauge_max=100),
        column("4xx", "percent", steps(25, 75), "color-text", decimals=0, width=80),
        column("5xx", "percent", steps(1, 5), "color-text", decimals=1, width=80),
        column("p95", "s", steps(1, 3), "color-text", decimals=2, width=100),
    ]
    return table("Private services: traffic, last 5 minutes", q, cols,
                 keep=["httproute", "hostname", "Req/s", "Share", "4xx", "5xx", "p95"],
                 sort=("Req/s", True),
                 desc="Every HTTPRoute behind the private Traefik gateway, with its first hostname. "
                      "4xx and 5xx are the share of that service's responses. Public routes are "
                      "on the HAProxy edge board.")


RUNNING = ' * on (namespace, pod) group_left () (kube_pod_status_phase{phase="Running"} == 1)'


def limit(resource):
    return by_workload(f'kube_pod_container_resource_limits{{resource="{resource}"}}{RUNNING}')


def resources():
    cpu = by_workload(f'rate(container_cpu_usage_seconds_total{{{RES},container!=""}}[5m])')
    mem = by_workload(f'container_memory_working_set_bytes{{{RES},container!=""}}')
    pvc = ("kube_pod_spec_volumes_persistentvolumeclaims_info"
           " * on (namespace, persistentvolumeclaim) group_left ()"
           " max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_{}_bytes)")
    q = [
        (cpu, "CPU"),
        (f"100 * {cpu} / {limit('cpu')}", "CPU of limit"),
        (mem, "Memory"),
        (f"100 * {mem} / {limit('memory')}", "Memory of limit"),
        (by_workload(pvc.format("used")), "Disk"),
        (f"100 * {by_workload(pvc.format('used'))} / {by_workload(pvc.format('capacity'))}",
         "Disk of volume"),
    ]
    cols = [
        column("namespace", rename="Namespace", width=150,
               link=("Workload", "/d/workload/workload?var-namespace=${__value.raw}")),
        column("workload", rename="Workload", width=300),
        column("CPU", "cores", decimals=2, width=100),
        column("CPU of limit", "percent", CPU, "gauge", decimals=0, gauge_max=100),
        column("Memory", "bytes", decimals=1, width=100),
        column("Memory of limit", "percent", MEM, "gauge", decimals=0, gauge_max=100),
        column("Disk", "bytes", decimals=1, width=100),
        column("Disk of volume", "percent", DISK, "gauge", decimals=0, gauge_max=100),
    ]
    return table("Services: resources", q, cols,
                 keep=["namespace", "workload", "CPU", "CPU of limit", "Memory", "Memory of limit",
                       "Disk", "Disk of volume"], sort=("Memory", True),
                 desc="Every workload, heaviest memory first. Bars are usage against the workload's "
                      "own limit (or volume size); no bar means no limit. Memory includes page "
                      "cache, which the kernel reclaims under pressure. Disk covers replicated "
                      "volumes only: local-path volumes report no usage.")


def clients():
    expr = (f"_time:15m {EDGE_ACCESS} | stats by (client_ip) count() requests,"
            " count() if (status:>=400) failed, count_uniq(path) paths,"
            " count_uniq(host) hosts | sort by (requests desc) | limit 15")
    cols = [
        column("client_ip", rename="Client"),
        column("requests", rename="Requests", display="gauge", decimals=0),
        column("failed", rename="Failed", thresholds=steps(20, 100), display="color-text", width=90),
        column("paths", rename="Paths", width=80),
        column("hosts", rename="Hosts", width=80),
    ]
    return edge_linked(log_table(
        "Top clients, last 15 minutes", expr, cols,
        keep=["client_ip", "requests", "failed", "paths", "hosts"],
        numeric=["requests", "failed", "paths", "hosts"], sort=("requests", True),
        desc="Public edge only, from HAProxy access logs. One client with many failed requests "
             "over many paths is a scanner."))


def paths():
    expr = (f"_time:15m {EDGE_ACCESS} | stats by (path) count() requests,"
            " count_uniq(client_ip) clients, count() if (status:>=400) failed"
            " | sort by (requests desc) | limit 15")
    cols = [
        column("path", rename="Path"),
        column("requests", rename="Requests", display="gauge", decimals=0),
        column("clients", rename="Clients", width=80),
        column("failed", rename="Failed", width=80),
    ]
    return edge_linked(log_table(
        "Most hit paths, last 15 minutes", expr, cols,
        keep=["path", "requests", "clients", "failed"],
        numeric=["requests", "clients", "failed"], sort=("requests", True),
        desc="Public edge only, from HAProxy access logs; query strings are never logged."))


def alerts():
    return table("Firing alerts", [('ALERTS{alertstate="firing",alertname!="Watchdog"}', "firing")],
                 [column("alertname", rename="Alert"),
                  column("severity", rename="Severity", width=110,
                         colors={"critical": CRIT, "warning": WARN, "info": MUTED}),
                  column("namespace", rename="Namespace", width=180)],
                 keep=["alertname", "severity", "namespace"], sort=("severity", False),
                 desc="Every alert firing right now, from vmalert. Empty means quiet.")


CLASSES = {"2xx": SERIES[0], "3xx": SERIES[2], "4xx": SERIES[3], "5xx": CRIT}
# Code 0 marks requests that ended before a response; they get no class.
CLASS = 'label_match(label_replace({}, "class", "${{1}}xx", "code", "([1-5]).."), "class", ".+")'


def build():
    b = Board("home", "Home", "What the cluster is doing right now. Drill-downs hold the history.",
              time="now-3h")

    node_gauges = [
        ("CPU", '100 * (1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m])))', CPU),
        ("Memory", "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", MEM),
        ("Disk", '100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})',
         DISK),
    ]
    for title, expr, th in node_gauges:
        b.put(gauge(title, [(f"sort_by_label({expr}, \"node\")", "{{node}}")], thresholds=th,
                    desc=f"{title} per node, now. The marks on the rim are the warning and critical "
                         "thresholds."), 8, 5)

    b.put(traffic(), 24, 8)

    b.put(edge_linked(histogram_bars(
        "Public responses per minute",
        [(f"sum by (code) (increase({EDGE_RESPONSES}[1m]))", "{{code}}")],
        overrides=fixed(CLASSES),
        desc="Every response from the public edge, stacked by status class. A tall yellow 4xx "
             "stack is a scan; raspberry is our own failures.")), 12, 8)
    quantiles = {"p50": SERIES[0], "p95": SERIES[1], "p99": SERIES[4]}
    b.put(edge_linked(timeseries(
        "Public response time",
        [vl(f"{EDGE_ACCESS} frontend:hug_* trs_ms:>=0 | stats quantile(0.5, trs_ms) p50,"
            " quantile(0.95, trs_ms) p95, quantile(0.99, trs_ms) p99", kind="statsRange")],
        "ms", overrides=fixed(quantiles), datasource=VL,
        desc="Median, 95th and 99th percentile time for services behind the public edge to send "
             "response headers, from HAProxy access logs. Private services are on Private gateway.")), 12, 8)

    b.put(resources(), 24, 10)

    b.put(clients(), 9, 9)
    b.put(paths(), 9, 9)
    b.put(edge_linked(donut("Public status mix, 15 minutes",
                            [(f"sum by (code) (increase({EDGE_RESPONSES}[15m]))", "{{code}}")],
                            overrides=fixed(CLASSES), desc="What the public edge answered lately.")),
          6, 9)

    b.put(state_timeline("Alerts",
                         [('max by (alertname) (ALERTS{alertstate="firing",severity="warning"})'
                           ' or 2 * max by (alertname) (ALERTS{alertstate="firing",severity="critical"})',
                           "{{alertname}}")],
                         *states((1, "warning", WARN), (2, "critical", CRIT)),
                         desc="When each alert was firing. The right edge is now."), 24, 6)
    return b
