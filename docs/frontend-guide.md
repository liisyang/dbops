# 前端开发约定

> 文档状态：已校准
> 最近校准：2026-05-22
> 依据来源：frontend/src 全部源码

## 1. 技术栈

| 类别 | 选型 | 版本 |
|---|---|---|
| 框架 | Vue 3 (Composition API) | ^3.4 |
| 构建 | Vite | ^5.0 |
| 语言 | TypeScript | ^6.0.3 |
| 路由 | vue-router | ^4.2 |
| 状态 | Pinia | ^3.0.4 |
| HTTP | Axios | ^1.6 |
| 样式 | TailwindCSS + MD3 暗色主题 | ^3.4.19 |
| 图标 | Google Material Symbols (CDN 字体) | — |
| 国际化 | vue-i18n | ^11.3 |
| 时间 | dayjs | ^1.11.20 |
| 测试 | Vitest + @vue/test-utils + happy-dom | ^3.2.4 |

## 2. 目录约定

```
src/
├── api/              # 按域拆分的 API 模块，每个文件导出 { xxxApi } 对象
│   └── request.js    # 唯一的 Axios 实例（拦截器、401、toast）
├── assets/styles/    # Tailwind 入口 + MD3 组件类（main.css）
├── components/
│   └── ops/          # 可复用布局/模式组件（Ops*），统一从 index.ts 导出
├── composables/      # Vue Composables（use*）
├── locales/          # i18n 语言文件（zh-CN, zh-TW, en, ja, pt-BR）
├── router/           # 路由配置（index.ts）
├── stores/           # Pinia Store
├── types/            # TypeScript 类型定义（api.ts）
├── utils/            # 工具函数（i18n, timezone）
└── views/            # 页面组件，按模块分子目录
    ├── audit/        # 审计与安全
    ├── backup/       # 备份与恢复
    ├── credentials/  # 凭证中心
    ├── inspection/   # 巡检与健康
    ├── knowledge/    # 知识库
    ├── ops/          # 自动化运维
    ├── sql/          # SQL 分析
    └── ui-preview/   # 开发预览页（Mock 数据，不调用真实 API）
```

**代码依据：** `frontend/src/` 目录结构。

## 3. 必须遵守

### 3.1 API 调用

1. 所有请求必须走 `@/api/request` 导出的 Axios 实例，不得直接使用 axios。
2. 新 API 模块在 `src/api/` 下新建 `{domain}.ts`，导出一个 plain object（如 `assetsApi`、`statsApi`）。
3. Token 由 request 拦截器自动附加，业务代码不手动传 Authorization。
4. 401 时自动清除 token 并跳转 `/login`，不另做 401 处理。

**代码依据：** `src/api/request.js:48-56` (请求拦截器), `src/api/request.js:113-126` (401 处理), `src/api/assets.ts` (API 模块模式)。

### 3.2 页面容器与布局

1. 列表/详情页统一包裹在 `<OpsPage>` 内。
2. 页面标题统一使用 `<OpsPageHeader :title="..." :subtitle="..." />`；需要展示状态和实体维度标签时使用 `<OpsEntityHeader />`。
3. 列表页固定结构：`OpsStatGrid` → 图表区（可折叠）→ `OpsFilterBar` → `OpsTableShell`（内含 `<table>`）。
4. 详情页使用 `OpsSectionCard` 分块展示信息。
5. 实例详情页（`InstanceDetail.vue`）已扩展"资产校验状态""最近执行记录""执行项明细""端点状态""变更建议"卡片；支持"校验资产"和"端口校准"双入口，其中端口校准调用 `POST /api/v1/collector/runs`（`run_type=port_calibration`），默认会带上 `include_related_server=true`，执行项会展示独立 `candidate_state` 列，并提供 proposal 同意/拒绝/应用操作；资产校验状态卡片提供手动刷新按钮，且 submitLaunch/launchPortCalibration 成功后会自动重新拉取实例详情以展示最新 trust_status/reachability_status 等字段。状态类字段（trust/reachability/run/result/endpoint/proposal）统一使用条件 Badge 样式；时间字段统一调用本地 `formatTime()`（内部走 `formatInTz`）。
6. 批量校验页 `BatchVerify.vue` 会优先展示结果摘要、分发明细、执行项明细和单项详情；执行项详情区直接渲染 `raw_result.facts` 和 `raw_result` 原文，跳过项会显示计数和原因提示，变更建议仅在相关批次中展示。

**代码依据：** `src/views/Servers.vue:2-6` (页面结构), `src/views/Instances.vue:2-6`, `src/views/Assets.vue:2-6`。

### 3.3 表格

1. 表格使用原生 `<table>` + Tailwind 类，不使用第三方表格组件。
2. 列定义使用常量数组 `COLUMNS`，通过 `useColumnVisibility()` 管理显示/隐藏/排序。
3. 空值统一展示 `-`（短横线）。
4. 行点击导航到详情页，操作按钮使用 `@click.stop` 阻止冒泡。

**代码依据：** `src/views/Servers.vue:148-200` (表格模板), `src/views/Servers.vue:346-358` (列定义), `src/composables/useColumnVisibility.ts`。

### 3.4 表单

1. 新增/编辑优先使用 `<OpsModal>` 弹窗承载表单。
2. 表单使用 `field-card` / `field-label` / `field-input` CSS 组件类（定义在 main.css）。
3. 提交按钮在 `#footer` 插槽中，取消按钮调用 `closeModal()`。
4. 表单验证在提交函数内做前置校验，错误展示在表单顶部红色提示区。

**代码依据：** `src/views/Instances.vue:53-133` (OpsModal + 表单), `src/assets/styles/main.css:72-99` (field-* 类)。

### 3.5 弹窗与抽屉

1. 弹窗使用 `<OpsModal>`，支持 `size` 属性控制宽度（sm/md/lg/xl）。
2. 抽屉使用 `<OpsDrawer>`，从右侧滑入。
3. 弹窗/抽屉均通过 `open` prop 控制显隐，`@close` 事件关闭。

**代码依据：** `src/components/ops/OpsModal.vue`, `src/components/ops/OpsDrawer.vue`。

### 3.6 空态与加载态

1. 统一使用 `<OpsEmptyState>` 组件，支持 `empty` / `loading` / `development` / `error` 四种状态。
2. `OpsTableShell` 内置了对 loading/empty 的处理，自动渲染 EmptyState。

**代码依据：** `src/components/ops/OpsEmptyState.vue`, `src/components/ops/OpsTableShell.vue:2-26`。

### 3.7 样式

1. **禁止**写大段内联 `style`，使用 Tailwind 工具类。
2. 按钮使用预定义组件类：`ops-primary-button` / `ops-secondary-button` / `ops-edit-button` / `ops-danger-button`。
3. 表单使用 `field-card` / `field-label` / `field-input` / `field-value` 组件类。
4. 颜色使用 `tailwind.config.js` 中定义的 MD3 Token（如 `text-on-surface`、`bg-surface-container`），不硬编码色值。

**代码依据：** `src/assets/styles/main.css:36-99` (组件类), `tailwind.config.js:11-57` (色值 Token)。

### 3.8 状态展示

1. 状态 Badge 使用条件 class 绑定，不硬编码颜色。
2. **状态格式化函数已统一**：使用 `useStatusFormatters` composable 中的 `formatStatusLabel()`、`getStatusBadgeClass()`、`formatStatusTransition()`、`formatContactTypeLabel()`。
3. 所有资产管理视图（Assets.vue、BusinessSystemDetail.vue 等）均使用统一的状态展示逻辑。

**代码依据：** `src/composables/useStatusFormatters.ts`, `src/views/Assets.vue:200-201`, `src/views/BusinessSystemDetail.vue:375-377`.

### 3.9 图标

1. 统一使用 Google Material Symbols（`material-symbols-outlined` 类），不直接使用 lucide-vue-next（虽然已安装但未在代码中使用）。
2. 数据库类型图标使用 `DbTypeIcon` 组件。

**代码依据：** 全局搜索 `material-symbols-outlined` 遍布所有视图，`src/components/DbTypeIcon.vue`。

### 3.10 路由与导航

1. 路由定义在 `src/router/index.ts`，使用 `createWebHistory`。
2. Layout 使用固定侧边栏 + 顶部导航 + `<router-view>` 内容区。
3. 路由 meta 统一包含 `title` 和可选的 `parent`。
4. 路由守卫检查 `localStorage.getItem('token')`，未登录跳 `/login`。
5. Router 实例挂载到 `window.__VITE_ROUTER__` 供 request.js 401 跳转使用。
6. `ui-preview` 路由只承载 mock-only 开发预览页，例如 `/ui-preview/assets` 和 `/ui-preview/servers.vue`，页面不得调用真实 API。

**代码依据：** `src/router/index.ts:24-220` (路由定义), `src/router/index.ts:231-239` (路由守卫), `src/router/index.ts:228`。

## 4. 推荐复用清单

| 场景 | 复用组件 | 代码位置 |
|---|---|---|
| 页面容器 | `OpsPage` | `src/components/ops/OpsPage.vue` |
| 页面标题 | `OpsPageHeader` | `src/components/ops/OpsPageHeader.vue` |
| 实体详情头部（状态+标签） | `OpsEntityHeader` | `src/components/ops/OpsEntityHeader.vue` |
| 统计卡片区 | `OpsStatGrid` + `AssetStatCard` | `src/components/ops/OpsStatGrid.vue` |
| 筛选区 | `OpsFilterBar` | `src/components/ops/OpsFilterBar.vue` |
| 表格壳（含分页/空态） | `OpsTableShell` | `src/components/ops/OpsTableShell.vue` |
| 列显示控制 | `OpsColumnPicker` | `src/components/ops/OpsColumnPicker.vue` |
| 弹窗表单 | `OpsModal` | `src/components/ops/OpsModal.vue` |
| 确认对话框 | `OpsConfirmDialog` | `src/components/ops/OpsConfirmDialog.vue` |
| 抽屉详情 | `OpsDrawer` | `src/components/ops/OpsDrawer.vue` |
| 内容卡片 | `OpsSectionCard` | `src/components/ops/OpsSectionCard.vue` |
| 空态/加载/错误 | `OpsEmptyState` | `src/components/ops/OpsEmptyState.vue` |
| 步骤指示器 | `OpsStepper` | `src/components/ops/OpsStepper.vue` |
| 柱状图 | `SimpleBarChart` | `src/components/SimpleBarChart.vue` |
| 环形图 | `DistributionDonutChart` | `src/components/DistributionDonutChart.vue` |
| 数据库图标 | `DbTypeIcon` | `src/components/DbTypeIcon.vue` |
| 分页列表数据 | `usePagedAssetList` | `src/composables/usePagedAssetList.ts` |
| 非分页列表数据 | `useAssetArrayList` | `src/composables/useAssetArrayList.ts` |
| 列显隐管理 | `useColumnVisibility` | `src/composables/useColumnVisibility.ts` |
| 页面统计指标 | `useAssetPageMetrics` + `assetPageMetric` | `src/composables/useAssetPageMetrics.ts` |
| 图表分组统计 | `useAssetStatBuckets` | `src/composables/useAssetStatBuckets.ts` |
| 状态展示格式化 | `useStatusFormatters` (formatStatusLabel / getStatusBadgeClass / formatStatusTransition / formatContactTypeLabel) | `src/composables/useStatusFormatters.ts` |
| 用户状态 | `useUserStore` | `src/stores/user.ts` |
| 时间格式化 | `$formatTime` (全局) | `src/main.ts:36-38` |
| 前端筛选逻辑 | 参考 Servers.vue / Instances.vue 的 draft+applied 双变量模式 | — |

## 5. 当前不一致点

| 问题 | 位置 | 影响 | 建议 | 代码依据 |
|---|---|---|---|---|
| lucide-vue-next 未使用 | `package.json` 依赖 | 增加包体积 | 确认是否需要，不需要则移除 | `package.json:14` |
| `.js` / `.ts` 文件并存 | `api/logs.js` vs `api/logs.ts`，`stores/user.js` vs `stores/user.ts`，`utils/*.js` vs `utils/*.ts` | TypeScript 项目中的 `.js` 文件不受类型检查 | 需现场确认：`.js` 文件是否还有引用方，如无则移除 | `src/api/logs.js`, `src/stores/user.js`, `src/utils/timezone.js` |
| CRUD 交互模式不统一 | `Servers.vue` 用路由切换创建/详情页；`Instances.vue` / `Assets.vue` 用 OpsModal 弹窗 | 用户心智模型不一致 | 需现场确认：统一为一种模式 | `src/views/Servers.vue` (路由模式), `src/views/Instances.vue:53-133` (弹窗模式) |
| 前端分页为全量加载后内存分页 | `usePagedAssetList` 一次性拉取所有页再前端切片 | 数据量大时性能瓶颈（目前无后端分页接口） | 后端提供分页查询参数后改为后端分页 | `src/composables/usePagedAssetList.ts:17-23` |
| 国际化覆盖率低 | 大部分页面中文硬编码 | 切换语言后大量中文不变 | 逐步迁移硬编码文案到 i18n | 各视图模板中的中文文案 |
| 仅有暗色模式 | `tailwind.config.js` 只定义了一套颜色 | 不支持亮色模式 | 如需亮色模式，需重新定义全部 MD3 Token | `tailwind.config.js:10-57` |

## 6. 需现场确认

- `api/logs.js`、`stores/user.js`、`utils/*.js` 是否还有外部引用？是否可以安全删除？
- CRUD 交互统一为弹窗模式还是路由模式？（当前两种模式并存）
- lucide-vue-next 是否需要保留？
- 后续是否需要支持亮色模式？
