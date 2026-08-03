import type { ToolbarNames } from 'md-editor-v3'

/**
 * md-editor-v3 工具栏配置（全局共享）。
 *
 * 移除依赖 unpkg CDN 扩展或外链的按钮：
 * - 'mermaid'/'katex'：渲染类扩展，本项目编辑器均为 :preview="false" 纯编辑模式，保留无意义
 * - 'prettier'：依赖 unpkg CDN 的 prettier（已通过 noPrettier 禁用），点击会触发占位 instance 报错
 * - 'github'：md-editor-v3 源码外链，桌面应用不需要
 *
 * 保留 'image'：后续通过 on-upload-img 回调实现本地图片插入（选本地图片纳入需求管理，
 * 非上传、不裁剪、不引用外网图），与 cropper 扩展无关。
 */
export const MD_EDITOR_TOOLBARS: ToolbarNames[] = [
  'bold',
  'underline',
  'italic',
  'strikeThrough',
  '-',
  'title',
  'sub',
  'sup',
  'quote',
  'unorderedList',
  'orderedList',
  'task',
  '-',
  'codeRow',
  'code',
  'link',
  'image',
  'table',
  '-',
  'revoke',
  'next',
  'save',
  '=',
  'pageFullscreen',
  'fullscreen',
  'preview',
  'previewOnly',
  'htmlPreview',
  'catalog',
]

/**
 * MdEditor 共享 props。
 *
 * 桌面应用离线运行，通过 noXxx 禁用 md-editor-v3 默认从 unpkg CDN 加载的扩展脚本
 * （highlight / prettier / cropper / mermaid / echarts / katex），消除 WebView2
 * Tracking Prevention 刷屏警告，并避免离线加载失败。
 *
 * 渲染类扩展（mermaid/echarts/katex/highlight）依赖预览渲染，:preview=false 下
 * 本就无作用；cropper 是裁剪上传扩展，本项目图片插入走 on-upload-img 本地回调
 * （不裁剪、不上传、不引用外网图），不需要 cropper。
 */
export const MD_EDITOR_PROPS = {
  preview: false,
  codeFoldable: false,
  toolbars: MD_EDITOR_TOOLBARS,
  noHighlight: true,
  noPrettier: true,
  noUploadImg: true,
  noMermaid: true,
  noEcharts: true,
  noKatex: true,
} as const
