import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Contacts from './Contacts.vue'

const listContactsMock = vi.fn().mockResolvedValue([
  {
    id: 1,
    employee_no: 'E001',
    contact_code: 'CT-001',
    contact_name: '张三',
    phone: '13800000000',
    email: 'zhangsan@example.com',
    dept: 'DBA',
    remark: 'owner',
  },
])

const createContactMock = vi.fn().mockResolvedValue({ id: 2 })
const updateContactMock = vi.fn().mockResolvedValue({ id: 1 })
const deleteContactMock = vi.fn().mockResolvedValue({ message: 'ok' })

vi.mock('@/api/assets', () => ({
  assetsApi: {
    listContacts: (...args: any[]) => listContactsMock(...args),
    createContact: (...args: any[]) => createContactMock(...args),
    updateContact: (...args: any[]) => updateContactMock(...args),
    deleteContact: (...args: any[]) => deleteContactMock(...args),
  },
}))

const globalStubs = {
  OpsPage: { template: '<div><slot /></div>' },
  OpsPageHeader: {
    props: ['title', 'subtitle'],
    template: '<header><h1>{{ title }}</h1><p>{{ subtitle }}</p><slot name="actions" /></header>',
  },
  OpsFilterBar: {
    emits: ['update:keyword', 'search', 'reset'],
    template: '<div><slot /></div>',
  },
  OpsSectionCard: {
    props: ['title', 'subtitle', 'icon'],
    template: '<section><h2>{{ title }}</h2><p>{{ subtitle }}</p><slot /></section>',
  },
  OpsTableShell: {
    template: '<div><slot /></div>',
  },
}

beforeEach(() => {
  listContactsMock.mockClear()
  createContactMock.mockClear()
  updateContactMock.mockClear()
  deleteContactMock.mockClear()
})

describe('Contacts view', () => {
  it('renders master data and supports create / edit / delete actions', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(Contacts, {
      global: {
        stubs: globalStubs,
      },
    })

    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('联系人管理')
    expect(wrapper.text()).toContain('张三')
    expect(wrapper.text()).toContain('新增联系人')

    await wrapper.findAll('button').find((button) => button.text() === '新增联系人')!.trigger('click')
    await flushPromises()

    await wrapper.find('input[placeholder="可选"]').setValue('E002')
    await wrapper.find('input[placeholder="必填"]').setValue('李四')
    const optionalInputs = wrapper.findAll('input[placeholder="可选"]')
    await optionalInputs[1].setValue('13900000000')
    await optionalInputs[2].setValue('lisi@example.com')
    await optionalInputs[3].setValue('应用部')
    await wrapper.find('textarea').setValue('new owner')
    await flushPromises()

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(createContactMock).toHaveBeenCalledWith({
      employee_no: 'E002',
      contact_name: '李四',
      phone: '13900000000',
      email: 'lisi@example.com',
      dept: '应用部',
      remark: 'new owner',
    })

    await wrapper.findAll('button').find((button) => button.text() === '编辑')!.trigger('click')
    await flushPromises()

    await wrapper.find('input[placeholder="必填"]').setValue('张三更新')
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await flushPromises()

    expect(updateContactMock).toHaveBeenCalledWith(1, expect.objectContaining({
      contact_name: '张三更新',
    }))

    await wrapper.findAll('button').find((button) => button.text() === '删除')!.trigger('click')
    await flushPromises()

    expect(deleteContactMock).toHaveBeenCalledWith(1)
  })
})
