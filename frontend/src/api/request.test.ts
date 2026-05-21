import { describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  const requestUse = vi.fn()
  const responseUse = vi.fn()
  const mockAxiosInstance = {
    interceptors: {
      request: { use: requestUse },
      response: { use: responseUse },
    },
  }
  return { requestUse, responseUse, mockAxiosInstance }
})

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => axiosMock.mockAxiosInstance),
  },
}))

import request from './request'

describe('request response interceptor', () => {
  it('accepts grouped stats responses', async () => {
    const onFulfilled = axiosMock.responseUse.mock.calls[0][0]

    await expect(
      Promise.resolve(
        onFulfilled({
          data: {
            groups: [{ factory_area: '龙华', count: 12 }],
          },
        }),
      ),
    ).resolves.toEqual({
      groups: [{ factory_area: '龙华', count: 12 }],
    })

    expect(request).toBeDefined()
  })
})
