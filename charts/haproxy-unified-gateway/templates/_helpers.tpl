{{- define "hug.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hug.selectorLabels" -}}
app.kubernetes.io/name: haproxy-unified-gateway
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "hug.labels" -}}
{{ include "hug.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/*
HUG lists Services by this label cluster-wide and rewrites their ports to
match the listeners; unique per release so two installs leave each other alone.
*/}}
{{- define "hug.serviceLabelKey" -}}
gate.haproxy.org/service
{{- end -}}

{{- define "hug.serviceLabelValue" -}}
{{- printf "%s.%s" .Release.Namespace (include "hug.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hug.hostNetwork" -}}
{{- if and (eq .Values.kind "DaemonSet") .Values.hostNetwork }}true{{ end -}}
{{- end -}}
