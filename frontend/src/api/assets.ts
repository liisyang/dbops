import request from './request'
import type {
  AssetEventRow,
  AssetVerifyLaunchPayload,
  AssetVerifyLaunchResponse,
  BusinessContactLinkPayload,
  ClusterDetail,
  ClusterRow,
  ClusterUpsertPayload,
  CollectorCheckDefinitionRow,
  ContactRow,
  ContactUpsertPayload,
  DbInstanceUpsertPayload,
  DbTypeRow,
  ImportBatchRow,
  ImportExecuteResult,
  ImportPreviewResult,
  CollectorRunRow,
  CollectorRunCreatePayload,
  CollectorRunCreateResponse,
  CollectorRunItemRow,
  CollectorEndpointRow,
  PortProfileRow,
  AssetChangeProposalRow,
  BatchRunRow,
  BatchRunCreatePayload,
  BatchRunCreateResponse,
  BatchRunItemRow,
  DispatchRunRow,
  RetryFailedPayload,
  InstanceDetail,
  InstanceListResponse,
  ServerDetail,
  ServerDropdownRow,
  ServerListResponse,
  ServerUpsertPayload,
  BusinessSystemUpsertPayload,
  SystemDetail,
  SystemRow,
  CredentialProfileRow,
  CredentialProfileCreatePayload,
  CredentialProfileUpdatePayload,
  CredentialBindingRow,
  CredentialBindingCreatePayload,
  CredentialBindingUpdatePayload,
  AssetFactSnapshotRow,
  AssetFactSnapshotSummary,
  AssetDriftRecordRow,
  InspectionItemRow,
  InspectionItemCreatePayload,
  InspectionItemUpdatePayload,
  InspectionTaskRow,
  InspectionTaskCreatePayload,
  InspectionTaskCreateResponse,
  InspectionResultRow,
  InspectionReportRow,
  InspectionReportListResponse,
  InspectionInstanceReportRow,
} from '@/types/api'

export const assetsApi = {
  listServers: (params?: Record<string, any>): Promise<ServerListResponse> =>
    request.get('/v1/servers/servers', { params }),
  getServer: (id: number | string): Promise<ServerDetail> =>
    request.get(`/v1/servers/servers/${id}`),
  createServer: (data: ServerUpsertPayload) =>
    request.post('/v1/servers/servers', data),
  updateServer: (id: number | string, data: ServerUpsertPayload) =>
    request.put(`/v1/servers/servers/${id}`, data),
  deleteServer: (id: number | string) =>
    request.delete(`/v1/servers/servers/${id}`),

  listInstances: (params?: Record<string, any>): Promise<InstanceListResponse> =>
    request.get('/v1/servers/instances', { params }),
  getInstance: (id: number | string, options?: { suppressErrorToast?: boolean }): Promise<InstanceDetail> =>
    request.get(`/v1/servers/instances/${id}`, { suppressErrorToast: options?.suppressErrorToast }),
  launchAssetVerify: (id: number | string, data: AssetVerifyLaunchPayload): Promise<AssetVerifyLaunchResponse> =>
    request.post(`/v1/automation/asset-verify/${id}/launch`, data),
  createCollectorRun: (data: CollectorRunCreatePayload): Promise<CollectorRunCreateResponse> =>
    request.post('/v1/collector/runs', data),
  getCollectorRun: (runId: string): Promise<CollectorRunRow> =>
    request.get(`/v1/collector/runs/${runId}`),
  listCollectorRunItems: (runId: string, options?: { suppressErrorToast?: boolean }): Promise<CollectorRunItemRow[]> =>
    request.get(`/v1/collector/runs/${runId}/items`, { suppressErrorToast: options?.suppressErrorToast }),
  listInstanceCollectorRuns: (
    id: number | string,
    params?: { limit?: number },
    options?: { suppressErrorToast?: boolean }
  ): Promise<CollectorRunRow[]> =>
    request.get(`/v1/collector/instances/${id}/runs`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listServerCollectorRuns: (
    id: number | string,
    params?: { limit?: number },
    options?: { suppressErrorToast?: boolean }
  ): Promise<CollectorRunRow[]> =>
    request.get(`/v1/collector/servers/${id}/runs`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listCollectorEndpoints: (
    params?: { entity_type?: string; entity_id?: number },
    options?: { suppressErrorToast?: boolean }
  ): Promise<CollectorEndpointRow[]> =>
    request.get('/v1/collector/endpoints', {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listAssetCollectorEndpoints: (
    targetScope: 'server' | 'db_instance',
    assetId: number | string,
    options?: { suppressErrorToast?: boolean }
  ): Promise<CollectorEndpointRow[]> =>
    request.get(`/v1/collector/assets/${targetScope}/${assetId}/endpoints`, {
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listPortProfiles: (
    params?: { target_scope?: string; db_type_code?: string; os_family?: string; is_enabled?: boolean }
  ): Promise<PortProfileRow[]> =>
    request.get('/v1/collector/port-profiles', { params }),

  // 资产校验功能优化 v2 / Follow-up A / 2026-06-17:
  // 检查项定义查询 — 替代 BatchVerify.vue 硬编码 7 个 check_code 列表。
  // suppressErrorToast: 表单 mount 失败时静默降级到 []，避免每次切 radio 触发 toast。
  listCheckCodes: (
    params?: { target_scope?: string; task_type?: string; is_enabled?: boolean },
    options?: { suppressErrorToast?: boolean }
  ): Promise<CollectorCheckDefinitionRow[]> =>
    request.get('/v1/collector/check-codes', {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listCollectorProposals: (
    params?: { target_type?: string; target_id?: number; proposal_type?: string; status?: string; source_run_id?: string | number; batch_run_id?: number },
    options?: { suppressErrorToast?: boolean }
  ): Promise<AssetChangeProposalRow[]> =>
    request.get('/v1/collector/proposals', {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  approveCollectorProposal: (proposalId: number | string): Promise<AssetChangeProposalRow> =>
    request.post(`/v1/collector/proposals/${proposalId}/approve`, {}),
  rejectCollectorProposal: (proposalId: number | string, data?: { reason?: string }): Promise<AssetChangeProposalRow> =>
    request.post(`/v1/collector/proposals/${proposalId}/reject`, data || {}),
  applyCollectorProposal: (proposalId: number | string): Promise<AssetChangeProposalRow> =>
    request.post(`/v1/collector/proposals/${proposalId}/apply`, {}),

  listClusters: (): Promise<ClusterRow[]> =>
    request.get('/v1/servers/clusters'),
  getCluster: (id: number | string): Promise<ClusterDetail> =>
    request.get(`/v1/servers/clusters/${id}`),
  getClusterInstances: (clusterId: number | string): Promise<InstanceDetail[]> =>
    request.get(`/v1/servers/clusters/${clusterId}/instances`),
  createCluster: (data: ClusterUpsertPayload) =>
    request.post('/v1/servers/clusters', data),
  updateCluster: (id: number | string, data: ClusterUpsertPayload) =>
    request.put(`/v1/servers/clusters/${id}`, data),
  deleteCluster: (id: number | string) =>
    request.delete(`/v1/servers/clusters/${id}`),

  listDbTypes: (): Promise<DbTypeRow[]> =>
    request.get('/v1/servers/dicts/db-types'),
  listServersDropdown: (): Promise<ServerDropdownRow[]> =>
    request.get('/v1/servers/dicts/servers-dropdown'),

  createDbInstance: (data: DbInstanceUpsertPayload) =>
    request.post('/v1/servers/dbinstances', data),
  updateDbInstance: (id: number | string, data: DbInstanceUpsertPayload) =>
    request.put(`/v1/servers/dbinstances/${id}`, data),
  deleteDbInstance: (id: number | string) =>
    request.delete(`/v1/servers/dbinstances/${id}`),

  listContacts: (): Promise<ContactRow[]> =>
    request.get('/v1/servers/contacts'),
  createContact: (data: ContactUpsertPayload) =>
    request.post('/v1/servers/contacts', data),
  updateContact: (id: number | string, data: ContactUpsertPayload) =>
    request.put(`/v1/servers/contacts/${id}`, data),
  deleteContact: (id: number | string) =>
    request.delete(`/v1/servers/contacts/${id}`),

  listBusinessSystems: (): Promise<SystemRow[]> =>
    request.get('/v1/servers/business-services'),
  getBusinessSystem: (id: number | string): Promise<SystemDetail> =>
    request.get(`/v1/servers/business-services/${id}`),
  createBusinessSystem: (data: BusinessSystemUpsertPayload) =>
    request.post('/v1/servers/business-services', data),
  updateBusinessSystem: (id: number | string, data: BusinessSystemUpsertPayload) =>
    request.put(`/v1/servers/business-services/${id}`, data),
  addBusinessSystemContact: (id: number | string, data: BusinessContactLinkPayload) =>
    request.post(`/v1/servers/business-services/${id}/contacts`, data),
  deleteBusinessSystemContact: (systemId: number | string, contactId: number | string, roleCode: string) =>
    request.delete(`/v1/servers/business-services/${systemId}/contacts/${contactId}/${roleCode}`),
  listBusinessSystemHistory: (id: number | string): Promise<AssetEventRow[]> =>
    request.get(`/v1/servers/business-services/${id}/lifecycle/history`),
  changeBusinessSystemLifecycle: (
    id: number | string,
    data: {
      action: 'building' | 'pending' | 'active' | 'retired'
      reason?: string | null
      remark?: string | null
      lifecycle_context?: Record<string, any>
    }
  ) => request.post(`/v1/servers/business-services/${id}/lifecycle`, data),

  previewImport: (data: FormData): Promise<ImportPreviewResult> =>
    request.post('/v1/servers/imports/preview', data),
  executeImport: (data: FormData): Promise<ImportExecuteResult> =>
    request.post('/v1/servers/imports/execute', data),
  getImportBatches: (): Promise<ImportBatchRow[]> =>
    request.get('/v1/servers/imports/batches'),

  // Phase 3.2 — Batch verify
  createBatchRun: (data: BatchRunCreatePayload): Promise<BatchRunCreateResponse> =>
    request.post('/v1/collector/batch-runs', data),
  listBatchRuns: (params?: Record<string, any>, config?: Record<string, any>): Promise<BatchRunRow[]> =>
    // M1 (40-tech-debt.md): when both the explicit `params` arg and a
    // `config.params` key are present, the explicit filter must win;
    // otherwise a caller-supplied config silently overrides the visible
    // query string. We only inject `params` when it is defined, so that
    // `listBatchRuns(undefined, { params: {...} })` still forwards the
    // config-side query string (the previous { params, ...config }
    // pattern lost config.params in that case too — same shape of bug).
    request.get('/v1/collector/batch-runs', {
      ...config,
      ...(params !== undefined && { params }),
    }),
  getBatchRun: (id: number | string, config?: Record<string, any>): Promise<BatchRunRow> =>
    request.get(`/v1/collector/batch-runs/${id}`, config),
  listBatchDispatches: (id: number | string): Promise<DispatchRunRow[]> =>
    request.get(`/v1/collector/batch-runs/${id}/dispatches`),
  listBatchItems: (
    id: number | string,
    params?: Record<string, any>,
    options?: { suppressErrorToast?: boolean }
  ): Promise<BatchRunItemRow[]> =>
    request.get(`/v1/collector/batch-runs/${id}/items`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  retryFailedBatchItems: (
    id: number | string,
    data?: RetryFailedPayload
  ): Promise<any> =>
    request.post(`/v1/collector/batch-runs/${id}/retry-failed`, data || { scope: 'failed' }),
  cancelBatchRun: (id: number | string): Promise<any> =>
    request.post(`/v1/collector/batch-runs/${id}/cancel`),

  // Phase 3.3A — Credential profiles
  listCredentialProfiles: (): Promise<CredentialProfileRow[]> =>
    request.get('/v1/credentials/profiles'),
  createCredentialProfile: (data: CredentialProfileCreatePayload): Promise<CredentialProfileRow> =>
    request.post('/v1/credentials/profiles', data),
  updateCredentialProfile: (id: number | string, data: CredentialProfileUpdatePayload): Promise<CredentialProfileRow> =>
    request.put(`/v1/credentials/profiles/${id}`, data),

  // Phase 3.3A — Credential bindings
  listCredentialBindings: (params?: Record<string, any>): Promise<CredentialBindingRow[]> =>
    request.get('/v1/credentials/bindings', { params }),
  createCredentialBinding: (data: CredentialBindingCreatePayload): Promise<CredentialBindingRow> =>
    request.post('/v1/credentials/bindings', data),
  updateCredentialBinding: (id: number | string, data: CredentialBindingUpdatePayload): Promise<CredentialBindingRow> =>
    request.put(`/v1/credentials/bindings/${id}`, data),
  deleteCredentialBinding: (id: number | string): Promise<any> =>
    request.delete(`/v1/credentials/bindings/${id}`),

  // Phase 3.3A — Asset facts
  getLatestAssetFacts: (
    targetType: string,
    targetId: number | string,
    options?: { suppressErrorToast?: boolean }
  ): Promise<AssetFactSnapshotRow | null> =>
    request.get(`/v1/assets/${targetType}/${targetId}/facts/latest`, {
      suppressErrorToast: options?.suppressErrorToast,
    }),
  getAssetFactHistory: (
    targetType: string,
    targetId: number | string,
    params?: { limit?: number },
    options?: { suppressErrorToast?: boolean }
  ): Promise<AssetFactSnapshotSummary[]> =>
    request.get(`/v1/assets/${targetType}/${targetId}/facts/history`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),

  // Phase 3.3A — Asset drifts
  getAssetDrifts: (
    targetType: string,
    targetId: number | string,
    params?: { is_resolved?: boolean },
    options?: { suppressErrorToast?: boolean }
  ): Promise<AssetDriftRecordRow[]> =>
    request.get(`/v1/assets/${targetType}/${targetId}/drifts`, {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),
  listAllAssetDrifts: (
    params?: { target_type?: string; is_resolved?: boolean },
    options?: { suppressErrorToast?: boolean }
  ): Promise<AssetDriftRecordRow[]> =>
    request.get('/v1/assets/drifts', {
      params,
      suppressErrorToast: options?.suppressErrorToast,
    }),

  // Phase 3.4 — Inspection center
  listInspectionItems: (params?: { enabled?: boolean; db_type_code?: string; source?: string; inspection_type?: string }): Promise<InspectionItemRow[]> =>
    request.get('/v1/inspection/items', { params }),
  listInspectionTypes: (): Promise<string[]> =>
    request.get('/v1/inspection/types'),
  batchDisableInspectionItems: (item_ids: number[]): Promise<{ disabled: number[]; skipped: number[]; total: number }> =>
    request.post('/v1/inspection/items/batch-disable', { item_ids }),
  createInspectionItem: (data: InspectionItemCreatePayload): Promise<InspectionItemRow> =>
    request.post('/v1/inspection/items', data),
  updateInspectionItem: (id: number | string, data: InspectionItemUpdatePayload): Promise<InspectionItemRow> =>
    request.put(`/v1/inspection/items/${id}`, data),
  listInspectionTasks: (params?: { limit?: number }): Promise<InspectionTaskRow[]> =>
    request.get('/v1/inspection/tasks', { params }),
  getInspectionTask: (id: number | string): Promise<InspectionTaskRow> =>
    request.get(`/v1/inspection/tasks/${id}`),
  createInspectionTask: (data: InspectionTaskCreatePayload): Promise<InspectionTaskCreateResponse> =>
    request.post('/v1/inspection/tasks', data),
  listInspectionResults: (
    params?: {
      task_id?: number
      target_type?: 'db_instance' | 'server'
      target_id?: number
      result_status?: string
      limit?: number
    }
  ): Promise<InspectionResultRow[]> =>
    request.get('/v1/inspection/results', { params }),

  // Phase 3.5: SQL safety + verify-sql endpoints (frontend polls
  // verify_sql_result while AWX runs the one-shot SQL).
  validateInspectionSql: (payload: {
    db_type_code: string
    sql_text: string
  }): Promise<{
    valid: boolean
    sql_hash: string
    message: string
    errors: string[]
  }> => request.post('/v1/inspection/items/validate-sql', payload),

  verifyInspectionSql: (payload: {
    instance_ids: number[]
    db_type_code: string
    sql_text: string
    timeout_seconds?: number
    max_rows?: number
  }): Promise<{
    verify_run_ids: number[]
    collector_run_ids: string[]
    status: string
    awx_job_id: number | null
  }> => request.post('/v1/inspection/items/verify-sql', payload),

  getVerifySqlResult: (verifyRunId: number): Promise<{
    success: boolean
    verified: boolean
    sql_hash: string
    duration_ms: number
    columns: string[]
    rows: unknown[]
    message: string
    status: string
  }> => request.get(`/v1/inspection/items/verify-sql/${verifyRunId}`),

  // P0 soft-disable only; no hard delete per plan (history-preserving).
  patchInspectionItem: (
    id: number | string,
    data: Partial<InspectionItemUpdatePayload>,
  ): Promise<InspectionItemRow> => request.patch(`/v1/inspection/items/${id}`, data),

  // v5.1 Report endpoints
  listInspectionReports: (params?: {
    page?: number
    page_size?: number
    health_level?: string
    report_status?: string
  }): Promise<InspectionReportListResponse> =>
    request.get('/v1/inspection/reports', { params }),

  getInspectionReport: (reportId: number | string): Promise<InspectionReportRow> =>
    request.get(`/v1/inspection/reports/${reportId}`),

  getInspectionReportByTask: (taskId: number | string): Promise<InspectionReportRow> =>
    request.get(`/v1/inspection/reports/task/${taskId}`),

  listInstanceReports: (
    reportId: number | string,
    params?: { health_level?: string },
  ): Promise<InspectionInstanceReportRow[]> =>
    request.get(`/v1/inspection/reports/${reportId}/instances`, { params }),

  getInstanceReportResults: (
    reportId: number | string,
    targetType: string,
    targetId: number,
  ): Promise<InspectionResultRow[]> =>
    request.get(`/v1/inspection/reports/${reportId}/instances/${targetType}/${targetId}/results`),

  regenerateReport: (reportId: number | string): Promise<InspectionReportRow> =>
    request.post(`/v1/inspection/reports/${reportId}/regenerate`),

  /**
   * Download the report as a DOCX file. Bypasses the shared axios response
   * interceptor (which would treat the binary blob as an error) and uses
   * fetch + Authorization header directly. Triggers a browser download via
   * a temporary <a download> element. Honors Content-Disposition filename
   * when the server provides it.
   */
  exportReport: async (
    reportId: number | string,
    opts?: { includeEvidence?: boolean },
  ): Promise<void> => {
    const params = new URLSearchParams()
    if (opts?.includeEvidence) params.set('include_evidence', 'true')
    const qs = params.toString()
    const url = `/api/v1/inspection/reports/${reportId}/export${qs ? `?${qs}` : ''}`
    await _downloadInspectionReportDocx(url, `inspection-report-${reportId}.docx`)
  },

  /**
   * Export a single instance's slice of the report (post-verification 2026-06-26).
   * Identical download mechanics to exportReport; only the URL is constrained
   * to a (target_type, target_id) tuple.
   */
  exportInstanceReport: async (
    reportId: number | string,
    targetType: string,
    targetId: number | string,
    opts?: { includeEvidence?: boolean },
  ): Promise<void> => {
    const params = new URLSearchParams()
    if (opts?.includeEvidence) params.set('include_evidence', 'true')
    const qs = params.toString()
    const url = `/api/v1/inspection/reports/${reportId}/instances/${encodeURIComponent(targetType)}/${targetId}/export${qs ? `?${qs}` : ''}`
    await _downloadInspectionReportDocx(
      url,
      `inspection-report-${reportId}-instance-${targetId}.docx`,
    )
  },

  // 资产校验功能优化 v2 / 2026-06-17: 批量 proposal 操作 + asset report
  batchActionProposals: (
    payload: {
      proposal_ids: number[]
      action: 'approve' | 'reject' | 'apply'
      comment?: string
      override_values?: Record<string, number>
    }
  ): Promise<{
    action: string
    results: Array<{ id: number; success: boolean; error?: string }>
    success_count: number
    fail_count: number
  }> => request.post('/v1/collector/proposals/batch-action', payload),

  applyProposalWithValue: (
    proposalId: number,
    payload: { selected_value?: number; comment?: string }
  ): Promise<AssetChangeProposalRow> =>
    request.post(`/v1/collector/proposals/${proposalId}/apply-with-value`, payload),

  getAssetReport: (
    batchRunId: number,
    options?: { suppressErrorToast?: boolean }
  ): Promise<{
    batch_run_id: number
    batch_code: string
    assets: Array<{
      entity_type: string
      entity_id: number
      entity_name?: string | null
      ip_address?: string | null
      db_port_status?: string | null
      os_port_status?: string | null
      fact_status?: string | null
      fact_count: number
      error_messages: string[]
      items: Array<Record<string, unknown>>
      // M6 (PR review 2026-06-18): backend returns cluster_type_suspected on
      // every asset (C3 fix). TypeScript consumers need this in the contract.
      cluster_type_suspected?: Record<string, unknown> | null
    }>
  }> =>
    request.get(`/v1/collector/batch-runs/${batchRunId}/asset-report`, {
      suppressErrorToast: options?.suppressErrorToast,
    }),
}

/**
 * Shared DOCX download helper for the inspection report export endpoints.
 * Uses fetch (not the shared axios interceptor) to avoid the response
 * interceptor treating the binary blob as a JSON error envelope, and
 * surfaces the server's detail message on failure.
 */
async function _downloadInspectionReportDocx(
  url: string,
  fallbackFilename: string,
): Promise<void> {
  const token = localStorage.getItem('token')
  const resp = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    const text = await resp.text()
    let detail = text
    try {
      const parsed = JSON.parse(text)
      detail = parsed.detail || parsed.message || text
    } catch {
      // not JSON, keep raw text
    }
    throw new Error(`导出失败 (${resp.status}): ${detail}`)
  }
  const blob = await resp.blob()
  const disp = resp.headers.get('Content-Disposition') || ''
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disp)
  const filename = decodeURIComponent(m?.[1] || m?.[2] || fallbackFilename)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(a.href)
    a.remove()
  }, 0)
}
