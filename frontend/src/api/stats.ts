import request from './request'
import type { DashboardSummary, GroupedResult } from '@/types/api'

export const statsApi = {
  getDashboard: (): Promise<DashboardSummary> =>
    request.get('/v1/servers/stats/dashboard'),
  getByCountry: (): Promise<GroupedResult<{ country: string }>> =>
    request.get('/v1/servers/stats/by-country'),
  getByFactory: (): Promise<GroupedResult<{ factory_area: string }>> =>
    request.get('/v1/servers/stats/by-factory'),
  getByCluster: (): Promise<{ groups: any[] }> =>
    request.get('/v1/servers/stats/by-cluster'),
  getByDeployType: (): Promise<GroupedResult<{ deploy_type: string }>> =>
    request.get('/v1/servers/stats/by-deploy-type'),
  getByProvider: (): Promise<GroupedResult<{ provider: string }>> =>
    request.get('/v1/servers/stats/by-provider'),
  getSummaryByType: (): Promise<GroupedResult<{ db_type: string }>> =>
    request.get('/v1/servers/stats/summary-by-type'),
  getBySystemGroup: (): Promise<GroupedResult<{ system_group: string }>> =>
    request.get('/v1/servers/stats/by-system-group'),
}
