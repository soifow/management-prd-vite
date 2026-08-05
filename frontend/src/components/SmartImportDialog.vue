<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DotLottieVue } from '@lottiefiles/dotlottie-vue'

import aiAnalyzingUrl from '@/assets/lottie/ai-analyzing.lottie?url'
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
    title="✨ 智能导入"
    width="960px"
    top="5vh"
    :close-on-click-modal="false"
  >
    <!-- stepper -->
    <el-steps :active="stepIndex" finish-status="success" class="smart-steps">
      <el-step title="选择文件" />
      <el-step title="AI 分析" />
      <el-step title="预览并应用" />
    </el-steps>

    <!-- ① 选择文件 -->
    <div v-if="step === 'pickFile'" class="step-content">
      <div class="pick-file-hint">
        <p>选择一个需求文档或文本文件，AI 将自动识别结构并创建新项目。</p>
        <p class="pick-hint-sub">支持 .txt / .md / .docx 等文本文件（.docx 可能产生乱码，AI 尽力识别）</p>
      </div>
      <el-button type="primary" @click="onPickFile">
        选择文件
      </el-button>
    </div>

    <!-- ② AI 分析 -->
    <div v-else-if="step === 'analyzing'" class="step-content">
      <!-- 正常态：转圈 + 进度 + 计时 -->
      <template v-if="!errorMsg">
        <div class="analyzing-overlay">
          <DotLottieVue
            :src="aiAnalyzingUrl"
            autoplay
            loop
            class="lottie-spinner"
          />
          <p class="analyzing-text">正在调用 {{ llmModel }}，请稍候…</p>
          <el-progress :percentage="progress" :stroke-width="6" class="progress-bar" />
          <p class="timer-text">已等待 {{ elapsedFmt }} / 上限 {{ timeoutFmt }}</p>
          <el-button @click="onCancel">取消</el-button>
        </div>
      </template>

      <!-- error 态 -->
      <template v-else>
        <div class="error-block">
          <el-alert type="error" :closable="false" show-icon>
            <template #title>{{ errorMsg }}</template>
          </el-alert>
          <div class="error-actions">
            <el-button type="primary" @click="onRetry">重试</el-button>
            <el-button @click="onCloseError">关闭</el-button>
          </div>
        </div>
      </template>
    </div>

    <!-- ③ 预览并应用 -->
    <div v-else-if="step === 'preview' && parsed">
      <ImportPreviewPanel
        :parsed="parsed"
        :target="{ name: '' }"
        :reuse-id="false"
        apply-label="智能导入并新建"
        v-model:project-name="projectName"
        @apply-success="onApplySuccess"
      />
    </div>
  </el-dialog>
</template>

<style scoped>
.smart-steps {
  margin-bottom: 24px;
}

.step-content {
  min-height: 200px;
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
  padding: 24px 0;
}
.lottie-spinner {
  width: 160px;
  height: 160px;
}
.analyzing-text {
  font-size: 14px;
  color: #374151;
  margin: 0;
}
.progress-bar {
  width: 320px;
}
.timer-text {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}

/* error 态 */
.error-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 0;
  width: 100%;
}
.error-block :deep(.el-alert) {
  max-width: 480px;
  width: 100%;
}
.error-actions {
  display: flex;
  gap: 8px;
}
</style>
