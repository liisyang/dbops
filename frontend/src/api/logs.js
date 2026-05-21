import request from './request'

export const logsApi = {
  list: () => request.get('/logs/list')
}