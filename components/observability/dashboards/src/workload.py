from grammar import (LOG_ERRORS, VL, Board, column, gauge, histogram_bars, logs, query_var,
                     stat, steps, table, timeseries, vl)
from home import CPU, MEM, RES, restarts

SEL = 'namespace="$namespace",pod=~"$pod"'
CONT = f'{RES},container!="",{SEL}'
RUNNING = ' * on (namespace, pod) group_left () (kube_pod_status_phase{phase="Running"} == 1)'


def build():
    b = Board("workload", "Workload",
              "One app: its pods, how close they run to their limits, restarts and logs.",
              variables=[
                  query_var("namespace", "Namespace", "label_values(kube_pod_info, namespace)"),
                  query_var("pod", "Pods", 'label_values(kube_pod_info{namespace="$namespace"}, pod)',
                            multi=True, include_all=True),
              ])
    b.variables[0]["current"] = {"text": "argocd", "value": "argocd"}
    b.variables[1]["current"] = {"text": "All", "value": "$__all"}

    b.put(stat("Running", f'count(kube_pod_status_phase{{phase="Running",{SEL}}} == 1) or vector(0)',
               sparkline=False, desc="Pods in the Running phase."), 4, 5)
    b.put(stat("Not ready",
               f'(sum((kube_pod_status_ready{{condition="false",{SEL}}} == 1){RUNNING})'
               f' + sum(kube_pod_status_phase{{phase=~"Pending|Failed|Unknown",{SEL}}})) or vector(0)',
               thresholds=steps(1, 3), sparkline=False,
               desc="Pods pending, failed, or running without passing readiness."), 4, 5)
    b.put(stat("Restarts 24h", f'sum({restarts("namespace, pod", "24h", SEL)}) or vector(0)',
               thresholds=steps(1, 5), decimals=0, sparkline=False,
               desc="Container restarts across the selected pods in the last day."), 4, 5)
    b.put(gauge("CPU of limit",
                [(f"100 * sum(rate(container_cpu_usage_seconds_total{{{CONT}}}[5m]))"
                  f' / sum(kube_pod_container_resource_limits{{resource="cpu",{SEL}}}{RUNNING})', "CPU")],
                thresholds=CPU, desc="All selected pods together against the sum of their CPU limits."),
          6, 5)
    b.put(gauge("Memory of limit",
                [(f"100 * sum(container_memory_working_set_bytes{{{CONT}}})"
                  f' / sum(kube_pod_container_resource_limits{{resource="memory",{SEL}}}{RUNNING})', "Memory")],
                thresholds=MEM, desc="Working set against the sum of memory limits. At 100% the kernel kills."),
          6, 5)

    b.put(timeseries("CPU by pod",
                     [(f"sum by (pod) (rate(container_cpu_usage_seconds_total{{{CONT}}}[$__rate_interval]))", "{{pod}}")],
                     "cores", legend="table", desc="Cores in use per pod."), 12, 8)
    b.put(timeseries("Memory by pod",
                     [(f"sum by (pod) (container_memory_working_set_bytes{{{CONT}}})", "{{pod}}")],
                     "bytes", legend="table", desc="Working set per pod, page cache included."), 12, 8)

    b.put(timeseries("CPU throttling",
                     [(f'100 * sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{{container!="",{SEL}}}[$__rate_interval]))'
                       f' / sum by (pod) (rate(container_cpu_cfs_periods_total{{container!="",{SEL}}}[$__rate_interval]))',
                       "{{pod}}")],
                     "percent", thresholds=steps(10, 25), legend="table", maximum=100,
                     desc="Share of scheduling periods a pod hit its CPU limit. Throttled pods are slow "
                          "without looking busy."), 12, 8)
    b.put(histogram_bars("Restarts",
                         [(f"sum by (pod) (changes(max by (pod, container) (kube_pod_container_status_restarts_total{{{SEL}}})[10m:1m])) > 0",
                           "{{pod}}")],
                         interval="10m", desc="Container restarts per ten minutes, by pod."), 12, 8)

    b.put(timeseries("Network",
                     [(f"sum(rate(container_network_receive_bytes_total{{{SEL}}}[$__rate_interval]))", "in"),
                      (f"-sum(rate(container_network_transmit_bytes_total{{{SEL}}}[$__rate_interval]))", "out")],
                     "Bps", minimum=None, desc="Pod network traffic: in above the line, out below."), 12, 8)
    b.put(histogram_bars("Log lines",
                         [vl('kubernetes.pod_namespace:"$namespace" kubernetes.pod_name:~"$pod"'
                             " | stats by (kubernetes.pod_name) count() lines", kind="statsRange",
                             legend="{{kubernetes.pod_name}}")],
                         desc="How chatty each pod is. A sudden wall usually means errors."), 12, 8)
    b.panels[-1]["datasource"] = VL

    b.put(table("Containers",
                [(f'sum by (pod, container) (rate(container_cpu_usage_seconds_total{{{CONT}}}[5m]))', "CPU"),
                 (f'sum by (pod, container) (kube_pod_container_resource_requests{{resource="cpu",{SEL}}})', "CPU request"),
                 (f'sum by (pod, container) (kube_pod_container_resource_limits{{resource="cpu",{SEL}}})', "CPU limit"),
                 (f'sum by (pod, container) (container_memory_working_set_bytes{{{CONT}}})', "Memory"),
                 (f'sum by (pod, container) (kube_pod_container_resource_requests{{resource="memory",{SEL}}})', "Memory request"),
                 (f'sum by (pod, container) (kube_pod_container_resource_limits{{resource="memory",{SEL}}})', "Memory limit")],
                [column("pod", rename="Pod"), column("container", rename="Container", width=180),
                 column("CPU", "cores", decimals=2, width=90),
                 column("CPU request", "cores", decimals=2, width=110),
                 column("CPU limit", "cores", decimals=2, width=100),
                 column("Memory", "bytes", decimals=1, width=100),
                 column("Memory request", "bytes", decimals=1, width=130),
                 column("Memory limit", "bytes", decimals=1, width=120)],
                keep=["pod", "container", "CPU", "CPU request", "CPU limit", "Memory",
                      "Memory request", "Memory limit"],
                sort=("Memory", True), desc="Usage next to what each container asked for and may use."),
          24, 8)

    b.put(logs("Errors", f'kubernetes.pod_namespace:"$namespace" kubernetes.pod_name:~"$pod" {LOG_ERRORS}',
               desc="Error-level lines from the selected pods."), 12, 12)
    b.put(logs("All logs", 'kubernetes.pod_namespace:"$namespace" kubernetes.pod_name:~"$pod"',
               desc="Everything the selected pods printed, newest first."), 12, 12)
    return b
