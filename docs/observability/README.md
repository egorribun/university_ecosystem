# Observability JSON examples

The [Grafana dashboard](grafana-dashboard.json) and
[Prometheus alerts](prometheus-alerts.json) are portable reference examples.
The current Compose stack does not load them. Their thresholds are not
production SLOs or release gates; review and adapt an example before adopting it.

## Active configuration

- Compose Prometheus reads [prometheus.yml](../../infrastructure/observability/prometheus.yml),
  which loads `infrastructure/observability/alerts/*.yaml`. The current rules
  are in [gateway.yaml](../../infrastructure/observability/alerts/gateway.yaml).
- Kubernetes rules are maintained separately in
  [prometheus-rules.yaml](../../k8s/monitoring/prometheus-rules.yaml).
- Compose Grafana provisions [datasources](../../infrastructure/observability/grafana/provisioning/datasources/datasources.yaml).
  It does not provision dashboards from this directory.

## Metric notes

The dashboard queries backend metrics defined in
[metrics.py](../../app/core/metrics.py). GPU collection uses the optional
`GPUtil` package, so `gpu_load_percent` can be absent when that package or a
supported GPU is unavailable. An empty GPU panel alone does not establish a
scrape failure.

The CSP example uses
`sum(rate(csp_reports_total{outcome="accepted"}[5m])) > 20`: more than 20 accepted
reports per second across all series, averaged over the preceding five minutes.
With `for: 5m`, the condition must stay true for five minutes before firing.
The annotation describes this unchanged threshold; the example does not define
an approved alert policy.
