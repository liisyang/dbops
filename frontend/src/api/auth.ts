import request from './request'
import type { User } from '@/types/api'

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export const authApi = {
  login: (username: string, password: string): Promise<LoginResponse> =>
    request.post('/auth/login', { username, password })
}
