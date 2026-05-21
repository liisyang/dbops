import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Assets from './Assets.vue'

const listBusinessSystemsMock = vi.fn().mockResolvedValue([
  {
    id: 7,
    system_code: 'SYS-007',
    system_name: '订单系统',
    business_unit: '事业群',
    department: '平台部',
    biz_level: '重要',
    status: 'building',
    contacts: [],
    clusters: [],
  },
])
const createBusinessSystemMock = vi.fn().mockResolvedValue({ id: 8 })
const updateBusinessSystemMock = vi.fn().mockResolvedValue({ id: 7 })

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listBusinessSystems: (...args: any[]) => listBusinessSystemsMock(...args),
    createBusinessSystem: (...args: any[]) => createBusinessSystemMock(...args),
    updateBusinessSystem: (...args: any[]) => updateBusinessSystemMock(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

beforeEach(() => {
  listBusinessSystemsMock.mockClear()
  createBusinessSystemMock.mockClear()
  updateBusinessSystemMock.mockClear()
})

const globalStubs = {
  OpsPage: { template: '<div><slot /></div>' },
  OpsPageHeader: { template: '<header><slot name="actions" /></header>' },
  OpsSectionCard: { template: '<section><slot /></section>' },
  OpsStatGrid: { template: '<div />' },
  OpsTableShell: { template: '<div><slot /></div>' },
  SimpleBarChart: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
}

describe('Assets business lifecycle list', () => {
  it('shows the status column and the status filter', async () => {
    const wrapper = mount(Assets, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('状态')
    expect(wrapper.text()).toContain('全部生命周期状态')
    expect(wrapper.text()).toContain('待上线')
    expect(wrapper.text()).toContain('已上线')
    expect(wrapper.text()).toContain('已下线')
    expect(wrapper.text()).toContain('建设中')
    expect(wrapper.findAll('select')).toHaveLength(3)
  })

  it('supports creating and editing a business system from the list page', async () => {
    const wrapper = mount(Assets, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '新增业务系统')!.trigger('click')
    await flushPromises()

    await wrapper.find('input[placeholder="必填"]').setValue('报表系统')
    const optionalInputs = wrapper.findAll('input[placeholder="可选"]')
    await optionalInputs[0].setValue('事业群')
    await optionalInputs[1].setValue('平台部')
    await optionalInputs[2].setValue('关键')
    await wrapper.findAll('textarea')[0].setValue('业务报表服务')
    await wrapper.findAll('textarea')[1].setValue('核心业务系统')
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(createBusinessSystemMock).toHaveBeenCalledWith({
      system_name: '报表系统',
      business_unit: '事业群',
      department: '平台部',
      service_scope: '业务报表服务',
      biz_level: '关键',
      remark: '核心业务系统',
    })

    await wrapper.findAll('button').find((button) => button.text() === '编辑')!.trigger('click')
    await flushPromises()

    await wrapper.find('input[placeholder="必填"]').setValue('订单系统-更新')
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(updateBusinessSystemMock).toHaveBeenCalledWith(7, expect.objectContaining({
      system_name: '订单系统-更新',
    }))
  })
})
