export interface ApiResponse<T = any> {
  code?: number
  message?: string
  data?: T
}

export interface User {
  id: string
  username: string
  email?: string
  full_name?: string
  department?: string
  role?: string
  is_active?: boolean
  timezone?: string
  language?: string
}

export interface LoginResponse {
  access_token: string
  token_type?: string
  user?: User
}

export interface BusinessContactRow {
  id: number
  contact_type: string
  name: string
  phone?: string | null
}

export interface ContactRow {
  id: number
  employee_no?: string | null
  contact_code: string
  contact_name: string
  phone?: string | null
  email?: string | null
  dept?: string | null
  remark?: string | null
}

export interface ContactUpsertPayload {
  employee_no?: string | null
  contact_name: string
  phone?: string | null
  email?: string | null
  dept?: string | null
  remark?: string | null
}

export interface ClusterRef {
  id: number
  cluster_code: string
  cluster_name: string
  cluster_type: string
}

export interface AssetEventRow {
  id: number
  asset_type: string
  asset_id: number
  event_type: string
  before_status?: string | null
  after_status?: string | null
  changed_fields?: Record<string, any>
  reason?: string | null
  operator?: string | null
  operated_at: string
  remark?: string | null
}

export interface BusinessLifecycleSnapshot {
  history: AssetEventRow[]
}

export interface SystemRow {
  id: number
  system_code: string
  system_name: string
  system_group_id?: number | null
  business_unit?: string | null
  department?: string | null
  service_scope?: string | null
  biz_level?: string | null
  status?: string | null
  remark?: string | null
  contacts: BusinessContactRow[]
  clusters: ClusterRef[]
}

export interface SystemDetail extends SystemRow {
  lifecycle?: BusinessLifecycleSnapshot
}

export interface BusinessSystemUpsertPayload {
  system_name: string
  business_unit?: string | null
  department?: string | null
  service_scope?: string | null
  biz_level?: string | null
  remark?: string | null
  system_group_id?: number | null
}

export interface BusinessContactLinkPayload {
  contact_id: number
  role_code: string
  remark?: string | null
}

export interface ClusterRow {
  id: number
  cluster_code: string
  cluster_name: string
  cluster_type: string
  business_system_id: number
  business_system_name?: string | null
  source_cluster_no?: string | null
  vip_addresses: string[]
  instance_count: number
  roles: string[]
}

export interface InstanceRow {
  id: number
  instance_code: string
  instance_name: string
  cluster_id: number
  cluster_code?: string | null
  cluster_name?: string | null
  cluster_type?: string | null
  db_type?: string | null
  db_version?: string | null
  node_role: string
  engine_role?: string | null
  source_node_role?: string | null
  server_id: number
  server_ip?: string | null
  hostname?: string | null
  country?: string | null
  factory_area?: string | null
  room_location?: string | null
  deploy_type?: string | null
  provider?: string | null
  system_name?: string | null
  trust_status?: 'unverified' | 'verified' | 'missing' | 'drifted' | string | null
  reachability_status?: 'unknown' | 'online' | 'offline' | string | null
  last_seen_at?: string | null
  last_verify_at?: string | null
  verify_message?: string | null
  last_verify_run_id?: string | null
  last_awx_job_id?: number | null
  verify_detail?: Record<string, any> | null
}

export interface InstanceDetail extends InstanceRow {}

export interface AssetVerifyLaunchPayload {
  check_timeout: number
  target_host_override?: string
  target_port_override?: number
}

export interface AssetVerifyLaunchResponse {
  detail: string
  run_id: string
  collector_run_id: number
  instance_id: number
  awx_job_id?: number | null
  awx_job_url?: string | null
  status: string
}

export interface CollectorRunResultRow {
  run_id: string
  item_key: string
  check_code: string
  target_scope: 'db_instance' | 'server' | string
  status: string
  port_reachable?: boolean | null
  target_host: string
  target_port: number
  error_message?: string | null
  result_message?: string | null
  candidate_state?: string | null
  awx_job_id?: number | null
  checked_by?: string | null
  checked_at?: string | null
  raw_result: Record<string, any>
  created_at?: string | null
  updated_at?: string | null
}

export interface CollectorRunRow {
  id: number
  run_id: string
  target_scope: string
  run_type?: string
  instance_id?: number | null
  server_id?: number | null
  job_type: string
  status:
    | 'pending'
    | 'launched'
    | 'running'
    | 'success'
    | 'partial_success'
    | 'failed'
    | 'callback_failed'
    | 'timeout'
    | 'canceled'
    | string
  item_count?: number
  awx_job_id?: number | null
  awx_job_url?: string | null
  awx_job_template_id?: number | null
  awx_job_template_name?: string | null
  target_host: string
  target_port: number
  callback_url?: string | null
  requested_by?: string | null
  request_payload?: Record<string, any>
  extra_vars?: Record<string, any>
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  latest_result?: CollectorRunResultRow | null
  items?: CollectorRunItemRow[]
}

export interface CollectorRunItemRow {
  id: number
  collector_run_id: number
  run_id: string
  item_key: string
  check_code: string
  target_scope: 'db_instance' | 'server' | string
  server_id?: number | null
  db_instance_id?: number | null
  target_host: string
  target_port: number
  protocol: string
  endpoint_type?: string | null
  port_source?: string | null
  is_required?: boolean
  timeout_seconds: number
  status: string
  result_status?: string | null
  result_message?: string | null
  candidate_state?: string | null
  raw_result: Record<string, any>
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface CollectorEndpointRow {
  id: number
  entity_type: 'server' | 'db_instance' | string
  entity_id: number
  endpoint_type: string
  host: string
  port: number
  protocol: string
  source: string
  expected: boolean
  status: string
  reachable?: boolean | null
  port_source?: string | null
  is_required?: boolean
  last_checked_at?: string | null
  last_item_key?: string | null
  last_seen_at?: string | null
  last_verify_at?: string | null
  last_run_id?: string | null
  last_message?: string | null
  evidence: Record<string, any>
  created_at?: string | null
  updated_at?: string | null
}

export interface CollectorRunCreatePayload {
  run_type?: string
  scope: {
    target_scope: 'db_instance' | 'server'
    asset_ids: number[]
  }
  target_scope?: 'db_instance' | 'server'
  asset_ids?: number[]
  check_codes: string[]
  options?: Record<string, any>
}

export interface PortProfileRow {
  id: number
  profile_code: string
  target_scope: 'server' | 'db_instance'
  endpoint_type: string
  db_type_code?: string | null
  os_family?: string | null
  protocol: string
  default_port: number
  is_required: boolean
  is_candidate: boolean
  is_enabled: boolean
  priority: number
  remark?: string | null
}

export interface AssetChangeProposalRow {
  id: number
  target_type: 'server' | 'db_instance' | string
  target_id: number
  proposal_type: string
  field_path?: string | null
  current_value?: any
  suggested_value?: any
  confidence?: string | null
  evidence: Record<string, any>
  source_run_id?: string | null
  source_item_key?: string | null
  status: 'pending' | 'approved' | 'rejected' | 'applied' | 'cancelled' | string
  requested_by?: string | null
  approved_by?: string | null
  approved_at?: string | null
  applied_at?: string | null
  rejected_reason?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface CollectorRunCreateResponse {
  detail: string
  run_id: string
  collector_run_id: number
  awx_job_id?: number | null
  awx_job_url?: string | null
  status: string
  item_count: number
}

export interface ClusterDetail extends ClusterRow {
  instances: InstanceRow[]
}

export interface ServerRow {
  id: number
  server_code: string
  ip_address: string
  hostname?: string | null
  dns_name?: string | null
  server_type?: string | null
  cpu_cores?: number | null
  memory_gb?: number | null
  disk_gb?: number | null
  business_group?: string | null
  os_name?: string | null
  os_version?: string | null
  country?: string | null
  factory_area?: string | null
  deploy_type?: string | null
  provider?: string | null
  room_location?: string | null
  instance_count: number
}

export interface ServerDetail extends ServerRow {
  instances: InstanceRow[]
}

export interface ServerUpsertPayload {
  ip: string
  hostname?: string | null
  dns_name?: string | null
  host_type?: string | null
  cpu_cores?: number | null
  memory_gb?: number | null
  disk_gb?: number | null
  business_group?: string | null
  factory?: string | null
  machine_room?: string | null
  room_location?: string | null
  os_type?: string | null
  os_version?: string | null
  status?: string | null
}

export interface PaginatedResult<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface ServerListResponse extends PaginatedResult<ServerRow> {}

export interface InstanceListResponse extends PaginatedResult<InstanceRow> {}

export interface ImportPreviewRow {
  row_num: number
  status: 'ok' | 'error'
  errors: string[]
  warnings?: string[]
  fields: Record<string, any>
  source_file_name: string
}

export interface ImportIssueGroup {
  key: 'schema' | 'validation' | 'conflict' | 'other'
  label: string
  count: number
  items: string[]
}

export interface ImportPreviewResult {
  total: number
  success_count: number
  error_count: number
  warning_count?: number
  conflict_count?: number
  errors: string[]
  warnings?: string[]
  issue_groups?: ImportIssueGroup[]
  import_mode?: string
  stage?: string
  stage_label?: string
  progress?: number
  items: ImportPreviewRow[]
  debug_headers: string[]
}

export interface ImportExecuteResult {
  import_batch_id?: string
  import_mode?: string
  stage?: string
  stage_label?: string
  progress?: number
  total?: number
  success: number
  updated: number
  error: number
  error_count: number
  errors: string[]
  warnings?: string[]
  issue_groups?: ImportIssueGroup[]
  warning_count?: number
  conflict_count?: number
  message: string
}

export interface ImportBatchRow {
  import_batch_id: string
  source_file_name: string
  uploaded_by?: string
  total_rows: number
  imported_at?: string | null
}

export interface DashboardSummary {
  total_business_systems: number
  total_clusters: number
  total_instances: number
  total_servers: number
}

export interface GroupedResult<T> {
  groups: Array<T & { count: number }>
}

export interface OperationLog {
  id: string
  action: string
  target: string
  operator: string
  created_at: string
  result?: string
}

export type BusinessService = SystemRow

export interface DbTypeRow {
  id: number
  name: string
  type_code: string
}

export interface ServerDropdownRow {
  id: number
  hostname: string
  server_code: string
}

export interface ClusterUpsertPayload {
  cluster_name: string
  business_system_id: number
  db_type_id: number
  cluster_type: string
  status?: string | null
  remark?: string | null
  vip_addresses?: string[]
}

export interface DbInstanceUpsertPayload {
  instance_name: string
  cluster_id: number
  db_type_id: number
  server_id: number
  db_version_id?: number | null
  node_role: string
  service_name?: string | null
  status?: string | null
  remark?: string | null
}

// ============================================================================
// Phase 3.2 — Batch Verify types
// ============================================================================

export interface BatchRunFilters {
  db_type_code?: string
  status?: string
  site_id?: number
  target_scope?: 'server' | 'db_instance'
}

export interface BatchRunCreatePayload {
  run_type?: string
  target_scope: 'db_instance' | 'server'
  asset_ids?: number[]
  filters?: BatchRunFilters
  check_codes: string[]
  include_related_server?: boolean
  max_items_per_dispatch?: number
  timeout_seconds?: number
}

export interface DispatchRunSummary {
  dispatch_run_id: number
  dispatch_code?: string | null
  collector_run_id?: number | null
  network_zone?: string | null
  awx_instance_group?: string | null
  awx_job_template?: string
  awx_job_id?: number | null
  status: string
  item_count: number
  success_item_count: number
  failed_item_count: number
  error_message?: string | null
  launched_at?: string | null
  finished_at?: string | null
  created_at?: string | null
}

export interface BatchRunCreateResponse {
  batch_run_id: number
  batch_code: string
  status: string
  run_type: string
  target_scope: string
  total_asset_count: number
  total_item_count: number
  dispatch_count: number
  dispatches: DispatchRunSummary[]
}

export interface BatchRunRow {
  id: number
  batch_code: string
  run_type: string
  target_scope: string
  status: string
  total_asset_count: number
  total_item_count: number
  success_item_count: number
  failed_item_count: number
  pending_item_count: number
  running_item_count: number
  skipped_item_count: number
  dispatch_count: number
  request_payload?: Record<string, any>
  error_message?: string | null
  created_by?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  dispatches?: DispatchRunSummary[]
}

export interface DispatchRunRow {
  id: number
  dispatch_code?: string | null
  batch_run_id: number
  collector_run_id?: number | null
  network_zone?: string | null
  awx_instance_group?: string | null
  awx_job_template?: string
  awx_job_id?: number | null
  status: string
  item_count: number
  success_item_count: number
  failed_item_count: number
  request_payload?: Record<string, any>
  error_message?: string | null
  launched_at?: string | null
  finished_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface BatchRunItemRow extends CollectorRunItemRow {
  batch_run_id?: number | null
  dispatch_run_id?: number | null
  network_zone?: string | null
  awx_instance_group?: string | null
}

export interface RetryFailedPayload {
  scope: 'failed' | 'dispatch_failed'
}
