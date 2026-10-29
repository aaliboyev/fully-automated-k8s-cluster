#!/usr/bin/env bash
# Create the secrets in ns flow-history; existing ones are left alone.
#   flow-history-clickhouse          passwords of the ClickHouse users vector and grafana
#   flow-history-grafana-datasource  Grafana's datasource for them (label grafana_datasource)
#   flow-history-s3                  access key of IAM user hubble-flow-history, whose
#                                    inline policy covers only bucket example-hubble-flows
# Values travel through pipes only. To rotate the passwords, delete the first
# two together, rerun, and restart clickhouse and vector; for the S3 key, delete
# flow-history-s3, rerun, restart clickhouse, then delete the old IAM key.
# AWS credentials come from the environment (AWS_PROFILE).
set -euo pipefail

command -v kubectl >/dev/null || { echo "kubectl not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl not found" >&2; exit 1; }

ns=flow-history
kubectl get namespace "$ns" >/dev/null 2>&1 || kubectl create namespace "$ns" >/dev/null

has() { kubectl -n "$ns" get secret "$1" >/dev/null 2>&1; }

if has flow-history-clickhouse; then
  echo "= $ns/flow-history-clickhouse exists"
else
  { openssl rand -hex 32; openssl rand -hex 32; } | jq -Rn --arg ns "$ns" '
    [inputs] as [$vector, $grafana]
    | {apiVersion: "v1", kind: "List", items: [
        {apiVersion: "v1", kind: "Secret",
         metadata: {name: "flow-history-clickhouse", namespace: $ns},
         stringData: {"vector-password": $vector, "grafana-password": $grafana}},
        {apiVersion: "v1", kind: "Secret",
         metadata: {name: "flow-history-grafana-datasource", namespace: $ns, labels: {grafana_datasource: "1"}},
         stringData: {"flow-history.yaml": ({apiVersion: 1, datasources: [{
           name: "ClickHouse-Flows", uid: "clickhouse-flows",
           type: "grafana-clickhouse-datasource", access: "proxy",
           jsonData: {host: "clickhouse.\($ns).svc.cluster.local", port: 9000, protocol: "native",
                      secure: false, username: "grafana", defaultDatabase: "hubble"},
           secureJsonData: {password: $grafana}}]} | tojson)}}
      ]}' | kubectl create -f - >/dev/null
  echo "✓ $ns/flow-history-clickhouse, $ns/flow-history-grafana-datasource"
fi

if has flow-history-s3; then
  echo "= $ns/flow-history-s3 exists"
else
  command -v aws >/dev/null || { echo "aws not found" >&2; exit 1; }
  aws iam create-access-key --user-name hubble-flow-history --output json \
    | jq --arg ns "$ns" '{apiVersion: "v1", kind: "Secret",
        metadata: {name: "flow-history-s3", namespace: $ns},
        stringData: {AWS_ACCESS_KEY_ID: .AccessKey.AccessKeyId, AWS_SECRET_ACCESS_KEY: .AccessKey.SecretAccessKey}}' \
    | kubectl create -f - >/dev/null
  echo "✓ $ns/flow-history-s3"
fi
