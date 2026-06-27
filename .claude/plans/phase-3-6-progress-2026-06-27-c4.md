# Phase 3.6 AI Copilot — C4 完成进度

**Date**: 2026-06-27
**Branch**: `feature/phase-3.6-ai-copilot`
**Base HEAD**: `1a6c7c2` (C3 commit)
**New HEAD**: (本 commit)
**Plan**: `.claude/plans/phase-3-6-ai-copilot-full-plan.md` (v4 Final)
**Resumption**: 新会话用 `/feature-dev` 加载此文件从 C5 起手

---

## ✅ 本轮已完成（C4 — Frontend 入口）

### C4-1 (`frontend/src/types/ai.ts` NEW, 99 行)
- [x] `AiCapabilities`（对齐 backend `CapabilitiesResponse`）
- [x] `AiChatSessionCreateRequest` / `AiChatSession` / `AiChatSessionListResponse`
- [x] `AiChatMessageSendRequest` / `AiChatMessage` / `AiChatMessageListResponse`
- [x] `AiChatSendResponse`（`assistant_message: AiChatMessage | null`，`idempotent_replay: boolean`）
- [x] Literal types: `role` / `message_type` / `status` 对齐后端 Pydantic

### C4-2 (`frontend/src/api/ai.ts` NEW, 137 行)
- [x] `aiApi` 对象：5 函数 + `getCapabilities`
  - `getCapabilities()` — 无需登录
  - `createSession(data?)`
  - `listSessions(params?, { suppressErrorToast })` — 失败时静默降级
  - `sendMessage(sessionId, data)` — 核心端点（幂等 client_request_id）
  - `listMessages(sessionId, params?, { suppressErrorToast })`
- [x] `loadAiCapabilities(force?)` 单例缓存函数：
  - 失败时返回"全 false"占位（不阻塞 UI）
  - 并发安全（in-flight Promise 复用）
  - 测试 / 热重载用 `__resetCapabilitiesCacheForTest()`
- [x] 错误码文档注释（plan §11：404/409/422/502/503/504）

### C4-3 (`frontend/src/router/index.ts` UPDATE, +6 行)
- [x] 新增路由 `AiChat`：path=`/ai/chat`、lazy import `@/views/ai/Chat.vue`、meta `{ title: 'AI Copilot', parent: 'AI 助手' }`
- [x] 未触动其他路由 / createRouter / beforeEach

### C4-4 (`frontend/src/views/Layout.vue` UPDATE, +34 行)
- [x] `import { loadAiCapabilities } from '@/api/ai'`
- [x] `const chatEnabled = ref(false)` + onMounted 异步拉取
- [x] `MenuItem` / `MenuChild` interface 显式声明（替代原内联字面量类型）
- [x] `baseMenuItems: MenuItem[]` 不含 AI 项 + `aiMenuItem` + `menuItems` computed：
  - `chatEnabled=true` → `[...baseMenuItems, aiMenuItem]`（追加到尾部）
  - `chatEnabled=false` → 仅 `baseMenuItems`
- [x] `topTabs` 末尾追加 `{ key: 'ai', label: 'AI Copilot', path: '/ai/chat', match: ['/ai'] }`
- [x] 模板**未触动**（`menuItems` 引用名保持，computed 自动响应）

### C4-5 (`frontend/src/views/ai/Chat.vue` NEW, 22 行)
- [x] `<OpsPage>` + `<OpsPageHeader title="AI Copilot" subtitle="基于 Dify 的智能运维对话（C5 落地交互界面）" />`
- [x] `<OpsSectionCard>` + `<OpsEmptyState state="development">` — 提示 "Chat UI 将在 C5 实现"

### C4-6 (verification)
- [x] `npx vue-tsc --noEmit` → 0 错（修了一个 `menuItems.value.find()` script 内 unwrap）
- [x] `bash scripts/ai/verify.sh` → 269 passed 2 skipped 0 failed
- [x] 重启 backend（PID 2524930 → 922792）→ capabilities live API 返回 200 + 6 boolean + sql_supported_db_types[]
- [x] 灰度翻转验证（AI_CHAT_ENABLED=true via TestClient）→ chat_enabled=true，其他 5 项仍 false
- [x] 实际 dev backend (AI_CHAT_ENABLED 未设) → chat_enabled=false → 菜单**隐藏** AI Copilot 入口

---

## 🔧 关键设计决策（C4）

1. **`types/ai.ts` 独立文件 vs 追加到 `types/api.ts`**：选独立文件（对齐后端 `schemas/ai.py`，后续 SQL/Inspection 类型继续追加）
2. **`api/ai.ts` 独立对象 vs 合并到 `assetsApi`**：选独立 `aiApi`（chat 是新业务域，与现有资产管理无交集）
3. **capabilities 单例缓存**：启动时 Layout.vue onMounted 拉取一次 → 全局复用；失败兜底"全 false"避免弹错阻塞 UI
4. **菜单灰度 vs 路由灰度**：菜单按钮按 `chat_enabled` 控制显示；路由**始终注册**（AI 路由定义是 C4 完成的，与菜单独立）
5. **AI Copilot 菜单位置**：追加到 `baseMenuItems` 尾部（紧跟"知识库"），topTabs 末尾；不插入中间保持视觉稳定
6. **`menuItems` 改 computed 但保留变量名**：模板里 `v-for="item in menuItems"` 自动响应 computed，无模板改动

---

## ⚠ 验证中的坑（已解决）

1. **vue-tsc `@/api/ai` 找不到**：第一次 Write 后 ls 显示文件不存在 — 重新 Write 成功落盘
   - 教训：Write 后立即 ls 验证文件存在，避免 Gateguard 触发时的"假成功"
2. **vue-tsc `menuItems.find` 类型错误**：computed 在 script 内需要 `.value.find(...)`，模板内自动 unwrap
3. **backend 404 capabilities**：PID 2524930 是 Jun 26 启动的，那时 ai router 未注册
   - 解决：kill + nohup 重启 → PID 922792 → capabilities live API 工作

---

## 📁 文件清单（C4 共 5 文件变更）

```
frontend/src/types/ai.ts                | A  +99  (NEW)
frontend/src/api/ai.ts                  | A  +137 (NEW)
frontend/src/router/index.ts            | M  +6   (AiChat route)
frontend/src/views/Layout.vue           | M  +34  (chat_enabled + computed menuItems)
frontend/src/views/ai/Chat.vue          | A  +22  (NEW, 占位)
```

---

## 🚧 未做（保留给后续 commit）

### C5 — Chat UI（Chat.vue + 消息组件）
- 会话列表侧栏 + 消息流 + 输入框 + 错误兜底
- 复用 `<OpsPage>` / `<OpsSectionCard>` / `<OpsEmptyState>` / `<OpsModal>`
- 新组件：会话项、用户/助手消息气泡、状态徽章（pending/failed/stale）

### C6~C26 — 见 plan §14 序列
- C6: SQL Schema Snapshot
- C13: SQL Preview
- C19: SQL Execute
- C24-C25: Inspection AI Analysis

### Phase 3.6B0/C/D... — 见 plan §14
### C28~C32 — 收尾（verify.sh 更新 + .env.example + grep 检查 + DDL 幂等 + 启动清理）

---

## 🛠 真实环境信息（继承 C1+C2+C3）

- **Backend**: PID 922792，端口 60801（重启后）
- **Live capabilities**: `GET /api/v1/ai/capabilities` → 200，默认 chat_enabled=false
- **Dify endpoints**（C1 已就位，未启用）
- **Redis**: 10.134.185.85:6379, password=redis2026@qwer
- **DDL target**: 10.134.185.85:5432, user=dbops, db=dbops

**API Key 安全**：Dify API key 不入代码/日志/git。C30 commit 实现 grep 检查。

---

## ⚠ 风险与注意

1. **菜单灰度**：`chat_enabled=false` 时菜单完全隐藏 AI 入口，但路由 `/ai/chat` 仍可达（chat_enabled 验证在 send_message 端点，不在路由层）
2. **capabilities 缓存**：Layout.vue mount 后才拉取，**首屏渲染时菜单无 AI 项**；若需 SSR 首屏可见，需后端把 capabilities 注入 HTML（plan 未要求）
3. **失败兜底**：capabilities 拉取失败时 chatEnabled=false，可能误判为"功能禁用"。运维人员排障需查 backend 日志
4. **顶级 Tab 顺序**：AI Copilot 在 topTabs 末尾，与菜单顺序一致；后续增加 SQL/Report AI 时需评估排序
5. **图标 `auto_awesome`**：MD3 字体图标，google material symbols；如未渲染需检查字体 CDN（与现有 `dashboard`/`build` 等图标同源）

---

## 📋 收尾待办（按 plan §14 顺序）

- C5: Chat UI（Chat.vue + 消息组件）
- C6~C26: plan §14 主线
- C28: 全量 ~105 测试 + 日志脱敏
- C29: verify.sh 更新 + .env.example + docs/10-module-map.md
- C30: API Key 泄漏 grep 检查
- C31: DDL 幂等验证 + 回滚安全检查
- C32: 启动时 stale 清理（chat pending — C3 已完成；analysis pending + snapshot running 待后续）
