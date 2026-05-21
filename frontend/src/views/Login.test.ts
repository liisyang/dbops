import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Login from './Login.vue'
import { createRouter, createMemoryHistory } from 'vue-router'

// Mock authApi
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn()
  }
}))

// Mock useUserStore
vi.mock('@/stores/user', () => ({
  useUserStore: () => ({
    login: vi.fn(),
    setUserTimezone: vi.fn(),
    setUserLanguage: vi.fn()
  })
}))

// Mock utils
vi.mock('@/utils/timezone', () => ({
  detectTimezone: () => 'Asia/Shanghai'
}))

vi.mock('@/utils/i18n', () => ({
  detectLanguage: () => 'zh-CN'
}))

describe('Login Form Validation', () => {
  let router: any

  beforeEach(() => {
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div>Home</div>' } },
        { path: '/login', component: Login }
      ]
    })
    router.push('/login')
  })

  it('shows error when username is empty', async () => {
    const wrapper = mount(Login, {
      global: {
        plugins: [router]
      }
    })

    // Find password input and fill it
    const passwordInput = wrapper.find('input[type="password"]')
    await passwordInput.setValue('testpassword')

    // Trigger form submit directly
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    // Should show username error
    await flushPromises()
    const errorMsg = wrapper.find('.bg-red-500')
    expect(errorMsg.exists()).toBe(true)
  })

  it('shows error when password is empty', async () => {
    const wrapper = mount(Login, {
      global: {
        plugins: [router]
      }
    })

    // Find username input and fill it
    const usernameInput = wrapper.find('input[type="text"]')
    await usernameInput.setValue('testuser')

    // Trigger form submit directly
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    // Should show password error
    await flushPromises()
    const errorMsg = wrapper.find('.bg-red-500')
    expect(errorMsg.exists()).toBe(true)
  })

  it('shows error when credentials are invalid', async () => {
    const { authApi } = await import('@/api/auth')
    ;(authApi.login as any).mockRejectedValue(new Error('用户名或密码错误'))

    const wrapper = mount(Login, {
      global: {
        plugins: [router]
      }
    })

    // Fill in both fields
    const usernameInput = wrapper.find('input[type="text"]')
    const passwordInput = wrapper.find('input[type="password"]')
    await usernameInput.setValue('wronguser')
    await passwordInput.setValue('wrongpassword')

    // Trigger form submit directly
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    // Wait for the API call to fail
    await flushPromises()
    await flushPromises()

    // Should show error message
    const errorMsg = wrapper.find('.bg-red-500')
    expect(errorMsg.exists()).toBe(true)
  })

  it('redirects to home on successful login', async () => {
    const { authApi } = await import('@/api/auth')
    ;(authApi.login as any).mockResolvedValue({
      access_token: 'fake-token',
      user: { id: 1, username: 'testuser' }
    })

    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mount(Login, {
      global: {
        plugins: [router]
      }
    })

    // Fill in both fields
    const usernameInput = wrapper.find('input[type="text"]')
    const passwordInput = wrapper.find('input[type="password"]')
    await usernameInput.setValue('testuser')
    await passwordInput.setValue('testpassword')

    // Trigger form submit directly
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')

    // Wait for the API call and navigation
    await flushPromises()
    await flushPromises()

    // Should redirect to home
    expect(pushSpy).toHaveBeenCalledWith('/')
  })
})