import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true
})

// Simple message toast using native browser
function showMessage(type, content) {
  const colors = {
    success: 'bg-green-600',
    error: 'bg-red-600',
    info: 'bg-blue-600'
  }
  const el = document.createElement('div')
  el.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded-lg text-white ${colors[type]} shadow-lg transform transition-all duration-300`
  el.textContent = content
  el.style.cssText = 'min-width: 200px;'
  document.body.appendChild(el)
  setTimeout(() => {
    el.classList.add('opacity-0', 'translate-x-full')
    setTimeout(() => el.remove(), 300)
  }, 3000)
}

function extractErrorMessage(payload) {
  if (!payload) return '请求失败'
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message
  }
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail
  }
  if (Array.isArray(payload.detail) && payload.detail.length) {
    return payload.detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join('；')
  }
  return '请求失败'
}

function isPlainObject(value) {
  return Boolean(value) && Object.prototype.toString.call(value) === '[object Object]'
}

// 请求拦截器
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    const res = response.data
    // 处理 FastAPI 返回格式：{code: 0, message: "...", data: ...}
    // 也处理直接返回数组的情况（公开端点）
    // 还处理直接返回对象的情况（如 task 状态返回）
    if (Array.isArray(res)) {
      return res
    }
    if (res && res.code === 0) {
      return res
    }
    // 如果响应没有 code 字段但有预期的数据结构，认为是有效的直接响应
    if (res && (res.task_id || res.success !== undefined || res.total_hosts !== undefined)) {
      return res
    }
    // 处理分页响应格式：{total, page, page_size, items}
    if (res && res.items !== undefined && res.total !== undefined) {
      return res
    }
    // 处理分组统计响应格式：{groups: [...]}
    if (res && Array.isArray(res.groups)) {
      return res
    }
    // 处理统计响应格式：{total_instances, total_servers, by_type, by_bia, by_role}
    if (res && (res.total_instances !== undefined || res.total_servers !== undefined)) {
      return res
    }
    // 处理批量操作响应格式：{deleted, total}
    if (res && res.deleted !== undefined) {
      return res
    }
    // 处理简单消息响应（如 delete 操作返回 {message: "..."}）
    if (res && res.message && !res.code) {
      // 有 message 但无 code，表示操作成功，直接返回
      return res
    }
    // 处理登录响应格式：{access_token, token_type, user}
    if (res && res.access_token) {
      return res
    }
    // 详情类接口直接返回对象时，不再套分页或 code 包装，按成功结果透传。
    if (isPlainObject(res)) {
      return res
    }
    // 错误情况
    if (res && res.message) {
      showMessage('error', res.message || '请求失败')
    }
    return Promise.reject(new Error(res?.message || '请求失败'))
  },
  error => {
    if (error.response) {
      if (error.response.status === 401) {
        // Only redirect if not already on login page and router is available
        if (!window.location.pathname.includes('/login')) {
          showMessage('error', '登录已过期，请重新登录')
          localStorage.removeItem('token')
          // Use Vue Router for SPA navigation if available
          if (window.__VITE_ROUTER__) {
            window.__VITE_ROUTER__.push('/login')
          } else {
            window.location.href = '/login'
          }
        }
      } else {
        showMessage('error', extractErrorMessage(error.response.data))
      }
    } else {
      showMessage('error', '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request
