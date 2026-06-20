# Plan: 资产校验功能优化 v2

**Source**: 用户需求 + 11 条评审建议（逐条验证后采纳）
**Complexity**: Large
**Status**: READY_FOR_IMPLEMENTATION

---

## 验证记录

| # | 建议 | 验证结果 | 采纳 |
|---|---|---|---|
| 1 | 连通性门控前移到 AWX Playbook | 确认 Playbook 执行顺序 port_check → db_fact → os_fact，可在中间插入门控 | ✅ P0 |
| 2 | `collect_all_facts()` vs `collect_basic_facts()` 不一致 | 确认，统一为 `collect_all_facts()` | ✅ P0 |
| 3 | Windows 端口 3389 错误 | 确认 `os_fact_collect` 仅支持 SSH，3389 是 RDP | ✅ P0 |
| 4 | 候选端口合并后采集端口选择规则缺失 | 确认需要明确规则 | ✅ P0 |
| 5 | db_fact_collect 缺 `failed_when: false` | **已验证**：db_fact_collect 仅有 `changed_when: false`，无 `failed_when: false` | ✅ P0 |
| 6 | 部署需兼容窗口 | 确认有风险 | ✅ P0 |
| 7 | 补 DB seed 数据 | 已查 DB：`collector_check_definition` 仅 4 行（均 DB_SQL_COLLECT），缺少 PORT_CHECK 定义 | ✅ P1 |
| 8 | AssetVerifyReport 需后端 API | 确认当前无聚合接口 | ✅ P1 |
| 9 | 批量 apply 需事务锁 | 确认高风险 | ✅ P1 |
| 10 | raw_result 标准化 | **已验证**：port_check 的 `elapsed_ms` 实际是秒，不是毫秒 | ✅ P1 |
| 11 | database_status → status 映射危险 | 确认语义不一致，仅做 fact_snapshot 展示 | ✅ P1 |

### 额外发现的 Bug

- `collector_check_definition` 表中 `OS_BASIC_FACT_COLLECTION` 的 `task_type` 错误设为 `DB_SQL_COLLECT`，应为 `OS_DISCOVERY`
- `collector_check_definition` 表缺少 `DB_PORT_REACHABILITY`、`SSH_PORT_REACHABILITY`、`PORT_CANDIDATE_REACHABILITY` 三行定义
- `elapsed_ms` 实际存储秒值，命名误导

---

## 一、P0 — 连通性门控前移到 AWX Playbook（方案 A）

### 1.1 当前问题

原 plan 将门控放在 `handle_callback_post_process()` 中，但此时 AWX 已经执行完整个 Job（包括 DB/OS 采集），无法阻止实际采集发生。

### 1.2 方案 A：AWX 单 Job 两阶段门控

Playbook 当前执行顺序天然支持两阶段：port_check 全部完成后才进入 db_fact / os_fact。只需在中间插入门控。

**Playbook 修改**（`dbops_collector_generic.yml`）：

在 port_check role 之后、DB/OS fact role 之前新增：

```yaml
# === 连通性门控：构建可达资产列表 ===
- name: Build reachable DB formal port asset list
  ansible.builtin.set_fact:
    reachable_db_asset_ids: >-
      {{
        collector_results
        | selectattr('check_code', 'equalto', 'DB_PORT_REACHABILITY')
        | selectattr('target_scope', 'equalto', 'db_instance')
        | selectattr('reachable', 'equalto', true)
        | selectattr('is_formal_port', 'equalto', true)
        | map(attribute='asset_id') | list | unique
      }}

- name: Build reachable OS asset id list
  ansible.builtin.set_fact:
    reachable_os_asset_ids: >-
      {{
        collector_results
        | selectattr('check_code', 'in', ['OS_PORT_REACHABILITY', 'SSH_PORT_REACHABILITY'])
        | selectattr('target_scope', 'equalto', 'server')
        | selectattr('reachable', 'equalto', true)
        | map(attribute='asset_id') | list | unique
      }}
```

DB facts 路由加门控：

```yaml
when:
  - collector_item.check_code in db_fact_check_codes
  - collector_item.asset_id | int in reachable_db_asset_ids
```

OS facts 路由加门控：

```yaml
when:
  - collector_item.check_code == 'OS_BASIC_FACT_COLLECTION'
  - collector_item.asset_id | int in reachable_os_asset_ids
```

### 1.3 未通过门控的 item 如何处理

Playbook 本身无法标记 DB item 为 skipped（DB item 被 `when` 过滤后根本不会进入 role）。所以：
- **Playbook 侧**：未通过门控的 item 不执行
- **Callback 侧**：`handle_callback` 收到 callback 后，检查哪些 DB/OS item 未出现在 `collector_results` 中。**不能一律标记为 `CONNECTIVITY_GATE_FAILED`**，需按同资产端口探测结果聚合判断：

| 场景 | skip reason |
|---|---|
| 多候选端口 reachable | `PORT_CANDIDATE_CONFLICT` |
| 正式端口不通，单候选端口 reachable | `PORT_DRIFT_SUSPECTED` |
| 全部端口 unreachable | `CONNECTIVITY_GATE_FAILED` |
| Windows OS facts 未实现 | `OS_FACT_UNSUPPORTED_WINDOWS` |
| 其他未知缺失 | `CALLBACK_RESULT_MISSING` |

这样前端 `VerifyItemDetail` 才能展示准确的跳过原因。

### 1.4 port_check role 必须携带 `is_formal_port` 字段（含 Phase 1 兼容默认值）

**验证**：当前 `port_check/tasks/main.yml` 的 `collector_item_result` **不包含** `is_formal_port`、`is_required`、`port_source`。门控中 `selectattr('is_formal_port', 'equalto', true)` 会失效。

**关键兼容问题**：Phase 1 只部署 Playbook，旧后端下发的 `DB_PORT_REACHABILITY` item 没有 `is_formal_port` 字段。如果默认值是 `false`，所有正式端口的探测结果都会被门控排除，导致 DB facts 全部不执行。

**修正**：`is_formal_port` 默认值根据 `check_code` 推导 —— 旧后端下发的 `DB_PORT_REACHABILITY` 自动视为正式端口：

port_check 结果完整 yaml：

```yaml
collector_item_result:
  item_key: "{{ collector_item.item_key }}"
  check_code: "{{ collector_item.check_code }}"
  target_scope: "{{ collector_item.target_scope }}"
  asset_id: "{{ collector_item.asset_id | int }}"
  target_host: "{{ collector_item.target_host }}"
  target_port: "{{ collector_item.target_port | int }}"
  is_formal_port: >-
    {{
      collector_item.is_formal_port
      | default(collector_item.check_code == 'DB_PORT_REACHABILITY')
      | bool
    }}
  is_required: "{{ collector_item.is_required | default(false) | bool }}"
  port_source: "{{ collector_item.port_source | default('unknown') }}"
  status: "{{ 'verified' if not (port_check.failed | default(false) | bool) else 'missing' }}"
  reachable: "{{ not (port_check.failed | default(false) | bool) }}"
  message: >-
    {{ '' if not (port_check.failed | default(false) | bool)
       else (port_check.msg | default('PORT_REACHABILITY_FAILED')) }}
  raw_result:
    duration_sec: "{{ port_check.elapsed | default(0) }}"
    duration_ms: "{{ (port_check.elapsed | default(0) | float * 1000) | int }}"
    failed: "{{ port_check.failed | default(false) | bool }}"
    msg: "{{ port_check.msg | default('') }}"
    is_formal_port: >-
      {{
        collector_item.is_formal_port
        | default(collector_item.check_code == 'DB_PORT_REACHABILITY')
        | bool
      }}
    is_required: "{{ collector_item.is_required | default(false) | bool }}"
    port_source: "{{ collector_item.port_source | default('unknown') }}"
```

兼容逻辑：

| 场景 | check_code | 显式 is_formal_port | 最终值 |
|---|---|---|---|
| 旧后端下发正式端口探测 | `DB_PORT_REACHABILITY` | 无 | `true`（自动） |
| 旧后端下发候选端口探测 | `PORT_CANDIDATE_REACHABILITY` | 无 | `false`（自动） |
| 新后端下发正式端口 | `DB_PORT_REACHABILITY` | `true` | `true` |
| 新后端下发候选端口 | `DB_PORT_REACHABILITY` | `false` | `false` |

### 1.5 Callback Schema 必须保留 `is_formal_port`

**验证**：当前 `CollectorCallbackItem`（`schemas/collector.py:140-154`）有 `port_source`、`is_required`，但**没有 `is_formal_port`**。如果不补此字段，backend callback 处理时无法按实例聚合端口探测结果。

```python
# schemas/collector.py CollectorCallbackItem 新增
is_formal_port: bool = Field(default=False)

# schemas/collector.py CollectorRunItemResponse 同步新增
is_formal_port: bool = False
```

同时 `handle_callback` 从 `raw_result` 兜底读取：

```python
is_formal_port = item.is_formal_port
if is_formal_port is None:
    is_formal_port = (item.raw_result or {}).get("is_formal_port", False)
```

> 顶层字段用于 callback 入参校验和聚合查询。**持久化以 `raw_result.is_formal_port` 为准**（方案 A：不新增 DB 列，降低 DDL 改动面）。后端按实例聚合端口探测结果时从 `raw_result` 读取。

---

## 二、P0 — Collector Client 统一为 `collect_all_facts()`

### 2.1 当前问题

`cli.py` 按 check_code 分支调用不同方法。合并后只有 `DB_BASIC_FACT_COLLECTION`，但 `collect_basic_facts()` 不包含 version/role。

### 2.2 方案

```python
# base.py 新增默认实现
def collect_all_facts(self) -> dict[str, Any]:
    """Collect all facts: basic + version + role. Override per connector.
    
    Partial errors are recorded in _fact_errors so VerifyItemDetail can
    surface which collector module failed.
    """
    facts: dict[str, Any] = {}
    fact_errors: list[dict[str, str]] = []

    collectors = [
        ("basic", getattr(self, "collect_basic_facts", None)),
        ("version", getattr(self, "collect_version_facts", None)),
        ("role", getattr(self, "collect_role_facts", None)),
    ]

    for name, func in collectors:
        if func is None:
            continue   # connector 未实现此方法，跳过
        try:
            result = func()
            if isinstance(result, dict):
                facts.update(result)
        except Exception as exc:
            fact_errors.append({
                "collector": name,
                "error": str(exc),
            })

    if fact_errors:
        facts["_fact_errors"] = fact_errors

    # 全部 collector 都失败 → 不返回空 facts，避免假阳性
    if not facts or set(facts.keys()) == {"_fact_errors"}:
        raise RuntimeError(f"all fact collectors failed: {fact_errors}")

    return facts
```

```python
# cli.py collect_db_facts() 简化
def collect_db_facts(item: CollectorItemInput) -> CollectorItemOutput:
    # 统一调用 collect_all_facts()，不再按 check_code 分支
    all_facts = connector.collect_all_facts()
    # ...
```

保留 `collect_basic_facts` / `collect_version_facts` / `collect_role_facts` 旧接口不变。

---

## 三、P0 — OS 端口语义修正

### 3.1 当前问题

原 plan 写 Linux=22, Windows=3389。但：
- `os_fact_collect` role 仅实现 Linux SSH 采集
- 3389 是 RDP，不是采集通道
- Windows WinRM 端口是 5985/5986

### 3.2 修正

| 场景 | 默认端口 | OS_BASIC_FACT_COLLECTION 行为 |
|---|---|---|
| Linux (`os_family=linux` 或空) | **22** (SSH) | 正常下发采集 |
| Windows (`os_family=windows`) | **5985** (WinRM HTTP) | **暂不下发采集**（WinRM 采集未实现），仅检查端口连通性 |
| 其他 OS | 从 PortProfile 获取 | 按 PortProfile 确定 |

`OS_PORT_REACHABILITY` 定义为"OS 采集通道连通性"，不是"登录桌面端口连通性"。

### 3.3 Builder 阶段禁止 Windows 下发 OS facts

`_OsBasicFactCollectionBuilder` 必须在生成 item 时判断 `os_family`：

```python
os_family = str((server.extra_attrs or {}).get("os_family") or "linux").lower()
if os_family == "windows":
    # 只生成 OS_PORT_REACHABILITY，OS_BASIC_FACT_COLLECTION 标记为 skipped
    items.append(self._build_skipped_item(
        item={...},
        reason="OS_FACT_UNSUPPORTED_WINDOWS"
    ))
    continue
```

> 如果在 Builder 不做此判断，仅依赖 Playbook 门控，Windows 5985 可达时 `reachable_os_asset_ids` 会包含该资产，Playbook 仍可能进入 `os_fact_collect` 执行 SSH 采集并失败。

### 3.4 OS 端口解析优先级（兜底链）

`extra_attrs.os_family` 覆盖不完整（仅 1/2 服务器有值），OS admin port 解析顺序：

```
1. server.extra_attrs.os_family → 判断 Linux/Windows
2. server.os_version_id → JOIN os_version.os_name / version_name →
   含 "windows"/"win" → Windows；含 "linux"/"centos"/"rhel"/"ubuntu" → Linux
3. PortProfile (target_scope=server, db_type_code=NULL) → 获取 default_port
4. 默认 Linux / 22
```

---

## 四、P0 — 候选端口合并后采集端口选择规则

### 4.1 背景：实际 PortProfile 数据

DB 中已配置的端口（7 行）：

| scope | db_type | port | required | 说明 |
|---|---|---|---|---|
| db_instance | ORACLE | **1521** | ✅ required | Oracle 默认监听端口 |
| db_instance | ORACLE | 1526 | candidate | Oracle 备用监听端口 |
| db_instance | ORACLE | 1903 | candidate | Oracle 自定义服务端口 |
| db_instance | SQLSERVER | **1433** | ✅ required | SQL Server 默认 TDS 端口 |
| db_instance | SQLSERVER | 3000 | candidate | SQL Server 备用端口 |
| server | linux | 22 | required | Linux SSH |

### 4.2 方案 A：不在 AWX 内动态切换采集端口（本次采纳）

**决策**：第一版不实现"候选端口可达后自动切换采集端口"。候选端口探测只在门控中判断连通性，不通的资产不采集，只生成 proposal。操作员 apply proposal 后，下次重跑时正式端口已修正，自动采集通过。

**理由**：
- Ansible Jinja2 不支持 `groupby` + `append` 等命令式操作，伪代码不可落地
- 避免在 AWX Playbook 内做复杂的端口重写逻辑
- 降低首次实施风险，proposal 审批链路已成熟

### 4.3 规则（收紧"正式端口"定义）

**正式端口定义**：仅指 `DbInstance.port` 当前记录值。`PortProfile.is_required=true` 仅表示默认必测端口，不能等同于资产正式端口。

```
规则 1：DbInstance.port 不为空，且该端口 reachable=true
        → 进入 reachable_db_asset_ids → DB_BASIC_FACT_COLLECTION 正常执行

规则 2：DbInstance.port 为空，且 PortProfile 候选端口仅 1 个 reachable
        → 不进入 reachable_db_asset_ids → 生成 PORT_FILL_SUGGESTION proposal

规则 3：DbInstance.port 不为空但不可达，且仅 1 个候选端口 reachable
        → 不进入 reachable_db_asset_ids → 生成 PORT_DRIFT_SUSPECTED proposal

规则 4：多个候选端口 reachable（≥2）
        → 不进入 reachable_db_asset_ids
        → 生成 PORT_CANDIDATE_CONFLICT proposal (suggested_value={"candidates":[...]}, confidence=low)

规则 5：全部 unreachable
        → 不进入 reachable_db_asset_ids
        → item status=skipped, reason=CONNECTIVITY_GATE_FAILED（不生成 proposal）
```

### 4.4 Playbook 门控实现（可落地的 Jinja2）

利用 Ansible 内置 `selectattr` + `map` filter，不需要自定义 Python：

```yaml
# Step 1: 提取正式端口可达的资产 ID
- name: Build reachable formal port asset list
  ansible.builtin.set_fact:
    reachable_db_asset_ids: >-
      {{
        collector_results
        | selectattr('check_code', 'equalto', 'DB_PORT_REACHABILITY')
        | selectattr('target_scope', 'equalto', 'db_instance')
        | selectattr('reachable', 'equalto', true)
        | selectattr('is_formal_port', 'equalto', true)
        | map(attribute='asset_id') | list | unique
      }}

# Step 2: DB fact 路由加门控
- name: Route db_fact_collect items
  ansible.builtin.include_role:
    name: db_fact_collect
  loop: "{{ items }}"
  loop_control:
    loop_var: collector_item
    label: "{{ collector_item.item_key }}"
  when:
    - collector_item.check_code in db_fact_check_codes
    - collector_item.asset_id | int in reachable_db_asset_ids
```

> 候选端口的 reachable 信息在 callback 后端处理（`handle_callback` 按 `db_instance_id` 聚合同 item 的多个端口探测结果），不放在 Playbook 里。

### 4.5 PORT_CANDIDATE_CONFLICT 处理链路

```
Playbook 侧：
  DB_PORT_REACHABILITY 探测所有候选端口（正式+候选，每个端口一个 item）
  门控：只有正式端口可达的 asset_id 才进入 reachable_db_asset_ids

Callback 侧 (CollectorService.handle_callback)：
  1. 接收所有 DB_PORT_REACHABILITY item 的回调结果
  2. 按 (db_instance_id) 聚合端口探测结果
  3. 判断规则 1-4
  4. 规则 2 → 生成 PORT_DRIFT_SUSPECTED proposal
  5. 规则 3 → 生成 PORT_CANDIDATE_CONFLICT proposal
  6. 规则 2/3 对应的 DB_BASIC_FACT_COLLECTION item → skipped

前端侧 (ProposalPanel)：
  展示 PORT_CANDIDATE_CONFLICT → 操作员选择候选端口 → apply
```

### 4.6 Proposal 新增类型

| proposal_type | 触发条件 | apply 要求 |
|---|---|---|
| PORT_FILL_SUGGESTION | port=null, 1 个候选可达 | 直接 apply |
| PORT_DRIFT_SUSPECTED | 正式端口不通, 1 个候选可达 | 直接 apply |
| **PORT_CANDIDATE_CONFLICT** | 正式端口不通, 多个候选可达 | **必须传入 `selected_value`（单个整数端口）** |

---

## 五、P0 — `db_fact_collect` 加 `failed_when: false`

### 5.1 已验证事实

```yaml
# db_fact_collect/tasks/main.yml:35 — 仅有 changed_when
- name: Call collector client for DB facts
  ansible.builtin.command:
    ...
  register: _db_result
  changed_when: false
  # ❌ 缺少 failed_when: false

# os_fact_collect/tasks/main.yml:29-30 — 两者都有
  register: _os_result
  changed_when: false
  failed_when: false  # ✅
```

### 5.2 修复

```yaml
- name: Call collector client for DB facts
  ansible.builtin.command:
    ...
  register: _db_result
  changed_when: false
  failed_when: false  # 新增
```

同时将 `rc/stderr/stdout` 写进 `raw_result`：

```yaml
raw_result:
  facts: "{{ _parsed.facts | default([]) }}"
  error_code: "{{ _parsed.error_code | default('') }}"
  connector: "{{ _parsed.connector | default('') }}"
  duration_ms: "{{ _parsed.duration_ms | default(0) }}"
  rc: "{{ _db_result.rc | default(-1) }}"         # 新增
  stderr: "{{ _db_result.stderr | default('') }}"  # 新增
```

---

## 六、P0 — 三阶段兼容部署

### 6.1 当前问题

原 plan 写"先 push playbook，再部署后端"。如果 playbook 只支持新 check_code，旧后端下发的 `SSH_PORT_REACHABILITY` 等旧 check_code 会无法路由。

### 6.2 三阶段部署

```
Phase 1 — 兼容窗口：仅部署 Playbook 兼容新旧 check_code
  port_check when: ['DB_PORT_REACHABILITY', 'SSH_PORT_REACHABILITY', 'OS_PORT_REACHABILITY', 'PORT_CANDIDATE_REACHABILITY']
  db_fact_check_codes: ['DB_BASIC_FACT_COLLECTION', 'DB_VERSION_FACT_COLLECTION', 'DB_ROLE_FACT_COLLECTION']
  加入两阶段门控逻辑
  **不部署新版 collector_client**（旧后端仍下发 3 个 DB fact check_code，新 client 的 collect_all_facts() 会重复采集）

Phase 2 — 切换：同批部署 DB Seed SQL + 后端 Registry + collector_client
  新任务只产生 4 个新 check_code
  旧任务仍可在此窗口完成

Phase 3 — 清理：确认无遗留旧任务后
  删除 playbook 中旧 check_code 路由
  collector_client 删除旧 check_code 分支
  可选：清理 collector_check_definition 旧行
```

---

## 七、P1 — DB Seed 数据脚本

### 7.1 已验证 DB 现状

`collector_check_definition` 表（4 行，均 `DB_SQL_COLLECT` 类型）：
```
OS_BASIC_FACT_COLLECTION | task_type=DB_SQL_COLLECT  ← 错误，应为 OS_DISCOVERY
DB_BASIC_FACT_COLLECTION | task_type=DB_SQL_COLLECT
DB_VERSION_FACT_COLLECTION | task_type=DB_SQL_COLLECT
DB_ROLE_FACT_COLLECTION | task_type=DB_SQL_COLLECT
```

**缺失**：`DB_PORT_REACHABILITY`、`SSH_PORT_REACHABILITY`、`PORT_CANDIDATE_REACHABILITY` 的定义行。

`inspection_item` 表（8 行）：与 registry 模板一致，需要同步更新。

### 7.2 Seed SQL

> ❗Dangerous：执行前必须备份 `collector_check_definition`、`inspection_item` 两张表。

```sql
-- 备份（执行前）
CREATE TABLE IF NOT EXISTS dbops.collector_check_definition_bak_20260617 AS
SELECT * FROM dbops.collector_check_definition;
CREATE TABLE IF NOT EXISTS dbops.inspection_item_bak_20260617 AS
SELECT * FROM dbops.inspection_item;
```

文件：`backend/db/dbops_check_code_convergence.sql`

```sql
BEGIN;

-- 1. 禁用旧 check_code
UPDATE dbops.collector_check_definition
SET enabled = false, updated_at = now()
WHERE check_code IN (
    'SSH_PORT_REACHABILITY',
    'PORT_CANDIDATE_REACHABILITY',
    'DB_VERSION_FACT_COLLECTION',
    'DB_ROLE_FACT_COLLECTION'
);

-- 2. 新增 OS_PORT_REACHABILITY
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES (
    'OS_PORT_REACHABILITY', 'OS管理端口连通性检查', 'server', 'PORT_CHECK',
    5, true, '{}', '检查服务器OS采集通道端口是否可达（Linux SSH 22 / Windows WinRM 5985）', now(), now()
) ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    enabled = true,
    description = EXCLUDED.description,
    updated_at = now();

-- 3. 修正 OS_BASIC_FACT_COLLECTION 的 task_type
UPDATE dbops.collector_check_definition
SET task_type = 'OS_DISCOVERY', updated_at = now()
WHERE check_code = 'OS_BASIC_FACT_COLLECTION' AND task_type = 'DB_SQL_COLLECT';

-- 4. 确保端口检查定义存在（idempotent）
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES
    ('DB_PORT_REACHABILITY', 'DB端口连通性检查（含候选端口探测）', 'db_instance', 'PORT_CHECK',
     5, true, '{}'::jsonb, '检查数据库实例端口是否可达（含 PortProfile 候选端口探测）', now(), now())
ON CONFLICT (check_code) DO UPDATE SET
    check_name = EXCLUDED.check_name,
    target_scope = EXCLUDED.target_scope,
    task_type = EXCLUDED.task_type,
    default_timeout_seconds = EXCLUDED.default_timeout_seconds,
    enabled = true,
    config = EXCLUDED.config,
    description = EXCLUDED.description,
    updated_at = now();

-- 5. inspection_item 更新
-- 禁用已合并或被新 item 替代的旧检查项
UPDATE dbops.inspection_item
SET enabled = false, updated_at = now()
WHERE item_code IN (
    'CONNECTIVITY_PORT_REACHABLE',   -- 由 CONNECTIVITY_DB_PORT 替代
    'DB_VERSION_COLLECTED',          -- 合并到 DB_BASIC_FACT_COLLECTION
    'DB_ROLE_COLLECTED',             -- 合并到 DB_BASIC_FACT_COLLECTION
    'DB_ROLE_CHANGED',               -- 由 DB_FACT_DRIFT_DETECTED 替代（覆盖 node_role 漂移）
    'INSTANCE_PORT_DRIFT'            -- PORT_CANDIDATE_REACHABILITY 已合并，由 CONNECTIVITY_DB_PORT 替代
);

-- 新增 DB/OS 端口连通性拆分
INSERT INTO dbops.inspection_item (
    item_code, item_name, check_code, target_scope, severity, enabled,
    description, rule_config, created_at, updated_at
) VALUES
    ('CONNECTIVITY_DB_PORT', 'DB端口连通性', 'DB_PORT_REACHABILITY', 'db_instance', 'critical', true,
     '数据库实例端口 TCP 连通性检查', '{}'::jsonb, now(), now()),
    ('CONNECTIVITY_OS_PORT', 'OS端口连通性', 'OS_PORT_REACHABILITY', 'server', 'critical', true,
     '服务器OS采集通道端口连通性检查', '{}'::jsonb, now(), now()),
    ('DB_FACT_DRIFT_DETECTED', 'DB事实字段漂移', 'DB_BASIC_FACT_COLLECTION', 'db_instance', 'warning', true,
     'DB基础事实采集后发现实例名、服务名、角色等字段与CMDB不一致',
     '{"fields":["instance_name","service_name","node_role","port"]}'::jsonb, now(), now())
ON CONFLICT (item_code) DO UPDATE SET
    item_name = EXCLUDED.item_name,
    check_code = EXCLUDED.check_code,
    target_scope = EXCLUDED.target_scope,
    severity = EXCLUDED.severity,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    rule_config = EXCLUDED.rule_config,
    updated_at = now();

-- 6. 补旧 check_code 的 disabled 定义（保证历史任务展示有名称）
INSERT INTO dbops.collector_check_definition (
    check_code, check_name, target_scope, task_type,
    default_timeout_seconds, enabled, config, description, created_at, updated_at
) VALUES
    ('SSH_PORT_REACHABILITY', '旧版SSH端口连通性检查', 'server', 'PORT_CHECK',
     5, false, '{}'::jsonb, '旧版检查项，已由 OS_PORT_REACHABILITY 替代', now(), now()),
    ('PORT_CANDIDATE_REACHABILITY', '旧版候选端口连通性检查', 'db_instance', 'PORT_CHECK',
     5, false, '{}'::jsonb, '旧版检查项，已合并到 DB_PORT_REACHABILITY', now(), now()),
    ('DB_VERSION_FACT_COLLECTION', '旧版DB版本事实采集', 'db_instance', 'DB_SQL_COLLECT',
     60, false, '{}'::jsonb, '旧版检查项，已合并到 DB_BASIC_FACT_COLLECTION', now(), now()),
    ('DB_ROLE_FACT_COLLECTION', '旧版DB角色事实采集', 'db_instance', 'DB_SQL_COLLECT',
     60, false, '{}'::jsonb, '旧版检查项，已合并到 DB_BASIC_FACT_COLLECTION', now(), now())
ON CONFLICT (check_code) DO UPDATE SET
    enabled = false,
    updated_at = now();

COMMIT;
```

> **注意**：字段名以实际 DB schema 为准；执行前建议 `SELECT * FROM dbops.collector_check_definition` 确认列名。

---

## 八、P1 — AssetVerifyReport 后端聚合 API

新增端点：

```http
GET /api/v1/collector/batch-runs/{batch_run_id}/asset-report
```

实现：`BatchCollectorService.get_asset_report(db, batch_run_id)`

```python
def get_asset_report(db, batch_run_id) -> list[dict]:
    """按资产维度聚合 batch 内所有 item 的结果。"""
    items = db.query(CollectorRunItem).filter(
        CollectorRunItem.collector_run.has(batch_run_id=batch_run_id)
    ).all()
    
    # 按 (target_scope, asset_id) 分组聚合
    groups: dict[tuple, dict] = {}
    for item in items:
        key = (item.target_scope, item.db_instance_id or item.server_id)
        if key not in groups:
            groups[key] = {
                "entity_type": item.target_scope,
                "entity_id": item.db_instance_id or item.server_id,
                "items": [],
                "db_port_status": None,
                "os_port_status": None,
                "fact_status": None,
                "fact_count": 0,
                "error_messages": [],
            }
        # 按 check_code 归类状态...
    
    # JOIN 获取 IP/名称
    return list(groups.values())
```

响应结构：

```json
{
  "batch_run_id": 123,
  "batch_code": "BATCH-...",
  "assets": [
    {
      "entity_type": "db_instance",
      "entity_id": 1001,
      "entity_name": "ORCL1",
      "ip_address": "10.1.1.10",
      "db_port_status": "reachable",
      "os_port_status": "n/a",
      "fact_status": "success",
      "fact_count": 12,
      "proposal_count": 2,
      "error_messages": [],
      "items": [ /* 该资产的所有 item 摘要 */ ]
    }
  ]
}
```

---

## 九、P1 — 批量 Proposal 操作事务安全

### 9.1 统一端点

```http
POST /api/v1/collector/proposals/batch-action
```

请求体：

```json
{
  "proposal_ids": [1, 2, 3],
  "action": "approve|reject|apply",
  "comment": "optional comment",
  "override_values": {
    "45": 1526
  }
}
```

`override_values` 用于 PORT_CANDIDATE_CONFLICT 场景：`suggested_value={"candidates":[1526,1903]}` 不能直接写入 `db_instance.port`（整数列），必须由用户选定单个端口后传入。

单条 apply 也需支持：

```http
POST /api/v1/collector/proposals/{proposal_id}/apply
```

```json
{
  "selected_value": 1526,
  "comment": "人工确认 1526 为正确监听端口"
}
```

### 9.2 后端实现要点

```python
def batch_action(db, proposal_ids, action, operator, comment=None, override_values=None):
    override_values = override_values or {}
    results = []
    for pid in proposal_ids:
        try:
            proposal = db.query(AssetChangeProposal).filter(
                AssetChangeProposal.id == pid
            ).with_for_update().first()
            
            if action == "apply" and proposal.status != "approved":
                results.append({"id": pid, "success": False, "error": "仅 approved 可 apply"})
                continue
            
            # PORT_CANDIDATE_CONFLICT：必须传入 selected_value，保留原始 candidates
            if action == "apply" and proposal.proposal_type == "PORT_CANDIDATE_CONFLICT":
                selected = override_values.get(str(pid))
                if selected is None or not isinstance(selected, int):
                    results.append({"id": pid, "success": False, 
                                    "error": "PORT_CANDIDATE_CONFLICT 必须传入 selected_value（单个整数端口）"})
                    continue
                # 校验 selected_value 合法性
                if not isinstance(selected, int) or selected < 1 or selected > 65535:
                    results.append({"id": pid, "success": False,
                                    "error": "selected_value 必须是 1-65535 的整数端口"})
                    continue
                # 校验 selected_value 在 candidates 内
                candidates = (proposal.suggested_value or {}).get("candidates", [])
                if selected not in candidates:
                    results.append({"id": pid, "success": False,
                                    "error": f"selected_value={selected} 不在候选端口列表 {candidates} 内"})
                    continue
                # 保留原始 suggested_value（含 candidates），传入 selected_value 给 apply
                apply_proposal(db, proposal_id=pid, operator=operator,
                              selected_value=selected, comment=comment)
                results.append({"id": pid, "success": True})
                continue
            
            # 调用现有单条方法
            if action == "approve":
                approve_proposal(db, proposal_id=pid, operator=operator)
            elif action == "apply":
                apply_proposal(db, proposal_id=pid, operator=operator)
            # ...
            results.append({"id": pid, "success": True})
        except Exception as e:
            results.append({"id": pid, "success": False, "error": str(e)})
    
    db.commit()
    return {"action": action, "results": results, "success_count": ..., "fail_count": ...}
```

---

## 十、P1 — raw_result 标准化

### 10.1 已验证问题

port_check `raw_result.elapsed_ms` 实际是秒值（来自 `wait_for.elapsed`）：

```yaml
# port_check/tasks/main.yml:46
raw_result:
  elapsed_ms: "{{ port_check.elapsed | default(0) }}"  # ← 实际是秒
```

### 10.2 标准化格式

所有 item 的 `raw_result` 统一为：

```json
{
  "status": "verified|missing|collected|failed",
  "reachable": true,
  "duration_ms": 1234,
  "error_code": "AUTHENTICATION_FAILED|CONNECTION_TIMEOUT|...",
  "message": "human-readable message",
  "rc": 0,
  "stdout": "...",
  "stderr": "...",
  "connector": "oracle|linux_ssh|...",
  "facts": [...]
}
```

### 10.3 stdout/stderr 脱敏与截断

`stdout`/`stderr` 可能包含连接串、用户名、异常堆栈中的敏感参数，入库前必须处理：

```python
import re

SENSITIVE_PATTERNS = [
    r"(?i)(password\s*[=:]\s*)[^;\s]+",
    r"(?i)(pwd\s*[=:]\s*)[^;\s]+",
    r"(?i)(token\s*[=:]\s*)[^;\s]+",
    r"(?i)(secret\s*[=:]\s*)[^;\s]+",
    r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._-]+",
]

def sanitize_output(value: str | None, max_len: int = 4000) -> str:
    if not value:
        return ""
    text = str(value)
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, r"\1***", text)
    return text[:max_len]
```

脱敏在 collector_client 输出端（`build_output()`）或 callback 入库端（`handle_callback`）执行。

**修改范围**：
- `port_check/tasks/main.yml`：`elapsed_ms` → `duration_sec`（如实命名），同时加 `duration_ms`
- `db_fact_collect/tasks/main.yml`：加 `rc`, `stderr`（脱敏后）
- `os_fact_collect/tasks/main.yml`：加 `rc`, `stderr`（脱敏后）

---

## 十一、P1 — `database_status` 不映射到 `db_instance.status`

`db_instance.status` 约束：`active / inactive / retired`
数据库采集状态：`OPEN / MOUNTED / STARTED / ONLINE / RECOVERING / READ WRITE`

语义不同，**不做自动变更 proposal**。仅作为 fact_snapshot 记录，在 `AssetVerifyReport` 中展示为信息列。

---

## 十二、P1 — 集群类型 (cluster_type) 校验（新增）

### 12.1 背景

`DbInstance` 没有直接的 `cluster_type` 字段，但通过 `cluster_id` FK 关联 `Cluster` 表：
- `Cluster.cluster_type` — 如 `master-slave`, `sharding`, `single`, `primary-standby` 等
- DB_BASIC_FACT_COLLECTION 采集到的 `database_role` / `is_in_recovery` 等事实可以**反向推断**集群拓扑

### 12.2 角色 → 集群类型推断规则

| 采集事实 | 实例级别推断 | 集群级别校验 |
|---|---|---|
| `database_role` = PRIMARY (Oracle) | 该实例是主库 | 集群应存在至少一个 STANDBY 实例 |
| `database_role` = PHYSICAL STANDBY (Oracle) | 该实例是备库 | 集群应存在 PRIMARY 实例 |
| `is_in_recovery` = false (PG) | 该实例是主库 | 同上 |
| `is_in_recovery` = true (PG) | 该实例是备库 | 同上 |
| `has_slave` = true (MySQL `SHOW SLAVE STATUS`) | 该实例有从库 | 集群类型不应该是 `single` |
| `is_hadr_enabled` = true (MSSQL) | Always On 启用 | 集群类型应该是 `alwayson` 或类似 |

### 12.3 实现方式：独立报告辅助函数（不走通用 drift/proposal 流程）

**决策**：cluster_type 不走 `DriftDetectionService._field_mappings()` 跨表映射。原因：
1. `_field_mappings()` 的 `target_type` 只能是 `server`/`db_instance`（与 inspection_item CHECK 约束一致）
2. 单实例无法可靠推断 cluster_type
3. 本次不自动生成可 apply 的 proposal

改用独立辅助函数，供 `AssetVerifyReport` 后端 API 调用：

```python
# drift_detection_service.py 新增
@staticmethod
def build_cluster_type_hint(db: Session, instance: DbInstance, facts: dict) -> dict | None:
    """从单实例采集事实推断 cluster_type 提示。
    
    本次仅作为 AssetVerifyReport 的信息提示，不生成 AssetChangeProposal。
    下轮跨实例聚合后再考虑自动 proposal。
    """
    db_type_code = (instance.db_type.type_code or "").lower() if instance.db_type else ""
    inferred = _infer_cluster_type_from_facts(facts, db_type_code)
    if not inferred:
        return None

    cluster = instance.cluster
    if not cluster or not cluster.cluster_type:
        return None
    
    current = cluster.cluster_type.lower()
    if current == inferred.lower():
        return None  # 一致，无需提示

    return {
        "item_code": "CLUSTER_TYPE_MISMATCH",
        "severity": "warning",
        "target_scope": "db_instance",
        "target_id": instance.id,
        "derived_target_type": "cluster",
        "derived_target_id": instance.cluster_id,
        "current_cluster_type": cluster.cluster_type,
        "inferred_cluster_type": inferred,
        "auto_proposal": False,   # 本次不自动生成可 apply 变更
        "message": f"采集事实推断的集群类型({inferred})与CMDB记录({cluster.cluster_type})不一致，请人工确认。"
    }

@staticmethod
def _infer_cluster_type_from_facts(facts: dict[str, Any], db_type_code: str) -> str | None:
    """从采集事实推断集群类型。"""
    role = str(facts.get("database_role") or facts.get("instance_role") or "").upper()
    is_recovery = facts.get("is_in_recovery")
    has_slave = facts.get("has_slave")

    if role in ("PRIMARY",) and has_slave:
        return "master-slave"
    if role in ("PHYSICAL STANDBY", "LOGICAL STANDBY", "SNAPSHOT STANDBY"):
        return "primary-standby"
    if is_recovery is True:
        return "primary-standby"
    # PRIMARY without slave / is_in_recovery=false → ambiguous, don't infer
    return None
```

### 12.5 新增 Inspection Item（挂 db_instance，派生校验 cluster）

**验证**：`inspection_item.target_scope` CHECK 约束为 `IN ('server', 'db_instance')`，不支持 `'cluster'`。因此巡检项挂在 `db_instance`，用 `rule_config.derived_target_type='cluster'` 表达跨表校验。

```sql
INSERT INTO dbops.inspection_item (
    item_code, item_name, check_code, target_scope, severity, enabled,
    description, rule_config, created_at, updated_at
) VALUES (
    'CLUSTER_TYPE_MISMATCH', '集群类型不匹配',
    'DB_BASIC_FACT_COLLECTION', 'db_instance', 'warning', true,
    '从实例角色采集推断的集群类型与CMDB记录不一致',
    '{"derived_target_type":"cluster","auto_proposal":false}'::jsonb,
    now(), now()
) ON CONFLICT (item_code) DO UPDATE SET
    item_name = EXCLUDED.item_name,
    check_code = EXCLUDED.check_code,
    target_scope = EXCLUDED.target_scope,
    severity = EXCLUDED.severity,
    enabled = EXCLUDED.enabled,
    description = EXCLUDED.description,
    rule_config = EXCLUDED.rule_config,
    updated_at = now();
```

### 12.6 本次范围：报告提示，不自动生成变更提案

**决策**：单实例无法可靠推断 cluster_type（一个 PRIMARY 可能是 single，也可能是主备集群里的主库），因此本次**仅作为 AssetVerifyReport 中的提示信息展示**，不自动生成可 apply 的 AssetChangeProposal，不允许更新 `Cluster.cluster_type`。

| 本次做 | 下轮做 |
|---|---|
| 单实例事实采集结果与 Cluster.cluster_type 比对 | 同一 cluster 下多个实例全部采集完后跨实例聚合推断 |
| AssetVerifyReport 展示 cluster_type_suspected 提示 | 生成 cluster_type 变更 proposal |
| DriftDetectionService 记录 drift_record（drift_type=info） | 自动 apply cluster_type |

---

## 十三、P0 — 字段更新白名单

### 13.1 风险

采集到的事实与正式资产字段比对后，漂移检测会生成 `AssetChangeProposal`。但某些字段语义不一致或更新后影响面大，不应自动 apply。

❗Dangerous：以下字段**禁止自动更新**正式资产表：
- `server.ip_address`：IP 变更涉及网络拓扑、防火墙规则、DNS 等
- `db_instance.status`：采集到的 DB 状态 (OPEN/MOUNTED) 与资产状态 (active/inactive) 语义不同
- `server.status`：同上
- `cluster.cluster_type`：单实例无法可靠推断

### 13.2 白名单

#### DB 实例 — 允许 apply

| 字段 | 风险 | 说明 |
|---|---|---|
| `db_instance.port` | **中** | 端口漂移/补齐，影响后续采集；apply 后 trust_status=unverified |
| `db_instance.instance_name` | 低 | 实例名变更 |
| `db_instance.service_name` | 低 | Oracle service_name 变更 |
| `db_instance.node_role` | **中** | 角色变更（需人工确认非临时切换） |

#### DB 实例 — 只展示/建议，不自动 apply

| 字段 | 原因 |
|---|---|
| `db_instance.db_version_id` | 版本号 → FK 映射需人工确认 |
| `db_instance.status` | 语义不一致 |
| 采集到的 `database_status` / `instance_status` | 仅做 fact_snapshot 展示 |

#### 服务器 — 允许 apply

| 字段 | 风险 | 说明 |
|---|---|---|
| `server.hostname` | 低 | 主机名变更 |
| `server.cpu_cores` | 低 | CPU 核数变更 |
| `server.memory_gb` | 低 | 内存变更 |
| `server.disk_gb` | **中** | 采集的 df -h 值与 CMDB 记录值可能有格式差异 |

#### 服务器 — 只展示/建议，不自动 apply

| 字段 | 原因 |
|---|---|
| `server.ip_address` | 高危：网络拓扑影响 |
| `server.os_version_id` | OS 版本 → FK 映射需人工确认 |
| `server.status` | 语义不一致 |

#### 集群 — 本次只展示，不 apply

| 字段 | 原因 |
|---|---|
| `cluster.cluster_type` | 单实例不可靠推断，下轮跨实例聚合后再考虑 |

### 13.3 实现约束

`AssetProposalService.apply_proposal()` 在 apply 前校验 `field_path` 是否在白名单内：

```python
APPLYABLE_FIELDS = {
    "db_instance": {"port", "instance_name", "service_name", "node_role"},
    "server": {"hostname", "cpu_cores", "memory_gb", "disk_gb"},
}

def apply_proposal(db, proposal_id, operator):
    # 现有逻辑 ...
    allowed = APPLYABLE_FIELDS.get(proposal.entity_type, set())
    if field_path not in allowed:
        raise ValueError(f"字段 {proposal.entity_type}.{field_path} 不在更新白名单内，不允许 apply")
    # 继续现有 apply 逻辑 ...
```

非白名单字段的漂移仅展示在 AssetVerifyReport 中，不生成 proposal（或生成 proposal 但 status=info_only，不可 apply）。

---

## 十三-A、文件清单（修订后）

| 仓库 | 文件 | Action |
|---|---|---|
| **ansible-playbooks** | `playbooks/dbops_collector_generic.yml` | UPDATE — 兼容新旧 check_code + 两阶段门控 |
| **ansible-playbooks** | `playbooks/roles/db_fact_collect/tasks/main.yml` | UPDATE — 加 `failed_when: false` + raw_result 标准化 |
| **ansible-playbooks** | `playbooks/roles/port_check/tasks/main.yml` | UPDATE — raw_result `elapsed_ms` → `duration_sec` |
| **ansible-playbooks** | `playbooks/roles/os_fact_collect/tasks/main.yml` | UPDATE — raw_result 加 `rc`, `stderr` |
| **dbops-collector** | `collector_client/cli.py` | UPDATE — 删除 check_code 分支，统一 `collect_all_facts()` |
| **dbops-collector** | `collector_client/db_connectors/base.py` | UPDATE — 新增 `collect_all_facts()` 默认实现 |
| **dbops-collector** | `collector_client/db_connectors/*.py` | UPDATE — 按需 override `collect_all_facts()` |
| **dbops** | `backend/app/services/check_item_builder_registry.py` | UPDATE — 检查项收敛 |
| **dbops** | `backend/app/services/batch_collector_service.py` | UPDATE — callback 阶段补标记 skipped + AssetReport |
| **dbops** | `backend/app/services/collector_service.py` | UPDATE — callback 适配合并后 check_code |
| **dbops** | `backend/app/services/fact_snapshot_service.py` | UPDATE — FACT_CHECK_CODES |
| **dbops** | `backend/app/services/drift_detection_service.py` | UPDATE — 新增字段映射白名单 + `build_cluster_type_hint()` 报告辅助函数（不走通用 proposal） |
| **dbops** | `backend/app/services/asset_proposal_service.py` | UPDATE — `batch_action()` + IP 增强 |
| **dbops** | `backend/app/schemas/collector.py` | UPDATE — ProposalResponse 加 ip_address/entity_name |
| **dbops** | `backend/app/api/collector.py` | UPDATE — 批量 proposal + asset-report 端点 |
| **dbops** | `backend/db/dbops_check_code_convergence.sql` | **CREATE** — Seed 数据迁移 |
| **dbops** | `frontend/src/components/ops/ProposalPanel.vue` | **CREATE** — 独立变更建议组件 |
| **dbops** | `frontend/src/components/ops/VerifyItemDetail.vue` | **CREATE** — 执行项详情组件 |
| **dbops** | `frontend/src/components/ops/AssetVerifyReport.vue` | **CREATE** — 资产维度校验报告 |
| **dbops** | `frontend/src/views/ops/BatchVerify.vue` | UPDATE — 引用新组件 |
| **dbops** | `frontend/src/api/assets.ts` | UPDATE — 新 API |
| **dbops** | `frontend/src/types/api.ts` | UPDATE — 新类型 |
| **dbops** | `backend/tests/test_check_item_builder_registry.py` | UPDATE |
| **dbops** | `backend/tests/test_batch_collector_service.py` | UPDATE |

---

## 十四、实施顺序

```
Phase 1 (兼容窗口 — 仅 Playbook)
  1a. Playbook: 兼容新旧 check_code + 两阶段门控 + failed_when + raw_result + is_formal_port
  1b. Push playbook → AWX Project sync
  **不要部署新版 collector_client**（旧后端仍下发 DB_VERSION/DB_ROLE_FACT_COLLECTION，collect_all_facts() 会导致重复采集）

Phase 2 (切换 — 同批部署)

  **上线前检查**：
  ```sql
  -- 确认无运行中任务
  SELECT id, batch_code, status, created_at
  FROM dbops.collector_batch_run
  WHERE status IN ('pending', 'dispatching', 'running');
  -- 如有结果，先等待完成或 cancel 后再执行 Phase 2
  ```
  确认 AWX 中无正在运行的旧版 collector job。

  2a. DB Seed SQL 执行（先备份）
  2b. collector_client: collect_all_facts() 部署 + EE 镜像更新
  2c. DBOPS 后端: Registry + Builder + callback + Proposal + AssetReport
  2d. DBOPS 前端: ProposalPanel + VerifyItemDetail + AssetVerifyReport
  2e. verify.sh + AWX 端到端验证

Phase 3 (清理，观察 1-2 周后)
  3a. Playbook: 删除旧 check_code 路由
  3b. collector_client: 删除旧 check_code 分支
  3c. 可选: DB 旧行清理
```

---

## 十五、最终实施边界

1. **不在 AWX 内动态切换 DB fact 采集端口**。候选端口可达只生成 proposal，不直接采集。
2. **只有 `DbInstance.port` 正式端口 reachable=true 时才执行 DB_BASIC_FACT_COLLECTION**。
3. **PORT_CANDIDATE_CONFLICT 必须由人工选择 `selected_value` 后才能 apply**。
4. **CLUSTER_TYPE_MISMATCH 本次只作为 AssetVerifyReport 提示**，不生成可 apply proposal。
5. **`inspection_item` 禁用旧 `CONNECTIVITY_PORT_REACHABLE`**，避免与 `CONNECTIVITY_DB_PORT` 重复。
6. **字段更新严格受 `APPLYABLE_FIELDS` 白名单控制**。
7. **`collector_run_item.status` 已确认支持 `skipped`**（CHECK 约束验证通过），无需 DDL。
8. **三阶段兼容部署**：先 Playbook 兼容新旧 → 再后端切换 → 最后清理旧路由。

---

## 十六、Acceptance

- [ ] Playbook 兼容新旧 check_code，`ansible-playbook --syntax-check` 通过
- [ ] AWX 内两阶段门控生效：正式端口不通的资产不进入 DB/OS fact role
- [ ] `db_fact_collect` 有 `failed_when: false`，失败不中断 Job，callback 仍含单项失败详情
- [ ] `collect_all_facts()` 统一接口，保留旧方法
- [ ] Seed SQL 执行后 collector_check_definition + inspection_item 正确（DO UPDATE 幂等）
- [ ] DB_PORT_REACHABILITY 支持正式端口 + 候选端口探测
- [ ] 正式端口不通但单候选端口可达时，生成 PORT_DRIFT_SUSPECTED proposal，不直接采集
- [ ] 多候选端口可达时，生成 PORT_CANDIDATE_CONFLICT proposal，不直接 apply
- [ ] PORT_CANDIDATE_CONFLICT apply 时必须人工选择单个端口（`selected_value`）
- [ ] raw_result 标准化：duration_ms、rc、stdout、stderr、error_code
- [ ] AssetVerifyReport API 返回按资产聚合的数据
- [ ] ProposalPanel 显示 IP、实体类型、实体名称，支持批量操作
- [ ] batch-action API 支持部分成功/失败返回
- [ ] cluster_type 本次仅报告提示展示（AssetVerifyReport），不自动生成可 apply 变更
- [ ] CLUSTER_TYPE_MISMATCH inspection item 挂 `db_instance`，rule_config 标注派生校验 cluster
- [ ] 字段更新白名单生效，非白名单字段不可 apply
- [ ] Callback Schema 保留 is_formal_port，后端可按实例聚合端口探测结果
- [ ] DB facts 未出现在 callback 时，skip reason 按端口聚合结果区分（PORT_DRIFT_SUSPECTED / PORT_CANDIDATE_CONFLICT / CONNECTIVITY_GATE_FAILED / OS_FACT_UNSUPPORTED_WINDOWS）
- [ ] collect_all_facts() 全部子采集失败时返回 failed，不产生空 facts 假阳性
- [ ] PORT_CANDIDATE_CONFLICT selected_value 校验：整数、1-65535、必须在 candidates 中
- [ ] Phase 1 不提前部署 collect_all_facts()，避免旧后端下发 3 个 DB fact check_code 时重复全量采集
- [ ] Windows 资产在 Builder 阶段即标记 OS_BASIC_FACT_COLLECTION 为 skipped，不进入 os_fact_collect
- [ ] is_formal_port 持久化以 raw_result 为准（方案 A），不新增 DB 列
- [ ] DB_ROLE_CHANGED 已禁用，由 DB_FACT_DRIFT_DETECTED 统一覆盖 node_role 漂移
- [ ] collect_all_facts() 使用 getattr 兼容未实现旧方法的 connector
- [ ] stdout/stderr 入库前脱敏并截断（4000 字符上限）
- [ ] Phase 1 兼容旧后端：旧 `DB_PORT_REACHABILITY` 在缺少 `is_formal_port` 时默认视为正式端口，旧 DB facts 不会被误跳过
- [ ] verify.sh 全部通过
- [ ] AWX 端到端回调正常，至少完成 1 次完整 batch run

---

# Follow-up A — 检查项前端收敛到 DB 单源（2026-06-17）

## 背景

`frontend/src/views/ops/BatchVerify.vue:475-483` 硬编码 7 个 check_code 列表，但 DB
`dbops.collector_check_definition` 才是单源真值（8 行，4 启用 + 4 禁用）。Phase 2a
改 DB 后未同步前端，导致：

- 缺 `OS_PORT_REACHABILITY`（plan v2 新增，DB 启用）→ 操作员看不到
- 多 4 个 disabled 码（`SSH_PORT_REACHABILITY` / `PORT_CANDIDATE_REACHABILITY` /
  `DB_VERSION_FACT_COLLECTION` / `DB_ROLE_FACT_COLLECTION`）→ 操作员可勾选但后端 400
  reject
- 违反 CLAUDE.md 规则 #13："前端不硬编码状态颜色、状态文案、枚举值"

**收敛目标** — 仿 `GET /collector/port-profiles` 模式新增 `GET /collector/check-codes`，
前端由 DB 取数据，`target_scope` 切换走客户端 filter（O(n) 小列表不值得 round-trip）。

**为什么之前没收敛** — plan v2 §13-A 显式列出 `check_item_builder_registry.py`
待改但未执行；后端 `_check_definition_defaults` 硬编码 dict +
`check_item_builder_registry` 都不含 `OS_PORT_REACHABILITY`（独立
bug，留后续）。本次只解决前端数据驱动，不碰后端 builder 路由（避免扩大范围）。

---

## A.1 Backend（4 文件）

### A.1.1 `backend/app/schemas/collector.py` — append after `PortProfileResponse` (line 273)

```python
class CollectorCheckDefinitionResponse(BaseModel):
    id: int
    check_code: str
    check_name: str
    target_scope: Literal["server", "db_instance"]
    task_type: Literal["PORT_CHECK", "DB_PORT_DISCOVERY", "OS_DISCOVERY", "DB_SQL_COLLECT"]
    db_type_code: Optional[str] = None
    os_type_code: Optional[str] = None
    awx_role: Optional[str] = None
    default_timeout_seconds: int
    enabled: bool  # 注意：DB 列名是 enabled（不是 is_enabled，与 port-profiles 不对称，按 DB 实际列名）
    config: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

Literal 与 `CollectorCheckDefinition.__table_args__` CheckConstraint
字符串保持手同步（与 `PortProfileResponse` 同模式）。

### A.1.2 `backend/app/services/collector_check_definition_service.py` (NEW)

1:1 镜像 `port_profile_service.py:11-55`：

- `_to_dict(row) -> dict` — 复制 schema 字段
- `list_definitions(db, *, target_scope=None, task_type=None, is_enabled=None) -> list[dict]`
  - query 顺序：`enabled.desc(), check_code.asc()`（无 priority 列）
  - 三个 filter 均为精确匹配（`target_scope` / `task_type` 在 model 中 nullable=False，无 `or_(is_(None), ==)` 需求）

### A.1.3 `backend/app/api/collector.py` — append after `list_port_profiles` (line 187)

```python
@router.get("/collector/check-codes", response_model=List[CollectorCheckDefinitionResponse])
async def list_check_codes(
    target_scope: Optional[str] = Query(default=None),
    task_type: Optional[str] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CollectorCheckDefinitionService.list_definitions(
        db, target_scope=target_scope, task_type=task_type, is_enabled=is_enabled,
    )
```

加 1 行 import：`from app.services.collector_check_definition_service import CollectorCheckDefinitionService`；schema 已在原 import 块。

### A.1.4 `backend/tests/test_collector_check_codes_endpoint.py` (NEW)

参照 `test_collector_tasks_p0_4_5_6.py` 风格，1 个集成测试：
- seed 2 行（1 server enabled + 1 db_instance disabled）
- `GET /v1/collector/check-codes?target_scope=server&is_enabled=true`
- assert 仅 1 行 + 字段匹配 `CollectorCheckDefinitionResponse`

---

## A.2 Frontend（3 文件）

### A.2.1 `frontend/src/types/api.ts` — append after `PortProfileRow`

```typescript
export interface CollectorCheckDefinitionRow {
  id: number
  check_code: string
  check_name: string
  target_scope: 'server' | 'db_instance'
  task_type: 'PORT_CHECK' | 'DB_PORT_DISCOVERY' | 'OS_DISCOVERY' | 'DB_SQL_COLLECT'
  db_type_code?: string | null
  os_type_code?: string | null
  awx_role?: string | null
  default_timeout_seconds: number
  enabled: boolean
  config?: Record<string, any>
  description?: string | null
}
```

### A.2.2 `frontend/src/api/assets.ts` — append after `listPortProfiles` (line 118)

```typescript
listCheckCodes: (
  params?: { target_scope?: string; task_type?: string; is_enabled?: boolean },
  options?: { suppressErrorToast?: boolean },
): Promise<CollectorCheckDefinitionRow[]> =>
  request.get('/v1/collector/check-codes', {
    params,
    suppressErrorToast: options?.suppressErrorToast,
  }),
```

加 `suppressErrorToast` 选项（与 `listPortProfiles` 不一样）— 表单 mount
失败时静默降级到 `[]`，避免每次切 radio 触发 toast。

### A.2.3 `frontend/src/views/ops/BatchVerify.vue` — 三处编辑

a) 删除 475-483 行硬编码 array

b) 在 `<script setup>` 加 state + fetch + computed（位置：onMounted 附近）

```typescript
const checkDefinitions = ref<CollectorCheckDefinitionRow[]>([])
const checkCodesLoading = ref(false)

async function fetchCheckCodes() {
  checkCodesLoading.value = true
  try {
    // 一次取所有 enabled，由 computed 客户端 filter（O(n) 小列表不值得 refetch）
    checkDefinitions.value = await assetsApi.listCheckCodes(
      { is_enabled: true },
      { suppressErrorToast: true },
    )
  } finally {
    checkCodesLoading.value = false
  }
}

// 保留模板的 {value, label} 形状，line 81 / 303 的 v-for 不动
const checkCodeOptions = computed(() =>
  checkDefinitions.value
    .filter(d => d.target_scope === form.target_scope)
    .map(d => ({ value: d.check_code, label: d.check_name })),
)
```

c) 挂载 + watch target_scope

```typescript
onMounted(() => {
  void fetchCheckCodes()
  // ... 已有 onMounted 内容并入或新增一个 onMounted
})

// target_scope 切换时清空旧选择（避免残留无效 check_code）
watch(() => form.target_scope, () => {
  form.check_codes = []
})
```

---

## A.3 范围控制

**不在本次改**：
- `backend/app/services/collector_service.py:250-278, 316-317`（`if check_code == "..."` 反模式分支）
- `backend/app/services/check_item_builder_registry.py:732-738`（`OS_PORT_REACHABILITY` 未注册，独立 bug）
- `backend/app/services/collector_service.py:136-189`（`_check_definition_defaults` fallback dict）
- `frontend/src/components/ops/ProposalPanel.vue`（`PORT_CANDIDATE_CONFLICT` 字符串硬编码，不同 concern：proposal_type 而非 check_code）
- `frontend/src/views/InstanceDetail.vue:460, 475-482, 712-713, 772`（同模式第 2 消费者，含 description/disabled overlay 语义；下次 follow-up 用同一 `assetsApi.listCheckCodes()` + computed 复刻即可，不引入新 pattern）

**理由** — Plan v2 §13-A 列出 builder registry 修改但未执行，扩到这块会让 diff 难审 +
需重测 AWX e2e。本次只收 1 个前端消费者，留出明确定义的 follow-up。

---

## A.4 实施顺序

1. schema → service → router（先 backend）
2. 重启后端，curl `GET /v1/collector/check-codes` 验证返回 8 行
3. 加后端测试 + pytest
4. 前端 type + API fn
5. BatchVerify.vue 三处编辑
6. `npm run build` (vue-tsc) 类型校验
7. `bash scripts/ai/verify.sh` 全套
8. live API 复测 + BatchVerify UI 加载（toggle target_scope 看到 1 个 server row / 3 个 db_instance row）

---

## A.5 关键引用文件

| 用途 | 文件 |
|---|---|
| 1:1 模式锚 | `backend/app/services/port_profile_service.py:11-55` |
| 1:1 模式锚 | `backend/app/api/collector.py:172-187` |
| 1:1 模式锚 | `backend/app/schemas/collector.py:257-272` |
| 1:1 模式锚 | `frontend/src/api/assets.ts:115-118` |
| DB 模型 | `backend/app/models/dbops_assets.py:508-535` |
| 待改主文件 | `frontend/src/views/ops/BatchVerify.vue:475-483` |
| 参考测试 | `backend/app/tests/test_collector_tasks_p0_4_5_6.py` |

---

## A.6 验证 (Verification)

```bash
# 1. 类型 + 145 测试全绿
bash scripts/ai/verify.sh

# 2. live API：3 个 filter 组合
TOKEN=$(curl -s -X POST http://localhost:60801/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 全量 enabled
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://localhost:60801/api/v1/collector/check-codes?is_enabled=true' \
  | python3 -c "import sys,json; rows=json.load(sys.stdin); print(f'{len(rows)} enabled'); [print(f'  {r[\"target_scope\"]:12} {r[\"check_code\"]}') for r in rows]"
# 预期 4 行：DB_PORT_REACHABILITY / DB_BASIC_FACT_COLLECTION / OS_BASIC_FACT_COLLECTION (db_instance)
#        + OS_PORT_REACHABILITY (server)

# server 过滤
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://localhost:60801/api/v1/collector/check-codes?target_scope=server&is_enabled=true' \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)), 'rows')"
# 预期 1 行（OS_PORT_REACHABILITY）

# 3. BatchVerify UI
# 浏览器打开 http://localhost:61088/ops/batch-verify
# - 默认 db_instance scope：勾选列表里看到 DB_PORT_REACHABILITY / DB_BASIC_FACT_COLLECTION / OS_BASIC_FACT_COLLECTION（没有 4 个 disabled 码）
# - 切到 server scope：只看到 OS_PORT_REACHABILITY

# 4. OS_PORT_REACHABILITY 不再 400
# 用 admin token 触发一次 server scope + OS_PORT_REACHABILITY 的 batch run
# （此为扩展验证，可选；如失败属于 builder registry 独立
# bug，按"不在本次改"记录为 follow-up）
```

---

## A.7 风险

| 风险 | 缓解 |
|---|---|
| 移除硬编码后 4 个 disabled 码从 UI 消失，操作员可能"以为还能用" | DB 已是 disabled，本次只暴露 DB 真值；后端校验仍兜底（如有前端 bypass） |
| API down 时表单 mount 拿不到数据，下拉空 | `suppressErrorToast: true` + 空数组不报错；可视化为"无选项"提示 |
| `enabled` vs `is_enabled` 命名不对称（port-profiles 用 `is_enabled`） | 跟随 DB 列实际名 `enabled`；PR description 标注 |
| 同一 `enabled` 字段下 Pydantic v1 vs v2 行为差异 | 已有 Pydantic v2.10 (per earlier verify.sh 警告)，用 `enabled: bool` 直声明即可 |
| `watch form.target_scope` 清空选择可能丢失用户已选 | 当前 line 662 已有 `form.check_codes = []` 行为，逻辑等价；如有保留选择需求可后续追加 |

