import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import Servers from './Servers.vue'

const listServersMock = vi.fn().mockResolvedValue({
  total: 1,
  page: 1,
  page_size: 50,
  items: [
    {
      id: 1,
      server_code: 'SRV-001',
      ip_address: '10.0.0.1',
      hostname: 'srv-01',
      server_type: 'VM',
      cpu_cores: 8,
      memory_gb: 32,
      disk_gb: 200,
      business_group: 'DBA',
      os_name: 'Ubuntu',
      os_version: '22.04',
      country: 'CN',
      factory_area: '龙华',
      deploy_type: '生产',
      provider: '自建机房',
      room_location: 'D13',
      instance_count: 0,
    },
  ],
})
const getServerMock = vi.fn().mockResolvedValue({
  id: 1,
  server_code: 'SRV-001',
  ip_address: '10.0.0.1',
  hostname: 'srv-01',
  server_type: 'VM',
  cpu_cores: 8,
  memory_gb: 32,
  disk_gb: 200,
  business_group: 'DBA',
  os_name: 'Ubuntu',
  os_version: '22.04',
  country: 'CN',
  factory_area: '龙华',
  deploy_type: '生产',
  provider: '自建机房',
  room_location: 'D13',
  instance_count: 1,
  instances: [
    {
      id: 11,
      instance_code: 'INS-001',
      instance_name: 'db-01',
      cluster_id: 101,
      cluster_code: 'CLS-001',
      cluster_name: 'cluster-a',
      db_type: 'MySQL',
      db_version: '8.0',
      node_role: 'primary',
      engine_role: 'primary',
      source_node_role: 'primary',
      server_id: 1,
      server_ip: '10.0.0.1',
      hostname: 'srv-01',
      country: 'CN',
      factory_area: '龙华',
      deploy_type: '生产',
      provider: '自建机房',
    },
  ],
})
const updateServerMock = vi.fn().mockResolvedValue({ message: 'ok' })
const deleteServerMock = vi.fn().mockResolvedValue({ message: 'ok' })
const createServerMock = vi.fn().mockResolvedValue({ id: 2 })
const routeState = reactive<{ params: Record<string, any>; query: Record<string, any> }>({
  params: {},
  query: {},
})
const pushMock = vi.fn(async (target: any) => {
  if (target && typeof target === 'object' && target.name === 'AssetServerCreate') {
    routeState.params = { id: 'new' }
    routeState.query = {}
  }
})

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listServers: (...args: any[]) => listServersMock(...args),
    getServer: (...args: any[]) => getServerMock(...args),
    createServer: (...args: any[]) => createServerMock(...args),
    updateServer: (...args: any[]) => updateServerMock(...args),
    deleteServer: (...args: any[]) => deleteServerMock(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: pushMock }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const globalStubs = {
  OpsPage: { template: '<div><slot /></div>' },
  OpsPageHeader: { template: '<div><slot name="actions" /><div><slot /></div></div>' },
  OpsStatGrid: { template: '<div />' },
  OpsFilterBar: { template: '<div><slot /><slot name="actions" /></div>' },
  OpsSectionCard: { props: ['title', 'subtitle', 'icon'], template: '<section><h2 v-if="title">{{ title }}</h2><slot /></section>' },
  OpsTableShell: { template: '<div><slot /></div>' },
  OpsEmptyState: { template: '<div />' },
  SimpleBarChart: { template: '<div />' },
  DistributionDonutChart: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
}

describe('Servers view', () => {
  it('supports create, edit and delete actions', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    routeState.params = {}
    routeState.query = {}

    const wrapper = mount(Servers, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('10.0.0.1')
    expect(wrapper.text()).toContain('D13')

    const createButton = wrapper.findAll('button').find((button) => button.text().includes('新增服务器'))
    expect(createButton).toBeTruthy()
    await createButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(pushMock).toHaveBeenCalled()

    const createInputs = wrapper.findAll('input')
    expect(createInputs.length).toBeGreaterThan(0)

    await createInputs[0].setValue('10.0.0.2')
    await createInputs[1].setValue('srv-02')
    await createInputs[8].setValue('华南')
    await createInputs[9].setValue('D18')

    const createForm = wrapper.find('form')
    expect(createForm.exists()).toBe(true)
    await createForm.trigger('submit.prevent')
    await flushPromises()

    expect(createServerMock).toHaveBeenCalled()

    routeState.params = {}
    routeState.query = {}
    await flushPromises()
    await flushPromises()

    expect(updateServerMock).not.toHaveBeenCalled()

    const deleteButton = wrapper.findAll('button').find((button) => button.text().includes('删除'))
    expect(deleteButton).toBeTruthy()
    await deleteButton!.trigger('click')
    await flushPromises()

    expect(deleteServerMock).toHaveBeenCalledWith(1)
  })

  it('shows overview and related instances in detail view', async () => {
    routeState.params = { id: '1' }
    routeState.query = {}

    const wrapper = mount(Servers, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(getServerMock).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('基礎信息')
    expect(wrapper.text()).toContain('当前关联实例')
    expect(wrapper.text()).toContain('10.0.0.1')
    expect(wrapper.text()).toContain('INS-001')
    expect(wrapper.text()).toContain('db-01')
    expect(wrapper.text()).toContain('MySQL')
    expect(wrapper.html()).toContain('field-card')
    expect(wrapper.html()).toContain('field-label')
    expect(wrapper.find('form').exists()).toBe(false)
  })
})
