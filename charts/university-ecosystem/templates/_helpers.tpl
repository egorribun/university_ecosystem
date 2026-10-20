{{/*
Expand the name of the chart.
*/}}
{{- define "university-ecosystem.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Fail closed without including untrusted address text in the diagnostic. */}}
{{- define "university-ecosystem.invalidTrustedProxy" -}}
{{- fail (printf "%s entries must be valid IP addresses or CIDRs" .fieldPath) -}}
{{- end -}}

{{/* Parse IPv4 octets as decimal, including zero-padded spellings. */}}
{{- define "university-ecosystem.parseTrustedProxyIPv4Octets" -}}
{{- $fieldPath := .fieldPath -}}
{{- $parts := splitList "." .address -}}
{{- if ne (len $parts) 4 -}}
  {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
{{- end -}}
{{- $octets := list -}}
{{- range $part := $parts -}}
  {{- if not (regexMatch "^[0-9]{1,3}$" $part) -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $number := atoi $part -}}
  {{- if or (lt $number 0) (gt $number 255) -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $octets = append $octets $part -}}
{{- end -}}
{{- toJson $octets -}}
{{- end -}}

{{/* Validate and canonicalize one IPv6 hextet. */}}
{{- define "university-ecosystem.normalizeTrustedProxyIPv6Hextet" -}}
{{- $fieldPath := .fieldPath -}}
{{- $hextet := lower .hextet -}}
{{- if not (regexMatch "^[0-9a-f]{1,4}$" $hextet) -}}
  {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
{{- end -}}
{{- $normalized := regexReplaceAll "^0+" $hextet "" -}}
{{- if eq $normalized "" -}}
  {{- "0" -}}
{{- else -}}
  {{- $normalized -}}
{{- end -}}
{{- end -}}

{{/* Parse colon-separated IPv6 hextets into normalized strings. */}}
{{- define "university-ecosystem.parseTrustedProxyIPv6Hextets" -}}
{{- $fieldPath := .fieldPath -}}
{{- $text := .text -}}
{{- $hextets := list -}}
{{- if ne $text "" -}}
  {{- range $hextet := splitList ":" $text -}}
    {{- $hextets = append $hextets (include "university-ecosystem.normalizeTrustedProxyIPv6Hextet" (dict "fieldPath" $fieldPath "hextet" $hextet)) -}}
  {{- end -}}
{{- end -}}
{{- toJson $hextets -}}
{{- end -}}

{{/*
Parse a proxy address/CIDR and return normalized classification facts.
The broad-private and IPv6 allocation checks reject complete designated blocks
and supernets covering them; narrower configured subnets remain eligible peers.
*/}}
{{- define "university-ecosystem.parseTrustedProxy" -}}
{{- $fieldPath := .fieldPath -}}
{{- $parts := splitList "/" (trim .proxy) -}}
{{- if gt (len $parts) 2 -}}
  {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
{{- end -}}
{{- $address := trim (index $parts 0) -}}
{{- if eq $address "" -}}
  {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
{{- end -}}
{{- $hasPrefix := eq (len $parts) 2 -}}
{{- $prefixText := "" -}}
{{- if $hasPrefix -}}
  {{- $prefixText = index $parts 1 -}}
  {{- if not (regexMatch "^[0-9]+$" $prefixText) -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $prefixText = regexReplaceAll "^0+" $prefixText "" -}}
  {{- if eq $prefixText "" -}}
    {{- $prefixText = "0" -}}
  {{- end -}}
  {{- if gt (len $prefixText) 3 -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
{{- end -}}
{{- if contains ":" $address -}}
  {{- if contains "%" $address -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- if contains "." $address -}}
    {{- $addressParts := splitList ":" $address -}}
    {{- if lt (len $addressParts) 2 -}}
      {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
    {{- end -}}
    {{- $lastIndex := sub (len $addressParts) 1 -}}
    {{- $ipv4Text := index $addressParts $lastIndex -}}
    {{- $ipv4Octets := fromJsonArray (include "university-ecosystem.parseTrustedProxyIPv4Octets" (dict "fieldPath" $fieldPath "address" $ipv4Text)) -}}
    {{- $high := add (mul (atoi (index $ipv4Octets 0)) 256) (atoi (index $ipv4Octets 1)) -}}
    {{- $low := add (mul (atoi (index $ipv4Octets 2)) 256) (atoi (index $ipv4Octets 3)) -}}
    {{- $address = printf "%s:%x:%x" (trimSuffix (printf ":%s" $ipv4Text) $address) $high $low -}}
  {{- end -}}
  {{- if regexMatch ".*::.*::.*" $address -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $groups := list -}}
  {{- if contains "::" $address -}}
    {{- $halves := splitList "::" $address -}}
    {{- if ne (len $halves) 2 -}}
      {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
    {{- end -}}
    {{- $left := fromJsonArray (include "university-ecosystem.parseTrustedProxyIPv6Hextets" (dict "fieldPath" $fieldPath "text" (index $halves 0))) -}}
    {{- $right := fromJsonArray (include "university-ecosystem.parseTrustedProxyIPv6Hextets" (dict "fieldPath" $fieldPath "text" (index $halves 1))) -}}
    {{- $missing := sub 8 (add (len $left) (len $right)) -}}
    {{- if lt $missing 1 -}}
      {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
    {{- end -}}
    {{- $groups = $left -}}
    {{- range $fill := until (int $missing) -}}
      {{- $groups = append $groups "0" -}}
    {{- end -}}
    {{- range $hextet := $right -}}
      {{- $groups = append $groups $hextet -}}
    {{- end -}}
  {{- else -}}
    {{- $groups = fromJsonArray (include "university-ecosystem.parseTrustedProxyIPv6Hextets" (dict "fieldPath" $fieldPath "text" $address)) -}}
    {{- if ne (len $groups) 8 -}}
      {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
    {{- end -}}
  {{- end -}}
  {{- $prefix := 128 -}}
  {{- if $hasPrefix -}}
    {{- $prefix = atoi $prefixText -}}
  {{- end -}}
  {{- if gt $prefix 128 -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $isMapped := and (eq (index $groups 0) "0") (eq (index $groups 1) "0") (eq (index $groups 2) "0") (eq (index $groups 3) "0") (eq (index $groups 4) "0") (eq (index $groups 5) "ffff") -}}
  {{- $isBroadIPv6HalfSpace := eq $prefix 1 -}}
  {{- $firstHextetPadded := replace " " "0" (printf "%04s" (index $groups 0)) -}}
  {{- $hexNibbleBits := dict "0" "0000" "1" "0001" "2" "0010" "3" "0011" "4" "0100" "5" "0101" "6" "0110" "7" "0111" "8" "1000" "9" "1001" "a" "1010" "b" "1011" "c" "1100" "d" "1101" "e" "1110" "f" "1111" -}}
  {{- $firstHextetBits := printf "%s%s" (get $hexNibbleBits (substr 0 1 $firstHextetPadded)) (get $hexNibbleBits (substr 1 2 $firstHextetPadded)) -}}
  {{- $broadIPv6UniqueLocal := false -}}
  {{- if and (gt $prefix 0) (le $prefix 7) -}}
    {{- $targetBits := substr 0 $prefix "1111110" -}}
    {{- $networkBits := substr 0 $prefix $firstHextetBits -}}
    {{- $broadIPv6UniqueLocal = eq $networkBits $targetBits -}}
  {{- end -}}
  {{- $broadIPv6GlobalUnicast := false -}}
  {{- if and (gt $prefix 0) (le $prefix 3) -}}
    {{- $targetBits := substr 0 $prefix "001" -}}
    {{- $networkBits := substr 0 $prefix $firstHextetBits -}}
    {{- $broadIPv6GlobalUnicast = eq $networkBits $targetBits -}}
  {{- end -}}
  {{- $isMappedLoopback := false -}}
  {{- $isMappedNonLoopback := false -}}
  {{- $isMappedUniversal := false -}}
  {{- if $isMapped -}}
    {{- if eq $prefix 96 -}}
      {{- $isMappedUniversal = true -}}
    {{- else -}}
      {{- $group6Padded := replace " " "0" (printf "%04s" (index $groups 6)) -}}
      {{- $mappedFirstOctet := substr 0 2 $group6Padded -}}
      {{- if and (ge $prefix 104) (eq $mappedFirstOctet "7f") -}}
        {{- $isMappedLoopback = true -}}
      {{- else -}}
        {{- $isMappedNonLoopback = true -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
  {{- $allButLastZero := and (eq (index $groups 0) "0") (eq (index $groups 1) "0") (eq (index $groups 2) "0") (eq (index $groups 3) "0") (eq (index $groups 4) "0") (eq (index $groups 5) "0") (eq (index $groups 6) "0") -}}
  {{- $lastGroup := index $groups 7 -}}
  {{- $isOnlyUnspecifiedOrLoopback := and (ge $prefix 127) $allButLastZero (or (eq $lastGroup "0") (eq $lastGroup "1")) (not $isMapped) -}}
  {{- $result := dict
    "family" "ipv6"
    "universal" (eq $prefix 0)
    "loopback" (or $isMappedLoopback $isOnlyUnspecifiedOrLoopback)
    "broadPrivate" false
    "broadIPv6HalfSpace" $isBroadIPv6HalfSpace
    "broadIPv6UniqueLocal" $broadIPv6UniqueLocal
    "broadIPv6GlobalUnicast" $broadIPv6GlobalUnicast
    "mappedNonLoopback" $isMappedNonLoopback
    "mappedUniversal" $isMappedUniversal
  -}}
  {{- toJson $result -}}
{{- else -}}
  {{- $octets := fromJsonArray (include "university-ecosystem.parseTrustedProxyIPv4Octets" (dict "fieldPath" $fieldPath "address" $address)) -}}
  {{- $prefix := 32 -}}
  {{- if $hasPrefix -}}
    {{- $prefix = atoi $prefixText -}}
  {{- end -}}
  {{- if gt $prefix 32 -}}
    {{- include "university-ecosystem.invalidTrustedProxy" (dict "fieldPath" $fieldPath) -}}
  {{- end -}}
  {{- $universal := eq $prefix 0 -}}
  {{- $loopback := and (ge $prefix 8) (eq (atoi (index $octets 0)) 127) -}}
  {{- $addressBits := "" -}}
  {{- range $octet := $octets -}}
    {{- $addressBits = printf "%s%08b" $addressBits (atoi $octet) -}}
  {{- end -}}
  {{- $broadPrivate := false -}}
  {{- if not $universal -}}
    {{- $privateRanges := list (dict "prefix" 8 "bits" "00001010") (dict "prefix" 12 "bits" "101011000001") (dict "prefix" 16 "bits" "1100000010101000") -}}
    {{- range $privateRange := $privateRanges -}}
      {{- $rangePrefix := index $privateRange "prefix" -}}
      {{- if and (le $prefix $rangePrefix) (eq (substr 0 $prefix $addressBits) (substr 0 $prefix (index $privateRange "bits"))) -}}
        {{- $broadPrivate = true -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
  {{- $result := dict
    "family" "ipv4"
    "universal" $universal
    "loopback" $loopback
    "broadPrivate" $broadPrivate
    "broadIPv6HalfSpace" false
    "broadIPv6UniqueLocal" false
    "broadIPv6GlobalUnicast" false
    "mappedNonLoopback" false
    "mappedUniversal" false
  -}}
  {{- toJson $result -}}
{{- end -}}
{{- end -}}

{{/* Require deployment-selected trusted proxy peers for an exposed edge route. */}}
{{- define "university-ecosystem.requireIngressProxyPeers" -}}
{{- $fieldPath := .fieldPath -}}
{{- $proxies := .proxies -}}
{{- $hasNonLoopbackPeer := false -}}
{{- $hasUniversalRoute := false -}}
{{- $hasMappedUniversal := false -}}
{{- $hasMappedNonLoopback := false -}}
{{- $hasBroadPrivateRoute := false -}}
{{- $hasBroadIPv6HalfSpace := false -}}
{{- $hasBroadIPv6UniqueLocal := false -}}
{{- $hasBroadIPv6GlobalUnicast := false -}}
{{- range $proxy := $proxies -}}
  {{- if ne (trim $proxy) "" -}}
    {{- $parsed := fromJson (include "university-ecosystem.parseTrustedProxy" (dict "fieldPath" $fieldPath "proxy" $proxy)) -}}
    {{- if get $parsed "universal" -}}
      {{- $hasUniversalRoute = true -}}
    {{- end -}}
    {{- if get $parsed "mappedUniversal" -}}
      {{- $hasMappedUniversal = true -}}
    {{- end -}}
    {{- if get $parsed "mappedNonLoopback" -}}
      {{- $hasMappedNonLoopback = true -}}
    {{- end -}}
    {{- if get $parsed "broadPrivate" -}}
      {{- $hasBroadPrivateRoute = true -}}
    {{- end -}}
    {{- if get $parsed "broadIPv6HalfSpace" -}}
      {{- $hasBroadIPv6HalfSpace = true -}}
    {{- end -}}
    {{- if get $parsed "broadIPv6UniqueLocal" -}}
      {{- $hasBroadIPv6UniqueLocal = true -}}
    {{- end -}}
    {{- if get $parsed "broadIPv6GlobalUnicast" -}}
      {{- $hasBroadIPv6GlobalUnicast = true -}}
    {{- end -}}
    {{- if and (not (get $parsed "loopback")) (not (get $parsed "mappedNonLoopback")) -}}
      {{- $hasNonLoopbackPeer = true -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if $hasUniversalRoute -}}
  {{- fail (printf "%s must not trust 0.0.0.0/0 or ::/0; configure explicit ingress proxy CIDRs" $fieldPath) -}}
{{- end -}}
{{- if $hasMappedUniversal -}}
  {{- fail (printf "%s must not trust the IPv4-mapped IPv6 all-IPv4 range; use native IPv4 addresses or CIDRs" $fieldPath) -}}
{{- end -}}
{{- if $hasMappedNonLoopback -}}
  {{- fail (printf "%s contains IPv4-mapped IPv6 peers; use native IPv4 addresses or CIDRs" $fieldPath) -}}
{{- end -}}
{{- if $hasBroadPrivateRoute -}}
  {{- fail (printf "%s must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR" $fieldPath) -}}
{{- end -}}
{{- if $hasBroadIPv6HalfSpace -}}
  {{- fail (printf "%s must not trust an IPv6 /1 half-space; configure explicit ingress proxy CIDRs" $fieldPath) -}}
{{- end -}}
{{- if $hasBroadIPv6UniqueLocal -}}
  {{- fail (printf "%s must not trust the IPv6 unique-local block fc00::/7 or a supernet covering it; use a narrower explicit ingress CIDR" $fieldPath) -}}
{{- end -}}
{{- if $hasBroadIPv6GlobalUnicast -}}
  {{- fail (printf "%s must not trust the IPv6 global-unicast block 2000::/3 or a supernet covering it; use a narrower explicit ingress CIDR" $fieldPath) -}}
{{- end -}}
{{- if not $hasNonLoopbackPeer -}}
  {{- fail (printf "%s requires explicit non-loopback ingress proxy CIDRs" $fieldPath) -}}
{{- end -}}
{{- end -}}
{{/* Render a first-party image by immutable digest when one is supplied. */}}
{{- define "university-ecosystem.image" -}}
{{- $root := .root -}}
{{- $image := .image -}}
{{- $global := $root.Values.global | default dict -}}
{{- $registry := $global.imageRegistry | default "" -}}
{{- $digest := $image.digest | default "" -}}
{{- if and (not $digest) (eq $image.repository "university-backend") -}}
{{- $digest = $global.backendImageDigest | default "" -}}
{{- end -}}
{{- if $digest -}}
{{- printf "%s/%s@%s" $registry $image.repository $digest | trimPrefix "/" -}}
{{- else -}}
{{- $tag := $image.tag | default $global.imageTag | default $root.Chart.AppVersion -}}
{{- printf "%s/%s:%s" $registry $image.repository $tag | trimPrefix "/" -}}
{{- end -}}
{{- end }}

{{/*
Public frontend origin. An explicit backend.config.frontendOrigin wins;
otherwise it is derived from the first ingress host. Empty (the application
falls back to its local development default) when neither is configured.
*/}}
{{- define "university-ecosystem.frontendOrigin" -}}
{{- if .Values.backend.config.frontendOrigin -}}
{{- .Values.backend.config.frontendOrigin | trimSuffix "/" -}}
{{- else if and .Values.ingress.enabled .Values.ingress.hosts -}}
{{- printf "https://%s" (index .Values.ingress.hosts 0).host -}}
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
Keep first-party Service names within 63 characters without losing the component.
Already-valid short names and the root fullname remain unchanged.
*/}}
{{- define "university-ecosystem.componentName" -}}
{{- $suffix := printf "-%s" .component -}}
{{- $budget := int (sub 63 (len $suffix)) -}}
{{- $base := include "university-ecosystem.fullname" .root -}}
{{- printf "%s%s" ($base | trunc $budget | trimSuffix "-") $suffix -}}
{{- end -}}

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

{{/*
AUD-189: TCP 443 egress for backup, backend, file-processor and outbox-worker.
Public destinations are reachable; cluster, private and link-local ranges are
excepted, including cloud metadata. Owner-verified private HTTPS endpoints are
added explicitly through networkPolicy.httpsEgress.privateCIDRs.
*/}}
{{- define "university-ecosystem.httpsEgressRules" -}}
- to:
    - ipBlock:
        cidr: "0.0.0.0/0"
        except:
{{- range .Values.networkPolicy.httpsEgress.exceptIPv4CIDRs }}
          - {{ . | quote }}
{{- end }}
    - ipBlock:
        cidr: "::/0"
        except:
{{- range .Values.networkPolicy.httpsEgress.exceptIPv6CIDRs }}
          - {{ . | quote }}
{{- end }}
  ports:
    - protocol: TCP
      port: 443
{{- range $cidr := .Values.networkPolicy.httpsEgress.privateCIDRs }}
{{- if regexMatch "/0$" (toString $cidr) }}
{{- fail (printf "networkPolicy.httpsEgress.privateCIDRs entry %q must not be a /0 range" $cidr) }}
{{- end }}
- to:
    - ipBlock:
        cidr: {{ $cidr | quote }}
  ports:
    - protocol: TCP
      port: 443
{{- end }}
{{- end -}}
