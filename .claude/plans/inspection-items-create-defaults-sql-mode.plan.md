# Plan: 修复 /inspection/items 「新增巡检项」弹窗默认走 SQL 模式 + 支持新增巡检类型

## 用户原始问题（已确认）

1. **弹窗默认走错分支**
   - 点 `/inspection/items` 「+ 新增巡检项」→ 弹窗显示"规则配置 (JSON)"大文本框
   - 点「编辑巡检项」（DB_READONLY_SQL_EXEC 项）→ 弹窗显示 SQL 文本框（正确）
   - 用户期望：点新增默认就是 SQL 模式

2. **巡检类型只有 3 个可选，不能新增**
   - 现在 `inspection_type` 字段是 `<select>`，选项来自 `assetsApi.listInspectionTypes()` → `InspectionService.list_inspection_types()`（`inspection_service.py:289-298`），从 inspection_item 表动态 distinct 出来
   - 用户想在弹窗里新增一个巡检类型，但下拉框不允许

## 根因

### Bug 1：resetForm 默认 check_code 为空
- `frontend/src/views/inspection/Items.vue:467` — `form.check_code = ''`
- `Items.vue:107` SQL 分支是 `v-if="form.check_code === 'DB_READONLY_SQL_EXEC'"`
- `Items.vue:152` v-else 分支显示 rule_config JSON 大文本框
- 新增时 check_code 是 `''` → 走 v-else → 显示 JSON 框

### Bug 2：inspection_type 是只读下拉
- `Items.vue:26-29`（filter）和 `Items.vue:87-93`（form）都是 `<select>` 渲染 inspectionTypes.value
- inspectionTypes.value 只来自 `assetsApi.listInspectionTypes()`，没有创建/管理入口
- 用户被锁死，只能选已有 3 个类型

## 需求重述

- **Fix 1**：点「新增巡检项」直接显示 SQL 文本框；check_code 改为下拉固定 `DB_READONLY_SQL_EXEC`（后端 `check_item_builder_registry.py:103-128` 唯一允许用户扩展的 check_code）；编辑系统默认项时下拉 disabled。
- **Fix 2**：inspection_type 字段支持自由输入（保留下拉作为自动补全），输入新值保存后自动出现在可选列表里。

## 改动清单

| # | 文件 | 改动 | 行号 |
|---|---|---|---|
| 1 | `frontend/src/views/inspection/Items.vue` | `resetForm()` 默认 `form.check_code = 'DB_READONLY_SQL_EXEC'` | `Items.vue:467` |
| 2 | `frontend/src/views/inspection/Items.vue` | `check_code` 字段 `<input>` → `<select>`，单选项 `DB_READONLY_SQL_EXEC`；编辑系统默认项时 disabled | `Items.vue:67-69` |
| 3 | `frontend/src/views/inspection/Items.vue` | `inspection_type` 字段 `<select>` → `<input list="inspection-types-list">` + `<datalist>` 自动补全 | `Items.vue:87-93` |
| 4 | `frontend/src/views/inspection/Items.vue` | 顶部 filter 栏的 inspection_type `<select>` 同步改成 `<input list>` + datalist | `Items.vue:26-29` |
| 5 | `frontend/src/views/inspection/Items.vue` | 加 `isCheckCodeLocked` computed，控制编辑系统默认项时 check_code 字段 disabled | `Items.vue:464-482` 附近 |

## Patterns to Mirror

| 类别 | 来源 | 模式 |
|---|---|---|
| Naming | `Items.vue:79-86` | DB 类型字段已经是 `<select>`，复用同样的 option 渲染样式 |
| Errors | `Items.vue:592-622` `onValidateSql` | SQL 校验 + 错误展示流程不变，仅换默认值 |
| Naming | `Tasks.vue:25-31` | Tasks.vue 里 `dbTypeFilter` 也是 `<select>`，保持一致 |
| HTML5 | 通用 | `<datalist>` 实现"自由输入 + 自动补全"，是 HTML 原生支持，无需第三方库 |

## Tasks

### Task 1：resetForm 默认 check_code
- **Action**: `Items.vue:467` `form.check_code = ''` → `form.check_code = 'DB_READONLY_SQL_EXEC'`
- **Validate**: `vue-tsc --noEmit` 通过

### Task 2：check_code 改下拉 + 锁定逻辑
- **Action**: `Items.vue:67-69` 替换 `<input>` 为 `<select>`，单选项 `DB_READONLY_SQL_EXEC`
- **锁定**:
  ```ts
  const isCheckCodeLocked = computed(() =>
    !!editingId.value && form.check_code !== 'DB_READONLY_SQL_EXEC'
  )
  ```
- **Mirror**: `Items.vue:79-86` DB 类型下拉写法
- **Validate**: live smoke — 编辑系统默认项下拉 disabled；新增/编辑 DB_READONLY_SQL_EXEC 项下拉可选

### Task 3：inspection_type 字段改自由输入 + 自动补全
- **Action**: `Items.vue:87-93`（form 字段）和 `Items.vue:26-29`（filter 字段）替换 `<select>` 为：
  ```vue
  <input
    v-model.trim="form.inspection_type"
    list="inspection-types-list"
    class="field-input"
    placeholder="可输入新类型，回车保存"
  />
  <datalist id="inspection-types-list">
    <option v-for="t in inspectionTypes" :key="t" :value="t" />
  </datalist>
  ```
- **关键**：保存成功后，调用 `loadInspectionTypes()` 刷新 inspectionTypes.value，新的 inspection_type 会自动出现在可选列表
- **后端零改动**：inspection_type 本来就是 inspection_item 表的字段，写入新值后下次 `list_inspection_types` 自动 distinct 出来
- **Validate**: live smoke — 输入新值「自定义类型 A」保存 → 关闭弹窗再打开 → 下拉自动补全里能看到

### Task 4：live 验证
- **Action**: 浏览器 `http://10.134.181.168:61088/inspection/items`
- **Validate**:
  - 点「+ 新增巡检项」→ 默认 SQL 文本框可见
  - check_code 下拉只有 `DB_READONLY_SQL_EXEC`
  - inspection_type 字段可输入新值；保存后该值出现在自动补全里
  - 点「编辑」DB_READONLY_SQL_EXEC 项 → SQL 文本框正常回填；inspection_type 回填到 input
  - 点「编辑」系统默认项（CONNECTIVITY_PORT_REACHABLE 等）→ check_code 字段 disabled 显示系统值；inspection_type 输入框仍可改（仅编辑 metadata）

### Task 5：回归
- **Action**: `bash scripts/ai/verify.sh`
- **Validate**: vue-tsc 0 错 + pytest 全过

## Validation

```bash
# 1. 类型检查
cd /home/lisiyang/dbops/frontend && npx vue-tsc --noEmit

# 2. 全量验证
bash /home/lisiyang/dbops/scripts/ai/verify.sh

# 3. live smoke（手动浏览器）
open http://10.134.181.168:61088/inspection/items
# 验证 4 个场景：
#   a) 点新增 → SQL 文本框可见
#   b) inspection_type 输入新值 → 保存 → 再打开弹窗 → 自动补全出现
#   c) 编辑 DB_READONLY_SQL_EXEC 项 → 正常回填
#   d) 编辑系统默认项 → check_code 字段 disabled
```

## 不动

- `backend/app/services/inspection_service.py` — 后端 list_inspection_types 已正确从 inspection_item 动态 distinct
- `backend/app/api/inspection.py` — `GET /inspection/types` 不变
- `backend/app/schemas/inspection.py` — `inspection_type: Optional[str] = None` 不变
- `frontend/src/views/inspection/Tasks.vue` — 任务页用 `item.enabled=true` 列表，不受 type 改动影响
- 数据库 schema — 不动；inspection_type 本来就是 inspection_item 表的字段，无需新增字典表

## Risks

| 风险 | 可能性 | 缓解 |
|---|---|---|
| 误输入超长字符串 | 低 | inspection_type 字段在 schema 里 `Optional[str]`，无长度限制；前端加 `maxlength=64` 兜底 |
| 输入重复 type | 低 | 不去重；同名 type 在 Tasks.vue 按 type 分组时会落到同一组，行为正确 |
| 改动 inspection_type 默认值后现有 item 显示异常 | 极低 | 不动 list 逻辑，只把 `<select>` 改 `<input list>` |
| datalist 浏览器兼容 | 极低 | 所有现代浏览器 + Element UI 早已支持，dbops 前端用 Chromium，无问题 |

## Acceptance

- [ ] `vue-tsc --noEmit` 0 错
- [ ] `bash scripts/ai/verify.sh` 全绿
- [ ] 点「新增巡检项」直接显示 SQL 文本框（Fix 1 验收）
- [ ] inspection_type 字段可输入新值，保存后自动补全出现新值（Fix 2 验收）
- [ ] 编辑 DB_READONLY_SQL_EXEC 项 / 系统默认项行为不变
- [ ] 总改动 ≤ 20 行

## Complexity: **Low** (< 1.5 小时)

仅前端 1 文件 5 处改动；后端 / DB / schema / API 完全不动。

## 相关文件

- 计划根因追溯：`frontend/src/views/inspection/Items.vue:464-482`（resetForm）、`Items.vue:107-156`（SQL/JSON 分支）、`Items.vue:87-93`（inspection_type form）、`Items.vue:26-29`（inspection_type filter）
- 后端 list：`backend/app/services/inspection_service.py:289-298`
- 后端 schema：`backend/app/schemas/inspection.py:31,50,71`
