<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DotLottieVue } from '@lottiefiles/dotlottie-vue'

import aiAnalyzingUrl from '@/assets/lottie/ai-analyzing.lottie?url'
import aiErrorUrl from '@/assets/lottie/ai-error.lottie?url'
import { useRequirementsStore } from '@/stores/requirements'
import { useSettingsStore } from '@/stores/settings'
import type { ParsedProject } from '@/types'
import ImportPreviewPanel from '@/components/ImportPreviewPanel.vue'

const store = useRequirementsStore()
const settingsStore = useSettingsStore()

const visible = ref(false)
type Step = 'pickFile' | 'analyzing' | 'preview'
const step = ref<Step>('pickFile')

// 第①步 pick 结果
const pickedFilename = ref('')
const pickedText = ref('')

// 第②步 analyzing 状态
const progress = ref(0)
const elapsed = ref(0) // 秒
const errorMsg = ref('')
const cancelled = ref(false)

// 第③步 preview 数据
const parsed = ref<ParsedProject | null>(null)
const projectName = ref('')

// 定时器引用
let progressTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null

// stepper active index
const stepIndex = computed(() => {
  if (step.value === 'pickFile') return 0
  if (step.value === 'analyzing') return 1
  return 2
})

// 计时器显示
const llmTimeout = computed(() => settingsStore.llmTimeout)
const elapsedFmt = computed(() => fmtMmSs(elapsed.value))
const timeoutFmt = computed(() => fmtMmSs(llmTimeout.value))
const llmModel = computed(() => settingsStore.llmModel || 'AI')

// 进度条渐变色：随进度增长 红 → 橙 → 蓝 → 绿（设计 §10 进度反馈）
const progressColors = [
  { color: '#f56c6c', percentage: 20 },
  { color: '#e6a23c', percentage: 50 },
  { color: '#409eff', percentage: 80 },
  { color: '#67c23a', percentage: 100 },
]

function fmtMmSs(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 公开方法 ──

function open() {
  step.value = 'pickFile'
  pickedFilename.value = ''
  pickedText.value = ''
  progress.value = 0
  elapsed.value = 0
  errorMsg.value = ''
  cancelled.value = false
  parsed.value = null
  projectName.value = ''
  store.smartImporting = true
  visible.value = true
}

defineExpose({ open })

// ── 第①步：选择文件 ──

async function onPickFile() {
  try {
    const result = await store.pickSmartImportFile()
    if (!result) return // 用户取消选文件，留在 ①
    pickedFilename.value = result.filename
    pickedText.value = result.text
    // 已识别格式提示（决策 10）：xlsx/docx 为解析后文本，其余为原样读取
    if (result.source_format) {
      ElMessage.info(`已识别为 ${result.source_format.toUpperCase()} 文档`)
    }
    startAnalyzing()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '选择文件失败')
  }
}

// ── 第②步：AI 分析 ──

function startAnalyzing() {
  step.value = 'analyzing'
  progress.value = 0
  elapsed.value = 0
  errorMsg.value = ''
  cancelled.value = false

  // 伪进度条（设计 §6.1）
  const timeout = llmTimeout.value
  const startMs = Date.now()
  progressTimer = setInterval(() => {
    const elapsedMs = Date.now() - startMs
    const elapsedSec = elapsedMs / 1000
    progress.value = Math.round(95 * (1 - Math.exp(-elapsedSec / (timeout / 3))))
  }, 200)

  // 计时器
  elapsedTimer = setInterval(() => {
    elapsed.value += 1
  }, 1000)

  // 调 LLM
  store
    .runSmartImport(pickedText.value, pickedFilename.value)
    .then((result) => {
      if (cancelled.value) return // 软取消：丢弃结果
      clearTimers()
      progress.value = 100
      // 停留 ~150ms 给「满格」反馈
      setTimeout(() => {
        if (cancelled.value) return // 软取消：丢弃结果
        parsed.value = result.parsed
        projectName.value = result.filename || result.parsed.name
        step.value = 'preview'
      }, 150)
    })
    .catch((e) => {
      if (cancelled.value) return
      clearTimers()
      // 错误态：进度条卡在超时那一刻的进度（不再前进，也不归零）
      errorMsg.value = e instanceof Error ? e.message : 'AI 分析失败'
    })
}

// ── 取消（软取消） ──

function onCancel() {
  cancelled.value = true
  clearTimers()
  step.value = 'pickFile'
  visible.value = false
}

// ── 第②步 error 态操作 ──

function onRetry() {
  errorMsg.value = ''
  startAnalyzing()
}

function onCloseError() {
  step.value = 'pickFile'
  errorMsg.value = ''
  visible.value = false
}

// ── 第③步：预览并应用 ──

function onApplySuccess() {
  visible.value = false
}

// ── 清理 ──

function clearTimers() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

// 弹窗关闭时统一清理（X 按钮 / 取消 / apply 成功 / 关闭遮罩）
watch(visible, (v) => {
  if (!v) {
    cancelled.value = true
    clearTimers()
    store.smartImporting = false
  }
})
</script>

<template>
  <el-dialog
    v-model="visible"
    title="智能导入"
    width="960px"
    top="5vh"
    class="smart-import-dialog"
    :close-on-click-modal="false"
  >
    <!-- stepper -->
    <el-steps
      :active="stepIndex"
      align-center
      process-status="process"
      finish-status="success"
      class="smart-steps"
    >
      <el-step title="选择文件" />
      <el-step title="AI 分析" />
      <el-step title="预览并应用" />
    </el-steps>

    <!-- ① 选择文件 -->
    <div v-if="step === 'pickFile'" class="step-content">
      <div class="pick-file-hint">
        <p>选择一个需求记录文件，AI将尝试自动识别结构并创建新项目</p>
        <p class="pick-hint-sub">支持 .txt / .md / .csv / .xls / .xlsx / .docx（Excel/Word 将自动解析为文本）</p>
      </div>
      <el-button type="primary" @click="onPickFile">
        选择文件
      </el-button>
    </div>

    <!-- ② AI 分析 -->
    <div v-else-if="step === 'analyzing'" class="step-content">
      <div class="analyzing-overlay">
        <!-- lottie：等待态与错误态切换，结构保持一致 -->
        <DotLottieVue
          v-if="!errorMsg"
          :src="aiAnalyzingUrl"
          autoplay
          loop
          class="lottie-spinner"
        />
        <DotLottieVue
          v-else
          :src="aiErrorUrl"
          autoplay
          loop
          class="lottie-spinner"
        />

        <!-- 提示文字：错误信息直接复用等待态位置 -->
        <p class="analyzing-text" :class="{ 'is-error': !!errorMsg }">
          {{ errorMsg || `正在调用 ${llmModel}，请稍候…` }}
        </p>

        <!-- 进度条：错误态保留卡住的超时进度，不重置 -->
        <el-progress
          :percentage="progress"
          :stroke-width="22"
          text-inside
          :color="progressColors"
          class="progress-bar"
        />

        <!-- 计时文本：错误态保持不动 -->
        <p class="timer-text">已等待 {{ elapsedFmt }} / 上限 {{ timeoutFmt }}</p>

        <!-- 操作按钮：等待态=取消；错误态=重试+关闭 -->
        <div class="analyzing-actions">
          <el-button v-if="!errorMsg" @click="onCancel">取消</el-button>
          <template v-else>
            <el-button type="primary" @click="onRetry">重试</el-button>
            <el-button @click="onCloseError">关闭</el-button>
          </template>
        </div>
      </div>
    </div>

    <!-- ③ 预览并应用 -->
    <div v-else-if="step === 'preview' && parsed" class="preview-step">
      <ImportPreviewPanel
        :parsed="parsed"
        :target="{ name: '' }"
        :reuse-id="false"
        apply-label="智能导入并新建"
        v-model:project-name="projectName"
        @apply-success="onApplySuccess"
      />
    </div>

    <!-- lottie 预载：dialog 打开即在①隐藏挂载实例，提前完成动画资源的拉取与解析，消除②进入时的 ~2s 空白 -->
    <div
      v-if="visible && step === 'pickFile'"
      class="lottie-preload-host"
      aria-hidden="true"
    >
      <DotLottieVue :src="aiAnalyzingUrl" autoplay loop />
    </div>
  </el-dialog>
</template>

<style scoped>
.smart-steps {
  margin-bottom: 24px;
}

/* 当前步骤（process）文字与圆圈改为深蓝色；未执行步骤保持灰色 */
.smart-steps :deep(.el-step__head.is-process),
.smart-steps :deep(.el-step__title.is-process) {
  color: #1d4ed8;
  border-color: #1d4ed8;
}

.smart-import-dialog {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
}

/* 弹窗 body 填满 dialog，并让 body 内的弹性链生效 */
.smart-import-dialog :deep(.el-dialog__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 第三步容器：让顶栏/主区域/底栏按纵向弹性排布 */
.preview-step {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 覆盖 ImportPreviewPanel 的 main-body 固定高度，改为填满可用空间；
   其内部 tree-panel / detail-panel 已有 overflow:auto，会自动滚动 */
.preview-step :deep(.main-body) {
  height: auto;
  flex: 1;
  min-height: 0;
}

/* 双重保险：左右面板即使内容再高，也被限制在 main-body 内滚动 */
.preview-step :deep(.tree-panel),
.preview-step :deep(.detail-panel) {
  min-height: 0;
}

.step-content {
  min-height: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

/* ① 选择文件 */
.pick-file-hint {
  text-align: center;
}
.pick-file-hint p {
  margin: 0 0 8px;
  font-size: 14px;
  color: #374151;
}
.pick-hint-sub {
  font-size: 12px !important;
  color: #9ca3af !important;
}

/* ② AI 分析 */
.analyzing-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 0;
  width: 100%;
}
.lottie-spinner {
  width: 160px;
  height: 160px;
}
.analyzing-text {
  font-size: 14px;
  color: #374151;
  margin: 0;
  text-align: center;
  max-width: 720px;
}
/* 错误态文字：复用同一段文字位置，仅切换颜色 */
.analyzing-text.is-error {
  color: #dc2626;
}
.analyzing-actions {
  display: flex;
  gap: 8px;
}
.progress-bar {
  width: 90%;
  max-width: 720px;
}
/* lottie 预载宿主：离屏隐藏但保持挂载，触发资源提前加载 */
.lottie-preload-host {
  position: absolute;
  left: -9999px;
  top: -9999px;
  width: 160px;
  height: 160px;
  opacity: 0;
  pointer-events: none;
}
.timer-text {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}
</style>
