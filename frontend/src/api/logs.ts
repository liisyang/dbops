import request from './request'
import type { OperationLog } from '@/types/api'

export const logsApi = {
  list: (params?: { page?: number; page_size?: number; action?: string }): Promise<any> =>
    request.get('/logs', { params }),
  get: (id: string): Promise<OperationLog> => request.get(`/logs/${id}`)
}
