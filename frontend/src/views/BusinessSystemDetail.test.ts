import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import Assets from './Assets.vue'
import BusinessSystemDetail from './BusinessSystemDetail.vue'

const listBusinessSystemsMock = vi.fn().mockResolvedValue([
  {
    id: 7,
    system_code: 'SYS-007',
    system_name: '订单系统',
    business_unit: '事业群',
    department: '平台部',
    biz_level: '重要',
    contacts: [
      {
        id: 31,
        contact_type: 'BUSINESS_MANAGER',
        name: '张三',
        phone: '13800000001',
      },
      {
        id: 32,
        contact_type: 'DBA_OWNER',
        name: '李四',
        phone: '13800000002',
      },
    ],
    clusters: [
      {
        id: 901,
        cluster_code: 'CLU-901',
        cluster_name: 'order-rac',
        cluster_type: 'RAC',
      },
    ],
  },
])

const getBusinessSystemMock = vi.fn().mockResolvedValue({
  id: 7,
  system_code: 'SYS-007',
  system_name: '订单系统',
  business_unit: '事业群',
  department: '平台部',
  biz_level: '重要',
  status: 'retired',
  contacts: [
    {
      id: 31,
      contact_type: 'BUSINESS_MANAGER',
      name: '张三',
      phone: '13800000001',
    },
    {
      id: 32,
      contact_type: 'DBA_OWNER',
      name: '李四',
      phone: '13800000002',
    },
  ],
  clusters: [
    {
      id: 901,
      cluster_code: 'CLU-901',
      cluster_name: 'order-rac',
      cluster_type: 'RAC',
    },
  ],
})

const listBusinessSystemHistoryMock = vi.fn().mockResolvedValue([
  {
    id: 1001,
    asset_type: 'business_system',
    asset_id: 7,
    event_type: 'status_change',
    before_status: 'retired',
    after_status: 'active',
    reason: 'maintenance',
    operator: 'admin',
    operated_at: '2026-05-18 10:00:00',
    remark: 'planned restart',
  },
])

const changeBusinessSystemLifecycleMock = vi.fn().mockResolvedValue({ ok: true })
const listContactsMock = vi.fn().mockResolvedValue([
  {
    id: 31,
    employee_no: 'E001',
    contact_code: 'CT-001',
    contact_name: '张三',
    phone: '13800000001',
    email: 'zhangsan@example.com',
    dept: 'DBA',
    remark: 'owner',
  },
  {
    id: 32,
    employee_no: 'E002',
    contact_code: 'CT-002',
    contact_name: '李四',
    phone: '13800000002',
    email: 'lisi@example.com',
    dept: '应用部',
    remark: 'manager',
  },
])
const addBusinessSystemContactMock = vi.fn().mockResolvedValue({ id: 88 })
const deleteBusinessSystemContactMock = vi.fn().mockResolvedValue({ message: 'ok' })

const routeState = reactive<{ params: Record<string, any> }>({
  params: { id: '7' },
})

const pushMock = vi.fn()

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listBusinessSystems: (...args: any[]) => listBusinessSystemsMock(...args),
    getBusinessSystem: (...args: any[]) => getBusinessSystemMock(...args),
    listBusinessSystemHistory: (...args: any[]) => listBusinessSystemHistoryMock(...args),
    changeBusinessSystemLifecycle: (...args: any[]) => changeBusinessSystemLifecycleMock(...args),
    listContacts: (...args: any[]) => listContactsMock(...args),
    addBusinessSystemContact: (...args: any[]) => addBusinessSystemContactMock(...args),
    deleteBusinessSystemContact: (...args: any[]) => deleteBusinessSystemContactMock(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: pushMock }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const globalStubs = {
  OpsPage: { template: '<div><slot /></div>' },
  OpsPageHeader: {
    props: ['title', 'subtitle'],
    template: '<header><h1>{{ title }}</h1><p>{{ subtitle }}</p><slot name="actions" /></header>',
  },
  OpsSectionCard: {
    props: ['title', 'subtitle', 'icon'],
    template: '<section><h2 v-if="title">{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p><slot name="actions" /><slot /></section>',
  },
  OpsStatGrid: { template: '<div />' },
  OpsFilterBar: { template: '<div><slot /><slot name="actions" /></div>' },
  OpsTableShell: { template: '<div><slot /></div>' },
  OpsEmptyState: { template: '<div />' },
  SimpleBarChart: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
}

beforeEach(() => {
  listBusinessSystemsMock.mockClear()
  getBusinessSystemMock.mockClear()
  listBusinessSystemHistoryMock.mockClear()
  changeBusinessSystemLifecycleMock.mockClear()
  listContactsMock.mockClear()
  addBusinessSystemContactMock.mockClear()
  deleteBusinessSystemContactMock.mockClear()
  pushMock.mockClear()
  routeState.params = { id: '7' }
})

describe('Business system detail shell', () => {
  it('navigates from the business list to the detail page', async () => {
    routeState.params = {}

    const wrapper = mount(Assets, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(1)

    await rows[0].trigger('click')
    expect(pushMock).toHaveBeenCalledWith('/assets/businesses/7')
  })

  it('renders the unified page shell and compact cards', async () => {
    const wrapper = mount(BusinessSystemDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(getBusinessSystemMock).toHaveBeenCalledWith('7')
    expect(wrapper.text()).toContain('返回列表')
    expect(wrapper.text()).toContain('基础信息')
    expect(wrapper.text()).toContain('联系人')
    expect(wrapper.text()).toContain('关联集群')
    expect(wrapper.text()).toContain('SYS-007')
    expect(wrapper.text()).toContain('订单系统')
    expect(wrapper.text()).toContain('事业群')
    expect(wrapper.text()).toContain('平台部')
    expect(wrapper.text()).toContain('重要')
    expect(wrapper.html()).toContain('field-card')
    expect(wrapper.html()).toContain('xl:grid-cols-4')
  })

  it('renders the lifecycle card and toggles the history list', async () => {
    const wrapper = mount(BusinessSystemDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(listBusinessSystemHistoryMock).toHaveBeenCalledWith('7')
    expect(wrapper.text()).toContain('生命周期')
    expect(wrapper.text()).toContain('设为建设中')
    expect(wrapper.text()).toContain('设为待上线')
    expect(wrapper.text()).toContain('标记已上线')
    expect(wrapper.text()).toContain('标记已下线')
    expect(wrapper.text()).toContain('查看历史')
    expect(wrapper.text()).not.toContain('status_change')

    const historyButton = wrapper.findAll('button').find((button) => button.text() === '查看历史')
    expect(historyButton).toBeTruthy()
    await historyButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('status_change')
    expect(wrapper.text()).toContain('已下线 -> 已上线')
    expect(wrapper.text()).toContain('admin')
  })

  it('binds and unbinds contacts from the detail page', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(BusinessSystemDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('新增绑定')
    expect(wrapper.text()).toContain('解除绑定')

    const remarkInput = wrapper.findAll('input').find((input) => input.element instanceof HTMLInputElement && input.attributes('placeholder') === '可选')
    expect(remarkInput).toBeTruthy()
    await remarkInput!.setValue('绑定说明')

    const bindButton = wrapper.findAll('button').find((button) => button.text() === '绑定联系人')
    expect(bindButton).toBeTruthy()
    await bindButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(addBusinessSystemContactMock).toHaveBeenCalledWith(7, {
      contact_id: 31,
      role_code: 'BUSINESS_MANAGER',
      remark: '绑定说明',
    })

    const unbindButton = wrapper.findAll('button').find((button) => button.text() === '解除绑定')
    expect(unbindButton).toBeTruthy()
    await unbindButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(deleteBusinessSystemContactMock).toHaveBeenCalledWith(7, 31, 'BUSINESS_MANAGER')
  })

  it.each([
    ['设为建设中', 'building' as const],
    ['设为待上线', 'pending' as const],
    ['标记已上线', 'active' as const],
    ['标记已下线', 'retired' as const],
  ])('submits %s with the expected lifecycle payload', async (buttonLabel, action) => {
    const wrapper = mount(BusinessSystemDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    const actionButton = wrapper.findAll('button').find((button) => button.text() === buttonLabel)
    expect(actionButton).toBeTruthy()
    await actionButton!.trigger('click')
    await flushPromises()

    await wrapper.find('input[placeholder="例如：例行维护 / 业务切换"]').setValue('例行维护')
    const textareas = wrapper.findAll('textarea')
    await textareas[0].setValue('补充说明')
    await textareas[1].setValue('IP-Group-A')
    await flushPromises()

    const confirmButton = wrapper.findAll('button').find((button) => button.text() === `确认${buttonLabel}`)
    expect(confirmButton).toBeTruthy()
    await confirmButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(changeBusinessSystemLifecycleMock).toHaveBeenCalledWith(7, {
      action,
      reason: '例行维护',
      remark: '补充说明',
      lifecycle_context: {
        context_text: 'IP-Group-A',
      },
    })
    expect(getBusinessSystemMock).toHaveBeenCalledTimes(2)
    expect(listBusinessSystemHistoryMock).toHaveBeenCalledTimes(2)
  })
})
