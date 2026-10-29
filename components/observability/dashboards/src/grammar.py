"""Shared look for every dashboard: palette, thresholds, panel builders, layout.

Healthy values render in plain text colour; only warning and critical states
are coloured, so a calm screen is a grey screen.
"""

VM = {"type": "prometheus", "uid": "VictoriaMetrics"}
VL = {"type": "victoriametrics-logs-datasource", "uid": "VictoriaLogs"}

# Categorical slots in fixed order, the dark steps, validated against
# Grafana's dark panel surface (#181b1f). Assign in order, never cycle.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
# Fox orange is the calm colour; the alarms moved off amber and red so all
# three stay distinct, including under colour blindness.
FOX = "#e8743b"
WARN, CRIT = "#ecd13a", "#d9367e"
CALM = "text"
MUTED = "#898781"

NODES = ["node2", "node1", "node3", "node4", "node5"]
GATEWAYS = ["public", "private"]

# Namespaces that run the cluster rather than a product.
SYSTEM_NS = (
    "kube-system|kube-public|kube-node-lease"
    "|piraeus-datastore|argocd|observability|network|cert-manager|tailscale|local-path-storage"
    "|arc-systems|arc-runners|ci-egress|backup|default"
)


def steps(warn=None, crit=None, base=CALM):
    """Threshold steps, rising: base below warn, then warn, then crit."""
    out = [{"color": base, "value": None}]
    for color, value in ((WARN, warn), (CRIT, crit)):
        if value is not None:
            out.append({"color": color, "value": value})
    return {"mode": "absolute", "steps": out}


def falling(warn=None, crit=None):
    """Threshold steps where lower is worse (e.g. free space, ready ratio)."""
    out = [{"color": CRIT if crit is not None else WARN, "value": None}]
    if crit is not None and warn is not None:
        out.append({"color": WARN, "value": crit})
    out.append({"color": CALM, "value": warn if warn is not None else crit})
    return {"mode": "absolute", "steps": out}


def fixed(name_to_color):
    """Overrides pinning a series colour to its entity, so filters never repaint."""
    return [{"matcher": {"id": "byName", "options": name},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}
            for name, color in name_to_color.items()]


def node_colors():
    return fixed(dict(zip(NODES, SERIES)))


def gateway_colors():
    return fixed(dict(zip(GATEWAYS, SERIES)))


def vm(expr, legend="", ref="A", instant=False, fmt=None):
    t = {"datasource": VM, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t["instant"], t["range"] = True, False
    if fmt:
        t["format"] = fmt
    return t


def vl(expr, ref="A", kind="instant", legend=""):
    return {"datasource": VL, "expr": expr, "queryType": kind, "refId": ref,
            "editorMode": "code", "legendFormat": legend}


def _targets(targets):
    out = []
    for i, t in enumerate(targets):
        if isinstance(t, tuple):
            t = vm(t[0], t[1] if len(t) > 1 else "")
        t = dict(t, refId=chr(65 + i))
        out.append(t)
    return out


def _links(link):
    return [{"title": link[0], "url": link[1]}] if link else []


def stat(title, expr, unit="short", desc="", thresholds=None, decimals=None, link=None,
         sparkline=True, mappings=None, text_size=None):
    target = vm(expr) if isinstance(expr, str) else expr
    p = {"type": "stat", "title": title, "description": desc,
         "datasource": target["datasource"], "targets": [target],
         "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "thresholds"},
                                      "thresholds": thresholds or steps(),
                                      "mappings": mappings or [], "links": _links(link)},
                         "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                     "colorMode": "value", "graphMode": "area" if sparkline else "none",
                     "justifyMode": "auto", "textMode": "value", "wideLayout": True,
                     "showPercentChange": False, "orientation": "auto"}}
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals
    if text_size:
        p["options"]["text"] = {"valueSize": text_size}
    return p


def timeseries(title, targets, unit="short", desc="", thresholds=None, overrides=None,
               stack=False, minimum=0, maximum=None, legend="list", fill=None, width=None,
               decimals=None, datasource=VM):
    many = legend == "table"
    defaults = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": "line", "lineInterpolation": "smooth",
            "lineWidth": width or (1 if many else 2),
            "fillOpacity": fill if fill is not None else (35 if stack else 6),
            "gradientMode": "opacity", "showPoints": "never", "spanNulls": True,
            "stacking": {"mode": "normal" if stack else "none", "group": "A"},
            "axisBorderShow": False, "axisPlacement": "auto", "axisCenteredZero": False,
            "thresholdsStyle": {"mode": "dashed" if thresholds else "off"},
        },
        "thresholds": thresholds or steps(),
    }
    if minimum is not None:
        defaults["min"] = minimum
    if maximum is not None:
        defaults["max"] = maximum
    if decimals is not None:
        defaults["decimals"] = decimals
    legend_opts = ({"displayMode": "table", "placement": "right", "showLegend": True,
                    "calcs": ["mean", "max", "lastNotNull"], "sortBy": "Last *", "sortDesc": True}
                   if many else {"displayMode": "list", "placement": "bottom", "showLegend": True,
                                 "calcs": []})
    return {"type": "timeseries", "title": title, "description": desc, "datasource": datasource,
            "targets": _targets(targets),
            "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
            "options": {"legend": legend_opts, "tooltip": {"mode": "multi", "sort": "desc"}}}


def column(name, unit=None, thresholds=None, display=None, width=None, link=None, decimals=None,
           rename=None, gauge_max=None, colors=None):
    """Per-column table override; `display` is a cellOptions type."""
    props = []
    if unit:
        props.append({"id": "unit", "value": unit})
    if decimals is not None:
        props.append({"id": "decimals", "value": decimals})
    if display == "gauge":
        # Bars are fox orange until a threshold says otherwise.
        thresholds = thresholds or steps()
        thresholds = dict(thresholds, steps=[dict(thresholds["steps"][0], color=FOX)]
                          + thresholds["steps"][1:])
    if thresholds:
        props.append({"id": "thresholds", "value": thresholds})
        props.append({"id": "color", "value": {"mode": "thresholds"}})
    if display == "gauge":
        props.append({"id": "custom.cellOptions",
                      "value": {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}})
        props.append({"id": "min", "value": 0})
        # Without a fixed max the bar scales to the column's largest value.
        props.append({"id": "max", "value": gauge_max} if gauge_max
                     else {"id": "fieldMinMax", "value": True})
    elif display:
        props.append({"id": "custom.cellOptions", "value": {"type": display}})
    if width:
        props.append({"id": "custom.width", "value": width})
    if link:
        props.append({"id": "links", "value": [{"title": link[0], "url": link[1]}]})
        props.append({"id": "color", "value": {"mode": "fixed", "fixedColor": FOX}})
        props.append({"id": "custom.cellOptions", "value": {"type": "color-text"}})
    if rename:
        props.append({"id": "displayName", "value": rename})
    if colors:
        props.append({"id": "mappings", "value": [{"type": "value", "options": {
            value: {"color": color, "index": i} for i, (value, color) in enumerate(colors.items())}}]})
        props.append({"id": "custom.cellOptions", "value": {"type": "color-text"}})
    return {"matcher": {"id": "byName", "options": name}, "properties": props}


# Missing values read as a quiet dash rather than taking the threshold base colour.
DASH = [{"type": "special", "options": {"match": "nan", "result": {"text": "–", "color": MUTED, "index": 0}}},
        {"type": "special", "options": {"match": "null", "result": {"text": "–", "color": MUTED, "index": 1}}}]

LOG_ERRORS = 'level:~"(?i)^(error|err|fatal|crit.*|panic)$"'


def table(title, targets, columns, desc="", keep=None, sort=None, datasource=VM):
    """Instant queries merged into one row per shared label set.

    Target `(expr, name)` pairs become columns called `name`; `keep` lists the
    columns to show, in order; `columns` styles them by that name.
    """
    rename = {}
    for i, t in enumerate(targets):
        rename["Value" if len(targets) == 1 else f"Value #{chr(65 + i)}"] = t[1]
    transformations = [{"id": "merge", "options": {}}] if len(targets) > 1 else []
    transformations.append({"id": "organize", "options": {"renameByName": rename}})
    if keep:
        transformations.append({"id": "filterFieldsByName",
                                "options": {"include": {"names": list(keep)}}})
        transformations.append({"id": "organize", "options": {
            "indexByName": {name: i for i, name in enumerate(keep)}}})
    p = {"type": "table", "title": title, "description": desc, "datasource": datasource,
         "targets": [vm(t[0], ref=chr(65 + i), instant=True, fmt="table")
                     for i, t in enumerate(targets)],
         "transformations": transformations,
         "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"},
                                                 "inspect": False},
                                      "color": {"mode": "fixed", "fixedColor": "text"},
                                      "mappings": DASH},
                         "overrides": columns},
         "options": {"showHeader": True, "cellHeight": "sm",
                     "footer": {"show": False, "reducer": ["sum"], "countRows": False}}}
    if sort:
        p["options"]["sortBy"] = [{"displayName": sort[0], "desc": sort[1]}]
    return p


def log_table(title, expr, columns, keep, numeric=(), desc="", sort=None):
    """A VictoriaLogs `| stats by (...)` result as a table, one column per field."""
    p = table(title, [], columns, desc=desc, keep=None, sort=sort, datasource=VL)
    p["targets"] = [vl(expr)]
    p["transformations"] = [
        {"id": "extractFields", "options": {"source": "labels", "format": "json", "replace": True,
                                            "keepTime": False}},
        {"id": "convertFieldType", "options": {"conversions": [
            {"targetField": f, "destinationType": "number"} for f in numeric]}},
        {"id": "filterFieldsByName", "options": {"include": {"names": list(keep)}}},
        {"id": "organize", "options": {"indexByName": {n: i for i, n in enumerate(keep)}}},
    ]
    return p


def bars(title, targets, unit="short", desc="", thresholds=None, maximum=None, decimals=None,
         datasource=VM, link=None):
    """Horizontal bar gauge: one thin bar per series, coloured only past a threshold."""
    defaults = {"unit": unit, "min": 0, "color": {"mode": "thresholds"},
                "thresholds": thresholds or steps(), "links": _links(link)}
    if maximum is not None:
        defaults["max"] = maximum
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"type": "bargauge", "title": title, "description": desc, "datasource": datasource,
            "targets": _targets(targets),
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"orientation": "horizontal", "displayMode": "basic",
                        "valueMode": "text", "namePlacement": "left", "showUnfilled": True,
                        "sizing": "manual", "minVizHeight": 14, "maxVizHeight": 18,
                        "minVizWidth": 8, "reduceOptions": {"calcs": ["lastNotNull"],
                                                            "fields": "", "values": False}}}


def logs(title, expr, desc=""):
    return {"type": "logs", "title": title, "description": desc, "datasource": VL,
            "targets": [vl(expr)],
            "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                        "enableLogDetails": True, "dedupStrategy": "none",
                        "prettifyLogMessage": False, "showLabels": False}}


def text(content, title=""):
    return {"type": "text", "title": title, "options": {"mode": "markdown", "content": content}}


def query_var(name, label, query, multi=False, include_all=False, regex="", hide=0):
    return {"name": name, "label": label, "type": "query", "datasource": VM,
            "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery",
                      "qryType": 1},
            "definition": query, "refresh": 2, "regex": regex, "sort": 1, "multi": multi,
            "includeAll": include_all, "allValue": ".*" if include_all else None,
            "current": {}, "options": [], "hide": hide}


class Board:
    """A dashboard laid out left to right, wrapping at 24 columns."""

    def __init__(self, uid, title, description, tags=("cluster",), variables=(),
                 time="now-6h", refresh="1m"):
        self.uid, self.title, self.description = uid, title, description
        self.tags, self.variables = list(tags), list(variables)
        self.time, self.refresh = time, refresh
        self.panels, self._row = [], None
        self._x = self._y = self._line_h = 0
        self._id = 0

    def _newline(self):
        self._y += self._line_h
        self._x = self._line_h = 0

    def row(self, title, collapsed=False):
        self._newline()
        self._id += 1
        r = {"type": "row", "title": title, "id": self._id, "collapsed": collapsed,
             "gridPos": {"h": 1, "w": 24, "x": 0, "y": self._y}, "panels": []}
        self.panels.append(r)
        self._row = r if collapsed else None
        self._y += 1
        return self

    def put(self, panel, w, h):
        if self._x + w > 24:
            self._newline()
        self._id += 1
        panel = dict(panel, id=self._id, gridPos={"h": h, "w": w, "x": self._x, "y": self._y})
        (self._row["panels"] if self._row else self.panels).append(panel)
        self._x += w
        self._line_h = max(self._line_h, h)
        return self

    def json(self):
        return {
            "uid": self.uid, "title": self.title, "description": self.description,
            "tags": self.tags, "editable": False, "graphTooltip": 1, "timezone": "browser",
            "schemaVersion": 41, "version": 1, "refresh": self.refresh,
            "time": {"from": self.time, "to": "now"},
            "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
            "fiscalYearStartMonth": 0, "liveNow": False, "weekStart": "",
            "annotations": {"list": []},
            "templating": {"list": self.variables},
            "links": [{"type": "dashboards", "tags": ["cluster"], "asDropdown": False,
                       "includeVars": False, "keepTime": True, "title": "Cluster",
                       "targetBlank": False, "icon": "external link"}],
            "panels": self.panels,
        }



def gauge(title, targets, unit="percent", thresholds=None, desc="", maximum=100, decimals=0):
    """Radial gauges, one per series, fox orange until a threshold is crossed."""
    th = thresholds or steps()
    th = dict(th, steps=[dict(th["steps"][0], color=FOX)] + th["steps"][1:])
    return {"type": "gauge", "title": title, "description": desc, "datasource": VM,
            "targets": _targets(targets),
            "fieldConfig": {"defaults": {"unit": unit, "min": 0, "max": maximum, "decimals": decimals,
                                         "color": {"mode": "thresholds"}, "thresholds": th},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "orientation": "auto", "showThresholdMarkers": True,
                        "showThresholdLabels": False, "sizing": "auto", "minVizWidth": 75,
                        "minVizHeight": 75}}


def histogram_bars(title, targets, unit="short", desc="", overrides=None, interval="1m"):
    """Counts per time bucket as stacked bars: easier to read than spiky rate lines."""
    p = timeseries(title, targets, unit, desc=desc, overrides=overrides, stack=True, fill=85,
                   width=0)
    p["fieldConfig"]["defaults"]["custom"].update({"drawStyle": "bars", "barAlignment": 0,
                                                  "lineWidth": 0, "gradientMode": "none"})
    p["interval"] = interval
    return p


def heatmap(title, expr, unit="s", desc=""):
    """A latency distribution over time from histogram buckets, in an orange ramp."""
    return {"type": "heatmap", "title": title, "description": desc, "datasource": VM,
            "interval": "1m",
            "targets": [dict(vm(expr, "{{le}}"), format="heatmap")],
            "fieldConfig": {"defaults": {"custom": {"scaleDistribution": {"type": "linear"},
                                                    "hideFrom": {"legend": False, "tooltip": False,
                                                                 "viz": False}}},
                            "overrides": []},
            "options": {"calculate": False, "cellGap": 2, "cellValues": {},
                        "color": {"mode": "scheme", "scheme": "Oranges", "fill": FOX,
                                  "scale": "exponential", "exponent": 0.4, "steps": 64,
                                  "reverse": False},
                        "exemplars": {"color": MUTED}, "filterValues": {"le": 1e-9},
                        "legend": {"show": True}, "rowsFrame": {"layout": "auto"},
                        "tooltip": {"mode": "single", "yHistogram": True, "showColorScale": True},
                        "yAxis": {"axisPlacement": "left", "unit": unit, "reverse": False}}}


def donut(title, targets, unit="short", desc="", overrides=None, datasource=VM):
    """Part-to-whole for a handful of slices; values and shares in the legend."""
    return {"type": "piechart", "title": title, "description": desc, "datasource": datasource,
            "targets": _targets(targets),
            "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}},
                            "overrides": overrides or []},
            "options": {"pieType": "donut", "displayLabels": [],
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "legend": {"displayMode": "table", "placement": "right", "showLegend": True,
                                   "values": ["value", "percent"]},
                        "tooltip": {"mode": "single", "sort": "none"}}}


def state_timeline(title, targets, mappings, thresholds, desc="", overrides=None):
    """Bands of state over time, one lane per series; colour comes from thresholds."""
    return {"type": "state-timeline", "title": title, "description": desc, "datasource": VM,
            "targets": _targets(targets),
            "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": thresholds,
                                         "mappings": mappings,
                                         "custom": {"fillOpacity": 85, "lineWidth": 0}},
                            "overrides": overrides or []},
            "options": {"showValue": "never", "rowHeight": 0.8, "mergeValues": True,
                        "alignValue": "left", "legend": {"showLegend": False},
                        "tooltip": {"mode": "single", "sort": "none"}}}


def states(*pairs):
    """Value mappings and matching thresholds for state_timeline: (value, text, colour)."""
    mappings = [{"type": "value", "options": {str(v): {"text": t, "index": i}
                                              for i, (v, t, c) in enumerate(pairs)}}]
    th = {"mode": "absolute", "steps": [{"color": "transparent", "value": None}]
          + [{"color": c, "value": v} for v, t, c in pairs]}
    return mappings, th
