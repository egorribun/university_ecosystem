{{- define "redis.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "redis.commonLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/name: redis
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "redis.masterSelectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/name: redis
app.kubernetes.io/component: master
{{- end -}}

{{- define "redis.image" -}}
{{- $registry := default "docker.io" .Values.image.registry -}}
{{- $repo := .Values.image.repository -}}
{{- if .Values.image.digest -}}
{{- printf "%s/%s@%s" $registry $repo .Values.image.digest -}}
{{- else -}}
{{- printf "%s/%s:%s" $registry $repo .Values.image.tag -}}
{{- end -}}
{{- end -}}

{{- define "redis.metricsImage" -}}
{{- $registry := default "docker.io" .Values.metrics.image.registry -}}
{{- $repo := .Values.metrics.image.repository -}}
{{- if .Values.metrics.image.digest -}}
{{- printf "%s/%s@%s" $registry $repo .Values.metrics.image.digest -}}
{{- else -}}
{{- printf "%s/%s:%s" $registry $repo .Values.metrics.image.tag -}}
{{- end -}}
{{- end -}}

{{- define "redis.metricsPasswordFileInitImage" -}}
{{- $global := .Values.global | default dict -}}
{{- $image := .Values.metrics.passwordFileInitImage -}}
{{- $registry := $global.imageRegistry | default "" -}}
{{- $digest := $image.digest | default "" -}}
{{- if and (not $digest) (eq $image.repository "university-backend") -}}
{{- $digest = $global.backendImageDigest | default "" -}}
{{- end -}}
{{- if $digest -}}
{{- printf "%s/%s@%s" $registry $image.repository $digest | trimPrefix "/" -}}
{{- else -}}
{{- $tag := $image.tag | default $global.imageTag | default "1.0.0" -}}
{{- printf "%s/%s:%s" $registry $image.repository $tag | trimPrefix "/" -}}
{{- end -}}
{{- end -}}
