{{/*
Create a default fully qualified app name.
*/}}
{{- define "orbit.fullname" -}}
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

{{/* Shared database configuration for the Catalog API and migration container. */}}
{{- define "orbit.catalog.env" -}}
- name: CATALOG_HOST
  value: {{ include "orbit.fullname" . }}-catalog
- name: CATALOG_PORT
  value: {{ .Values.catalog.service.port | quote }}
{{- range $name, $value := .Values.catalog.env }}
- name: {{ $name }}
  value: {{ $value | quote }}
{{- end }}
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: orbit-catalog-secrets
      key: DB_USER
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: orbit-catalog-secrets
      key: DB_PASSWORD
{{- end }}
