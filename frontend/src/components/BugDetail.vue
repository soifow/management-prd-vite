<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { MdEditor } from 'md-editor-v3'

import { useBugsStore } from '@/stores/bugs'
import { useProjectsStore } from '@/stores/projects'
import {
  BUG_STATUS_LABEL,
  LEVEL_LABEL,
  LEVEL_TAG_TYPE,
} from '@/types/bug'
import type { BugItem, BugLevel, BugLinkInfo, BugStatus } from '@/types'
import { formatDate } from '@/utils'

const emit = defineEmits<{ (e: 'jump-requirement', link: BugLinkInfo): void }>()

const bugsStore = useBugsStore()
const projectsStore = useProjectsStore()
const { currentBug, linkedInfo, modules } = storeToRefs(bugsStore)
const { activeProjectId } = storeToRefs(projectsStore)

// 编辑缓冲（避免直接改 store 引用）
const bufferModule = ref('')
const bufferLevel = ref<BugLevel>('P3')
const bufferStatus = ref<BugStatus>('open')
const bufferDate = ref('')
const bufferContent = ref('')
const bufferLinkedId = ref<string | null>(null)
const bufferClearLinked = ref(false)

const features = ref<string[]>([])
const iterations = ref<{ id: string; date: string; content: string }[]>([])

const levelOptions: { value: BugLevel; label: string }[] = (
  Object.keys(LEVEL_LABEL) as BugLevel[]
).map((k) => ({ value: k, label: LEVEL_LABEL[k] }))

// 模块下拉选项：项目已有模块 + 当前 bug 的模块（兜底，防止该模块在需求中被删后无法显示）
const moduleOptions = computed(() => {
  const opts = new Set<string>(modules.value)
  if (bufferModule.value) opts.add(bufferModule.value)
  return Array.from(opts).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
})

// 关联功能下拉：当前选中模块下需求的 feature 列表
async function refreshFeatures() {
  if (!activeProjectId.value || !bufferModule.value) {
    features.value = []
    return
  }
  features.value = await bugsStore.listFeaturesFor(bufferModule.value)
}

async function refreshIterations(feature: string) {
  if (!activeProjectId.value || !bufferModule.value || !feature) {
    iterations.value = []
    return
  }
  const iters = await bugsStore.listIterationsFor(bufferModule.value, feature)
  iterations.value = iters.map((i) => ({
    id: i.id,
    date: i.date,
    content: i.content,
  }))
}

// 关联迭代下拉的当前选中 feature（用于两级级联）
const linkedFeature = ref('')
watch(linkedFeature, (f) => {
  if (f) void refreshIterations(f)
})

function resetBuffer(b: BugItem | null) {
  if (!b) return
  bufferModule.value = b.module
  bufferLevel.value = b.level
  bufferStatus.value = b.status
  bufferDate.value = b.date
  bufferContent.value = b.content
  bufferLinkedId.value = b.linked_iteration_id
  bufferClearLinked.value = false
  linkedFeature.value = ''
  features.value = []
  iterations.value = []
}

// 切换 bug 时回填缓冲 + 解析关联
watch(currentBug, (b) => {
  if (!b) return
  resetBuffer(b)
  void bugsStore.refreshLinked()
}, { immediate: true })

// 关联解析完成后，若有链接，回填功能名以便下拉显示
watch(linkedInfo, (info) => {
  if (info) {
    linkedFeature.value = info.feature
    void refreshFeatures()
    void refreshIterations(info.feature)
  }
})

watch(bufferModule, () => {
  void refreshFeatures()
})

async function onSave() {
  const b = currentBug.value
  if (!b) return
  if (!bufferContent.value.trim()) {
    ElMessage.warning('bug 内容不能为空')
    return
  }
  try {
    await bugsStore.updateBugItem(b.id, {
      module: bufferModule.value,
      content: bufferContent.value,
      level: bufferLevel.value,
      status: bufferStatus.value,
      date: bufferDate.value,
      linked_iteration_id: bufferLinkedId.value ?? undefined,
      clear_linked: bufferClearLinked.value,
    })
    bufferClearLinked.value = false
    await bugsStore.refreshLinked()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}

async function onClearLinked() {
  bufferLinkedId.value = null
  bufferClearLinked.value = true
  linkedFeature.value = ''
  ElMessage.info('清除后点击保存生效')
}

function onJumpToRequirement() {
  if (linkedInfo.value) emit('jump-requirement', linkedInfo.value)
}

async function onDelete() {
  const b = currentBug.value
  if (!b) return
  try {
    await ElMessageBox.confirm('确定删除这条 bug？', '删除 bug', { type: 'warning' })
    await bugsStore.removeBug(b.id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function onBack() {
  bugsStore.closeBug()
}

/** 切换关联迭代后同步 buffer。 */
function onIterationChange(id: string | null) {
  bufferLinkedId.value = id
  bufferClearLinked.value = false
}
</script>

<template>
  <div v-if="currentBug" class="detail">
    <el-page-header class="head" @back="onBack">
      <template #content>
        <el-tag :type="LEVEL_TAG_TYPE[currentBug.level] as never" effect="dark" size="small" style="margin-right: 8px">
          {{ LEVEL_LABEL[currentBug.level] }}
        </el-tag>
        <span class="title">{{ currentBug.content.slice(0, 20) || '（空）' }}</span>
      </template>
      <template #extra>
        <el-button :icon="Delete" type="danger" @click="onDelete">删除</el-button>
      </template>
    </el-page-header>

    <div class="body">
      <!-- 左：md-editor -->
      <div class="editor-pane">
        <div class="iter-head">
          <el-date-picker
            v-model="bufferDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="bug 日期"
            size="small"
            style="width: 150px"
          />
          <el-select v-model="bufferModule" size="small" placeholder="所属模块" style="width: 160px">
            <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
          </el-select>
          <el-select v-model="bufferLevel" size="small" style="width: 160px">
            <el-option v-for="opt in levelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <el-select v-model="bufferStatus" size="small" style="width: 120px">
            <el-option
              v-for="(label, key) in BUG_STATUS_LABEL"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
          <el-button type="primary" size="small" @click="onSave">保存</el-button>
        </div>
        <div class="editor-wrapper">
          <MdEditor
            v-model="bufferContent"
            :key="currentBug.id"
            :preview="false"
            :code-foldable="false"
            class="editor"
          />
        </div>
      </div>

      <!-- 右：关联需求迭代 -->
      <div class="link-pane">
        <div class="link-title">关联需求迭代</div>
        <div class="link-scroll">
          <!-- 关联当前生效 -->
          <div v-if="linkedInfo" class="link-card active">
            <div class="link-line"><span class="lk-label">模块</span>{{ linkedInfo.module }}</div>
            <div class="link-line"><span class="lk-label">功能</span>{{ linkedInfo.feature }}</div>
            <div class="link-line"><span class="lk-label">日期</span>📅 {{ formatDate(linkedInfo.date) }}</div>
            <div class="link-content">{{ linkedInfo.content }}</div>
            <el-button type="primary" size="small" @click="onJumpToRequirement">跳转查看</el-button>
            <el-button size="small" @click="onClearLinked">清除关联</el-button>
          </div>

          <!-- 已关联但失效 -->
          <div v-else-if="bufferLinkedId" class="link-card stale">
            <div class="stale-text">⚠ 关联已失效（对应需求迭代已被删除）</div>
            <el-button size="small" @click="onClearLinked">清除关联</el-button>
          </div>

          <!-- 重新选择关联 -->
          <div v-if="!linkedInfo && !bufferLinkedId" class="link-card select-link">
            <el-select
              v-model="linkedFeature"
              size="small"
              clearable
              filterable
              placeholder="选择功能"
              style="width: 100%; margin-bottom: 8px"
            >
              <el-option v-for="f in features" :key="f" :label="f" :value="f" />
            </el-select>
            <el-select
              :model-value="bufferLinkedId"
              size="small"
              clearable
              placeholder="选择迭代（日期-内容）"
              style="width: 100%"
              @change="onIterationChange"
            >
              <el-option
                v-for="it in iterations"
                :key="it.id"
                :label="`${formatDate(it.date)} · ${it.content.slice(0, 16)}`"
                :value="it.id"
              />
            </el-select>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.head {
  flex-shrink: 0;
  margin-bottom: 12px;
}
.title {
  font-weight: 600;
  font-size: 15px;
}
.body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}
.editor-pane {
  flex: 2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.iter-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}
.editor-wrapper {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.editor-wrapper :deep(.md-editor) {
  height: 100%;
}
.editor-wrapper :deep(.md-editor-footer-item) {
  align-items: center;
}
.editor-wrapper :deep(.md-editor-footer-item label),
.editor-wrapper :deep(.md-editor-footer-item span) {
  line-height: 24px;
}
.link-pane {
  flex: 1;
  min-width: 220px;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid #e5e7eb;
  padding-left: 12px;
}
.link-title {
  flex-shrink: 0;
  font-weight: 600;
  font-size: 13px;
  color: #374151;
  margin-bottom: 10px;
}
.link-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.link-card {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}
.link-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.link-card.stale {
  border-color: #fca5a5;
  background: #fef2f2;
}
.link-card.select-link {
  background: #f9fafb;
}
.link-line {
  font-size: 13px;
  margin-bottom: 6px;
  word-break: break-all;
}
.lk-label {
  display: inline-block;
  width: 40px;
  color: #6b7280;
  font-weight: 500;
}
.link-content {
  font-size: 13px;
  color: #374151;
  line-height: 1.5;
  margin: 8px 0;
  padding: 6px 8px;
  background: #ffffff;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}
.stale-text {
  font-size: 13px;
  color: #dc2626;
  margin-bottom: 8px;
}
</style>
