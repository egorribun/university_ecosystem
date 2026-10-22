{{- define "university-ecosystem.secretVolumeMounts" -}}
{{- $secrets := dict -}}
{{- range .secrets -}}
{{- $id := required "secret volume id must be set" .id -}}
{{- $secretName := required (printf "secret volume %s must set secretName" $id) .secretName -}}
{{- $keys := required (printf "secret volume %s must set keys" $id) .keys -}}
{{- if hasKey $secrets $secretName -}}
{{- $entry := get $secrets $secretName -}}
{{- range $keys -}}
{{- if not (has . $entry.keys) -}}
{{- $_ := set $entry "keys" (append $entry.keys .) -}}
{{- end -}}
{{- end -}}
{{- else -}}
{{- $_ := set $secrets $secretName (dict "id" $id "secretName" $secretName "keys" ($keys | uniq)) -}}
{{- end -}}
{{- end -}}
{{- range $secretName, $secret := $secrets }}
- name: {{ printf "secret-%s" $secret.id }}
  mountPath: {{ printf "/run/secrets/%s" $secretName | quote }}
  readOnly: true
{{- end }}
{{- end }}

{{- define "university-ecosystem.secretVolumes" -}}
{{- $secrets := dict -}}
{{- range .secrets -}}
{{- $id := required "secret volume id must be set" .id -}}
{{- $secretName := required (printf "secret volume %s must set secretName" $id) .secretName -}}
{{- $keys := required (printf "secret volume %s must set keys" $id) .keys -}}
{{- if hasKey $secrets $secretName -}}
{{- $entry := get $secrets $secretName -}}
{{- range $keys -}}
{{- if not (has . $entry.keys) -}}
{{- $_ := set $entry "keys" (append $entry.keys .) -}}
{{- end -}}
{{- end -}}
{{- else -}}
{{- $_ := set $secrets $secretName (dict "id" $id "secretName" $secretName "keys" ($keys | uniq)) -}}
{{- end -}}
{{- end -}}
{{- range $secretName, $secret := $secrets }}
- name: {{ printf "secret-%s" $secret.id }}
  secret:
    secretName: {{ $secretName | quote }}
    defaultMode: 0440
    items:
      {{- range $secret.keys }}
      - key: {{ . | quote }}
        path: {{ . | quote }}
      {{- end }}
{{- end }}
{{- end }}
