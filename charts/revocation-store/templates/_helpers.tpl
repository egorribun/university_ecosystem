{{- define "revocation-store.serviceHost" -}}
{{- printf "%s-revocation-redis-master" .Values.applicationReleaseName -}}
{{- end -}}

{{- define "revocation-store.redis.fullname" -}}
{{- .Values.redis.fullnameOverride -}}
{{- end -}}

{{- define "revocation-store.redis.masterName" -}}
{{- printf "%s-master" (include "revocation-store.redis.fullname" .) -}}
{{- end -}}

{{- define "revocation-store.redis.headlessName" -}}
{{- printf "%s-headless" (include "revocation-store.redis.fullname" .) -}}
{{- end -}}

{{- define "revocation-store.redis.chartLabel" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "revocation-store.redis.labels" -}}
app.kubernetes.io/instance: {{ .Values.applicationReleaseName | quote }}
app.kubernetes.io/managed-by: Helm
app.kubernetes.io/name: revocation-redis
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ include "revocation-store.redis.chartLabel" . | quote }}
university-ecosystem.io/revocation-store-for: {{ .Values.applicationReleaseName | quote }}
{{- end -}}

{{- define "revocation-store.redis.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Values.applicationReleaseName | quote }}
app.kubernetes.io/name: revocation-redis
app.kubernetes.io/component: master
{{- end -}}

{{- define "revocation-store.redis.masterConfig" -}}
dir /data
{{ .Values.redis.commonConfiguration }}
aclfile /run/redis-runtime/users.acl
{{ range .Values.redis.master.disableCommands }}
rename-command {{ . }} ""
{{ end }}
{{- end -}}

{{- define "revocation-store.redis.image" -}}
{{- printf "%s/%s:%s@%s" .Values.redis.image.registry .Values.redis.image.repository .Values.redis.image.tag .Values.redis.image.digest -}}
{{- end -}}

{{- define "revocation-store.redis.exporterImage" -}}
{{- printf "%s/%s:%s@%s" .Values.redis.metrics.image.registry .Values.redis.metrics.image.repository .Values.redis.metrics.image.tag .Values.redis.metrics.image.digest -}}
{{- end -}}

{{- define "revocation-store.redis.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  add: []
  drop:
    - ALL
privileged: false
procMount: Default
readOnlyRootFilesystem: true
runAsGroup: 1001
runAsNonRoot: true
runAsUser: 1001
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "revocation-store.redis.podSecurityContext" -}}
fsGroup: 1001
fsGroupChangePolicy: OnRootMismatch
runAsGroup: 1001
runAsNonRoot: true
runAsUser: 1001
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "revocation-store.validate" -}}
{{- $expectedFullname := printf "%s-revocation-redis" .Values.applicationReleaseName -}}
{{- $expectedCommands := list "ACL" "CONFIG" "FLUSHDB" "FLUSHALL" "FUNCTION" "MIGRATE" "MODULE" "MONITOR" "REPLICAOF" "SLAVEOF" "SHUTDOWN" -}}
{{- $expectedMasterResources := dict "requests" (dict "cpu" "100m" "memory" "128Mi") "limits" (dict "cpu" "500m" "memory" "512Mi") -}}
{{- $expectedMetricsResources := dict "requests" (dict "cpu" "25m" "memory" "24Mi") "limits" (dict "cpu" "100m" "memory" "64Mi") -}}
{{- if or
  (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" .Values.applicationReleaseName))
  (gt (len .Values.applicationReleaseName) 63)
  (ne .Values.redis.fullnameOverride $expectedFullname)
  (ne (toJson .Values.redis.commonLabels) (toJson (dict "university-ecosystem.io/revocation-store-for" .Values.applicationReleaseName "app.kubernetes.io/instance" .Values.applicationReleaseName)))
-}}
{{- fail "revocation-store release identity and labels are immutable deployment-contract fields" -}}
{{- end -}}
{{- if or
  (ne .Values.redis.auth.existingSecret "revocation-redis-credentials")
  (ne .Values.redis.auth.existingSecretPasswordKey "revocation-redis-password")
-}}
{{- fail "revocation-store credential Secret name and key are immutable" -}}
{{- end -}}
{{- if or
  (ne .Values.redis.image.registry "docker.io")
  (ne .Values.redis.image.repository "redis")
  (ne .Values.redis.image.tag "7.4.11-alpine")
  (ne .Values.redis.image.pullPolicy "Always")
  (ne .Values.redis.metrics.image.registry "docker.io")
  (ne .Values.redis.metrics.image.repository "oliver006/redis_exporter")
  (ne .Values.redis.metrics.image.tag "v1.93.0")
  (ne .Values.redis.metrics.image.pullPolicy "Always")
-}}
{{- fail "revocation-store image identities and pull policies are immutable" -}}
{{- end -}}
{{- if or
  (not (regexMatch "^sha256:[0-9a-f]{64}$" .Values.redis.image.digest))
  (not (regexMatch "^sha256:[0-9a-f]{64}$" .Values.redis.metrics.image.digest))
-}}
{{- fail "revocation-store requires exact immutable image digests before rendering" -}}
{{- end -}}
{{- if or
  (ne (toJson .Values.redis.master.disableCommands) (toJson $expectedCommands))
  (ne .Values.redis.commonConfiguration "maxmemory 384mb\nmaxmemory-policy noeviction\nsave 60 1\nappendonly yes\nappendfsync everysec")
  (ne (toJson .Values.redis.master.resources) (toJson $expectedMasterResources))
  (ne (int .Values.redis.master.count) 1)
  (ne (int .Values.redis.master.revisionHistoryLimit) 10)
  (ne (int .Values.redis.master.terminationGracePeriodSeconds) 30)
  (ne (toJson .Values.redis.master.updateStrategy) (toJson (dict "type" "RollingUpdate")))
  (ne (toJson .Values.redis.master.persistence) (toJson (dict "enabled" true "size" "2Gi")))
  (ne (toJson .Values.redis.master.persistentVolumeClaimRetentionPolicy) (toJson (dict "enabled" true "whenScaled" "Retain" "whenDeleted" "Retain")))
  (ne (toJson .Values.redis.master.pdb) (toJson (dict "minAvailable" 1)))
-}}
{{- fail "revocation-store durability, retention, command, and resource controls are immutable" -}}
{{- end -}}
{{- if or
  (ne (toJson .Values.redis.networkPolicy) (toJson (dict "enabled" true "monitoringNamespace" "monitoring")))
  (ne .Values.redis.metrics.enabled true)
  (ne (int .Values.redis.metrics.port) 9121)
  (ne (toJson .Values.redis.metrics.resources) (toJson $expectedMetricsResources))
-}}
{{- fail "revocation-store network and metrics boundaries are immutable" -}}
{{- end -}}
{{- end -}}
