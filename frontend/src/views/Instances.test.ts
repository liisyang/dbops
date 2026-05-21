import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import InstanceDetail from './InstanceDetail.vue'
import Instances from './Instances.vue'

const listInstancesMock = vi.fn().mockResolvedValue({
  total: 1,
  page: 1,
  page_size: 30,
  items: [
    {
      id: 7,
      instance_code: 'INS-007',
      instance_name: 'db-prod-07',
      cluster_id: 301,
      cluster_code: 'CLS-301',
      cluster_name: 'orders-rac',
      cluster_type: 'RAC',
      db_type: 'Oracle',
      db_version: '19c',
      node_role: 'PRIMARY',
      engine_role: 'RW',
      source_node_role: 'MASTER',
      server_id: 21,
      server_ip: '10.10.7.21',
      hostname: 'dbhost-07',
      country: 'CN',
      factory_area: '龙华',
      deploy_type: '生产',
      provider: '自建机房',
    },
  ],
})

const getInstanceMock = vi.fn().mockResolvedValue({
  id: 7,
  instance_code: 'INS-007',
  instance_name: 'db-prod-07',
  cluster_id: 301,
  cluster_code: 'CLS-301',
  cluster_name: 'orders-rac',
  cluster_type: 'RAC',
  db_type: 'Oracle',
  db_version: '19c',
  node_role: 'PRIMARY',
  engine_role: 'RW',
  source_node_role: 'MASTER',
  server_id: 21,
  server_ip: '10.10.7.21',
  hostname: 'dbhost-07',
  country: 'CN',
  factory_area: '龙华',
  deploy_type: '生产',
  provider: '自建机房',
})

const routeState = reactive<{ params: Record<string, any> }>({
  params: { id: '7' },
})
const pushMock = vi.fn()

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listInstances: (...args: any[]) => listInstancesMock(...args),
    getInstance: (...args: any[]) => getInstanceMock(...args),
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
  OpsTableShell: { template: '<div><slot /></div>' },
  SimpleBarChart: { template: '<div />' },
  OpsSectionCard: { props: ['title', 'subtitle', 'icon'], template: '<section><h2 v-if="title">{{ title }}</h2><slot /></section>' },
  OpsEmptyState: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
}

describe('Instances view and detail view', () => {
  it('navigates from the instance list row to the detail route', async () => {
    const wrapper = mount(Instances, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(listInstancesMock).toHaveBeenCalled()

    const row = wrapper.find('tbody tr')
    expect(row.exists()).toBe(true)

    await row.trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/assets/instances/7')
  })

  it('loads detail payload and renders the compact sections', async () => {
    routeState.params = { id: '7' }

    const wrapper = mount(InstanceDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(getInstanceMock).toHaveBeenCalledWith('7')
    expect(wrapper.text()).toContain('基础信息')
    expect(wrapper.text()).toContain('角色信息')
    expect(wrapper.text()).toContain('主机信息')
    expect(wrapper.text()).toContain('集群信息')
    expect(wrapper.text()).toContain('db-prod-07')
    expect(wrapper.text()).toContain('10.10.7.21')
    expect(wrapper.text()).toContain('生产')
    expect(wrapper.text()).toContain('自建机房')
    expect(wrapper.text()).toContain('RAC')
    expect(wrapper.text()).not.toContain('实例 ID')
    expect(wrapper.text()).not.toContain('集群 ID')
    expect(wrapper.html()).toContain('field-card')
  })
})
