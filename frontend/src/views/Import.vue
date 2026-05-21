<template>
  <OpsPage class="space-y-6">
    <OpsPageHeader
      title="导入资产"
      subtitle="通过 Excel 文件批量导入服务器、实例、集群和业务资产"
    />

    <OpsStepper :steps="wizardSteps" :current-step="wizardStepperStep" />

    <section v-if="isCompletionView" class="space-y-6">
      <div class="space-y-5">
        <div class="overflow-hidden rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-start gap-3">
              <span class="material-symbols-outlined shrink-0 text-[3rem] leading-none text-emerald-300">check_circle</span>
              <div>
                <div class="text-lg font-semibold text-on-surface">导入完成</div>
                <div class="mt-1.5 text-xs text-on-surface">本次导入已成功完成。</div>
              </div>
            </div>
          </div>
          <div class="mt-4 border-t border-outline-variant/40 pt-3">
            <div class="text-sm font-semibold text-on-surface">导入统计</div>
            <div class="mt-2 grid grid-cols-2 gap-1.5 lg:grid-cols-4">
              <div
                v-for="item in summaryStats"
                :key="item.label"
                class="rounded-2xl border border-outline-variant/60 bg-black/10 p-1.5"
              >
                <div class="text-[11px] text-on-surface-variant">{{ item.label }}</div>
                <div
                  class="mt-0.5 text-base font-semibold"
                  :class="item.tone === 'success'
                    ? 'text-emerald-300'
                    : item.tone === 'warning'
                      ? 'text-amber-300'
                      : item.tone === 'primary'
                        ? 'text-cyan-300'
                        : 'text-on-surface'"
                >
                  {{ item.value }}
                </div>
                <div class="mt-0.5 text-[11px] leading-snug text-on-surface-variant">{{ item.hint }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="grid gap-6 xl:grid-cols-2">
          <div class="h-full rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
            <div class="mb-4 flex items-center gap-2 text-sm font-semibold text-on-surface">
              <span class="material-symbols-outlined text-[20px] text-primary">assignment</span>
              批次信息
            </div>
            <div class="grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2">
              <div>
                <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">批次号</div>
                <div class="mt-1 break-all text-on-surface">{{ executeResult?.import_batch_id || 'N/A' }}</div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">文件名称</div>
                <div class="mt-1 text-on-surface">{{ selectedFile?.name || 'N/A' }}</div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">导入时间</div>
                <div class="mt-1 text-on-surface">{{ importCompletedAt || 'N/A' }}</div>
              </div>
              <div>
                <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">文件大小</div>
                <div class="mt-1 text-on-surface">{{ selectedFileSize }}</div>
              </div>
            </div>
          </div>

          <div class="h-full rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
            <div class="text-sm font-semibold text-on-surface">后续操作</div>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]"
                @click="showCompletionLog = !showCompletionLog"
              >
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant">description</span>
                查看导入日志
              </button>
              <button
                type="button"
                class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]"
                @click="downloadIssueReport"
              >
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant">download</span>
                下载错误明细
              </button>
              <button type="button" class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]" @click="restartWizard">
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant">refresh</span>
                重新导入
              </button>
              <button
                type="button"
                class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]"
                @click="goToAssetList"
              >
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant">table_view</span>
                返回资产列表
              </button>
            </div>
            <div v-if="showCompletionLog" class="mt-4 rounded-2xl border border-outline-variant/60 bg-black/15 p-3">
              <div class="mb-2 text-xs uppercase tracking-[0.22em] text-on-surface-variant">导入日志</div>
              <div v-if="activityLog.length" class="space-y-2">
                <div
                  v-for="entry in activityLog"
                  :key="`${entry.time}-${entry.message}`"
                  class="rounded-xl bg-white/[0.03] px-3 py-2 text-xs text-on-surface-variant"
                >
                  <span class="font-mono text-on-surface">{{ entry.time }}</span>
                  <span class="ml-2">{{ entry.message }}</span>
                </div>
              </div>
              <div v-else class="text-xs text-on-surface-variant">暂无日志。</div>
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
          <div class="text-sm font-semibold text-on-surface">导入问题</div>
          <div v-if="issueSummarySections.length" class="mt-4 space-y-3">
            <div
              v-for="section in visibleIssueSystemSections"
              :key="section.title"
              class="rounded-2xl border border-outline-variant/60 bg-white/[0.03] p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-on-surface">{{ section.title }}</div>
                  <div class="mt-1 text-xs text-on-surface-variant">{{ section.count }} {{ section.countLabel }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <span class="rounded-full border px-2.5 py-1 text-[11px]" :class="section.toneClass">
                    {{ section.badge }}
                  </span>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                    @click="toggleSystemSection(section.title, section.items)"
                  >
                    {{ getVisibleSystemCount(section.title, section.items) > 0 ? '收起' : '展开' }}
                    <span class="material-symbols-outlined text-[14px]">
                      {{ getVisibleSystemCount(section.title, section.items) > 0 ? 'expand_less' : 'expand_more' }}
                    </span>
                  </button>
                </div>
              </div>
              <div v-if="getVisibleSystemCount(section.title, section.items) > 0" class="mt-3 space-y-3">
                <div
                  v-for="item in getVisibleSystemItems(section.title, section.items)"
                  :key="item.primary"
                  class="rounded-2xl border border-outline-variant/60 bg-black/10 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <div class="text-sm font-medium text-on-surface">{{ item.primary }}</div>
                      <div class="mt-1 text-xs text-on-surface-variant">{{ item.secondary.length }} 条明细</div>
                    </div>
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                      @click="toggleIpSection(section.title, item.primary, item.secondary)"
                    >
                      {{ getVisibleIpCount(section.title, item.primary, item.secondary) > 0 ? '收起' : '展开' }}
                      <span class="material-symbols-outlined text-[14px]">
                        {{ getVisibleIpCount(section.title, item.primary, item.secondary) > 0 ? 'expand_less' : 'expand_more' }}
                      </span>
                    </button>
                  </div>
                  <ul v-if="getVisibleIpCount(section.title, item.primary, item.secondary) > 0" class="mt-3 space-y-2 text-xs text-on-surface-variant">
                    <li v-for="detail in getVisibleIpItems(section.title, item.primary, item.secondary)" :key="detail" class="rounded-xl bg-black/10 px-3 py-2">
                      {{ detail }}
                    </li>
                    <li v-if="item.secondary.length > getVisibleIpCount(section.title, item.primary, item.secondary)" class="pt-1">
                      <button
                        type="button"
                        class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                        @click="expandIpSection(section.title, item.primary, item.secondary)"
                      >
                        展开更多 10 条
                        <span class="material-symbols-outlined text-[14px]">expand_more</span>
                      </button>
                    </li>
                  </ul>
                </div>
                <div v-if="section.items.length > getVisibleSystemCount(section.title, section.items)" class="pt-1">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                    @click="expandSystemSection(section.title, section.items)"
                  >
                    展开更多 10 个IP
                    <span class="material-symbols-outlined text-[14px]">expand_more</span>
                  </button>
                </div>
              </div>
            </div>
            <div class="flex items-center justify-between gap-3 rounded-2xl border border-outline-variant/60 bg-black/10 px-3 py-2 text-xs text-on-surface-variant">
              <div>第 {{ visibleIssueSystemPage }} / {{ issueSystemPageCount }} 页，共计 {{ issueSystemSections.length }} 个系统</div>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-full border border-outline-variant/60 px-3 py-1 transition-colors hover:border-primary/40 hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="visibleIssueSystemPage === 1"
                  @click="goIssueSystemPage(-1)"
                >
                  上一页
                </button>
                <button
                  type="button"
                  class="rounded-full border border-outline-variant/60 px-3 py-1 transition-colors hover:border-primary/40 hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="visibleIssueSystemPage === issueSystemPageCount"
                  @click="goIssueSystemPage(1)"
                >
                  下一页
                </button>
              </div>
            </div>
            <div
              v-for="section in issueOtherSections"
              :key="section.title"
              class="rounded-2xl border border-outline-variant/60 bg-white/[0.03] p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-on-surface">{{ section.title }}</div>
                  <div class="mt-1 text-xs text-on-surface-variant">{{ section.count }} {{ section.countLabel }}</div>
                </div>
                <span class="rounded-full border px-2.5 py-1 text-[11px]" :class="section.toneClass">
                  {{ section.badge }}
                </span>
              </div>
              <ul class="mt-3 space-y-2 text-xs text-on-surface-variant">
                <li v-for="item in getVisibleIssueItems(section.title, section.items)" :key="item.primary" class="rounded-xl bg-black/10 px-3 py-2">
                  <div class="text-sm font-medium text-on-surface">{{ item.primary }}</div>
                  <ul v-if="item.secondary.length" class="mt-2 space-y-1 text-xs text-on-surface-variant">
                    <li v-for="detail in item.secondary" :key="detail" class="rounded-lg bg-black/10 px-2 py-1">
                      {{ detail }}
                    </li>
                  </ul>
                </li>
                <li v-if="section.items.length > getVisibleIssueCount(section.title, section.items)" class="pt-1">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                    @click="expandIssueSection(section.title, section.items)"
                  >
                    展开更多 10 条
                    <span class="material-symbols-outlined text-[14px]">expand_more</span>
                  </button>
                </li>
              </ul>
            </div>
          </div>
          <OpsEmptyState
            v-else
            title="暂无问题"
            description="没有校验错误或覆盖风险。"
          />
        </div>
      </div>
    </section>

    <section v-else class="grid gap-6 xl:grid-cols-1">
      <div class="space-y-6">
        <OpsSectionCard :title="currentStepMeta.title" :subtitle="currentStepMeta.subtitle">
          <div class="space-y-6">
            <div v-if="currentStep === 1" class="space-y-4">
              <label
                class="group flex cursor-pointer flex-col gap-4 rounded-3xl border border-dashed border-outline-variant/70 bg-[linear-gradient(180deg,rgba(15,23,42,0.95),rgba(9,16,30,0.88))] p-5 transition-colors hover:border-primary/60 hover:bg-[linear-gradient(180deg,rgba(18,32,58,0.96),rgba(10,18,34,0.92))]"
              >
                <input
                  ref="fileInput"
                  type="file"
                  accept=".xlsx"
                  class="hidden"
                  @change="handleFileChange"
                />
                <div class="flex items-start gap-4">
                  <div class="rounded-2xl bg-primary/10 p-3 text-primary">
                    <span class="material-symbols-outlined text-3xl">cloud_upload</span>
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-base font-semibold text-on-surface">拖拽或点击选择 Excel 文件</div>
                    <p class="mt-1 text-sm text-on-surface-variant">
                      支持 `.xlsx`，建议直接上传 `hr_list.xlsx`。选择后继续下一步进入导入模式。
                    </p>
                    <div class="mt-4 flex flex-wrap gap-2">
                      <span class="rounded-full border border-outline-variant/60 bg-surface px-3 py-1 text-xs text-on-surface-variant">拖拽 / 点击都可以</span>
                      <span class="rounded-full border border-outline-variant/60 bg-surface px-3 py-1 text-xs text-on-surface-variant">先选择文件再继续</span>
                      <span class="rounded-full border border-outline-variant/60 bg-surface px-3 py-1 text-xs text-on-surface-variant">会先预览再写入</span>
                    </div>
                  </div>
                </div>
              </label>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="text-xs uppercase tracking-[0.24em] text-on-surface-variant">当前文件</div>
                <div class="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0">
                    <div class="truncate text-sm font-medium text-on-surface">
                      {{ fileName }}
                    </div>
                    <div class="mt-1 text-xs text-on-surface-variant">
                      {{ fileHint }}
                    </div>
                  </div>
                  <span class="rounded-full border border-outline-variant/60 bg-surface px-3 py-1 text-xs font-medium text-on-surface-variant">
                    {{ selectedFile ? '已选择' : '等待选择' }}
                  </span>
                </div>
              </div>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="text-xs uppercase tracking-[0.24em] text-on-surface-variant">模板说明</div>
                <ul class="mt-3 space-y-2 text-sm text-on-surface-variant">
                  <li>1. 使用当前模板文件，确保列名和顺序一致。</li>
                  <li>2. 预览阶段只做校验，不会影响正式数据。</li>
                  <li>3. 异常行会被跳过，覆盖风险会单独提示。</li>
                </ul>
              </div>
            </div>

            <div v-else-if="currentStep === 2" class="space-y-4">
              <div class="grid gap-3 sm:grid-cols-3">
                <button
                  v-for="mode in importModes"
                  :key="mode.value"
                  type="button"
                  class="rounded-2xl border px-4 py-3 text-left transition-colors"
                  :class="mode.value === importMode
                    ? 'border-primary/60 bg-primary/10 text-primary shadow-[0_0_0_1px_rgba(173,198,255,0.15)]'
                    : 'border-outline-variant/60 bg-background text-on-surface hover:border-primary/40 hover:bg-surface/70'"
                  @click="selectImportMode(mode.value)"
                >
                  <div class="text-sm font-semibold">{{ mode.label }}</div>
                  <div class="mt-2 text-xs leading-5 text-on-surface-variant">
                    {{ mode.description }}
                  </div>
                </button>
              </div>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="text-xs uppercase tracking-[0.24em] text-on-surface-variant">当前模式</div>
                <div class="mt-2 text-sm font-medium text-on-surface">{{ importMode }}</div>
              </div>
            </div>

            <div v-else-if="currentStep === 3" class="space-y-4">
              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    class="inline-flex min-w-[240px] items-center justify-center gap-2 rounded-2xl border border-[#8dc0ff]/60 bg-[linear-gradient(135deg,#2563eb,#0ea5e9)] px-5 py-3.5 text-sm font-semibold text-white shadow-[0_22px_48px_rgba(37,99,235,0.34)] transition-transform hover:-translate-y-0.5 hover:shadow-[0_24px_54px_rgba(14,165,233,0.42)] disabled:cursor-not-allowed disabled:opacity-55"
                    :disabled="!selectedFile || isBusy"
                    @click="handlePreview"
                  >
                    <span class="material-symbols-outlined text-[20px]">fact_check</span>
                    <span>{{ isPreviewing ? '预览中' : '开始预览校验' }}</span>
                  </button>
                  <div class="text-sm text-on-surface-variant">
                    先执行预览校验，再进入下一步。
                  </div>
                </div>
              </div>

              <div class="grid gap-3 sm:grid-cols-4">
                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                  <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">总数</div>
                  <div class="mt-2 text-2xl font-semibold text-on-surface">{{ previewResult.total }}</div>
                </div>
                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                  <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">通过</div>
                  <div class="mt-2 text-2xl font-semibold text-emerald-300">{{ previewResult.success_count }}</div>
                </div>
                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                  <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">错误</div>
                  <div class="mt-2 text-2xl font-semibold text-rose-300">{{ previewResult.error_count }}</div>
                </div>
                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                  <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">覆盖风险</div>
                  <div class="mt-2 text-2xl font-semibold text-amber-300">{{ previewResult.warning_count || 0 }}</div>
                </div>
              </div>

              <div class="max-h-[420px] overflow-auto rounded-2xl border border-outline-variant/60">
                <table class="min-w-full text-sm">
                  <thead class="bg-[#162127] text-left text-xs uppercase text-on-surface-variant">
                    <tr>
                      <th class="px-4 py-3">行</th>
                      <th class="px-4 py-3">状态</th>
                      <th class="px-4 py-3">系统</th>
                      <th class="px-4 py-3">IP</th>
                      <th class="px-4 py-3">Cluster Code</th>
                      <th class="px-4 py-3">实例</th>
                      <th class="px-4 py-3">覆盖风险</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="item in previewResult.items" :key="item.row_num">
                      <tr class="border-t border-outline-variant/40 transition-colors hover:bg-surface-container-high">
                        <td class="px-4 py-3 text-on-surface-variant">{{ item.row_num }}</td>
                        <td class="px-4 py-3">
                          <span
                            class="inline-flex rounded-full px-3 py-1 text-xs font-medium"
                            :class="item.status === 'ok'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'bg-rose-500/15 text-rose-300'"
                          >
                            {{ item.status === 'ok' ? '通过' : '异常' }}
                          </span>
                        </td>
                        <td class="px-4 py-3 text-on-surface">{{ item.fields.system_name || '-' }}</td>
                        <td class="px-4 py-3 font-mono text-on-surface">{{ getPreviewRowIp(item.fields) }}</td>
                        <td class="px-4 py-3 font-mono text-on-surface">{{ item.fields.cluster_code || '-' }}</td>
                        <td class="px-4 py-3 text-on-surface">{{ item.fields.instance_name || '-' }}</td>
                        <td class="px-4 py-3">
                          <div class="flex flex-wrap items-center gap-2">
                            <span
                              v-if="item.warnings?.length"
                              class="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-200"
                            >
                              覆盖风险 {{ item.warnings.length }}
                            </span>
                            <span
                              v-if="item.errors.length"
                              class="inline-flex items-center rounded-full border border-rose-400/30 bg-rose-500/10 px-3 py-1 text-xs font-medium text-rose-200"
                            >
                              校验错误 {{ item.errors.length }}
                            </span>
                            <button
                              v-if="item.warnings?.length || item.errors.length"
                              type="button"
                              class="inline-flex items-center gap-1 rounded-full border border-outline-variant/60 px-3 py-1 text-xs text-on-surface-variant transition-colors hover:border-primary/40 hover:text-on-surface"
                              @click="togglePreviewRow(item.row_num)"
                            >
                              {{ isPreviewRowExpanded(item.row_num) ? '收起' : '展开' }}
                              <span class="material-symbols-outlined text-[14px]">
                                {{ isPreviewRowExpanded(item.row_num) ? 'expand_less' : 'expand_more' }}
                              </span>
                            </button>
                            <span v-if="!item.warnings?.length && !item.errors.length" class="text-xs text-on-surface-variant">
                              -
                            </span>
                          </div>
                        </td>
                      </tr>
                      <tr
                        v-if="isPreviewRowExpanded(item.row_num) && (item.warnings?.length || item.errors.length)"
                        class="border-t border-outline-variant/40 bg-black/10"
                      >
                        <td colspan="7" class="px-4 py-4">
                          <div class="space-y-4 rounded-2xl border border-outline-variant/60 bg-white/[0.03] p-4">
                            <div v-if="item.errors.length">
                              <div class="text-xs font-semibold uppercase tracking-[0.18em] text-rose-200">校验错误</div>
                              <ul class="mt-2 space-y-2 text-xs text-on-surface-variant">
                                <li
                                  v-for="error in item.errors"
                                  :key="error"
                                  class="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-rose-100"
                                >
                                  {{ error }}
                                </li>
                              </ul>
                            </div>
                            <div v-if="item.warnings?.length">
                              <div class="text-xs font-semibold uppercase tracking-[0.18em] text-amber-200">覆盖风险</div>
                              <ul class="mt-2 space-y-2 text-xs text-on-surface-variant">
                                <li
                                  v-for="warning in item.warnings"
                                  :key="warning"
                                  class="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-amber-100"
                                >
                                  {{ formatPreviewWarningText(warning) }}
                                </li>
                              </ul>
                            </div>
                          </div>
                        </td>
                      </tr>
                    </template>
                    <tr v-if="!previewResult.items.length">
                      <td colspan="7" class="px-4 py-10 text-center">
                        <OpsEmptyState
                          title="暂无预览结果"
                          description="完成预览后，这里会显示每一行的校验结果。"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

            </div>

            <div v-else-if="currentStep === 4" class="space-y-4">
              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="flex items-start gap-3 text-sm text-on-surface-variant">
                  <span class="material-symbols-outlined mt-0.5 text-[20px] text-emerald-300">info</span>
                  <div>
                    <div class="font-medium text-on-surface">准备执行导入</div>
                    <div class="mt-1">
                      导入阶段会把已校验数据写入正式资产表，并输出实时日志。请确认预览内容无误后，再点击下方唯一的开始导入按钮。
                    </div>
                  </div>
                </div>
              </div>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="flex items-center justify-between gap-4">
                  <div>
                    <div class="text-xs uppercase tracking-[0.24em] text-on-surface-variant">执行进度</div>
                    <div class="mt-1 text-sm font-medium text-on-surface">{{ flowLabel }}</div>
                  </div>
                  <div class="text-2xl font-semibold text-on-surface">{{ flowProgress }}%</div>
                </div>
                <div class="mt-4 h-2 overflow-hidden rounded-full bg-white/5">
                  <div
                    class="h-full rounded-full transition-all duration-300"
                    :class="flowToneClass"
                    :style="{ width: `${flowProgress}%` }"
                  />
                </div>
                <div class="mt-3 text-xs text-on-surface-variant">
                  {{ flowMessage }}
                </div>
              </div>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-4">
                <div class="text-xs uppercase tracking-[0.24em] text-on-surface-variant">日志输出</div>
                <ul class="mt-3 space-y-2 text-sm text-on-surface-variant">
                  <li v-if="!activityLog.length" class="rounded-xl bg-white/5 px-3 py-2">
                    等待开始导入。
                  </li>
                  <li
                    v-for="entry in activityLog"
                    :key="`${entry.time}-${entry.message}`"
                    class="rounded-xl bg-white/5 px-3 py-2"
                  >
                    <span class="mr-2 text-xs text-on-surface-variant">{{ entry.time }}</span>
                    <span>{{ entry.message }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-else class="space-y-5">
              <div class="overflow-hidden rounded-2xl border border-outline-variant/60 bg-background/70 p-6">
                <div class="flex items-start justify-between gap-6">
                  <div class="flex items-start gap-5">
                    <div class="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-emerald-400/35 bg-emerald-500/10 text-emerald-300">
                      <span class="material-symbols-outlined text-4xl">check_circle</span>
                    </div>
                    <div>
                      <div class="text-2xl font-semibold text-on-surface">导入完成</div>
                      <div class="mt-2 text-sm text-on-surface-variant">本次导入已成功完成。</div>
                    </div>
                  </div>
                  <div class="hidden rounded-2xl border border-outline-variant/60 bg-white/[0.03] p-4 text-on-surface-variant md:block">
                    <span class="material-symbols-outlined text-5xl">fact_check</span>
                  </div>
                </div>
                <div class="mt-6 grid gap-3 border-t border-outline-variant/40 pt-5 sm:grid-cols-3">
                  <div class="rounded-2xl border border-outline-variant/60 bg-black/10 p-4">
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">新增</div>
                    <div class="mt-1 text-2xl font-semibold text-emerald-300">{{ completionStats.created }}</div>
                  </div>
                  <div class="rounded-2xl border border-outline-variant/60 bg-black/10 p-4">
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">更新</div>
                    <div class="mt-1 text-2xl font-semibold text-cyan-300">{{ completionStats.updated }}</div>
                  </div>
                  <div class="rounded-2xl border border-outline-variant/60 bg-black/10 p-4">
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">失败</div>
                    <div class="mt-1 text-2xl font-semibold text-rose-300">{{ completionStats.failed }}</div>
                  </div>
                </div>
              </div>

              <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
                <div class="mb-4 flex items-center gap-2 text-sm font-semibold text-on-surface">
                  <span class="material-symbols-outlined text-[20px] text-primary">assignment</span>
                  批次信息
                </div>
                <div class="grid gap-4 text-sm sm:grid-cols-2">
                  <div>
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">批次号</div>
                    <div class="mt-1 break-all text-on-surface">{{ executeResult?.import_batch_id || 'N/A' }}</div>
                  </div>
                  <div>
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">文件名称</div>
                    <div class="mt-1 text-on-surface">{{ selectedFile?.name || 'N/A' }}</div>
                  </div>
                  <div>
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">导入时间</div>
                    <div class="mt-1 text-on-surface">{{ importCompletedAt || 'N/A' }}</div>
                  </div>
                  <div>
                    <div class="text-xs uppercase tracking-[0.22em] text-on-surface-variant">文件大小</div>
                    <div class="mt-1 text-on-surface">{{ selectedFileSize }}</div>
                  </div>
                </div>
              </div>

              <div class="grid gap-4 lg:grid-cols-2">
                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
                  <div class="text-sm font-semibold text-on-surface">结果摘要</div>
                  <div class="mt-5 flex items-center gap-5">
                    <div class="flex h-28 w-28 shrink-0 items-center justify-center rounded-full border-[14px] border-emerald-400/80 bg-white/[0.03]">
                      <div class="text-center">
                        <div class="text-2xl font-semibold text-on-surface">{{ activeSummary.total }}</div>
                        <div class="text-xs text-on-surface-variant">总数</div>
                      </div>
                    </div>
                    <div class="min-w-0 flex-1 space-y-3 text-sm">
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-on-surface-variant">成功</span>
                        <span class="text-on-surface">{{ activeSummary.success }} ({{ completionRates.success }})</span>
                      </div>
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-on-surface-variant">失败</span>
                        <span class="text-on-surface">{{ activeSummary.error }} ({{ completionRates.failed }})</span>
                      </div>
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-on-surface-variant">跳过</span>
                        <span class="text-on-surface">{{ activeSummary.skipped }} ({{ completionRates.skipped }})</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="rounded-2xl border border-outline-variant/60 bg-background/70 p-5">
                  <div class="text-sm font-semibold text-on-surface">后续操作</div>
                  <div class="mt-4 space-y-3">
                    <button type="button" class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]">
                      <span class="material-symbols-outlined text-[20px] text-on-surface-variant">description</span>
                      查看导入日志
                    </button>
                    <button type="button" class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]">
                      <span class="material-symbols-outlined text-[20px] text-on-surface-variant">download</span>
                      下载错误明细
                    </button>
                    <button type="button" class="flex w-full items-center gap-3 rounded-2xl border border-outline-variant/60 px-4 py-3 text-left text-sm text-on-surface transition-colors hover:border-primary/40 hover:bg-white/[0.03]" @click="restartWizard">
                      <span class="material-symbols-outlined text-[20px] text-on-surface-variant">refresh</span>
                      重新导入
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex flex-col gap-3 border-t border-outline-variant/40 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <button
                v-if="currentStep > 1"
                type="button"
                class="rounded-2xl border border-outline-variant/60 px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:border-primary/40 hover:bg-surface/70"
                @click="goPrevious"
              >
                上一步
              </button>
              <div class="flex gap-3 sm:ml-auto">
                <button
                  v-if="currentStep > 1 && currentStep < 4"
                  type="button"
                  class="rounded-2xl border border-outline-variant/60 px-4 py-3 text-sm font-medium text-on-surface transition-colors hover:border-primary/40 hover:bg-surface/70"
                  @click="restartWizard"
                >
                  取消
                </button>
                <button
                  v-if="currentStep === 1 || currentStep === 2"
                  type="button"
                  class="rounded-2xl border border-primary/60 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="currentStep === 1 && !selectedFile"
                  @click="goNext"
                >
                  下一步
                </button>
                <button
                  v-else-if="currentStep === 3"
                  type="button"
                  class="rounded-2xl border border-primary/60 bg-primary/10 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="!hasPreview"
                  @click="goNext"
                >
                  进入执行
                </button>
                <button
                  v-else-if="currentStep === 4"
                  type="button"
                  class="rounded-2xl border border-emerald-400/35 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-200 transition-colors hover:bg-emerald-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="!hasPreview || isBusy"
                  @click="executeImport"
                >
                  {{ isExecuting ? '导入中' : '开始导入' }}
                </button>
              </div>
            </div>
          </div>
        </OpsSectionCard>
      </div>
    </section>

    <OpsSectionCard title="导入帮助">
      <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <p class="text-sm text-on-surface-variant">
          如果您在导入过程中遇到问题，可以查看导入指南或下载最新模板。
        </p>
        <div class="flex flex-wrap items-center gap-3 text-sm text-on-surface-variant">
          <a href="#" class="inline-flex items-center gap-2 rounded-xl border border-outline-variant/60 px-4 py-2 transition-colors hover:border-primary/40 hover:text-on-surface">
            <span class="material-symbols-outlined text-[18px]">download</span>
            下载导入模板
          </a>
          <a href="#" class="inline-flex items-center gap-2 rounded-xl border border-outline-variant/60 px-4 py-2 transition-colors hover:border-primary/40 hover:text-on-surface">
            <span class="material-symbols-outlined text-[18px]">article</span>
            导入指南
          </a>
          <a href="#" class="inline-flex items-center gap-2 rounded-xl border border-outline-variant/60 px-4 py-2 transition-colors hover:border-primary/40 hover:text-on-surface">
            <span class="material-symbols-outlined text-[18px]">help</span>
            常见问题
          </a>
        </div>
      </div>
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { assetsApi } from '@/api/assets'
import { OpsEmptyState, OpsPage, OpsPageHeader, OpsSectionCard, OpsStepper } from '@/components/ops'
import type { ImportExecuteResult, ImportIssueGroup, ImportPreviewResult } from '@/types/api'

type ImportMode = '新增' | '更新导入' | '更新联系人'
type WizardStep = 1 | 2 | 3 | 4 | 5
type ImportFlowStage = 'idle' | 'parsing' | 'validating' | 'writing' | 'completed' | 'failed'

interface WizardStepMeta {
  number: WizardStep
  label: string
  title: string
  subtitle: string
  description: string
}

interface SummarySnapshot {
  total: number
  success: number
  error: number
  conflict: number
  pending: number
  skipped: number
}

interface LogEntry {
  time: string
  message: string
}

const importModes: Array<{
  value: ImportMode
  label: string
  badge: string
  description: string
}> = [
  {
    value: '新增',
    label: '新增导入',
    badge: '默认',
    description: '新增业务系统、集群、实例和联系人关系。',
  },
  {
    value: '更新导入',
    label: '更新导入',
    badge: '可选',
    description: '预留给后续需要批量更新资产字段的场景。',
  },
  {
    value: '更新联系人',
    label: '更新联系人',
    badge: '可选',
    description: '预留给后续批量更新联系人与角色绑定。',
  },
]

const wizardSteps: WizardStepMeta[] = [
  {
    number: 1,
    label: '选择文件',
    title: '选择文件',
    subtitle: '上传 Excel 文件并确认模板格式。',
    description: '上传 .xlsx 导入模板',
  },
  {
    number: 2,
    label: '选择导入模式',
    title: '选择导入模式',
    subtitle: '选择本次导入的业务模式。',
    description: '选择新增或更新模式',
  },
  {
    number: 3,
    label: '预览与校验',
    title: '预览与校验',
    subtitle: '先预览，再查看校验结果和覆盖风险。',
    description: '生成预览结果和导入问题',
  },
  {
    number: 4,
    label: '执行导入',
    title: '执行导入',
    subtitle: '确认无误后开始写入正式资产表。',
    description: '执行写入并输出日志',
  },
  {
    number: 5,
    label: '完成',
    title: '完成',
    subtitle: '查看导入结果总结并准备下一次导入。',
    description: '查看完成结果',
  },
]

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const importMode = ref<ImportMode>('新增')
const currentStep = ref<WizardStep>(1)
const busyAction = ref<'preview' | 'execute' | null>(null)
const flowStage = ref<ImportFlowStage>('idle')
const flowProgress = ref(0)
const flowMessage = ref('请选择 Excel 文件后先预览。')
const previewResult = ref<ImportPreviewResult>(emptyPreviewResult())
const executeResult = ref<ImportExecuteResult | null>(null)
const resultMessage = ref('')
const activityLog = ref<LogEntry[]>([])
const importCompletedAt = ref('')
const showCompletionLog = ref(false)
const expandedPreviewRows = ref<Record<number, boolean>>({})
const issueSectionVisibleCounts = ref<Record<string, number>>({})
const issueSystemVisibleCounts = ref<Record<string, number>>({})
const issueIpVisibleCounts = ref<Record<string, number>>({})
const issueSystemPage = ref(1)
const router = useRouter()

let stageTimers: number[] = []

const isPreviewing = computed(() => busyAction.value === 'preview')
const isExecuting = computed(() => busyAction.value === 'execute')
const isBusy = computed(() => busyAction.value !== null)

const fileName = computed(() => selectedFile.value?.name || '尚未选择文件')

const fileHint = computed(() => {
  if (!selectedFile.value) return '请选择一个 .xlsx 文件。'
  const sizeKb = Math.max(1, Math.round(selectedFile.value.size / 1024))
  return `${selectedFile.value.name} · ${sizeKb} KB`
})

function getPreviewRowIp(fields: Record<string, any>) {
  return fields.server_ip || fields.host_ip || fields.ip_address || fields.ip || fields.vip || '-'
}

function formatPreviewWarningText(text: string) {
  return text.replace(/^覆盖风险[:：]\s*/, '')
}

function isPreviewRowExpanded(rowNum: number) {
  return !!expandedPreviewRows.value[rowNum]
}

function togglePreviewRow(rowNum: number) {
  expandedPreviewRows.value = {
    ...expandedPreviewRows.value,
    [rowNum]: !expandedPreviewRows.value[rowNum],
  }
}

function getIssueSectionKey(title: string) {
  return title
}

function getVisibleIssueCount(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  const key = getIssueSectionKey(title)
  return Math.min(issueSectionVisibleCounts.value[key] || 10, items.length)
}

function getVisibleIssueItems(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  return items.slice(0, getVisibleIssueCount(title, items))
}

function expandIssueSection(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  const key = getIssueSectionKey(title)
  const current = issueSectionVisibleCounts.value[key] || 10
  issueSectionVisibleCounts.value = {
    ...issueSectionVisibleCounts.value,
    [key]: Math.min(current + 10, items.length),
  }
}

function resetIssueSectionExpansion() {
  expandedPreviewRows.value = {}
  issueSectionVisibleCounts.value = {}
  issueSystemVisibleCounts.value = {}
  issueIpVisibleCounts.value = {}
  issueSystemPage.value = 1
}

function getSystemSectionKey(title: string) {
  return title
}

function getVisibleSystemCount(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  const key = getSystemSectionKey(title)
  return Math.min(issueSystemVisibleCounts.value[key] || 0, items.length)
}

function getVisibleSystemItems(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  return items.slice(0, getVisibleSystemCount(title, items))
}

function toggleSystemSection(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  const key = getSystemSectionKey(title)
  const current = issueSystemVisibleCounts.value[key] || 0
  const willOpen = current <= 0
  issueSystemVisibleCounts.value = {
    ...issueSystemVisibleCounts.value,
    [key]: willOpen ? Math.min(10, items.length) : 0,
  }
  setSystemIpVisibility(title, items, willOpen)
}

function expandSystemSection(title: string, items: Array<{ primary: string; secondary: string[] }>) {
  const key = getSystemSectionKey(title)
  const current = issueSystemVisibleCounts.value[key] || 0
  const nextCount = Math.min((current || 0) + 10, items.length)
  const newlyVisibleItems = items.slice(current || 0, nextCount)
  issueSystemVisibleCounts.value = {
    ...issueSystemVisibleCounts.value,
    [key]: nextCount,
  }
  setSystemIpVisibility(title, newlyVisibleItems, true)
}

function getIpSectionKey(systemTitle: string, ip: string) {
  return `${systemTitle}::${ip}`
}

function getVisibleIpCount(systemTitle: string, ip: string, items: string[]) {
  const key = getIpSectionKey(systemTitle, ip)
  return Math.min(issueIpVisibleCounts.value[key] || 0, items.length)
}

function getVisibleIpItems(systemTitle: string, ip: string, items: string[]) {
  return items.slice(0, getVisibleIpCount(systemTitle, ip, items))
}

function toggleIpSection(systemTitle: string, ip: string, items: string[]) {
  const key = getIpSectionKey(systemTitle, ip)
  const current = issueIpVisibleCounts.value[key] || 0
  issueIpVisibleCounts.value = {
    ...issueIpVisibleCounts.value,
    [key]: current > 0 ? 0 : Math.min(10, items.length),
  }
}

function expandIpSection(systemTitle: string, ip: string, items: string[]) {
  const key = getIpSectionKey(systemTitle, ip)
  const current = issueIpVisibleCounts.value[key] || 0
  issueIpVisibleCounts.value = {
    ...issueIpVisibleCounts.value,
    [key]: Math.min((current || 0) + 10, items.length),
  }
}

function setSystemIpVisibility(systemTitle: string, items: Array<{ primary: string; secondary: string[] }>, expanded: boolean) {
  const next = { ...issueIpVisibleCounts.value }
  for (const item of items) {
    next[getIpSectionKey(systemTitle, item.primary)] = expanded ? Math.min(10, item.secondary.length) : 0
  }
  issueIpVisibleCounts.value = next
}

function setIssueSystemPage(page: number) {
  const maxPage = issueSystemPageCount.value
  issueSystemPage.value = Math.min(Math.max(page, 1), maxPage)
}

function goIssueSystemPage(delta: number) {
  setIssueSystemPage(issueSystemPage.value + delta)
}

const selectedFileSize = computed(() => {
  if (!selectedFile.value) return 'N/A'
  const sizeKb = Math.max(1, Math.round(selectedFile.value.size / 1024))
  return `${sizeKb} KB`
})

const activeResult = computed(() => executeResult.value ?? previewResult.value)
const issueGroups = computed<ImportIssueGroup[]>(() => activeResult.value?.issue_groups || [])
const issueSummarySections = computed(() => {
  const sections: Array<{
    kind: 'system' | 'group'
    title: string
    badge: string
    toneClass: string
    count: number
    countLabel: string
    items: Array<{
      primary: string
      secondary: string[]
    }>
  }> = []

  const systemConflictMap = new Map<string, Map<string, string[]>>()

  for (const item of previewResult.value.items) {
    const warnings = item.warnings || []
    const errors = item.errors || []
    if (!warnings.length && !errors.length) continue

    const systemName = item.fields.system_name || '未命名系统'
    const ip = getPreviewRowIp(item.fields)
    const bucket = systemConflictMap.get(systemName) || new Map<string, string[]>()
    const ipItems = bucket.get(ip) || []
    for (const warning of warnings) {
      const cleanedWarning = warning.replace(/^覆盖风险[:：]\s*/, '')
      ipItems.push(`覆盖风险：第 ${item.row_num} 行：${cleanedWarning}`)
    }
    for (const error of errors) ipItems.push(`校验错误：${error}`)
    bucket.set(ip, ipItems)
    systemConflictMap.set(systemName, bucket)
  }

  for (const [systemName, bucket] of systemConflictMap) {
    const items = Array.from(bucket.entries()).map(([ip, details]) => ({
      primary: ip,
      secondary: details,
    }))
    sections.push({
      kind: 'system',
      title: systemName,
      badge: '系统',
      toneClass: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
      count: items.length,
      countLabel: '个IP',
      items,
    })
  }

  for (const group of issueGroups.value) {
    sections.push({
      kind: 'group',
      title: group.key === 'validation'
        ? '校验错误'
        : group.key === 'conflict'
          ? '覆盖风险'
          : group.label,
      badge: group.key === 'validation'
        ? '校验错误'
        : group.key === 'conflict'
          ? '覆盖风险'
          : group.key,
      toneClass: group.key === 'conflict'
        ? 'border-amber-400/30 bg-amber-500/10 text-amber-200'
        : group.key === 'validation'
          ? 'border-rose-400/30 bg-rose-500/10 text-rose-200'
          : 'border-outline-variant/60 bg-white/5 text-on-surface-variant',
      count: group.count,
      countLabel: '条',
      items: group.items.map((item) => ({
        primary: item,
        secondary: [],
      })),
    })
  }

  return sections
})
const issueSystemSections = computed(() => issueSummarySections.value.filter((section) => section.kind === 'system'))
const issueOtherSections = computed(() => issueSummarySections.value.filter((section) => section.kind !== 'system'))
const issueSystemPageSize = 8
const issueSystemPageCount = computed(() => Math.max(Math.ceil(issueSystemSections.value.length / issueSystemPageSize), 1))
const visibleIssueSystemPage = computed(() => Math.min(issueSystemPage.value, issueSystemPageCount.value))
const visibleIssueSystemSections = computed(() => {
  const start = (visibleIssueSystemPage.value - 1) * issueSystemPageSize
  return issueSystemSections.value.slice(start, start + issueSystemPageSize)
})
const currentStepMeta = computed(() => wizardSteps[currentStep.value - 1])
const wizardStepperStep = computed(() => {
  if (currentStep.value === 5 && flowStage.value === 'completed') return 6
  return currentStep.value
})
const isCompletionView = computed(() => currentStep.value === 5 && flowStage.value === 'completed')
const hasPreview = computed(() => previewResult.value.stage === 'previewed' && previewResult.value.items.length > 0)
const hasExecuteResult = computed(() => executeResult.value?.stage === 'completed')

const activeSummary = computed<SummarySnapshot>(() => {
  const result = executeResult.value ?? previewResult.value
  if (!result) {
    return { total: 0, success: 0, error: 0, conflict: 0, pending: 0, skipped: 0 }
  }
  if ('success' in result) {
    const skipped = typeof (result as ImportExecuteResult & { skip?: number }).skip === 'number'
      ? (result as ImportExecuteResult & { skip?: number }).skip || 0
      : 0
    return {
      total: result.total ?? (result.success + result.updated + result.error),
      success: result.success + result.updated,
      error: result.error_count,
      conflict: result.conflict_count || 0,
      pending: 0,
      skipped,
    }
  }
  return {
    total: result.total,
    success: result.success_count,
    error: result.error_count,
    conflict: result.conflict_count || 0,
    pending: Math.max(result.total - result.success_count - result.error_count, 0),
    skipped: 0,
  }
})

const completionStats = computed(() => ({
  created: executeResult.value?.success ?? 0,
  updated: executeResult.value?.updated ?? 0,
  failed: executeResult.value?.error_count ?? executeResult.value?.error ?? activeSummary.value.error,
}))

function formatRate(value: number, total: number) {
  if (!total) return '0%'
  return `${((value / total) * 100).toFixed(2)}%`
}

const completionRates = computed(() => ({
  success: formatRate(activeSummary.value.success, activeSummary.value.total),
  failed: formatRate(activeSummary.value.error, activeSummary.value.total),
  skipped: formatRate(activeSummary.value.skipped, activeSummary.value.total),
}))

const completionChartTotal = computed(() => {
  const total = activeSummary.value.success + activeSummary.value.error + activeSummary.value.skipped
  return total || activeSummary.value.total
})

const completionBreakdown = computed(() => [
  {
    label: '成功',
    count: activeSummary.value.success,
    percent: formatRate(activeSummary.value.success, completionChartTotal.value),
    dotClass: 'bg-emerald-400',
    percentClass: 'text-emerald-300',
  },
  {
    label: '失败',
    count: activeSummary.value.error,
    percent: formatRate(activeSummary.value.error, completionChartTotal.value),
    dotClass: 'bg-rose-400',
    percentClass: 'text-rose-300',
  },
  {
    label: '跳过',
    count: activeSummary.value.skipped,
    percent: formatRate(activeSummary.value.skipped, completionChartTotal.value),
    dotClass: 'bg-amber-400',
    percentClass: 'text-amber-300',
  },
])

const completionSegments = computed(() => {
  const total = completionChartTotal.value
  const circumference = 2 * Math.PI * 46
  if (!total) {
    return [
      {
        label: 'empty',
        stroke: '#334155',
        dasharray: `${circumference} 0`,
        dashoffset: '0',
      },
    ]
  }

  let offset = 0
  return [
    {
      label: 'success',
      stroke: '#34d399',
      value: activeSummary.value.success,
    },
    {
      label: 'failed',
      stroke: '#fb7185',
      value: activeSummary.value.error,
    },
    {
      label: 'skipped',
      stroke: '#fbbf24',
      value: activeSummary.value.skipped,
    },
  ]
    .filter((segment) => segment.value > 0)
    .map((segment) => {
      const length = (segment.value / total) * circumference
      const currentOffset = offset
      offset += length
      return {
        label: segment.label,
        stroke: segment.stroke,
        dasharray: `${length} ${circumference - length}`,
        dashoffset: `${-currentOffset}`,
      }
    })
})

const summaryStats = computed(() => [
  {
    label: '总数',
    value: activeSummary.value.total,
    hint: '本次文件总行数',
    icon: 'list_alt',
    tone: 'muted' as const,
  },
  {
    label: '新增',
    value: executeResult.value?.success ?? 0,
    hint: '本次新增记录',
    icon: 'add_circle',
    tone: 'success' as const,
  },
  {
    label: '更新',
    value: executeResult.value?.updated ?? 0,
    hint: '本次更新记录',
    icon: 'update',
    tone: 'primary' as const,
  },
  {
    label: '成功',
    value: activeSummary.value.success,
    hint: '已成功处理',
    icon: 'task_alt',
    tone: 'success' as const,
  },
  {
    label: '失败',
    value: activeSummary.value.error,
    hint: '校验或写入失败',
    icon: 'error',
    tone: 'warning' as const,
  },
  {
    label: '冲突',
    value: activeSummary.value.conflict,
    hint: '重复或冲突项',
    icon: 'report',
    tone: 'primary' as const,
  },
  {
    label: '跳过',
    value: activeSummary.value.skipped,
    hint: '执行时跳过的异常行',
    icon: 'skip_next',
    tone: 'warning' as const,
  },
  {
    label: '待处理',
    value: activeSummary.value.pending,
    hint: '尚未进入导入',
    icon: 'schedule',
    tone: 'muted' as const,
  },
])

const wizardProgress = computed(() => {
  switch (currentStep.value) {
    case 1:
      return selectedFile.value ? 18 : 8
    case 2:
      return 34
    case 3:
      return hasPreview.value ? 60 : 46
    case 4:
      return isExecuting.value ? flowProgress.value : (hasExecuteResult.value ? 92 : 76)
    case 5:
      return 100
    default:
      return 0
  }
})

const wizardStatusText = computed(() => {
  switch (currentStep.value) {
    case 1:
      return selectedFile.value ? '文件已选择，继续选择导入模式。' : '等待选择 Excel 文件。'
    case 2:
      return `当前导入模式：${importMode.value}`
    case 3:
      if (previewResult.value.stage === 'previewed') return `预览完成：成功 ${previewResult.value.success_count} 行，错误 ${previewResult.value.error_count} 行。`
      return '先预览并校验，再进入执行。'
    case 4:
      return flowMessage.value
    case 5:
      return executeResult.value?.message || '导入完成。'
    default:
      return '等待开始。'
  }
})

const flowLabel = computed(() => {
  if (busyAction.value === 'preview') {
    if (flowStage.value === 'parsing') return '正在解析 Excel'
    if (flowStage.value === 'validating') return '正在校验数据'
  }
  if (busyAction.value === 'execute') {
    if (flowStage.value === 'parsing') return '正在解析 Excel'
    if (flowStage.value === 'validating') return '正在校验数据'
    if (flowStage.value === 'writing') return '正在写入数据库'
  }
  if (flowStage.value === 'completed') return executeResult.value?.stage_label || previewResult.value.stage_label || '完成'
  if (flowStage.value === 'failed') return '导入失败'
  return '等待开始'
})

const flowToneClass = computed(() => {
  if (flowStage.value === 'failed') return 'bg-rose-500'
  if (flowStage.value === 'completed') return 'bg-emerald-500'
  if (busyAction.value === 'execute') return 'bg-gradient-to-r from-emerald-400 via-cyan-400 to-primary'
  return 'bg-gradient-to-r from-primary via-cyan-400 to-emerald-400'
})

function emptyPreviewResult(): ImportPreviewResult {
  return {
    total: 0,
    success_count: 0,
    error_count: 0,
    warning_count: 0,
    conflict_count: 0,
    errors: [],
    warnings: [],
    issue_groups: [],
    items: [],
    debug_headers: [],
    import_mode: '新增',
    stage: 'idle',
    stage_label: '等待上传',
    progress: 0,
  }
}

function pushLog(message: string) {
  const time = new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  activityLog.value = [{ time, message }, ...activityLog.value].slice(0, 8)
}

function clearStageTimers() {
  stageTimers.forEach((timerId) => window.clearTimeout(timerId))
  stageTimers = []
}

function resetRuntimeState(message?: string) {
  clearStageTimers()
  busyAction.value = null
  flowStage.value = 'idle'
  flowProgress.value = selectedFile.value ? 12 : 0
  flowMessage.value = message || (selectedFile.value ? '文件已上传，请继续下一步。' : '请选择 Excel 文件。')
  previewResult.value = emptyPreviewResult()
  executeResult.value = null
  resultMessage.value = ''
  importCompletedAt.value = ''
  showCompletionLog.value = false
  resetIssueSectionExpansion()
  activityLog.value = message ? [{ time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), message }] : []
}

function restartWizard() {
  selectedFile.value = null
  importMode.value = '新增'
  currentStep.value = 1
  resetRuntimeState()
  pushLog('已重置导入向导。')
}

function goPrevious() {
  if (currentStep.value === 1) return
  currentStep.value = Math.max(1, currentStep.value - 1) as WizardStep
  pushLog(`返回到步骤 ${currentStep.value}。`)
}

function goNext() {
  if (currentStep.value === 1) {
    if (!selectedFile.value) {
      resultMessage.value = '请先选择 Excel 文件。'
      return
    }
    currentStep.value = 2
    pushLog('进入步骤 2：选择导入模式。')
    return
  }
  if (currentStep.value === 2) {
    currentStep.value = 3
    pushLog('进入步骤 3：预览与校验。')
    return
  }
  if (currentStep.value === 3) {
    if (!hasPreview.value) {
      resultMessage.value = '请先完成预览与校验。'
      return
    }
    currentStep.value = 4
    pushLog('进入步骤 4：执行导入。')
    return
  }
  if (currentStep.value === 5) {
    restartWizard()
  }
}

function buildIssueReport() {
  const lines = [
    'DBOps 导入错误明细',
    `批次号: ${executeResult.value?.import_batch_id || 'N/A'}`,
    `文件名称: ${selectedFile.value?.name || 'N/A'}`,
    `导入时间: ${importCompletedAt.value || 'N/A'}`,
    `总数: ${activeSummary.value.total}`,
    `成功: ${activeSummary.value.success}`,
    `失败: ${activeSummary.value.error}`,
    `冲突: ${activeSummary.value.conflict}`,
    `跳过: ${activeSummary.value.skipped}`,
    '',
    '问题摘要:',
  ]

  if (!issueSummarySections.value.length) {
    lines.push('暂无校验错误或覆盖风险。')
  }

  for (const section of issueSummarySections.value) {
    lines.push(`[${section.title}] ${section.count} 条`)
    for (const item of section.items) {
      lines.push(`- ${item.primary}`)
      for (const detail of item.secondary) {
        lines.push(`  - ${detail}`)
      }
    }
  }

  return lines.join('\n')
}

function downloadIssueReport() {
  const blob = new Blob([buildIssueReport()], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `dbops-import-${executeResult.value?.import_batch_id || 'result'}.txt`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function goToAssetList() {
  router.push({ name: 'AssetInstances' })
}

function startFlow(action: 'preview' | 'execute') {
  clearStageTimers()
  busyAction.value = action
  flowStage.value = 'parsing'
  flowProgress.value = 18
  flowMessage.value = '正在解析 Excel 表头与内容。'

  stageTimers.push(
    window.setTimeout(() => {
      if (busyAction.value !== action) return
      flowStage.value = 'validating'
      flowProgress.value = 55
      flowMessage.value = '正在校验字段、字典和必填项。'
    }, 450),
  )

  if (action === 'execute') {
    stageTimers.push(
      window.setTimeout(() => {
        if (busyAction.value !== action) return
        flowStage.value = 'writing'
        flowProgress.value = 82
        flowMessage.value = '正在写入数据库并更新关系。'
      }, 1000),
    )
  }
}

function finishFlow(success: boolean, message: string, resultStageLabel?: string) {
  clearStageTimers()
  busyAction.value = null
  flowStage.value = success ? 'completed' : 'failed'
  flowProgress.value = success ? 100 : Math.max(flowProgress.value, 0)
  flowMessage.value = resultStageLabel || message
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
  currentStep.value = 1
  resetRuntimeState()
  if (selectedFile.value) {
    flowMessage.value = `已选择 ${selectedFile.value.name}，请继续下一步。`
    pushLog(`已选择文件：${selectedFile.value.name}`)
  } else {
    flowMessage.value = '请选择 Excel 文件。'
  }
}

function buildFormData() {
  if (!selectedFile.value) return null
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('mode', importMode.value)
  return formData
}

function selectImportMode(mode: ImportMode) {
  importMode.value = mode
  if (currentStep.value >= 3) {
    resetRuntimeState('导入模式已变更，请重新预览。')
  }
  pushLog(`已选择导入模式：${mode}`)
}

async function handlePreview() {
  const formData = buildFormData()
  if (!formData) return

  startFlow('preview')
  pushLog('开始预览与校验。')
  try {
    previewResult.value = await assetsApi.previewImport(formData)
    executeResult.value = null
    resetIssueSectionExpansion()
    resultMessage.value = `预览完成：成功 ${previewResult.value.success_count} 行，错误 ${previewResult.value.error_count} 行。`
    flowProgress.value = previewResult.value.progress ?? 100
    flowMessage.value = previewResult.value.stage_label || '预览完成。'
    if (previewResult.value.error_count > 0) {
      pushLog(`预览完成，存在 ${previewResult.value.error_count} 条导入问题。`)
    } else {
      pushLog('预览完成，未发现导入问题。')
    }
    if (previewResult.value.warning_count) {
      pushLog(`发现 ${previewResult.value.warning_count} 条覆盖风险提示。`)
    }
    flowStage.value = 'completed'
  } catch (error) {
    const message = error instanceof Error ? error.message : '预览失败'
    resultMessage.value = message
    flowMessage.value = message
    flowStage.value = 'failed'
    pushLog(message)
  } finally {
    finishFlow(flowStage.value === 'completed', resultMessage.value || '预览结束', flowMessage.value)
  }
}

async function executeImport() {
  const formData = buildFormData()
  if (!formData) return

  startFlow('execute')
  pushLog('开始执行导入。')
  try {
    const result = await assetsApi.executeImport(formData)
    executeResult.value = result
    resetIssueSectionExpansion()
    resultMessage.value = result.message
    flowProgress.value = result.progress ?? 100
    flowMessage.value = result.stage_label || result.message
    flowStage.value = 'completed'
    currentStep.value = 5
    importCompletedAt.value = new Date().toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    pushLog(result.message)
  } catch (error) {
    const message = error instanceof Error ? error.message : '导入失败'
    resultMessage.value = message
    flowMessage.value = message
    flowStage.value = 'failed'
    pushLog(message)
  } finally {
    finishFlow(flowStage.value === 'completed', resultMessage.value || '导入结束', flowMessage.value)
  }
}

onMounted(() => {
  pushLog('导入向导已就绪。')
})

onBeforeUnmount(() => {
  clearStageTimers()
})
</script>
