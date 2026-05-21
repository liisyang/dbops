import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard.vue'

vi.mock('@/api/stats', () => ({
  statsApi: {
    getDashboard: vi.fn().mockResolvedValue({
      total_business_systems: 1,
      total_clusters: 2,
      total_instances: 3,
      total_servers: 4,
    }),
    getByCountry: vi.fn().mockResolvedValue({
      groups: [
        { country: '中国', count: 20 },
        { country: '日本', count: 5 },
      ],
    }),
    getSummaryByType: vi.fn().mockResolvedValue({
      groups: [
        { db_type: 'Oracle', count: 13 },
        { db_type: 'PostgreSQL', count: 7 },
      ],
    }),
    getByFactory: vi.fn().mockResolvedValue({
      groups: [
        { factory_area: '龙华', count: 12 },
        { factory_area: '郑州', count: 8 },
      ],
    }),
    getByDeployType: vi.fn().mockResolvedValue({
      groups: [
        { deploy_type: '生产', count: 14 },
        { deploy_type: '测试', count: 6 },
      ],
    }),
    getByProvider: vi.fn().mockResolvedValue({
      groups: [
        { provider: '自建机房', count: 11 },
        { provider: '阿里云', count: 9 },
      ],
    }),
  },
}))

describe('Dashboard', () => {
  it('renders factory area instance statistics', async () => {
    const wrapper = mount(Dashboard)

    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('按国家 / 厂区 / 实例数')
    expect(wrapper.text()).toContain('实例总数')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('按国家分布')
    expect(wrapper.text()).toContain('中国')
    expect(wrapper.text()).toContain('20')
    expect(wrapper.text()).toContain('日本')
    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('按数据库类型分布')
    expect(wrapper.text()).toContain('Oracle')
    expect(wrapper.text()).toContain('13')
    expect(wrapper.text()).toContain('PostgreSQL')
    expect(wrapper.text()).toContain('7')
    expect(wrapper.findAll('div[style*="width:"]').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('按厂区分布')
    expect(wrapper.text()).toContain('龙华')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('郑州')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('按部署类型 / Provider / 实例数')
    expect(wrapper.text()).toContain('实例总数')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('按部署类型分布')
    expect(wrapper.text()).toContain('生产')
    expect(wrapper.text()).toContain('14')
    expect(wrapper.text()).toContain('测试')
    expect(wrapper.text()).toContain('6')
    expect(wrapper.text()).toContain('按资源提供方分布')
    expect(wrapper.text()).toContain('自建机房')
    expect(wrapper.text()).toContain('11')
    expect(wrapper.text()).toContain('阿里云')
    expect(wrapper.text()).toContain('9')
  })
})
