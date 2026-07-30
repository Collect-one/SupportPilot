<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BookCheck, ChevronRight, FileText, LoaderCircle, RefreshCcw, Search, Upload, X } from '@lucide/vue'
import { api } from '../api'
import type { DocumentRecord } from '../types'

const documents = ref<DocumentRecord[]>([])
const active = ref<DocumentRecord | null>(null)
const loading = ref(true)
const uploading = ref(false)
const error = ref('')
const query = ref('')
const input = ref<HTMLInputElement | null>(null)
const filtered = computed(() => documents.value.filter(document => document.logical_name.toLowerCase().includes(query.value.toLowerCase())))

async function load() {
  loading.value = true
  try { documents.value = await api<DocumentRecord[]>('/documents') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { loading.value = false }
}
async function viewDocument(document: DocumentRecord) { active.value = await api<DocumentRecord>(`/documents/${document.id}`) }
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  uploading.value = true; error.value = ''
  const form = new FormData(); form.append('file', file)
  try { await api('/documents', { method: 'POST', body: form }); await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '上传失败' }
  finally { uploading.value = false; if (input.value) input.value.value = '' }
}
async function act(document: DocumentRecord, action: 'publish' | 'disable' | 'retry') {
  error.value = ''
  try { await api(`/documents/${document.id}/${action}`, { method: 'POST' }); await load(); active.value = null }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '操作失败' }
}
function statusLabel(status: string) { return { UPLOADED: '等待解析', PROCESSING: '解析中', READY: '待发布', PUBLISHED: '已发布', DISABLED: '已停用', FAILED: '解析失败' }[status] || status }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value)) }
onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="page-heading"><div><p class="eyebrow">可信知识</p><h2>知识库</h2><p>只有人工确认发布的版本会进入客户问答检索。</p></div><label class="primary-button upload-button"><LoaderCircle v-if="uploading" class="spin" :size="17" /><Upload v-else :size="17" />{{ uploading ? '正在上传' : '上传文档' }}<input ref="input" type="file" accept=".md,.txt,.pdf" :disabled="uploading" @change="upload" /></label></section>
    <div class="knowledge-summary"><div><span class="summary-icon published"><BookCheck :size="19" /></span><div><strong>{{ documents.filter(d => d.status === 'PUBLISHED').length }}</strong><span>已发布</span></div></div><div><span class="summary-icon ready"><FileText :size="19" /></span><div><strong>{{ documents.filter(d => d.status === 'READY').length }}</strong><span>待审核发布</span></div></div><div><span class="summary-icon failed"><RefreshCcw :size="19" /></span><div><strong>{{ documents.filter(d => d.status === 'FAILED').length }}</strong><span>解析失败</span></div></div></div>
    <p v-if="error" class="form-error">{{ error }}</p>
    <section class="knowledge-table-wrap">
      <header><div><strong>全部文档</strong><span>{{ documents.length }} 个版本</span></div><label class="search-input"><Search :size="16" /><input v-model="query" placeholder="搜索文档" /></label></header>
      <div class="knowledge-table"><div class="table-head"><span>文档</span><span>版本</span><span>状态</span><span>片段</span><span>更新时间</span><span></span></div>
        <button v-for="document in filtered" :key="document.id" class="table-row" @click="viewDocument(document)"><span class="document-name"><i><FileText :size="18" /></i><span><strong>{{ document.logical_name }}</strong><small>{{ document.filename }}</small></span></span><span>v{{ document.version }}</span><span><em :class="['document-status', document.status.toLowerCase()]">{{ statusLabel(document.status) }}</em></span><span>{{ document.chunk_count }}</span><span>{{ formatDate(document.created_at) }}</span><span><ChevronRight :size="17" /></span></button>
      </div>
      <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载文档</div>
    </section>
    <aside v-if="active" class="detail-drawer knowledge-drawer"><header><div><p>文档预览</p><h2>{{ active.logical_name }}</h2></div><button class="icon-button" title="关闭预览" @click="active = null"><X :size="18" /></button></header><div class="drawer-meta"><span>版本 v{{ active.version }}</span><span :class="['document-status', active.status.toLowerCase()]">{{ statusLabel(active.status) }}</span><span>{{ active.chunk_count }} 个片段</span></div><p v-if="active.error_message" class="form-error">{{ active.error_message }}</p><div class="chunk-preview"><article v-for="chunk in active.chunks" :key="chunk.id"><header><span>#{{ chunk.position + 1 }}</span><strong>{{ chunk.heading || '正文片段' }}</strong></header><p>{{ chunk.content }}</p></article></div><footer><button v-if="active.status === 'READY'" class="primary-button" @click="act(active, 'publish')"><BookCheck :size="16" />确认发布</button><button v-if="active.status === 'PUBLISHED'" class="secondary-button danger-button" @click="act(active, 'disable')">停用文档</button><button v-if="active.status === 'FAILED' && active.retry_count < 3" class="secondary-button" @click="act(active, 'retry')"><RefreshCcw :size="16" />重新解析</button></footer></aside>
  </div>
</template>
