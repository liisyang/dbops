import { onMounted, ref } from 'vue'
import type { PaginatedResult } from '@/types/api'

type PageFetcher<T> = (params: { page: number; page_size: number }) => Promise<PaginatedResult<T>>

export function usePagedAssetList<T>(fetchPage: PageFetcher<T>, pageSize = 50) {
  const items = ref<T[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function reload() {
    loading.value = true
    error.value = null

    try {
      const firstPage = await fetchPage({ page: 1, page_size: pageSize })
      const mergedItems = [...firstPage.items]
      const totalPages = Math.ceil(firstPage.total / pageSize)

      for (let page = 2; page <= totalPages; page += 1) {
        const nextPage = await fetchPage({ page, page_size: pageSize })
        mergedItems.push(...nextPage.items)
      }

      items.value = mergedItems
      total.value = firstPage.total
    } catch (err: any) {
      error.value = err?.message || '请求失败'
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void reload()
  })

  return {
    items,
    total,
    loading,
    error,
    reload,
  }
}
