import request from './request'
import type {
  AssetEventRow,
  AssetVerifyLaunchPayload,
  AssetVerifyLaunchResponse,
  BusinessContactLinkPayload,
  ClusterDetail,
  ClusterRow,
  ClusterUpsertPayload,
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
  listCollectorProposals: (
    params?: { target_type?: string; target_id?: number; proposal_type?: string; status?: string },
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
  listBatchRuns: (params?: Record<string, any>): Promise<BatchRunRow[]> =>
    request.get('/v1/collector/batch-runs', { params }),
  getBatchRun: (id: number | string): Promise<BatchRunRow> =>
    request.get(`/v1/collector/batch-runs/${id}`),
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
}
