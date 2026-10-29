from grammar import (SERIES, VL, Board, column, fixed, histogram_bars, log_table, logs, node_colors,
                     query_var, stat, steps, table, timeseries, vl)
from home import CLASSES, EDGE_FE as FE, EDGE_JOB as JOB, EDGE_LOGS, RES, restarts

FE_5XX = f'{FE},code="5xx"'
NOT_UP = f'{JOB},state!="UP"'
HUG = 'namespace="network",container="hug",pod=~"haproxy-public-.+"'
# HAProxy series carry the pod but not the node.
PODS = ('max by (namespace, pod, node) (kube_pod_info{namespace="network",'
        'created_by_name="haproxy-public",node=~"$node"})')
LOGS = f'{EDGE_LOGS} kubernetes.pod_node_name:~"$node"'
ACCESS = f"{LOGS} status:* -frontend:stats"

REQUESTS = "haproxy_backend_http_requests_total"
RESPONSES = "haproxy_backend_http_responses_total"


def on_node(expr):
    return f"({expr}) * on (namespace, pod) group_left (node) {PODS}"


def gauge_on_node(metric, sel=JOB):
    return on_node(f"{metric}{{{sel}}}")


def rate(metric, sel=JOB, window="$__rate_interval"):
    return on_node(f"rate({metric}{{{sel}}}[{window}])")


def route(expr):
    """Backend hug_<namespace>_<service>_<port>_<hash> as namespace/service:port."""
    out = f'label_replace({expr}, "route", "$1", "proxy", "(.*)")'
    out = f'label_replace({out}, "route", "$1/$2:$3", "proxy", "hug_([^_]+)_([^_]+)_([0-9]+)_.*")'
    return f'label_replace({out}, "route", "redirect $1", "proxy", "hug_redirect_(.{{6}}).*")'


def by_route(expr, agg="sum"):
    return f"{agg} by (route) ({route(expr)})"


def share_by_route(code, window="$__rate_interval"):
    sel = f'{JOB},code="{code}"'
    return (f"100 * {by_route(rate(RESPONSES, sel, window))}"
            f" / {by_route(rate(RESPONSES, JOB, window))}")


def servers(sel):
    """Servers per route matching `sel`, as the node that sees most of them."""
    return f"max by (route) (sum by (route, pod) ({route(gauge_on_node('haproxy_server_status', sel))}))"


def routes():
    q = [
        (by_route(rate(REQUESTS, JOB, "5m")), "Req/s"),
        (share_by_route("4xx", "5m"), "4xx"),
        (share_by_route("5xx", "5m"), "5xx"),
        (by_route(gauge_on_node("haproxy_backend_response_time_average_seconds"), "max"), "Response"),
        (servers(f'{JOB},state="UP"'), "Up"),
        (servers(NOT_UP), "Not up"),
        (by_route(gauge_on_node("haproxy_backend_current_queue")), "Queue"),
        (by_route(gauge_on_node("haproxy_backend_current_sessions")), "Sessions"),
    ]
    cols = [
        column("route", rename="Route", width=320),
        column("Req/s", "reqps", decimals=2, width=100),
        column("4xx", "percent", steps(25, 75), "color-text", decimals=0, width=70),
        column("5xx", "percent", steps(1, 5), "color-text", decimals=1, width=70),
        column("Response", "s", steps(1, 3), "color-text", decimals=3, width=100),
        column("Up", width=60),
        column("Not up", thresholds=steps(1), display="color-text", width=80),
        column("Queue", thresholds=steps(1, 50), display="color-text", width=80),
        column("Sessions", width=90),
    ]
    return table("Routes, last 5 minutes", q, cols,
                 keep=["route", "Req/s", "4xx", "5xx", "Response", "Up", "Not up", "Queue",
                       "Sessions"], sort=("Req/s", True),
                 desc="Every HAProxy backend: one per Service port an HTTPRoute sends to. Response "
                      "is the average over the backend's last 1024 requests on the slower node. "
                      "Up and Not up count servers as one node sees them.")


def build():
    b = Board("edge", "HAProxy edge",
              "The public HAProxy edge: traffic, errors, latency, connections and the pods themselves.",
              variables=[query_var("node", "Node",
                                   'label_values(kube_pod_info{namespace="network",'
                                   'created_by_name="haproxy-public"}, node)',
                                   multi=True, include_all=True)])
    b.variables[0]["current"] = {"text": "All", "value": "$__all"}

    fe_resp = "haproxy_frontend_http_responses_total"
    b.put(stat("Requests/s", f"sum({rate('haproxy_frontend_http_requests_total', FE, '5m')})",
               "reqps", decimals=1, desc="Requests through the listener frontends, last 5 minutes."),
          3, 4)
    b.put(stat("5xx share",
               f"100 * sum({rate(fe_resp, FE_5XX, '5m')}) / sum({rate(fe_resp, FE, '5m')})",
               "percent", thresholds=steps(1, 5), decimals=2,
               desc="Share of responses that were 5xx, ours or the backends', last 5 minutes."), 3, 4)
    b.put(stat("Connections", f"sum({gauge_on_node('haproxy_process_current_connections')})",
               desc="Client and server connections HAProxy holds open now."), 3, 4)
    b.put(stat("TLS handshakes/s", f"sum({rate('haproxy_process_ssl_connections_total', JOB, '5m')})",
               "cps", decimals=1, desc="New TLS connections per second, last 5 minutes."), 3, 4)
    b.put(stat("Servers not up",
               f"sum({gauge_on_node('haproxy_server_status', NOT_UP)}) or vector(0)",
               thresholds=steps(1, 3), decimals=0, sparkline=False,
               desc="Backend servers in any state but UP, counted on every node."), 3, 4)
    b.put(stat("Queued", f"sum({gauge_on_node('haproxy_backend_current_queue')}) or vector(0)",
               thresholds=steps(1, 50), decimals=0,
               desc="Requests waiting for a free server slot (default-server maxconn)."), 3, 4)
    b.put(stat("Hostnames down", 'count(probe_success{job="public-edge"} == 0) or vector(0)',
               thresholds=steps(1, 2), decimals=0, sparkline=False,
               desc="Public hostnames failing the blackbox probe from inside the cluster."), 3, 4)
    b.put(stat("Restarts 24h", f'sum({on_node(restarts("namespace, pod", "24h", HUG))}) or vector(0)',
               thresholds=steps(1, 3), decimals=0, sparkline=False,
               desc="Container restarts of the edge pods in the last day."), 3, 4)

    b.row("Traffic")
    b.put(timeseries("Requests by frontend",
                     [(f"sum by (proxy) ({rate('haproxy_frontend_http_requests_total', FE)})", "{{proxy}}")],
                     "reqps", stack=True,
                     overrides=fixed({"hug_https_443": SERIES[0], "hug_http_80": SERIES[1]}),
                     desc="Requests per second per listener port."), 8, 8)
    b.put(timeseries("Requests by route", [(by_route(rate(REQUESTS)), "{{route}}")],
                     "reqps", stack=True, legend="table",
                     desc="Requests per second per backend, stacked. redirect is an HTTPRoute "
                          "redirect; backend_not_found is a Host no route claims."), 16, 8)
    b.put(histogram_bars("Responses per minute",
                         [(f"sum by (code) ({on_node(f'increase({fe_resp}{{{FE}}}[1m])')})", "{{code}}")],
                         overrides=fixed(CLASSES),
                         desc="Every response from the listener frontends, stacked by status class."),
          12, 8)
    b.put(timeseries("5xx share by route", [(share_by_route("5xx"), "{{route}}")],
                     "percent", thresholds=steps(1, 5), legend="table",
                     desc="Share of each backend's responses that were 5xx."), 12, 8)
    b.put(routes(), 24, 9)

    b.row("Latency")
    b.put(timeseries("Response time by route",
                     [(by_route(gauge_on_node("haproxy_backend_response_time_average_seconds"), "max")
                       + " > 0", "{{route}}")],
                     "s", thresholds=steps(1, 3), legend="table",
                     desc="Average time to response headers over each backend's last 1024 requests, "
                          "slower node. HAProxy exports no latency histograms."), 12, 8)
    quantiles = {"p50": SERIES[0], "p95": SERIES[1], "p99": SERIES[4]}
    b.put(timeseries("Response time percentiles",
                     [vl(f"{ACCESS} frontend:hug_* trs_ms:>=0 | stats quantile(0.5, trs_ms) p50,"
                         " quantile(0.95, trs_ms) p95, quantile(0.99, trs_ms) p99", kind="statsRange")],
                     "ms", overrides=fixed(quantiles), datasource=VL,
                     desc="Time from sending the request to the server until its response headers "
                          "(Tr), from access logs. Streaming bodies are not counted."), 12, 8)

    b.row("Connections")
    b.put(timeseries("Sessions by frontend",
                     [(f"sum by (node, proxy) ({gauge_on_node('haproxy_frontend_current_sessions', FE)})",
                       "{{node}} {{proxy}}")],
                     desc="Client sessions open now, per node and listener port."), 8, 8)
    b.put(timeseries("Connections by node",
                     [(f"sum by (node) ({gauge_on_node('haproxy_process_current_connections')})", "{{node}}")],
                     overrides=node_colors(), desc="All connections each HAProxy holds open."), 8, 8)
    b.put(timeseries("New connections by frontend",
                     [(f"sum by (proxy) ({rate('haproxy_frontend_connections_total', FE)})", "{{proxy}}")],
                     "cps", desc="Client connections accepted per second."), 8, 8)
    b.put(timeseries("TLS",
                     [(f"sum by (node) ({rate('haproxy_process_ssl_connections_total')})",
                       "{{node}} connections"),
                      (f"sum by (node) ({gauge_on_node('haproxy_process_current_frontend_ssl_key_rate')})",
                       "{{node}} full handshakes")],
                     "cps", desc="New TLS connections per second, and how many needed a full key "
                                 "exchange rather than a resumed session."), 8, 8)
    b.put(timeseries("Queue by route",
                     [(by_route(gauge_on_node("haproxy_backend_current_queue")) + " > 0", "{{route}}")],
                     thresholds=steps(1, 50),
                     desc="Requests waiting for a server slot. Empty means nothing queued."), 8, 8)
    b.put(timeseries("Bytes",
                     [(f"sum({rate('haproxy_frontend_bytes_in_total', FE)})", "from clients"),
                      (f"-sum({rate('haproxy_frontend_bytes_out_total', FE)})", "to clients")],
                     "Bps", minimum=None,
                     desc="Listener traffic: received above the line, sent below."), 8, 8)

    b.row("Pods")
    cont = f'{RES},{HUG},node=~"$node"'
    b.put(timeseries("CPU",
                     [(f"sum by (node) (rate(container_cpu_usage_seconds_total{{{cont}}}[$__rate_interval]))",
                       "{{node}}")],
                     "cores", overrides=node_colors(),
                     desc="Cores used by HAProxy and the controller together. No CPU limit."), 8, 8)
    b.put(timeseries("Memory",
                     [(f"sum by (node) (container_memory_working_set_bytes{{{cont}}})", "{{node}}"),
                      (f'max(kube_pod_container_resource_limits{{resource="memory",{HUG}}})', "limit")],
                     "bytes", overrides=node_colors(),
                     desc="Working set per pod against the memory limit. HAProxy gets two thirds of "
                          "the limit, the controller one third."), 8, 8)
    metrics_ep = f'{JOB},endpoint="metrics"'
    b.put(histogram_bars("Restarts and reloads",
                         [(f"sum({on_node(f'changes(kube_pod_container_status_restarts_total{{{HUG}}}[10m])')})",
                           "container restarts"),
                          (f"sum({on_node(f'changes(process_start_time_seconds{{{metrics_ep}}}[10m])')})",
                           "controller restarts"),
                          (f"sum({on_node(f'increase(hug_haproxy_reload_total{{{JOB}}}[10m])')})",
                           "HAProxy reloads")],
                         interval="10m",
                         desc="Per ten minutes. Reloads follow config changes HUG cannot apply at "
                              "runtime; restarts are crashes or rollouts."), 8, 8)

    b.row("Access logs")
    clients = (f"{ACCESS} | stats by (client_ip) count() requests,"
               " count() if (status:>=400) failed, count_uniq(path) paths, count_uniq(host) hosts"
               " | sort by (requests desc) | limit 25")
    b.put(log_table("Clients in range", clients,
                    [column("client_ip", rename="Client"),
                     column("requests", rename="Requests", display="gauge", decimals=0),
                     column("failed", rename="Failed", thresholds=steps(20, 100), display="color-text", width=90),
                     column("paths", rename="Paths", width=80),
                     column("hosts", rename="Hosts", width=80)],
                    keep=["client_ip", "requests", "failed", "paths", "hosts"],
                    numeric=["requests", "failed", "paths", "hosts"], sort=("requests", True),
                    desc="Busiest clients in the time range. One client with many failed requests "
                         "over many paths is a scanner."), 12, 10)
    hosts = (f"{ACCESS} | stats by (host) count() requests, count_uniq(client_ip) clients,"
             " count() if (status:>=400) failed | sort by (requests desc) | limit 25")
    b.put(log_table("Hosts asked for", hosts,
                    [column("host", rename="Host"),
                     column("requests", rename="Requests", display="gauge", decimals=0),
                     column("clients", rename="Clients", width=80),
                     column("failed", rename="Failed", width=80)],
                    keep=["host", "requests", "clients", "failed"],
                    numeric=["requests", "clients", "failed"], sort=("requests", True),
                    desc="The Host header clients sent. Bare IPs and strangers' domains are scanners."),
          12, 10)
    b.put(logs("Errors", f"{LOGS} (status:>=500 or error:*)",
               desc="5xx access lines, connections that failed before a request (TLS handshakes "
                    "mostly) and controller errors. Paths carry no query string."), 24, 10)
    return b
