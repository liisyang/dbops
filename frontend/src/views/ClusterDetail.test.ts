import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import Clusters from './Clusters.vue'
import ClusterDetail from './ClusterDetail.vue'

const listClustersMock = vi.fn().mockResolvedValue([
  {
    id: 9,
    cluster_code: 'CLS-009',
    cluster_name: 'orders-rac',
    cluster_type: 'RAC',
    business_system_id: 88,
    business_system_name: '订单系统',
    source_cluster_no: 'SRC-009',
    vip_addresses: ['10.0.0.9'],
    instance_count: 2,
    roles: ['PRIMARY', 'STANDBY'],
  },
  {
    id: 10,
    cluster_code: 'CLS-010',
    cluster_name: 'audit-single',
    cluster_type: 'SINGLE',
    business_system_id: 89,
    business_system_name: '审计系统',
    source_cluster_no: 'SRC-010',
    vip_addresses: [],
    instance_count: 1,
    roles: ['PRIMARY'],
  },
])

const getClusterMock = vi.fn().mockResolvedValue({
  id: 9,
  cluster_code: 'CLS-009',
  cluster_name: 'orders-rac',
  cluster_type: 'RAC',
  business_system_id: 88,
  business_system_name: '订单系统',
  source_cluster_no: 'SRC-009',
  vip_addresses: ['10.0.0.9'],
  instance_count: 2,
  roles: ['PRIMARY', 'STANDBY'],
  instances: [
    {
      id: 101,
      instance_code: 'INS-101',
      instance_name: 'orders-db-01',
      cluster_id: 9,
      cluster_code: 'CLS-009',
      cluster_name: 'orders-rac',
      cluster_type: 'RAC',
      db_type: 'Oracle',
      db_version: '19c',
      node_role: 'PRIMARY',
      engine_role: 'RW',
      source_node_role: 'MASTER',
      server_id: 7001,
      server_ip: '10.0.0.21',
      hostname: 'dbhost-01',
      country: 'CN',
      factory_area: '龙华',
      deploy_type: '生产',
      provider: '自建机房',
    },
  ],
})

const routeState = reactive<{ params: Record<string, any> }>({
  params: { clusterCode: 'CLS-009' },
})
const pushMock = vi.fn()

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listClusters: (...args: any[]) => listClustersMock(...args),
    getCluster: (...args: any[]) => getClusterMock(...args),
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
    template: '<div><h1>{{ title }}</h1><p>{{ subtitle }}</p><slot name="actions" /><div><slot /></div></div>',
  },
  OpsStatGrid: { template: '<div />' },
  OpsFilterBar: { template: '<div><slot /><slot name="actions" /></div>' },
  OpsSectionCard: {
    props: ['title', 'subtitle', 'icon'],
    template: '<section><h2 v-if="title">{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p><slot /></section>',
  },
  OpsTableShell: { template: '<div><slot /></div>' },
  OpsEmptyState: { template: '<div />' },
  OpsTopology: { template: '<div>TOPOLOGY</div>' },
  SimpleBarChart: { template: '<div />' },
  RouterLink: { template: '<a><slot /></a>' },
}

beforeEach(() => {
  listClustersMock.mockClear()
  getClusterMock.mockClear()
  pushMock.mockClear()
  routeState.params = { clusterCode: 'CLS-009' }
})

describe('Cluster detail flow', () => {
  it('navigates from non-SINGLE cluster rows and keeps SINGLE rows non-navigable', async () => {
    routeState.params = {}

    const wrapper = mount(Clusters, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)

    await rows[0].trigger('click')
    expect(pushMock).toHaveBeenCalledWith('/assets/clusters/CLS-009')

    pushMock.mockClear()
    await rows[1].trigger('click')
    expect(pushMock).not.toHaveBeenCalled()
  })

  it('renders the shared page shell and dense summary cards', async () => {
    routeState.params = { clusterCode: 'CLS-009' }

    const wrapper = mount(ClusterDetail, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(listClustersMock).toHaveBeenCalled()
    expect(getClusterMock).toHaveBeenCalledWith(9)
    expect(wrapper.text()).toContain('返回集群列表')
    expect(wrapper.text()).toContain('基础信息')
    expect(wrapper.text()).toContain('动态集群架构图')
    expect(wrapper.text()).toContain('实例编码')
    expect(wrapper.text()).toContain('orders-db-01')
    expect(wrapper.text()).toContain('Cluster Code')
    expect(wrapper.text()).toContain('集群名称')
    expect(wrapper.text()).toContain('CLS-009')
    expect(wrapper.text()).toContain('orders-rac')
    expect(wrapper.text()).toContain('RAC')
    expect(wrapper.html()).toContain('field-card')
    expect(wrapper.html()).toContain('xl:grid-cols-4')
  })
})
