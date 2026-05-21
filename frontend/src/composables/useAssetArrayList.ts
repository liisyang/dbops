import { onMounted, ref } from 'vue'

type ArrayFetcher<T> = () => Promise<T[]> | T[]

export function useAssetArrayList<T>(fetchList: ArrayFetcher<T>) {
  const items = ref<T[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function reload() {
    loading.value = true
    error.value = null

    try {
      items.value = await Promise.resolve(fetchList())
    } catch (err: any) {
      error.value = err?.message || '请求失败'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void reload()
  })

  return {
    items,
    loading,
    error,
    reload,
  }
}
