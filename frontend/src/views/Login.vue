<template>
  <div class="min-h-screen flex items-center justify-center relative px-6 py-12 bg-[#0a151a]">
    <!-- Background Decor -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-[#9ecaff]/5 rounded-full blur-[120px]"></div>
      <div class="absolute -bottom-[10%] -right-[10%] w-[30%] h-[30%] bg-[#4edea3]/5 rounded-full blur-[100px]"></div>
    </div>

    <div class="w-full max-w-[1100px] grid grid-cols-1 lg:grid-cols-12 gap-12 items-center relative z-10">
      <!-- Left Side: Editorial Authority & Security Tips -->
      <div class="lg:col-span-5 hidden lg:block">
        <div class="space-y-8">
          <div class="space-y-2">
            <span class="text-[#9ecaff] text-[0.75rem] uppercase tracking-[0.2rem]">DBOPS 统一入口</span>
            <h1 class="text-[#dae2fd] font-['Inter'] font-black text-5xl tracking-tighter leading-none">
              资产管理<br/>
              <span class="text-[#c2c6d6]">运维工作台</span>
            </h1>
          </div>
          <p class="text-[#c2c6d6] text-lg leading-relaxed max-w-sm">
            统一进入服务器、数据库实例、业务系统和集群关系的管理入口。登录后可查看资产、导入数据和运维信息。
          </p>
          <div class="space-y-6 pt-8">
            <!-- Security Tip Card -->
            <div class="bg-[#121d23] p-6 rounded-xl border-l-4 border-[#9ecaff]">
              <div class="flex items-start gap-4">
                <span class="material-symbols-outlined text-[#9ecaff]">verified_user</span>
                <div>
                  <h4 class="font-bold text-[#dae2fd] text-sm uppercase tracking-wider mb-1">访问确认</h4>
                  <p class="text-[#c2c6d6] text-xs leading-normal">请确认当前访问的是正确的 DBOPS 地址，再输入账号和密码。</p>
                </div>
              </div>
            </div>
            <div class="bg-[#121d23] p-6 rounded-xl">
              <div class="flex items-start gap-4">
                <span class="material-symbols-outlined text-[#4edea3]">encrypted</span>
                <div>
                  <h4 class="font-bold text-[#dae2fd] text-sm uppercase tracking-wider mb-1">权限隔离</h4>
                  <p class="text-[#c2c6d6] text-xs leading-normal">登录后依据角色权限展示对应模块，避免误操作和越权访问。</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Side: Login Card -->
      <div class="lg:col-span-7 flex flex-col items-center">
        <div class="w-full max-w-md glass-effect p-10 rounded-xl shadow-[0_32px_32px_rgba(218,226,253,0.08)]">
          <!-- Branding -->
          <div class="mb-8 flex flex-col items-center gap-3 text-center">
            <img
              :src="logoUrl"
              alt="DBOPS Logo"
              class="h-14 w-14 rounded-xl object-contain shadow-[0_10px_24px_rgba(173,198,255,0.18)]"
            />
            <div>
              <h2 class="text-[#9ecaff] font-black text-2xl tracking-tighter">DBOPS</h2>
              <p class="mt-1 text-xs uppercase tracking-[0.24rem] text-[#c2c6d6]/70">资产管理平台</p>
            </div>
          </div>

          <!-- Login Form Section -->
          <div class="space-y-6">
            <div class="space-y-1">
              <h3 class="text-2xl font-bold text-[#dae2fd] tracking-tight">账号登录</h3>
              <p class="text-[#c2c6d6] text-sm">请输入账号信息后继续进入系统。</p>
            </div>

            <form @submit.prevent="handleLogin" class="space-y-4">
              <!-- Username -->
              <div class="space-y-1.5">
                <label class="text-[0.7rem] font-bold text-[#c2c6d6] uppercase tracking-widest pl-1">用户名</label>
                <div class="bg-[#2b363d] flex items-center px-4 py-3 rounded argon-input-focus transition-all">
                  <span class="material-symbols-outlined text-[#8c909f] text-lg mr-3">person</span>
                  <input
                    v-model="loginForm.username"
                    type="text"
                    placeholder="请输入用户名"
                    required
                    class="w-full bg-transparent border-none text-[#dae2fd] placeholder:text-[#c2c6d6]/40 focus:outline-none"
                  />
                </div>
              </div>

              <!-- Password -->
              <div class="space-y-1.5">
                <label class="text-[0.7rem] font-bold text-[#c2c6d6] uppercase tracking-widest pl-1">密码</label>
                <div class="bg-[#2b363d] flex items-center px-4 py-3 rounded argon-input-focus transition-all">
                  <span class="material-symbols-outlined text-[#8c909f] text-lg mr-3">lock</span>
                  <input
                    v-model="loginForm.password"
                    type="password"
                    placeholder="请输入密码"
                    required
                    class="w-full bg-transparent border-none text-[#dae2fd] placeholder:text-[#c2c6d6]/40 focus:outline-none"
                  />
                </div>
              </div>

              <!-- Error message -->
              <div v-if="errorMsg" class="bg-[#93000a] text-[#ffb4ab] px-4 py-3 rounded text-sm">
                {{ errorMsg }}
              </div>

              <!-- Submit button -->
              <button
                type="submit"
                :disabled="loading"
                class="w-full py-3 px-4 bg-gradient-to-br from-[#9ecaff] to-[#0087df] text-[#003258] font-bold rounded-md hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#9ecaff] focus:ring-offset-2 focus:ring-offset-[#0a151a] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
              >
                <span v-if="loading" class="material-symbols-outlined animate-spin">progress_activity</span>
                <span>{{ loading ? '登录中...' : '登录' }}</span>
              </button>
            </form>

            <!-- Footer -->
            <div class="mt-6 text-center text-xs text-[#c2c6d6]/60">
              DBOPS 资产管理平台
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { detectTimezone } from '@/utils/timezone'
import { detectLanguage } from '@/utils/i18n'
const logoUrl = '/logo.png'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const errorMsg = ref('')

const loginForm = reactive({
  username: '',
  password: ''
})

const handleLogin = async () => {
  try {
    errorMsg.value = ''

    if (!loginForm.username.trim()) {
      errorMsg.value = '请输入用户名'
      return
    }
    if (!loginForm.password) {
      errorMsg.value = '请输入密码'
      return
    }

    loading.value = true

    const response = await authApi.login(loginForm.username, loginForm.password)

    const token = response.access_token
    const userData = response.user
    if (token) {
      userStore.login(userData, token)
      if (!userData.timezone) {
        userStore.setUserTimezone(detectTimezone())
      }
      if (!userData.language) {
        userStore.setUserLanguage(detectLanguage())
      }
    }

    router.push('/')
  } catch (error: any) {
    // 优先展示后端返回的具体错误原因
    const serverDetail = error?.response?.data?.detail
    if (serverDetail) {
      errorMsg.value = serverDetail
    } else if (error?.response?.status >= 500) {
      errorMsg.value = '服务器内部错误，请稍后重试或联系管理员'
    } else if (error?.response?.status === 401) {
      errorMsg.value = '用户名或密码错误'
    } else if (error?.code === 'ERR_NETWORK' || !error?.response) {
      errorMsg.value = '无法连接到服务器，请确认后端服务已启动'
    } else {
      errorMsg.value = error.message || '登录失败'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.glass-effect {
  backdrop-filter: blur(20px);
  background: rgba(19, 27, 46, 0.6);
}

.argon-input-focus:focus-within {
  border-bottom: 2px solid #9ecaff;
}
</style>
