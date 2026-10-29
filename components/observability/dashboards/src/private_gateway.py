from grammar import (SERIES, Board, donut, fixed, heatmap, histogram_bars, query_var, steps, text,
                     timeseries)
from home import CLASS, CLASSES, EDGE_LINK, HOSTS, traffic

R = 'route=~"$route"'


def build():
    b = Board("private-gateway", "Private gateway",
              "What reaches the private Traefik gateway and how each service answers.",
              variables=[query_var("route", "Service",
                                   'label_values(traefik_service_requests_total, route)',
                                   multi=True, include_all=True)])
    b.variables[0]["current"] = {"text": "All", "value": "$__all"}

    b.put(traffic(), 24, 8)

    by_service = f"sum by (httproute) (rate(traefik_service_requests_total{{{R}}}[$__rate_interval]) * on (route) group_left (httproute) {HOSTS})"
    b.put(timeseries("Requests by service", [(by_service, "{{httproute}}")], "reqps", stack=True,
                     legend="table", desc="Requests per second for each selected service, stacked."),
          16, 8)
    b.put(donut("Status mix",
                [(f"sum by (class) ({CLASS.format(f'increase(traefik_service_requests_total{{{R}}}[$__range])')})",
                  "{{class}}")],
                overrides=fixed(CLASSES), desc="Every response in the time range by status class."),
          8, 8)

    b.put(histogram_bars("Responses per minute",
                         [(f"sum by (class) ({CLASS.format(f'increase(traefik_service_requests_total{{{R}}}[1m])')})",
                           "{{class}}")],
                         overrides=fixed(CLASSES), desc="Selected services, stacked by status class."),
          12, 8)
    quantiles = {"p50": SERIES[0], "p95": SERIES[1], "p99": SERIES[4]}
    b.put(timeseries("Latency",
                     [(f"histogram_quantile({q}, sum by (le) (rate(traefik_service_request_duration_seconds_bucket{{{R}}}[$__rate_interval])))",
                       name) for q, name in ((0.5, "p50"), (0.95, "p95"), (0.99, "p99"))],
                     "s", thresholds=steps(1, 3), overrides=fixed(quantiles),
                     desc="Median, 95th and 99th percentile time to answer for the selected services."),
          12, 8)

    b.put(heatmap("Response time distribution",
                  f"sum by (le) (increase(traefik_service_request_duration_seconds_bucket{{{R}}}[$__interval]))",
                  desc="Every request placed by how long it took. Bright cells high up are slow periods."),
          12, 8)
    b.put(timeseries("Open connections",
                     [("sum by (gateway) (traefik_open_connections)", "{{gateway}}")], "short",
                     overrides=fixed({"public": SERIES[0], "private": SERIES[2]}),
                     desc="Connections Traefik holds open right now, per gateway."), 12, 8)

    b.row("Public clients")
    b.put(text(f"Public traffic, clients and hosts: [{EDGE_LINK['title']}]({EDGE_LINK['url']})."),
          24, 2)
    return b
