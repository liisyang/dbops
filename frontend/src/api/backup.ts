/**
 * Phase 3.5: backup status API client.
 *
 * Endpoints exposed by backend `app/api/backup.py` (mounted under
 * `/api/v1`). All requests go through `@/api/request` so the JWT
 * bearer token is injected automatically.
 */

import request from './request'

export interface BackupStatusLatest {
  id: number
  instance_id: number
  instance_name: string
  db_type_code: string
  host: string
  port: number
  backup_type: string | null
  source_type: string
  last_status: string
  last_success_at: string | null
  last_failure_at: string | null
  recovery_point_at: string | null
  age_minutes: number | null
  duration_seconds: number | null
  backup_size_mb: number | null
  message: string | null
  collected_at: string
  collector_run_id: number | null
  collector_run_item_id: number | null
}

export interface BackupStatusHistory {
  id: number
  instance_id: number
  backup_type: string | null
  source_type: string
  last_status: string
  last_success_at: string | null
  last_failure_at: string | null
  recovery_point_at: string | null
  age_minutes: number | null
  duration_seconds: number | null
  backup_size_mb: number | null
  message: string | null
  evidence: Record<string, unknown>
  collected_at: string
  created_at: string
}

export interface BackupCollectPayload {
  instance_ids: number[]
  db_type_code: string
  backup_type?: string | null
  sql_text: string
  timeout_seconds?: number
  max_rows?: number
}

export interface BackupCollectResponse {
  collector_run_id: number
  status: string
  awx_job_id: number | null
}

export interface BackupValidateSqlPayload {
  db_type_code: string
  sql_text: string
}

export interface BackupValidateSqlResponse {
  valid: boolean
  sql_hash: string
  message: string
  errors: string[]
}

export interface BackupLatestFilters {
  db_type_code?: string
  last_status?: string
  backup_type?: string
  keyword?: string
  limit?: number
}

export const backupApi = {
  listLatest(filters: BackupLatestFilters = {}): Promise<BackupStatusLatest[]> {
    return request.get('/v1/backup/status/latest', { params: filters })
  },
  listHistory(params: { instance_id?: number; limit?: number } = {}): Promise<BackupStatusHistory[]> {
    return request.get('/v1/backup/status/history', { params })
  },
  collect(payload: BackupCollectPayload): Promise<BackupCollectResponse> {
    return request.post('/v1/backup/status/collect', payload)
  },
  validateSql(payload: BackupValidateSqlPayload): Promise<BackupValidateSqlResponse> {
    return request.post('/v1/backup/status/validate-sql', payload)
  },
}

export default backupApi
