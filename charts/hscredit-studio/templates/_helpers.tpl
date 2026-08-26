{{/*
通用模板辅助函数
*/}}

{{- define "hscredit-studio.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hscredit-studio.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hscredit-studio.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "hscredit-studio.labels" -}}
helm.sh/chart: {{ include "hscredit-studio.chart" . }}
app.kubernetes.io/name: {{ include "hscredit-studio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: {{ .Values.component | default "core" }}
{{- end -}}

{{- define "hscredit-studio.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hscredit-studio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .Values.component | default "core" }}
{{- end -}}

{{- define "hscredit-studio.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "hscredit-studio.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
