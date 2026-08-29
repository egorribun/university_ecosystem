{{- define "revocation-store.serviceHost" -}}
{{- printf "%s-revocation-redis-master" .Values.applicationReleaseName -}}
{{- end -}}

{{- define "revocation-store.validate" -}}
{{- $expectedFullname := printf "%s-revocation-redis" .Values.applicationReleaseName -}}
{{- if ne .Values.redis.fullnameOverride $expectedFullname -}}
{{- fail "redis.fullnameOverride must equal <applicationReleaseName>-revocation-redis" -}}
{{- end -}}
{{- if ne (index .Values.redis.commonLabels "university-ecosystem.io/revocation-store-for") .Values.applicationReleaseName -}}
{{- fail "redis.commonLabels must bind the store to applicationReleaseName" -}}
{{- end -}}
{{- if ne (index .Values.redis.commonLabels "app.kubernetes.io/instance") .Values.applicationReleaseName -}}
{{- fail "redis.commonLabels app.kubernetes.io/instance must equal applicationReleaseName" -}}
{{- end -}}
{{- end -}}
