<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { useRequirementsStore } from '@/stores/requirements'
import { useProjectsStore } from '@/stores/projects'
import type {
  ParsedProject,
  ParsedIteration,
  ParsedBug,
  ParsedModule,
  ImportTarget,
  RequirementStatus,
} from '@/types'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { BUG_STATUS_LABEL, BUG_STATUS_TAG_TYPE, LEVEL_LABEL, LEVEL_TAG_TYPE } from '@/types/bug'
import { formatDate } from '@/utils'

const props = defineProps<{
  parsed: ParsedProject
  /** 导入目标：{project_id} 导入当前项目；{name} 新建项目。 */
  target: ImportTarget
  /** true=基础导入（ID 复用/冲突映射）；false=智能导入（全新建）。 */
  reuseId: boolean
  /** 底部主操作按钮文案。 */
  applyLabel?: string
}>()

const emit = defineEmits<{
  (e: 'apply-success'): void
}>()

const projectName = defineModel<string>('projectName', { required: false })

const store = useRequirementsStore()
const projectsStore = useProjectsStore()
const activeModuleNames = ref<string[]>([])
const defaultStatus = ref<RequirementStatus>('done')

// 左侧树选中项（迭代或 bug）
type TreeNode =
  | { kind: 'iteration'; data: ParsedIteration }
  | { kind: 'bug'; data: ParsedBug }
const selectedNode = ref<TreeNode | null>(null)

// 目标是否为「新建项目」：target 含 name 键（无论是否为空，空名由用户补填）。
// current 模式 target 只有 project_id，无 name 键，故不显示项目名输入框。
const isTargetNew = computed(() => 'name' in props.target)

// ── 统计 ──

const totalIterations = computed(() => props.parsed.iterations.length)
const totalBugs = computed(() => props.parsed.bugs.length)
const selectedIterCount = computed(
  () => props.parsed.iterations.filter((it) => it.selected).length,
)
const selectedBugCount = computed(
  () => props.parsed.bugs.filter((b) => b.selected).length,
)

// ── 左侧树形分组 ──

interface ModuleGroup {
  module: ParsedModule
  iterations: ParsedIteration[]
  bugs: ParsedBug[]
}

const grouped = computed<ModuleGroup[]>(() => {
  const parsed = props.parsed
  const modMap = new Map<string, ParsedModule>()
  for (const m of parsed.modules) modMap.set(m.id, m)

  // 按 module id 分组迭代
  const iterByMod = new Map<string, ParsedIteration[]>()
  for (const it of parsed.iterations) {
    const modIds = it.modules.length > 0 ? it.modules : ['__none__']
    for (const mid of modIds) {
      const list = iterByMod.get(mid)
      if (list) list.push(it)
      else iterByMod.set(mid, [it])
    }
  }

  // 按 module id 分组 bug
  const bugByMod = new Map<string, ParsedBug[]>()
  for (const b of parsed.bugs) {
    const modIds = b.modules.length > 0 ? b.modules : ['__none__']
    for (const mid of modIds) {
      const list = bugByMod.get(mid)
      if (list) {
        if (!list.some((x) => x.id === b.id)) list.push(b)
      } else {
        bugByMod.set(mid, [b])
      }
    }
  }

  // 组装：按 modules 顺序
  const result: ModuleGroup[] = []
  const seen = new Set<string>()
  for (const m of parsed.modules) {
    if (seen.has(m.id)) continue
    seen.add(m.id)
    result.push({
      module: m,
      iterations: iterByMod.get(m.id) ?? [],
      bugs: bugByMod.get(m.id) ?? [],
    })
  }
  // 未分组
  const ungroupedIters = iterByMod.get('__none__') ?? []
  const ungroupedBugs = bugByMod.get('__none__') ?? []
  if (ungroupedIters.length > 0 || ungroupedBugs.length > 0) {
    result.push({
      module: { id: '__none__', name: '（未分组）' },
      iterations: ungroupedIters,
      bugs: ungroupedBugs,
    })
  }
  return result
})

// ── 右侧详情 ──

const selectedIteration = computed<ParsedIteration | null>(
  () => selectedNode.value?.kind === 'iteration' ? selectedNode.value.data : null,
)
const selectedBug = computed<ParsedBug | null>(
  () => selectedNode.value?.kind === 'bug' ? selectedNode.value.data : null,
)

// 模块名解析（id -> name）
function moduleName(id: string): string {
  const m = props.parsed.modules.find((mod) => mod.id === id)
  return m ? m.name : id
}

// bug 关联迭代显示
function linkedIterationDisplay(linked: string | null): string {
  if (!linked) return ''
  const it = props.parsed.iterations.find((i) => i.id === linked)
  return it ? `${it.feature} (${it.date})` : '（关联已失效）'
}

// ── 操作 ──

const statusOptions: RequirementStatus[] = [
  'todo',
  'ui_done_waiting_backend',
  'done',
  'deferred',
]

/** 初始化默认展开 + 默认全选。parsed 变化（打开/切换预览）时自动重置。 */
function init() {
  activeModuleNames.value = grouped.value.map((g) => g.module.id)
}

function applyDefaultStatus() {
  for (const it of props.parsed.iterations) {
    if (it.status === 'done') it.status = defaultStatus.value
  }
  for (const it of props.parsed.iterations) {
    for (const s of it.subitems) {
      if (s.status === 'done') s.status = defaultStatus.value
    }
  }
}

function selectNode(node: TreeNode) {
  selectedNode.value = node
}

function toggleIteration(it: ParsedIteration, val: boolean) {
  it.selected = val
  // 子需求跟随
  for (const s of it.subitems) s.selected = val
}

function toggleBug(b: ParsedBug, val: boolean) {
  b.selected = val
}

function toggleGroupIterations(iters: ParsedIteration[], val: boolean) {
  for (const it of iters) toggleIteration(it, val)
}

function toggleGroupBugs(bugs: ParsedBug[], val: boolean) {
  for (const b of bugs) toggleBug(b, val)
}

// deferred 联动清空 deadline（前端即时反馈；后端亦强制）
watch(
  () => selectedIteration.value?.status,
  (s) => {
    if (s === 'deferred' && selectedIteration.value) {
      selectedIteration.value.completion_deadline = null
    }
  },
)

async function onApply() {
  const selIters = props.parsed.iterations.filter((it) => it.selected)
  const selBugs = props.parsed.bugs.filter((b) => b.selected)
  if (selIters.length === 0 && selBugs.length === 0) {
    ElMessage.warning('请至少选择一项')
    return
  }
  if (isTargetNew.value && !projectName.value?.trim()) {
    ElMessage.warning('项目名不能为空')
    return
  }

  try {
    // reuse_id：基础导入（current/new）true（ID 复用/冲突映射）；智能导入 false（全新建）
    props.parsed.reuse_id = props.reuseId

    let target: ImportTarget
    if (isTargetNew.value) {
      target = { name: projectName.value!.trim() }
    } else {
      const pid = props.target.project_id
      if (!pid) {
        ElMessage.warning('未选择项目')
        return
      }
      target = { project_id: pid }
    }

    const project = await store.applyFullImportTo(target, props.parsed)

    if (isTargetNew.value) {
      await projectsStore.loadSummaries()
      projectsStore.select(project.id)
      const prefix = !props.reuseId ? '智能导入完成：已新建项目' : '已新建项目'
      ElMessage.success(
        `${prefix}「${project.name}」并导入 ${selIters.length} 条迭代${selBugs.length > 0 ? `、${selBugs.length} 条 bug` : ''}`,
      )
    } else {
      ElMessage.success(
        `已导入 ${selIters.length} 条迭代${selBugs.length > 0 ? `、${selBugs.length} 条 bug` : ''}`,
      )
    }
    emit('apply-success')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入失败')
  }
}

// parsed 变化（首次挂载 / 切换预览数据）时重置默认展开
watch(() => props.parsed, () => init(), { immediate: true })
</script>

<template>
  <!-- 顶部：项目名 + 默认状态 + 统计 -->
  <div class="top-bar">
    <div v-if="isTargetNew" class="name-row">
      <span class="label">项目名：</span>
      <el-input
        :model-value="projectName"
        placeholder="项目名（可修改）"
        style="width: 320px"
        @update:model-value="projectName = $event"
      />
    </div>
    <div class="bar-row">
      <span class="label">默认状态（应用于非 to do 段的项）：</span>
      <el-select v-model="defaultStatus" style="width: 160px" @change="applyDefaultStatus">
        <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
      </el-select>
      <span class="hint">
        迭代 {{ selectedIterCount }}/{{ totalIterations }}
        <template v-if="totalBugs > 0"> · Bug {{ selectedBugCount }}/{{ totalBugs }}</template>
      </span>
    </div>
  </div>

  <!-- 主体：左树 + 右详情 -->
  <div class="main-body">
    <!-- 左侧树形 -->
    <div class="tree-panel">
      <el-collapse v-model="activeModuleNames" class="module-collapse">
        <el-collapse-item
          v-for="g in grouped"
          :key="g.module.id"
          :name="g.module.id"
        >
          <template #title>
            <span class="module-title" @click.stop>
              <el-checkbox
                :model-value="
                  g.iterations.every((it) => it.selected) &&
                  g.bugs.every((b) => b.selected)
                "
                :indeterminate="
                  (g.iterations.some((it) => it.selected) || g.bugs.some((b) => b.selected)) &&
                  !(g.iterations.every((it) => it.selected) && g.bugs.every((b) => b.selected))
                "
                @change="(v: boolean) => { toggleGroupIterations(g.iterations, v); toggleGroupBugs(g.bugs, v) }"
              />
              📦 {{ g.module.name }}
              <el-tag type="info" size="small" effect="plain" class="count-tag">
                {{ g.iterations.length + g.bugs.length }}
              </el-tag>
            </span>
          </template>

          <!-- 迭代 -->
          <div
            v-for="it in g.iterations"
            :key="it.id"
            class="tree-item"
            :class="{ active: selectedIteration?.id === it.id }"
            @click="selectNode({ kind: 'iteration', data: it })"
          >
            <el-checkbox
              :model-value="it.selected"
              @click.stop
              @change="(v: boolean) => toggleIteration(it, v)"
            />
            <span class="tree-item-name">{{ it.feature || '（未命名）' }}</span>
            <el-tag
              :type="STATUS_TAG_TYPE[it.status] as never"
              size="small"
              effect="light"
            >
              {{ STATUS_LABEL[it.status] }}
            </el-tag>
            <span class="tree-item-date">{{ formatDate(it.date) }}</span>
          </div>

          <!-- Bug -->
          <div
            v-for="b in g.bugs"
            :key="b.id"
            class="tree-item tree-item-bug"
            :class="{ active: selectedBug?.id === b.id }"
            @click="selectNode({ kind: 'bug', data: b })"
          >
            <el-checkbox
              :model-value="b.selected"
              @click.stop
              @change="(v: boolean) => toggleBug(b, v)"
            />
            <el-tag :type="LEVEL_TAG_TYPE[b.level] as never" size="small" effect="dark">
              {{ b.level }}
            </el-tag>
            <span class="tree-item-name">{{ b.content.slice(0, 20) }}</span>
            <span class="tree-item-date">{{ formatDate(b.date) }}</span>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 右侧详情 -->
    <div class="detail-panel">
      <template v-if="selectedIteration">
        <h4 class="detail-title">
          {{ selectedIteration.feature || '（未命名）' }}
          <el-tag
            :type="STATUS_TAG_TYPE[selectedIteration.status] as never"
            size="small"
            effect="light"
          >
            {{ STATUS_LABEL[selectedIteration.status] }}
          </el-tag>
        </h4>

        <el-form label-width="80px" size="small" class="detail-form">
          <el-form-item label="状态">
            <el-select v-model="selectedIteration.status" style="width: 100%">
              <el-option
                v-for="s in statusOptions"
                :key="s"
                :label="STATUS_LABEL[s]"
                :value="s"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              :model-value="selectedIteration.date"
              type="date"
              value-format="YYYY-MM-DD"
              readonly
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="完成时限">
            <el-date-picker
              v-model="selectedIteration.completion_deadline"
              type="date"
              value-format="YYYY-MM-DD"
              clearable
              placeholder="选填，留空表示无时限"
              style="width: 100%"
              :disabled="selectedIteration.status === 'deferred'"
            />
          </el-form-item>
          <el-form-item label="模块">
            <div class="module-tags">
              <el-tag
                v-for="mid in selectedIteration.modules"
                :key="mid"
                size="small"
                effect="plain"
              >
                {{ moduleName(mid) }}
              </el-tag>
              <span v-if="selectedIteration.modules.length === 0" class="no-modules">
                （未分组）
              </span>
            </div>
          </el-form-item>
          <el-form-item label="内容">
            <div class="content-preview">{{ selectedIteration.content }}</div>
          </el-form-item>

          <!-- 子需求 -->
          <el-form-item v-if="selectedIteration.subitems.length > 0" label="子需求">
            <div class="subitem-list">
              <div
                v-for="s in selectedIteration.subitems"
                :key="s.seq"
                class="subitem-row"
              >
                <el-checkbox v-model="s.selected" />
                <span class="subitem-seq">{{ s.seq }}.</span>
                <span class="subitem-content">{{ s.content }}</span>
                <el-select
                  v-model="s.status"
                  size="small"
                  style="width: 120px; flex-shrink: 0"
                >
                  <el-option
                    v-for="st in statusOptions"
                    :key="st"
                    :label="STATUS_LABEL[st]"
                    :value="st"
                  />
                </el-select>
              </div>
            </div>
          </el-form-item>
        </el-form>
      </template>

      <template v-else-if="selectedBug">
        <h4 class="detail-title">
          Bug 详情
          <el-tag
            :type="LEVEL_TAG_TYPE[selectedBug.level] as never"
            size="small"
            effect="dark"
          >
            {{ LEVEL_LABEL[selectedBug.level] }}
          </el-tag>
          <el-tag
            :type="BUG_STATUS_TAG_TYPE[selectedBug.status] as never"
            size="small"
            effect="light"
          >
            {{ BUG_STATUS_LABEL[selectedBug.status] }}
          </el-tag>
        </h4>

        <el-form label-width="80px" size="small" class="detail-form">
          <el-form-item label="级别">
            <el-select v-model="selectedBug.level" style="width: 100%">
              <el-option
                v-for="(label, key) in LEVEL_LABEL"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="selectedBug.status" style="width: 100%">
              <el-option
                v-for="(label, key) in BUG_STATUS_LABEL"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              :model-value="selectedBug.date"
              type="date"
              value-format="YYYY-MM-DD"
              readonly
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="模块">
            <div class="module-tags">
              <el-tag
                v-for="mid in selectedBug.modules"
                :key="mid"
                size="small"
                effect="plain"
              >
                {{ moduleName(mid) }}
              </el-tag>
              <span v-if="selectedBug.modules.length === 0" class="no-modules">
                （未分组）
              </span>
            </div>
          </el-form-item>
          <el-form-item label="关联迭代">
            <span v-if="selectedBug.linked" class="linked-info">
              {{ linkedIterationDisplay(selectedBug.linked) }}
            </span>
            <span v-else class="no-modules">无关联</span>
          </el-form-item>
          <el-form-item label="内容">
            <div class="content-preview">{{ selectedBug.content }}</div>
          </el-form-item>
        </el-form>
      </template>

      <div v-else class="detail-empty">
        点击左侧条目查看详情
      </div>
    </div>
  </div>

  <!-- 底部主操作按钮 -->
  <div class="panel-footer">
    <el-button type="primary" @click="onApply">
      {{ applyLabel || '应用导入' }}
    </el-button>
  </div>
</template>

<style scoped>
.top-bar {
  margin-bottom: 16px;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.label {
  font-size: 13px;
  color: #374151;
  flex-shrink: 0;
}
.hint {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
}

/* 主体：左右分栏 */
.main-body {
  display: flex;
  gap: 16px;
  height: 520px;
}

/* 左侧树形面板 */
.tree-panel {
  width: 340px;
  flex-shrink: 0;
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px;
}
.module-collapse {
  border: none;
}
.module-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
  background: #f9fafb;
  border-radius: 4px;
  padding: 0 6px;
  height: 34px;
}
.module-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  padding: 4px 0 0 8px;
}
.module-title {
  display: flex;
  align-items: center;
  gap: 6px;
}
.count-tag {
  margin-left: 2px;
}

/* 树形条目 */
.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}
.tree-item:hover {
  background: #f3f4f6;
}
.tree-item.active {
  background: #ecf5ff;
}
.tree-item-bug {
  border-top: 1px dashed #f3f4f6;
  margin-top: 2px;
  padding-top: 6px;
}
.tree-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-item-date {
  font-size: 11px;
  color: #d97706;
  flex-shrink: 0;
}

/* 右侧详情面板 */
.detail-panel {
  flex: 1;
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 16px;
}
.detail-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-form {
  max-width: 100%;
}
.detail-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
  font-size: 14px;
}

/* 模块标签 */
.module-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.no-modules {
  font-size: 12px;
  color: #9ca3af;
}

/* 内容预览 */
.content-preview {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
  max-height: 120px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f9fafb;
  border-radius: 4px;
  padding: 8px;
}

/* 子需求列表 */
.subitem-list {
  width: 100%;
}
.subitem-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid #f3f4f6;
}
.subitem-row:last-child {
  border-bottom: none;
}
.subitem-seq {
  font-size: 12px;
  color: #6b7280;
  flex-shrink: 0;
  min-width: 20px;
}
.subitem-content {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 关联迭代 */
.linked-info {
  font-size: 13px;
  color: #409eff;
}

/* 底部操作区 */
.panel-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
