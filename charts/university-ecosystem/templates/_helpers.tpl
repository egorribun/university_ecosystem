{{/*
Expand the name of the chart.
*/}}
{{- define "university-ecosystem.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Render a first-party image by immutable digest when one is supplied. */}}
{{- define "university-ecosystem.image" -}}
{{- $root := .root -}}
{{- $image := .image -}}
{{- $registry := $root.Values.global.imageRegistry -}}
{{- if $image.digest -}}
{{- printf "%s/%s@%s" $registry $image.repository $image.digest | trimPrefix "/" -}}
{{- else -}}
{{- $tag := $image.tag | default $root.Values.global.imageTag | default $root.Chart.AppVersion -}}
{{- printf "%s/%s:%s" $registry $image.repository $tag | trimPrefix "/" -}}
{{- end -}}
{{- end }}

{{/* Name of the Secret containing application credentials and JWT keys. */}}
{{- define "university-ecosystem.applicationSecretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.applicationSecrets.existingSecret -}}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "university-ecosystem.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "university-ecosystem.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "university-ecosystem.labels" -}}
helm.sh/chart: {{ include "university-ecosystem.chart" . }}
{{ include "university-ecosystem.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "university-ecosystem.selectorLabels" -}}
app.kubernetes.io/name: {{ include "university-ecosystem.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
