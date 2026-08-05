<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { IPixelCheck, IPixelClose, IPixelFolder, IPixelSortVertical } from '@/constants/icons'

import { useSettingsStore } from '@/stores/settings'
import { testLlm, whenReady } from '@/api'
import { moveKey, normalizeOrder } from '@/utils/settingsOrder'
import type { ProjectListDateMode, ViewMode } from '@/types/settings'

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'cancel'): void
}>()

const settingsStore = useSettingsStore()
const { storageInfo, loading, defaultViewMode, settingsOrder, importBackups } =
  storeToRefs(settingsStore)

// 分组注册表（未来追加分组只需在此扩展，合法 key 由此决定）
const GROUPS = [
  { key: 'storage', label: '存储位置' },
  { key: 'display', label: '显示设置' },
  { key: 'reminder', label: '提醒设置' },
  { key: 'subitem', label: '子需求进度' },
  { key: 'llm', label: '智能导入' },
  { key: 'backup', label: '数据备份与回滚' },
] as const
// 全部已注册分组的 key（规范化顺序与拖拽重排的合法集合；新增分组自动纳入）
const GROUP_KEYS = GROUPS.map((g) => g.key)

// 项目列表「最新」日期口径下拉选项：value/label/desc，desc 随选中项联动显示
const DATE_MODE_OPTIONS: { value: ProjectListDateMode; label: string; desc: string }[] = [
  {
    value: 'latest_any',
    label: '最新需求日期',
    desc: '取项目内所有需求日期的最新值，不限状态。新增任意需求（含待办/进行中）都会刷新该日期。',
  },
  {
    value: 'latest_done',
    label: '最新已完成日期',
    desc: '只统计「已完成/等待对接」状态的需求日期，反映项目最近一次完成或等待对接的时间点。',
  },
  {
    value: 'latest_activity',
    label: '最近操作时间',
    desc: '取项目最近一次新增/编辑/删除需求（或重命名）的时间。任何改动都会把该项目顶到最新。',
  },
]

// 拖拽编辑态：editingOrder=true 时用 draftOrder 渲染并可拖拽；false 时用已落盘 settingsOrder
const editingOrder = ref(false)
const draftOrder = ref<string[]>([...settingsOrder.value])
const dragKey = ref<string | null>(null)
const dragOverKey = ref<string | null>(null)

// 草稿统一在 onMounted 中从「已加载的后端设置」初始化，避免组件 setup 早于
// App.vue 的 loadSettings() 完成时把草稿锁定为默认值（导致展示与配置文件不一致、
// 保存后把默认值回写覆盖真值）。先用 null 占位，模板在初始化完成前不渲染表单。
const draftThreshold = ref<number | null>(null)
const draftUrgentThreshold = ref<number | null>(null)
const draftReminderColor = ref<string | null>(null)
const draftUrgentColor = ref<string | null>(null)
const draftShowNoDeadline = ref<boolean | null>(null)
// 子需求进度草稿
const draftShowSubitemProgress = ref<boolean | null>(null)
// LLM 智能导入配置草稿
const draftLlmEnabled = ref<boolean | null>(null)
const draftLlmBaseUrl = ref<string | null>(null)
const draftLlmApiKey = ref<string | null>(null)
const draftLlmModel = ref<string | null>(null)
const draftLlmTimeout = ref<number | null>(null)
const testingLlm = ref(false)
// 测试连接结果（常驻展示，避免 toast 一闪而过用户看不到）。null=未测试过。
type LlmTestResult = {
  status: 'success' | 'error'
  model?: string
  reply?: string
  error?: string
  at: number
}
const llmTestResult = ref<LlmTestResult | null>(null)
// 导入备份保留数量草稿
const draftBackupRetention = ref<number | null>(null)

// 项目列表日期口径草稿（保存时一并落盘）
const draftProjectListDateMode = ref<ProjectListDateMode | null>(null)

// 紧急阈值必定 ≤ 提醒阈值：当提醒阈值被下调到低于当前紧急阈值时，
// 自动把紧急阈值对齐到提醒阈值（后端校验器同样拒绝前者 > 后者）。
watch(draftThreshold, (t) => {
  if (t !== null && draftUrgentThreshold.value !== null && draftUrgentThreshold.value > t) {
    draftUrgentThreshold.value = t
  }
})

// 当前选中口径的说明文字（随下拉选项联动）
const dateModeDesc = computed(
  () => DATE_MODE_OPTIONS.find((o) => o.value === draftProjectListDateMode.value)?.desc ?? '',
)

// 实际用于渲染的顺序：编辑态用草稿，非编辑态用已落盘值
const activeOrder = computed(() => (editingOrder.value ? draftOrder.value : settingsOrder.value))

// 按 activeOrder 排序的分组（规范化：过滤未知 key、补齐缺失 key）
const sortedGroups = computed(() =>
  normalizeOrder(activeOrder.value, GROUP_KEYS).map((k) => GROUPS.find((g) => g.key === k)!),
)

const activeKey = ref<string>(GROUPS[0].key)
const scrollRef = useTemplateRef<HTMLDivElement>('scrollRef')

// 草稿是否已从后端初始化完成（false 时表单不渲染，避免 null 默认值闪现）
const draftsReady = ref(false)

onMounted(async () => {
  // 视图用 v-show 常驻、应用挂载即触发本钩子；须先等待桥接就绪再调后端，
  // 否则与 App.vue 的 whenReady 并发执行时桥接尚未注入会抛 ApiError。
  await whenReady()
  await settingsStore.loadStorageInfo()
  // 主动从配置文件加载最新设置，并用其初始化草稿——保证展示值与配置文件一致，
  // 不受 App.vue 启动时 loadSettings() 的时序影响（避免草稿被默认值锁定）。
  // 读取失败时仍用 store 当前值填充草稿并渲染表单（至少可编辑），同时提示。
  try {
    await settingsStore.loadSettings()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载设置失败，已使用当前缓存值')
  }
  draftThreshold.value = settingsStore.reminderThresholdDays
  draftUrgentThreshold.value = settingsStore.urgentThresholdDays
  draftReminderColor.value = settingsStore.reminderWarningColor
  draftUrgentColor.value = settingsStore.urgentWarningColor
  draftShowNoDeadline.value = settingsStore.showNoDeadlineInTodo
  draftShowSubitemProgress.value = settingsStore.showSubitemProgressInTree
  draftLlmEnabled.value = settingsStore.llmEnabled
  draftLlmBaseUrl.value = settingsStore.llmBaseUrl
  draftLlmApiKey.value = settingsStore.llmApiKey
  draftLlmModel.value = settingsStore.llmModel
  draftLlmTimeout.value = settingsStore.llmTimeout
  draftBackupRetention.value = settingsStore.backupRetentionCount
  draftProjectListDateMode.value = settingsStore.projectListDateMode
  draftsReady.value = true
  // 备份清单容错加载：失败不阻断设置页其余初始化
  void settingsStore.loadImportBackups().catch(() => {
    /* 忽略：备份 manifest 读取失败不阻断设置页 */
  })
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = 0
})

function scrollToGroup(key: string) {
  // 编辑态下禁用点击滚动（避免与拖拽冲突）
  if (editingOrder.value) return
  activeKey.value = key
  const el = document.getElementById(`setting-section-${key}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// scroll-spy：滚动时高亮当前可见分组（按排序后的分组）
function onScroll() {
  if (editingOrder.value) return
  const container = scrollRef.value
  if (!container) return
  const top = container.scrollTop
  let current: string = sortedGroups.value[0]?.key ?? GROUPS[0].key
  for (const g of sortedGroups.value) {
    const el = document.getElementById(`setting-section-${g.key}`)
    if (!el) continue
    if (el.offsetTop - 12 <= top) current = g.key
  }
  activeKey.value = current
}

// ── 分组顺序拖拽（HTML5 DnD）──
function onToggleOrder() {
  if (editingOrder.value) {
    // 完成：落盘 draftOrder
    finishOrderEdit()
    return
  }
  // 进入编辑态：用当前已落盘顺序初始化草稿，并规范化补齐全部分组 key。
  // 关键：旧版本持久化的 settings_order 可能只含部分 key，若不补齐，缺失的
  // 分组虽能渲染但 draftOrder.indexOf() 返回 -1，导致 onDrop 静默失败无法重排。
  draftOrder.value = normalizeOrder([...settingsOrder.value], GROUP_KEYS)
  editingOrder.value = true
}

async function finishOrderEdit() {
  try {
    await settingsStore.saveSettingsOrder(draftOrder.value)
    editingOrder.value = false
    dragKey.value = null
    dragOverKey.value = null
    ElMessage.success('分组顺序已保存')
  } catch (e) {
    // 落盘失败：回滚草稿为已落盘值，保留编辑态供重试
    draftOrder.value = [...settingsOrder.value]
    ElMessage.error(e instanceof Error ? e.message : '保存顺序失败')
  }
}

function onDragStart(key: string) {
  dragKey.value = key
}

function onDragOver(key: string, e: DragEvent) {
  if (!editingOrder.value || dragKey.value === null || dragKey.value === key) return
  e.preventDefault()
  dragOverKey.value = key
}

function onDrop(key: string, e: DragEvent) {
  if (!editingOrder.value || dragKey.value === null || dragKey.value === key) {
    dragKey.value = null
    dragOverKey.value = null
    return
  }
  e.preventDefault()
  // 经 normalizeOrder 保证 draftOrder 始终包含 GROUP_KEYS 全部 key，
  // 因此缺失 key 导致 onDrop 失败的场景不再出现。
  draftOrder.value = moveKey(draftOrder.value, dragKey.value, key)
  dragKey.value = null
  dragOverKey.value = null
}

function onDragEnd() {
  dragKey.value = null
  dragOverKey.value = null
}

// 更改存储位置：选目录 → 二次确认 → 迁移
async function onChangeStorage() {
  try {
    const picked = await settingsStore.pickFolder()
    if (!picked) return
    await ElMessageBox.confirm(
      `将在所选目录下创建 management-prd-storage 文件夹，并将当前所有数据迁移至该文件夹；旧位置的数据将被清理。\n\n所选目录：${picked}`,
      '更改存储位置',
      { type: 'warning', confirmButtonText: '确认迁移', cancelButtonText: '取消' },
    )
    await settingsStore.migrate(picked)
    ElMessage.success(`已迁移到：${settingsStore.storageInfo?.storage_dir ?? picked}`)
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e instanceof Error ? e.message : '迁移失败')
  }
}

// 测试 LLM 连接：用表单草稿（未保存也能测），成功后提示
async function onTestLlm() {
  // 表单渲染（draftsReady）后才可能触发；收窄类型并兜底
  const baseUrl = draftLlmBaseUrl.value ?? ''
  const model = draftLlmModel.value ?? ''
  if (!baseUrl.trim() || !model.trim()) {
    ElMessage.warning('请先填写 API 地址与模型名')
    return
  }
  testingLlm.value = true
  try {
    const result = await testLlm({
      base_url: baseUrl.trim(),
      api_key: (draftLlmApiKey.value ?? '').trim(),
      model: model.trim(),
      timeout: draftLlmTimeout.value ?? 120,
    })
    llmTestResult.value = {
      status: 'success',
      model: result.model,
      reply: result.reply,
      at: Date.now(),
    }
    ElMessage.success('连接成功')
  } catch (e) {
    llmTestResult.value = {
      status: 'error',
      error: e instanceof Error ? e.message : String(e),
      at: Date.now(),
    }
    ElMessage.error(e instanceof Error ? e.message : '连接失败')
  } finally {
    testingLlm.value = false
  }
}

// 保存：落盘「默认聚合方式」+「项目列表日期口径」+「提醒设置」+「LLM 配置」，
// 不回写主界面当前视图（二者解耦：默认值只在冷启动生效）
const saving = ref(false)
async function onSave() {
  if (saving.value) return
  saving.value = true
  try {
    const steps: Array<{ name: string; run: () => Promise<unknown> }> = [
      {
        name: '默认聚合方式',
        run: () =>
          settingsStore.saveDefaultViewMode(defaultViewMode.value as ViewMode),
      },
      {
        name: '项目列表日期口径',
        run: () => settingsStore.saveProjectListDateMode(draftProjectListDateMode.value!),
      },
      {
        name: '提醒设置',
        run: () =>
          settingsStore.saveReminderSettings(
            draftThreshold.value!,
            draftUrgentThreshold.value!,
            draftReminderColor.value!,
            draftUrgentColor.value!,
            draftShowNoDeadline.value!,
          ),
      },
      {
        name: '子需求进度',
        run: () => settingsStore.saveSubitemProgressInTree(draftShowSubitemProgress.value!),
      },
      {
        name: '智能导入配置',
        run: () =>
          settingsStore.saveLlmConfig({
            enabled: draftLlmEnabled.value!,
            baseUrl: draftLlmBaseUrl.value!.trim(),
            apiKey: draftLlmApiKey.value!.trim(),
            model: draftLlmModel.value!.trim(),
            timeout: draftLlmTimeout.value!,
          }),
      },
      {
        name: '备份保留数量',
        run: () => settingsStore.saveBackupRetentionCount(draftBackupRetention.value!),
      },
    ]
    for (const step of steps) {
      try {
        await step.run()
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        // 单步失败立即终止，明确告知用户是哪一项保存失败，已保存的前序项保留。
        ElMessage.error(`保存失败（${step.name}）：${msg}`)
        return
      }
    }
    ElMessage.success('设置已保存')
    emit('save')
  } finally {
    saving.value = false
  }
}

// ── 数据备份与回滚 ──

/** 格式化文件大小（字节 -> KB/MB）。 */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 格式化 ISO 时间为本地可读格式（2026-08-04 10:15:30）。 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** trigger 中文标签。 */
function triggerLabel(trigger: string): string {
  if (trigger === 'smart_import') return '智能导入'
  if (trigger === 'import') return '基础导入'
  return trigger
}

/** 备份描述：来源 + 目标项目名（如有）。 */
function backupDesc(entry: { source: string; project_name: string | null }): string {
  const parts: string[] = []
  if (entry.source) parts.push(`来源：${entry.source}`)
  if (entry.project_name) parts.push(`导入到：${entry.project_name}`)
  return parts.length > 0 ? parts.join(' · ') : '—'
}

async function onRestoreBackup(id: string, createdAt: string) {
  try {
    await ElMessageBox.confirm(
      `回滚将用此备份点（${formatTime(createdAt)}）覆盖当前数据库，该备份点之后的所有改动（含多次导入与手动编辑）将永久丢失，且不可撤销。\n\n确定要回滚吗？`,
      '回滚到导入前状态',
      {
        type: 'warning',
        confirmButtonText: '确认回滚',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
    await settingsStore.restoreImportBackupById(id)
    ElMessage.success('已回滚到所选备份点')
    // 保留策略可能裁剪了部分旧备份，清单已在 store 内刷新；额外再刷新一次确保最新
    await settingsStore.loadImportBackups()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e instanceof Error ? e.message : '回滚失败')
  }
}

async function onDeleteBackup(id: string, createdAt: string) {
  try {
    await ElMessageBox.confirm(
      `确定删除备份点（${formatTime(createdAt)}）吗？删除后无法再回滚到该时间点。`,
      '删除备份',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await settingsStore.deleteImportBackupById(id)
    ElMessage.success('备份已删除')
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <section class="settings-page">
    <header class="page-header">
      <h2 class="page-title">设置</h2>
    </header>

    <div v-if="draftsReady" class="settings-body">
      <!-- 左：分组标签 -->
      <div class="tabs">
        <div
          v-for="g in sortedGroups"
          :key="g.key"
          class="tab"
          :class="{
            active: activeKey === g.key,
            'tab-editing': editingOrder,
            'tab-dragging': dragKey === g.key,
            'tab-drag-over': dragOverKey === g.key && dragKey !== g.key,
          }"
          :draggable="editingOrder"
          @click="scrollToGroup(g.key)"
          @dragstart="onDragStart(g.key)"
          @dragover="onDragOver(g.key, $event)"
          @drop="onDrop(g.key, $event)"
          @dragend="onDragEnd"
        >
          <el-icon v-if="editingOrder" class="drag-handle"><IPixelSortVertical /></el-icon>
          <span class="tab-label">{{ g.label }}</span>
        </div>
        <div v-if="editingOrder" class="edit-hint">拖拽手柄调整顺序</div>
      </div>

      <!-- 右：单一可滚动容器 -->
      <div ref="scrollRef" class="scroll-area" @scroll.passive="onScroll">
        <section
          v-for="g in sortedGroups"
          :key="g.key"
          :id="`setting-section-${g.key}`"
          class="settings-card"
        >
          <!-- 存储位置 -->
          <template v-if="g.key === 'storage'">
            <h3 class="section-title">存储位置</h3>
            <p class="section-desc">
              程序的数据与配置文件默认存储在此目录。更改时需选择一个父目录，程序会在其下创建 management-prd-storage 专属文件夹并迁入所有数据，旧位置将被清理。
            </p>
            <el-form label-position="top">
              <el-form-item label="当前存储目录">
                <el-input
                  :model-value="storageInfo?.storage_dir ?? '加载中…'"
                  readonly
                  :icon="IPixelFolder"
                >
                  <template #append>
                    <el-button :loading="loading" @click="onChangeStorage">更改位置</el-button>
                  </template>
                </el-input>
              </el-form-item>
              <el-form-item v-if="storageInfo && !storageInfo.is_default">
                <el-tag type="warning" size="small">当前为自定义位置</el-tag>
              </el-form-item>
              <el-form-item v-else-if="storageInfo">
                <el-tag type="info" size="small">默认位置</el-tag>
              </el-form-item>
            </el-form>
          </template>

          <!-- 显示设置 -->
          <template v-else-if="g.key === 'display'">
            <h3 class="section-title">显示设置</h3>
            <p class="section-desc">
              设置需求列表的默认聚合方式（程序冷启动时生效）。此设置与主界面当前的聚合切换相互独立——主界面切换不会修改这里的默认值。
            </p>
            <el-form label-position="top">
              <el-form-item label="默认聚合方式">
                <el-radio-group v-model="defaultViewMode">
                  <el-radio value="date">按时间</el-radio>
                  <el-radio value="module">按模块</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="项目列表日期">
                <el-select
                  v-model="draftProjectListDateMode"
                  style="width: 240px"
                  placeholder="选择日期口径"
                >
                  <el-option
                    v-for="opt in DATE_MODE_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <span v-if="dateModeDesc" class="field-hint">{{ dateModeDesc }}</span>
              </el-form-item>
            </el-form>
          </template>

          <!-- 提醒设置 -->
          <template v-else-if="g.key === 'reminder'">
            <h3 class="section-title">提醒设置</h3>
            <p class="section-desc">
              启动时待办提醒抽屉中只显示「剩余天数 ≤ 提醒阈值」且未完成的需求；「已逾期」始终置顶，状态为「暂缓」的项目不受阈值影响并始终显示在「远期规划」组。紧急阈值内的聚合标题栏用深红色背景，提醒阈值内的用橙色背景。
            </p>
            <el-form label-position="top">
              <el-form-item label="提醒阈值（天）">
                <el-input-number
                  v-model="draftThreshold"
                  :min="0"
                  :max="365"
                  :step="1"
                  style="width: 160px"
                />
                <span class="field-hint">仅剩余天数 ≤ 该值（且未完成）进入待办；0 表示只显示已逾期</span>
              </el-form-item>
              <el-form-item label="紧急阈值（天）">
                <el-input-number
                  v-model="draftUrgentThreshold"
                  :min="0"
                  :max="draftThreshold"
                  :step="1"
                  style="width: 160px"
                />
                <span class="field-hint">剩余天数 ≤ 该值的聚合标题栏用紧急警告色；应 ≤ 提醒阈值</span>
              </el-form-item>
              <el-form-item label="提醒警告色">
                <el-color-picker v-model="draftReminderColor" :show-alpha="false" />
                <span class="field-hint">提醒阈值内聚合标题栏的背景色</span>
              </el-form-item>
              <el-form-item label="紧急警告色">
                <el-color-picker v-model="draftUrgentColor" :show-alpha="false" />
                <span class="field-hint">紧急阈值内聚合标题栏的背景色</span>
              </el-form-item>
              <el-form-item label="无时限需求">
                <el-switch v-model="draftShowNoDeadline" />
                <span class="field-hint">开启时，未设置完成时限的未完成需求常驻待办列表</span>
              </el-form-item>
            </el-form>
          </template>

          <!-- 子需求进度 -->
          <template v-else-if="g.key === 'subitem'">
            <h3 class="section-title">子需求进度</h3>
            <p class="section-desc">
              控制树形功能节点是否显示子需求完成进度（done/total）。关闭时仅在功能详情页显示子需求进度信息。
            </p>
            <el-form label-position="top">
              <el-form-item label="树形显示子需求进度">
                <el-switch v-model="draftShowSubitemProgress" />
                <span class="field-hint">开启时，树形功能节点追加 (完成数/总数) 进度显示</span>
              </el-form-item>
            </el-form>
          </template>

          <!-- 智能导入（LLM） -->
          <template v-else-if="g.key === 'llm'">
            <h3 class="section-title">智能导入</h3>
            <p class="section-desc">
              配置 LLM（大语言模型）接口后，可使用「智能导入」功能将任意需求文档/文本自动识别为结构化需求。支持 OpenAI 兼容接口（覆盖 DeepSeek / 通义 / Kimi / ChatGLM 等提供 api_key 的模型）。
            </p>
            <el-form label-position="top">
              <el-form-item label="启用智能导入">
                <el-switch v-model="draftLlmEnabled" />
                <span class="field-hint">开启后允许使用智能导入</span>
              </el-form-item>
              <el-form-item label="API 地址">
                <el-input
                  v-model="draftLlmBaseUrl"
                  placeholder="https://api.deepseek.com/v1"
                  :disabled="!draftLlmEnabled"
                />
                <span class="field-hint">OpenAI 兼容接口基础地址，通常以 /v1 结尾</span>
              </el-form-item>
              <el-form-item label="API 密钥">
                <el-input
                  v-model="draftLlmApiKey"
                  type="password"
                  show-password
                  placeholder="sk-..."
                  :disabled="!draftLlmEnabled"
                />
                <span class="field-hint">本地明文存储（后续可加密）</span>
              </el-form-item>
              <el-form-item label="模型名">
                <el-input
                  v-model="draftLlmModel"
                  placeholder="deepseek-chat"
                  :disabled="!draftLlmEnabled"
                />
                <span class="field-hint">如 deepseek-chat、qwen-plus、moonshot-v1-8k 等</span>
              </el-form-item>
              <el-form-item label="超时（秒）">
                <el-input-number
                  v-model="draftLlmTimeout"
                  :min="10"
                  :max="600"
                  :step="10"
                  :disabled="!draftLlmEnabled"
                  style="width: 160px"
                />
                <span class="field-hint">大文件/复杂文档可适当增大</span>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  plain
                  :loading="testingLlm"
                  :disabled="!draftLlmEnabled || !(draftLlmBaseUrl || '').trim() || !(draftLlmModel || '').trim()"
                  @click="onTestLlm"
                >
                  测试连接
                </el-button>
                <span class="field-hint">验证 API 地址、密钥与模型是否可用</span>
              </el-form-item>
              <el-form-item v-if="llmTestResult">
                <div
                  class="llm-test-result"
                  :class="llmTestResult.status === 'success' ? 'is-success' : 'is-error'"
                >
                  <el-icon v-if="llmTestResult.status === 'success'"><IPixelCheck /></el-icon>
                  <el-icon v-else><IPixelClose /></el-icon>
                  <div class="llm-test-text">
                    <template v-if="llmTestResult.status === 'success'">
                      <span class="llm-test-title">连接成功</span>
                      <span v-if="llmTestResult.model" class="llm-test-detail">
                        模型：{{ llmTestResult.model }}
                      </span>
                      <span v-if="llmTestResult.reply" class="llm-test-reply">
                        回复：{{ llmTestResult.reply }}
                      </span>
                    </template>
                    <template v-else>
                      <span class="llm-test-title">连接失败</span>
                      <span class="llm-test-detail">{{ llmTestResult.error }}</span>
                    </template>
                  </div>
                  <el-button
                    size="small"
                    text
                    class="llm-test-dismiss"
                    @click="llmTestResult = null"
                  >
                    关闭
                  </el-button>
                </div>
              </el-form-item>
            </el-form>
          </template>

          <!-- 数据备份与回滚 -->
          <template v-else-if="g.key === 'backup'">
            <h3 class="section-title">数据备份与回滚</h3>
            <p class="section-desc">
              每次导入（基础 / 智能）在写入前都会自动整库备份，可随时回滚到导入前状态。回滚是破坏性操作：会用所选备份点覆盖当前数据库，该备份点之后的所有改动（含多次导入与手动编辑）将永久丢失。schema 迁移备份永久保留，不在此清单中，也不参与自动清理。
            </p>
            <el-form label-position="top">
              <el-form-item label="备份保留数量">
                <el-input-number
                  v-model="draftBackupRetention"
                  :min="1"
                  :max="100"
                  :step="1"
                  style="width: 160px"
                />
                <span class="field-hint">保留最近 N 个导入备份，超出自动清理；保存后生效</span>
              </el-form-item>
              <el-form-item>
                <el-button plain @click="settingsStore.loadImportBackups()">刷新清单</el-button>
                <span class="field-hint">导入后此清单不会自动刷新，可手动刷新</span>
              </el-form-item>
            </el-form>

            <div v-if="importBackups.length === 0" class="backup-empty">
              暂无导入备份（首次导入或保留策略已清空旧备份）
            </div>
            <div v-else class="backup-list">
              <div v-for="b in importBackups" :key="b.id" class="backup-item">
                <div class="backup-main">
                  <div class="backup-row">
                    <el-tag
                      :type="b.trigger === 'smart_import' ? 'success' : 'info'"
                      size="small"
                    >
                      {{ triggerLabel(b.trigger) }}
                    </el-tag>
                    <span class="backup-time">{{ formatTime(b.created_at) }}</span>
                    <span class="backup-size">{{ formatSize(b.size) }}</span>
                  </div>
                  <div class="backup-desc">{{ backupDesc(b) }}</div>
                </div>
                <div class="backup-actions">
                  <el-button size="small" @click="onRestoreBackup(b.id, b.created_at)">
                    回滚
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    @click="onDeleteBackup(b.id, b.created_at)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>
          </template>
        </section>
      </div>
    </div>

    <footer class="page-footer">
      <el-button :disabled="!draftsReady" @click="onToggleOrder">
        <el-icon><IPixelSortVertical /></el-icon>
        {{ editingOrder ? '完成' : '顺序' }}
      </el-button>
      <el-button type="primary" :loading="saving" :disabled="!draftsReady" @click="onSave">保存</el-button>
    </footer>
  </section>
</template>

<style scoped>
.settings-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
  border-left: 1px solid #e5e7eb;
}
.page-header {
  flex-shrink: 0;
  /* 整个 header 白底（全宽），底部 border 与下方内容分隔 */
  background: #ffffff;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #1f2937;
}
.settings-body {
  display: flex;
  flex: 1;
  min-height: 0;
  /* 左/上 padding 去掉：tabs 贴左边、内容顶格；间距由 tabs 与 scroll-area 的 gap 及卡片内边距提供 */
  padding: 0;
  gap: 16px;
}
.tabs {
  width: 160px;
  flex-shrink: 0;
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
  padding-right: 8px;
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
  margin-bottom: 4px;
  transition: background 0.15s;
  border: 1px solid transparent;
}
.tab:hover {
  background: #f3f4f6;
}
.tab.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}
.tab-editing {
  cursor: grab;
}
.tab-editing:active {
  cursor: grabbing;
}
.drag-handle {
  color: #9ca3af;
  flex-shrink: 0;
}
.tab-label {
  flex: 1;
}
.tab-dragging {
  opacity: 0.4;
}
.tab-drag-over {
  border-top: 2px solid #409eff;
}
.edit-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}
.scroll-area {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  scroll-behavior: smooth;
  /* 左缘间距已由 tabs 与 scroll-area 之间的 gap 提供，左 padding 置 0；上/右/下留灰让卡片浮起 */
  padding: 16px 16px 16px 0;
  background: transparent;
  border-radius: 0;
}
.settings-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 6px;
  color: #1f2937;
}
.section-desc {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 16px;
  line-height: 1.6;
}
.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.6;
}
/* LLM 测试连接结果区：常驻展示（成功绿/失败红），避免 toast 一闪而过 */
.llm-test-result {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
}
.llm-test-result.is-success {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  color: #67c23a;
}
.llm-test-result.is-error {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  color: #f56c6c;
}
.llm-test-result .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}
.llm-test-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  word-break: break-word;
}
.llm-test-title {
  font-weight: 600;
}
.llm-test-detail {
  color: #6b7280;
  font-size: 12px;
}
.llm-test-reply {
  color: #6b7280;
  font-size: 12px;
}
.llm-test-dismiss {
  flex-shrink: 0;
  align-self: flex-start;
}
.page-footer {
  flex-shrink: 0;
  padding: 12px 24px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  background: #fafafa;
}
/* 数据备份与回滚 */
.backup-empty {
  padding: 24px;
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  background: #f9fafb;
  border: 1px dashed #e5e7eb;
  border-radius: 6px;
}
.backup-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.backup-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
  gap: 12px;
}
.backup-main {
  flex: 1;
  min-width: 0;
}
.backup-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.backup-time {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  font-variant-numeric: tabular-nums;
}
.backup-size {
  font-size: 12px;
  color: #9ca3af;
}
.backup-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}
.backup-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
</style>
