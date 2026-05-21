import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const routerPushMock = vi.fn()

import ImportView from './Import.vue'

const previewImportMock = vi.fn().mockResolvedValue({
  total: 1,
  success_count: 0,
  error_count: 1,
  warning_count: 1,
  conflict_count: 0,
  errors: ['行2: CLUSTER_TYPE 不支持 (DATAGUARDX)'],
  warnings: ['覆盖风险: 主机 IP 10.0.0.10 已存在，导入会更新现有主机记录'],
  issue_groups: [
    {
      key: 'validation',
      label: '校验错误',
      count: 1,
      items: ['行2: CLUSTER_TYPE 不支持 (DATAGUARDX)'],
    },
  ],
  items: [
    {
      row_num: 2,
      status: 'error',
      errors: ['行2: CLUSTER_TYPE 不支持 (DATAGUARDX)'],
      warnings: ['覆盖风险: 主机 IP 10.0.0.10 已存在，导入会更新现有主机记录'],
      fields: {
        system_name: '测试系统',
        cluster_code: 'CLU-TEST',
        instance_name: 'TEST01',
        server_ip: '10.0.0.10',
        db_type: 'Oracle',
        node_role: 'primary',
      },
      source_file_name: 'hr_list.xlsx',
    },
  ],
  debug_headers: ['CLUSTER_TYPE'],
  import_mode: '新增',
  stage: 'previewed',
  stage_label: '预览完成',
  progress: 100,
})

const executeImportMock = vi.fn().mockResolvedValue({
  import_batch_id: 'batch-1',
  import_mode: '新增',
  stage: 'completed',
  stage_label: '导入完成',
  progress: 100,
  success: 1,
  updated: 0,
  error: 0,
  error_count: 0,
  warning_count: 0,
  conflict_count: 0,
  errors: [],
  warnings: [],
  issue_groups: [],
  message: '导入完成: 新增 1 条, 更新 0 条, 失败 0 条',
})

vi.mock('@/api/assets', () => ({
  assetsApi: {
    previewImport: (...args: any[]) => previewImportMock(...args),
    executeImport: (...args: any[]) => executeImportMock(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

describe('Import view', () => {
  it('renders wizard steps and structured preview results', async () => {
    const wrapper = mount(ImportView)

    await flushPromises()

    expect(wrapper.text()).toContain('导入资产')
    expect(wrapper.text()).toContain('选择文件')
    expect(wrapper.text()).toContain('选择导入模式')
    expect(wrapper.text()).toContain('预览与校验')
    expect(wrapper.text()).toContain('执行导入')
    expect(wrapper.text()).toContain('完成')
    expect(wrapper.text()).toContain('导入帮助')

    const fileInput = wrapper.find('input[type="file"]')
    const file = new File(['dummy'], 'hr_list.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      writable: false,
    })
    await fileInput.trigger('change')

    const nextButtonsAfterFile = wrapper.findAll('button').filter((button) => button.text().includes('下一步'))
    expect(nextButtonsAfterFile.length).toBeGreaterThan(0)
    await nextButtonsAfterFile[0].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('选择导入模式')
    expect(wrapper.text()).toContain('新增导入')
    expect(wrapper.text()).toContain('更新导入')
    expect(wrapper.text()).toContain('更新联系人')

    const modeButtons = wrapper.findAll('button').filter((button) => button.text().includes('新增导入'))
    expect(modeButtons.length).toBeGreaterThan(0)

    const secondNextButtons = wrapper.findAll('button').filter((button) => button.text().includes('下一步'))
    expect(secondNextButtons.length).toBeGreaterThan(0)
    await secondNextButtons[0].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('预览与校验')

    const previewButton = wrapper.findAll('button').find((button) => button.text().includes('开始预览校验'))
    expect(previewButton).toBeTruthy()
    await previewButton!.trigger('click')
    await flushPromises()

    expect(previewImportMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('总数')
    expect(wrapper.text()).toContain('错误')
    expect(wrapper.text()).toContain('10.0.0.10')
    expect(wrapper.text()).toContain('覆盖风险')

    const rowExpandButton = wrapper.findAll('button').find(
      (button) => button.text().includes('展开') && !button.text().includes('展开更多'),
    )
    expect(rowExpandButton).toBeTruthy()
    await rowExpandButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('10.0.0.10')
    expect(wrapper.text()).toContain('校验错误')
    expect(wrapper.text()).toContain('覆盖风险')
    expect(wrapper.text()).toContain('主机 IP 10.0.0.10 已存在，导入会更新现有主机记录')
    expect(wrapper.text()).toContain('行2: CLUSTER_TYPE 不支持 (DATAGUARDX)')

    const enterExecuteButton = wrapper.findAll('button').find((button) => button.text().includes('进入执行'))
    expect(enterExecuteButton).toBeTruthy()
    await enterExecuteButton!.trigger('click')
    await flushPromises()

    const executeButton = wrapper.findAll('button').find((button) => button.text().includes('开始导入'))
    expect(executeButton).toBeTruthy()
    await executeButton!.trigger('click')
    await flushPromises()

    expect(executeImportMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('导入完成')
    expect(wrapper.text()).toContain('batch-1')
  })
})
