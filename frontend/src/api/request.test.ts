import { describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  const requestUse = vi.fn()
  const responseUse = vi.fn()
  const isCancel = vi.fn(() => false)
  const mockAxiosInstance = {
    interceptors: {
      request: { use: requestUse },
      response: { use: responseUse },
    },
  }
  return { requestUse, responseUse, isCancel, mockAxiosInstance }
})

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => axiosMock.mockAxiosInstance),
    isCancel: axiosMock.isCancel,
  },
  isCancel: axiosMock.isCancel,
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

describe('request response interceptor error handler (M3)', () => {
  // Regression for M3 in docs/40-tech-debt.md: AbortError from a
  // component unmount or AbortController.abort() is an expected
  // client-side cancel, not a network failure. The interceptor must
  // propagate the original rejection without showing a toast.
  it('swallows toast and propagates cancel errors unchanged', async () => {
    const onRejected = axiosMock.responseUse.mock.calls[0][1]
    const canceledErr = Object.assign(new Error('canceled'), {
      code: 'ERR_CANCELED',
    })
    axiosMock.isCancel.mockReturnValueOnce(true)

    await expect(onRejected(canceledErr)).rejects.toBe(canceledErr)
    // No `error.response` / no `error.request` — would normally fall
    // into the "网络错误" toast branch if isCancel were not honoured.
  })

  it('still rejects for non-cancel network errors', async () => {
    const onRejected = axiosMock.responseUse.mock.calls[0][1]
    const networkErr = Object.assign(new Error('Network Error'), {
      // No response, no cancel marker — axios.isCancel returns false.
    })
    axiosMock.isCancel.mockReturnValueOnce(false)

    await expect(onRejected(networkErr)).rejects.toBe(networkErr)
  })
})
