# 导入流程说明

> 本说明梳理当前实现中「导入新建项目」「导入当前项目」「智能导入」三条路径的完整调用链与
> 重复/冲突处理语义。设计细节见 `docs/design/import-export-redesign.md` 与
> `docs/design/smart-import-progress.md`。

## 概览

三条导入路径最终都汇聚到同一个后端方法 `ProjectService.apply_full_import()`，由
`target`（新建/已有项目）与 `reuse_id`（基础/智能）两个参数控制行为分支。

| 维度 | 导入新建项目 | 导入当前项目 | 智能导入 |
|------|-------------|-------------|---------|
| 入口组件 | `ImportPreviewDialog` | `ImportPreviewDialog` | `SmartImportDialog` |
| 预览面板 | `ImportPreviewPanel` | `ImportPreviewPanel` | `ImportPreviewPanel` |
| 文件来源 | 用户选 .md 文件 | 用户选 .md 文件 | 任意文本文件 → LLM 解析 |
| 解析方式 | `Importer.parse()` (YAML frontmatter) | 同左 | `LlmClient.chat_structured()` → `from_llm_intermediate()` |
| target | `{name}` | `{project_id}` | `{name}`（仅新建） |
| reuse_id | `true` | `true` | `false` |
| ID 策略 | 复用原始 ID，冲突映射 | 同左 | 全量新建 DB id |
| 模块合并 | 新项目无已有 → 全建 | 同名复用 DB id | 新项目 → 全建 |
| upsert | 新项目 → 全 INSERT | 同 `(feature,date)` → UPDATE | 新项目 → 全 INSERT |
| 导入前备份 | ✅ trigger=`import` | ✅ trigger=`import` | ✅ trigger=`smart_import` |
| 后端统一路径 | `apply_full_import()` | `apply_full_import()` | `apply_full_import()` |

## 一、导入新建项目（基础导入，mode=`'new'`）

```
用户点击侧边栏「导入新建项目」按钮
        │
        ▼
ProjectSidebar.onImportAsNew()
        │
        ▼
store.parseImport()  ──►  api.parseMdImport()  ──►  bridge().parse_md_import()
        │                                                    │
        │                                          后端 WebApi.parse_md_import()
        │                                           ├─ _open_md_file() 弹原生文件框
        │                                           │   （.md/.txt/所有文件）
        │                                           ├─ 用户选文件 → 读文本(UTF-8)
        │                                           ├─ Importer.parse(text)
        │                                           │   ├─ 提取 YAML frontmatter
        │                                           │   ├─ 校验 format_version ∈ {1}
        │                                           │   └─ 构建 ParsedProject
        │                                           └─ 返回 {parsed, filename}
        │                                                    │
        │                                          用户取消 → 返回 null → 流程终止
        ▼
ImportPreviewDialogRef.open(parsed, 'new', filename)
        │
        ▼
ImportPreviewDialog（弹窗外壳）
  ├─ structuredClone(parsed) 深拷贝可编辑副本
  ├─ mode='new' → target={name:''}（项目名可编辑）
  ├─ reuseId=true（基础导入，ID 复用/冲突映射）
  └─ 内嵌 ImportPreviewPanel（共享子组件）
        │
        ▼  用户在预览面板中：
        │   ├─ 编辑项目名（必填）
        │   ├─ 选择默认状态（覆盖 done 项）
        │   ├─ 左树：按模块折叠，勾选/取消迭代和 bug
        │   ├─ 右详情：编辑状态/时限/查看子需求
        │   └─ 点击「新建并导入」
        ▼
ImportPreviewPanel.onApply()
  ├─ 校验：至少选一项 + 项目名非空
  ├─ parsed.reuse_id = true
  ├─ target = {name: 用户输入的项目名}
  └─ store.applyFullImportTo(target, parsed)
        │
        ▼
api.applyFullImport(target, parsed)  ──►  bridge().apply_full_import()
        │                                                    │
        │                                          后端 WebApi.apply_full_import()
        │                                           ├─ ParsedProject.model_validate(parsed)
        │                                           ├─ ProjectTarget(name=用户输入)
        │                                           ├─ 组装 backup_meta
        │                                           │   (trigger='import', source=项目名,
        │                                           │    retention_count=设置值)
        │                                           └─ ProjectService.apply_full_import()
        │                                                │
        │                                    ┌───────────┴───────────┐
        │                                    │  0. 导入前备份         │
        │                                    │  DbService.backup_for_import()
        │                                    │  (含用户数据才备份,    │
        │                                    │   命名 preimport.时间.bak)
        │                                    ├───────────────────────┤
        │                                    │  1. 新建项目行         │
        │                                    │  INSERT INTO projects  │
        │                                    ├───────────────────────┤
        │                                    │  2. 模块按名合并       │
        │                                    │  _build_module_id_map()│
        │                                    │  同名→复用DB id;      │
        │                                    │  否则→用导入id建       │
        │                                    │  (冲突→映射新id)       │
        │                                    ├───────────────────────┤
        │                                    │  3. ID冲突映射         │
        │                                    │  _build_entity_id_map()│
        │                                    │  扫全库占用ID求交;     │
        │                                    │  冲突→生成新id建map    │
        │                                    │  干净库→id_map恒等     │
        │                                    ├───────────────────────┤
        │                                    │  4. 写入迭代+子需求    │
        │                                    │  _write_imported_iterations()
        │                                    │  upsert: (feature,date)│
        │                                    │  子需求整体替换;       │
        │                                    │  deferred→deadline=NULL│
        │                                    ├───────────────────────┤
        │                                    │  5. 写入bug(如有)      │
        │                                    │  _write_imported_bugs()│
        │                                    │  upsert: (date,content)│
        │                                    │  linked经id_map解析    │
        │                                    ├───────────────────────┤
        │                                    │  全程单事务,失败回滚   │
        │                                    └───────────────────────┘
        │                                                    │
        │                                          返回完整 Project
        ▼
store.applyFullImportTo() 后续
  ├─ projectsStore.loadSummaries()  刷新侧边栏
  ├─ projectsStore.select(project.id)  选中新项目
  └─ ElMessage.success('已新建项目「…」并导入 N 条迭代…')
        │
        ▼
emit('apply-success') → ImportPreviewDialog 关闭弹窗
```

## 二、导入当前项目（基础导入，mode=`'current'`）

流程与「导入新建项目」几乎完全相同，差异点：

| 环节 | 导入新建项目 | 导入当前项目 |
|------|-------------|-------------|
| 入口 | `onImportAsNew()` | `onImportCurrent()`（需先选中项目） |
| 前置校验 | 无 | `activeProjectId` 为空时提示「请先选择项目」 |
| target | `{name: ''}`（项目名可编辑） | `{project_id: store.project.id}` |
| reuseId | `true` | `true` |
| 项目名输入 | 显示（必填） | 隐藏（`isTargetNew=false`） |
| 后端路径 | `apply_full_import` 内新建项目行 | `apply_full_import` 内 `_assert_project_exists` |
| 模块合并 | 新项目无已有模块，全部新建 | 目标项目已有同名模块 → 复用 DB id |
| upsert 语义 | 新项目无已有迭代，全部 INSERT | 同 `(feature,date)` 迭代 → UPDATE + 子需求整体替换 |
| 成功后 | `loadSummaries` + `select(新id)` | 就地刷新 `project.value = p` + `modules` |
| 提示文案 | 「已新建项目…并导入…」 | 「已导入 N 条迭代…」 |
| 按钮文案 | 「新建并导入」 | 「应用导入」 |

核心后端路径 `ProjectService.apply_full_import()` 完全共用，由 `target.project_id` 是否为
None 决定走新建还是已有项目分支。

## 三、智能导入（mode=`'smart'`，仅新建项目）

独立 `SmartImportDialog` 三步弹窗：

```
用户点击侧边栏「智能导入」按钮（需 LLM 已配置，否则灰显）
        │
        ▼
ProjectSidebar.onSmartImport() → SmartImportDialogRef.open()
        │
        ▼
SmartImportDialog 三步状态机：

═══ ① 选择文件 ═══
  ├─ 说明文案 + [选择文件] 按钮
  └─ 点击 → store.pickSmartImportFile()
              └─ api.pickSmartImportFile()
                  └─ bridge().pick_smart_import_file()
                      │
              后端 WebApi.pick_smart_import_file()
              ├─ 校验 LLM 配置（enabled + base_url/api_key/model 齐全）
              ├─ 弹原生文件框（.txt/.md/所有文件）
              ├─ 读文本（errors="replace"，二进制尽力识别）
              ├─ 校验长度 ≤ 100,000 字符
              └─ 返回 {filename, text, char_count}
                      │
              用户取消 → 返回 null → 留在①
        │
        ▼ resolve → step='analyzing'

═══ ② AI 分析 ═══
  ├─ Lottie 转圈动画 + 伪进度条 + 计时器
  ├─ store.runSmartImport(text, filename)
  │   └─ api.runSmartImport(text, filename)
  │       └─ bridge().run_smart_import(text, filename)
  │           │
  │   后端 WebApi.run_smart_import()
  │   ├─ 读已落盘 LLM 配置
  │   ├─ 构造 system+user prompt
  │   ├─ LlmClient.chat_structured() → tool use 强制结构化输出
  │   │   └─ httpx 同步 POST {base_url}/chat/completions
  │   │       Authorization: Bearer {api_key}，超时 llm_timeout 秒
  │   ├─ parse_llm_intermediate(tool_args)
  │   │   ├─ LlmParsedProject.model_validate(data)
  │   │   └─ from_llm_intermediate(llm)
  │   │       ├─ 模块/迭代/bug 生成 llm-mod- / llm-it- / llm-bug- 前缀 id
  │   │       ├─ bug linked 用 (feature,date) 查迭代
  │   │       └─ 返回 ParsedProject
  │   └─ 返回 {parsed, filename}
  │           │
  │   错误 → 留在② error 子态，显示 [重试]/[关闭]
  │   取消 → 软取消（置 cancelled，关弹窗，Promise 结果丢弃）
        │
        ▼ resolve → progress=100% → 150ms → step='preview'

═══ ③ 预览并应用 ═══
  └─ 内嵌 ImportPreviewPanel
      ├─ parsed 来自 LLM 解析结果
      ├─ target={name:''}（智能导入只新建项目）
      ├─ reuseId=false（全新建，不复用 ID）
      ├─ 项目名默认=文件名，可编辑
      └─ 点击「智能导入并新建」
          │
          ▼ onApply()
          ├─ parsed.reuse_id = false
          ├─ target = {name: 用户输入}
          └─ store.applyFullImportTo(target, parsed)
              └─ 后端 apply_full_import(reuse_id=False)
                  ├─ 全部实体生成新 DB id（不复用导入 id）
                  ├─ 其余流程同基础导入
                  └─ 返回 Project
                      │
          成功 → loadSummaries + select(新id)
          提示 → 「智能导入完成：已新建项目…」
          emit('apply-success') → 关闭弹窗
```

## 四、重复/冲突处理语义（导入当前项目）

「导入当前项目」对已有数据采用 **upsert（有则更新、无则新建）** + **整体替换** 语义，
去重键与替换范围如下：

| 实体 | 去重键 | 已存在时（UPDATE） | 新键值（INSERT） |
|------|--------|-------------------|------------------|
| 迭代 | `(project_id, feature, date)` | UPDATE content/status/completion_deadline；模块关联整体替换（删旧 `requirement_modules` 再插新）；**子需求整体替换**（先 `DELETE` 原子需求再按文件重建） | INSERT 新迭代 + 模块关联 + 子需求 |
| Bug | `(project_id, date, content)` | UPDATE level/status/linked_iteration_id；模块关联整体替换 | INSERT 新 bug |
| 模块 | `name`（项目内唯一） | 复用目标项目已有 DB id | 用导入 id 建（被占用则映射新 id） |
| 实体 ID | 全库主键占用 | 冲突 → 生成新 id 并建 `id_map{旧→新}`，重写全部引用字段 | 干净库 id_map 恒等，1:1 还原 |

关键点：

- **什么是「重复」**：迭代按「同一功能 + 同一迭代日期」判定；bug 按「同一天 + 完全相同
  content」判定。模块按「项目内同名」判定。
- **重复时的行为**：不是拒绝，而是**用导入文件覆盖**该条已存在记录——迭代的 content/状态/
  时限/模块被文件值覆盖，子需求被文件里的子需求**整体替换**（文件 = 该迭代的完整快照，
  原来手工维护的子需求会被覆盖掉）。
- **ID 冲突**：即使去重键不冲突，若导入文件的实体 ID（如 `it-1`）恰好被库里其他记录占用，
  会为该实体生成新 ID 并建映射表，把所有引用（子需求 iteration_id、bug linked、模块关联）
  一起重写，保证关联不悬空。
- **deferred 不变量**：导入的 deferred 迭代/子需求，`completion_deadline` 无论文件里是什么
  都强制置 NULL（后端写入单点）。
- **全程单事务**：任一写入失败整体回滚，不会出现半导入状态；成功前会先做整库导入前备份
  （`backups/`），可回滚。
- **模块合并**：导入到已有项目时，同名模块复用目标项目模块，不重复建模块；迭代的模块关联
  经 id_map 指向目标项目模块 id。

> 注意：以上「有则更新、子需求整体替换」是**导入当前项目**的现状行为。若希望改为「重复时
> 跳过/询问/合并」，需调整 `_write_imported_iterations` / `_write_imported_bugs` 的去重分支。

## 五、FAQ

### Q：导入当前项目时，与已有需求重复甚至冲突时目前是如何处理的？

A：现状是 **upsert（有则更新、无则新建）+ 整体替换**，不是拒绝、也不是跳过。核心在
`ProjectService._write_imported_iterations`（project_service.py:1092）和
`_write_imported_bugs`（project_service.py:1188）。具体分四类：

**1. 迭代重复 — 按 `(project_id, feature, date)` 判定**

- 命中（同一功能 + 同一迭代日期已存在）→ **UPDATE** 该记录：content / status /
  completion_deadline 被文件值覆盖，模块关联整体替换（`replace_requirement_modules` 删旧插
  新），并且**子需求整体替换**——先 `DELETE FROM requirement_subitems WHERE iteration_id=?`
  再按文件重建（project_service.py:1134-1137）。
- 未命中 → INSERT 新迭代 + 模块关联 + 子需求。

**2. Bug 重复 — 按 `(project_id, date, content)` 判定**

- 命中 → UPDATE level / status / linked_iteration_id，模块关联整体替换。
- 未命中 → INSERT。

**3. 模块重复 — 按项目内 `name` 合并**

- 目标项目已有同名模块 → 直接复用其 DB id（`_build_module_id_map`），不重复建模块；迭代
  的模块关联经 id_map 指向该 id。

**4. 实体 ID 冲突 — 全库主键占用判定**

- 即使去重键不冲突，若导入文件的 ID（如 `it-1`）已被库里其他记录占用，
  `_build_entity_id_map` 会为该实体生成新 ID 建 `id_map{旧→新}`，并重写全部引用字段
  （子需求 `iteration_id`、bug `linked_iteration_id`、模块关联 `module_id`），保证关联不悬
  空。

**几个关键语义**：

- **重复 = 覆盖，不是跳过**。导入文件被当作该迭代的「完整快照」——原来手工维护的子需求会
  被覆盖掉（这是设计文档 §6.4 明确写明的「子需求随迭代整体替换」）。
- **deferred 不变量**：deferred 项的 `completion_deadline` 无论文件里是什么都强制置 NULL。
- **全程单事务**：任一写入失败整体回滚，不产生半导入态；成功前会先做导入前备份
  （`backups/`），可回滚。

一句话总结：**导入当前项目时，同 `(feature,date)` 的旧迭代会被文件内容覆盖、子需求被整
体替换，不会报冲突、不会跳过、也无需手动确认去重**——去重键命中即覆盖。

> 若希望改为「重复时提示/跳过/合并」，需调整 `_write_imported_iterations` 和
> `_write_imported_bugs` 的命中分支。