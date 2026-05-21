import { beforeEach, describe, expect, it, vi } from 'vitest'

const requestMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('./request', () => ({
  default: requestMock,
}))

import { assetsApi } from './assets'

beforeEach(() => {
  requestMock.get.mockReset()
  requestMock.post.mockReset()
  requestMock.put.mockReset()
  requestMock.delete.mockReset()
})

describe('assetsApi server mutations', () => {
  it('calls the server CRUD endpoints', async () => {
    requestMock.post.mockResolvedValueOnce({ id: 1 })
    requestMock.put.mockResolvedValueOnce({ message: 'ok' })
    requestMock.delete.mockResolvedValueOnce({ message: 'ok' })

    await assetsApi.createServer({ ip: '10.0.0.1' })
    await assetsApi.updateServer(7, { ip: '10.0.0.2' })
    await assetsApi.deleteServer(7)

    expect(requestMock.post).toHaveBeenCalledWith('/v1/servers/servers', { ip: '10.0.0.1' })
    expect(requestMock.put).toHaveBeenCalledWith('/v1/servers/servers/7', { ip: '10.0.0.2' })
    expect(requestMock.delete).toHaveBeenCalledWith('/v1/servers/servers/7')
  })
})

describe('assetsApi business lifecycle helpers', () => {
  it('calls the lifecycle history and change endpoints', async () => {
    requestMock.get.mockResolvedValueOnce([])
    requestMock.post.mockResolvedValueOnce({ ok: true })

    const payload = {
      action: 'retired' as const,
      reason: 'maintenance',
      remark: 'planned shutdown',
      lifecycle_context: {
        source: 'unit-test',
      },
    }

    await assetsApi.listBusinessSystemHistory(12)
    await assetsApi.changeBusinessSystemLifecycle(12, payload)

    expect(requestMock.get).toHaveBeenCalledWith('/v1/servers/business-services/12/lifecycle/history')
    expect(requestMock.post).toHaveBeenCalledWith(
      '/v1/servers/business-services/12/lifecycle',
      payload
    )
  })
})

describe('assetsApi contact CRUD', () => {
  it('calls the contact endpoints', async () => {
    requestMock.get.mockResolvedValueOnce([])
    requestMock.post.mockResolvedValueOnce({ id: 3 })
    requestMock.put.mockResolvedValueOnce({ id: 3 })
    requestMock.delete.mockResolvedValueOnce({ message: 'ok' })

    await assetsApi.listContacts()
    await assetsApi.createContact({ contact_name: '张三' })
    await assetsApi.updateContact(3, { contact_name: '李四' })
    await assetsApi.deleteContact(3)

    expect(requestMock.get).toHaveBeenCalledWith('/v1/servers/contacts')
    expect(requestMock.post).toHaveBeenCalledWith('/v1/servers/contacts', { contact_name: '张三' })
    expect(requestMock.put).toHaveBeenCalledWith('/v1/servers/contacts/3', { contact_name: '李四' })
    expect(requestMock.delete).toHaveBeenCalledWith('/v1/servers/contacts/3')
  })
})

describe('assetsApi business system CRUD', () => {
  it('calls the business system and relation endpoints', async () => {
    requestMock.post.mockResolvedValueOnce({ id: 7 })
    requestMock.put.mockResolvedValueOnce({ id: 7 })
    requestMock.post.mockResolvedValueOnce({ id: 8 })
    requestMock.delete.mockResolvedValueOnce({ message: 'ok' })

    await assetsApi.createBusinessSystem({ system_name: '订单系统' })
    await assetsApi.updateBusinessSystem(7, { system_name: '订单系统' })
    await assetsApi.addBusinessSystemContact(7, { contact_id: 8, role_code: 'DBA_OWNER' })
    await assetsApi.deleteBusinessSystemContact(7, 8, 'DBA_OWNER')

    expect(requestMock.post).toHaveBeenNthCalledWith(1, '/v1/servers/business-services', { system_name: '订单系统' })
    expect(requestMock.put).toHaveBeenCalledWith('/v1/servers/business-services/7', { system_name: '订单系统' })
    expect(requestMock.post).toHaveBeenNthCalledWith(2, '/v1/servers/business-services/7/contacts', {
      contact_id: 8,
      role_code: 'DBA_OWNER',
    })
    expect(requestMock.delete).toHaveBeenCalledWith('/v1/servers/business-services/7/contacts/8/DBA_OWNER')
  })
})
