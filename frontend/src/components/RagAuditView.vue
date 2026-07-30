<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock3, FileSearch, LoaderCircle, RefreshCw, SearchX } from '@lucide/vue'
import { api } from '../api'
import type { RagTraceDetail, RagTraceList, RagTraceSummary } from '../types'

type DecisionFilter = 'ALL' | 'SUFFICIENT' | 'INSUFFICIENT' | 'CONFLICT' | 'FAILED' | 'NOT_SEARCHED' | 'LEGACY'

const traces = ref<RagTraceSummary[]>([])
const selected = ref<RagTraceDetail | null>(null)
const filter = ref<DecisionFilter>('ALL')
const total = ref(0)
const loading = ref(true)
const detailLoading = ref(false)
const error = ref('')

const filters: Array<{ value: DecisionFilter; label: string }> = [
  { value: 'ALL', label: '全部' },
  { value: 'SUFFICIENT', label: '证据充分' },
  { value: 'INSUFFICIENT', label: '证据不足' },
  { value: 'CONFLICT', label: '资料冲突' },
  { value: 'FAILED', label: '调用失败' },
  { value: 'NOT_SEARCHED', label: '未检索' },
  { value: 'LEGACY', label: '历史记录' },
]

const selectedCitationIds = computed(() => new Set(selected.value?.citations.map(item => item.chunk_id) || []))

async function load(preferredTraceId?: string) {
  loading.value = true
  error.value = ''
  try {
    const query = filter.value === 'ALL' ? '' : `&decision=${filter.value}`
    const result = await api<RagTraceList>(`/support/rag-traces?limit=50${query}`)
    traces.value = result.items
    total.value = result.total
    const target = preferredTraceId && traces.value.some(item => item.trace_id === preferredTraceId)
      ? preferredTraceId
      : traces.value[0]?.trace_id
    if (target) await selectTrace(target)
    else selected.value = null
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'RAG 验收记录加载失败'
  } finally {
    loading.value = false
  }
}

async function selectTrace(traceId: string) {
  detailLoading.value = true
  error.value = ''
  try {
    selected.value = await api<RagTraceDetail>(`/support/rag-traces/${traceId}`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'RAG 验收详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

async function changeFilter(value: DecisionFilter) {
  filter.value = value
  await load()
}

function decisionLabel(value: string) {
  return { SUFFICIENT: '证据充分', INSUFFICIENT: '证据不足', CONFLICT: '资料冲突', FAILED: '调用失败', NOT_SEARCHED: '未执行检索', LEGACY: '历史记录' }[value] || value
}
function reasonLabel(value: string | null) {
  if (!value) return '未记录证据判定'
  return { sufficient: '候选资料达到回答阈值', no_results: '没有检索到候选资料', identifier_not_found: '问题中的错误码或标识未命中', low_relevance: '候选资料相关性不足', ambiguous_sources: '候选资料难以区分', conflicting_identifier_sources: '不同资料对同一标识存在冲突' }[value] || value
}
function toolLabel(value: string) {
  return { search_knowledge: '检索知识库', generate_grounded_answer: '生成知识库回答', propose_ticket: '生成工单建议', get_ticket_status: '查询工单状态' }[value] || value
}
function percent(value: number | null) { return value === null ? '-' : `${Math.round(value * 100)}%` }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value)) }

onMounted(() => load())
</script>

<template>
  <div class="page-stack rag-audit-page">
    <section class="page-heading">
      <div><p class="eyebrow">内部质量验收</p><h2>RAG 验收</h2><p>检查检索候选、证据判定与最终回答的一致性。</p></div>
      <button class="secondary-button" :disabled="loading" @click="load(selected?.trace_id)"><LoaderCircle v-if="loading" class="spin" :size="16" /><RefreshCw v-else :size="16" />刷新</button>
    </section>
    <div class="audit-filters" role="tablist" aria-label="证据状态筛选"><button v-for="item in filters" :key="item.value" :class="{ active: filter === item.value }" @click="changeFilter(item.value)">{{ item.label }}</button></div>
    <p v-if="error" class="form-error">{{ error }}</p>

    <section class="audit-workspace" :class="{ 'detail-open': selected }">
      <div class="audit-list-panel">
        <header><strong>{{ total }} 条记录</strong><span>最近 50 条</span></header>
        <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载验收记录</div>
        <button v-for="trace in traces" :key="trace.trace_id" class="audit-row" :class="{ active: selected?.trace_id === trace.trace_id }" @click="selectTrace(trace.trace_id)">
          <div><span :class="['audit-status', trace.decision_status.toLowerCase()]">{{ decisionLabel(trace.decision_status) }}</span><time>{{ formatDate(trace.created_at) }}</time></div>
          <strong>{{ trace.question || '无客户问题' }}</strong><p>{{ trace.organization_name }} · {{ trace.customer_name }}</p><small>{{ trace.candidate_count }} 个候选 · {{ trace.citation_count }} 个最终引用 · {{ trace.latency_ms ?? 0 }} ms</small>
        </button>
        <div v-if="!loading && !traces.length" class="empty-state compact-empty"><span><SearchX :size="23" /></span><h3>当前筛选下没有记录</h3><p>新对话产生后会显示在这里。</p></div>
      </div>

      <article v-if="selected" class="audit-detail">
        <header><button class="icon-button audit-back" title="返回记录列表" @click="selected = null"><ArrowLeft :size="19" /></button><div><span class="trace-id">{{ selected.trace_id }}</span><h2>{{ selected.question || '无客户问题' }}</h2><p>{{ selected.organization_name }} · {{ selected.customer_name }} · {{ formatDate(selected.created_at) }}</p></div><span :class="['audit-status', selected.decision_status.toLowerCase()]">{{ decisionLabel(selected.decision_status) }}</span></header>
        <div v-if="detailLoading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载验收详情</div>
        <div v-else class="audit-detail-scroll">
          <p v-if="selected.legacy_partial" class="audit-warning"><AlertTriangle :size="16" />历史记录缺少候选快照，仅展示已保存的最终引用。</p>
          <section class="audit-answer"><h3>最终回答</h3><p>{{ selected.answer }}</p></section>
          <section class="audit-decision"><div><span>证据判定</span><strong>{{ reasonLabel(selected.decision_reason) }}</strong></div><div><span>最高综合分</span><strong>{{ percent(selected.top_score) }}</strong></div><div><span>最终引用</span><strong>{{ selected.citation_count }}</strong></div><div><span>总耗时</span><strong>{{ selected.latency_ms ?? 0 }} ms</strong></div></section>
          <section class="audit-candidates">
            <header><div><h3>Top {{ selected.candidates.length }} 检索候选</h3><p>绿色标记表示最终回答实际采用的片段。</p></div></header>
            <div class="candidate-head"><span>#</span><span>资料</span><span>综合分</span><span>语义分</span><span>关键词</span><span>标识命中</span></div>
            <details v-for="candidate in selected.candidates" :key="candidate.chunk_id" class="candidate-row" :class="{ cited: selectedCitationIds.has(candidate.chunk_id) }">
              <summary><span>{{ candidate.rank }}</span><span><strong>{{ candidate.document_name }} v{{ candidate.version }}</strong><small>{{ candidate.heading || '无标题分段' }}</small></span><span>{{ percent(candidate.score) }}</span><span>{{ percent(candidate.semantic_score) }}</span><span>{{ percent(candidate.keyword_coverage) }}</span><span><CheckCircle2 v-if="candidate.exact_identifier" :size="15" /><span v-else>-</span></span></summary><blockquote>{{ candidate.excerpt }}</blockquote>
            </details>
            <div v-if="!selected.candidates.length" class="empty-state audit-empty"><span><FileSearch :size="21" /></span><p>本次回答没有候选快照</p></div>
          </section>
          <section v-if="selected.tool_runs.length" class="audit-tools"><h3>工具耗时</h3><div v-for="tool in selected.tool_runs" :key="tool.tool_name" class="audit-tool-row"><span><Clock3 :size="14" />{{ toolLabel(tool.tool_name) }}</span><strong>{{ tool.duration_ms }} ms</strong><small :class="tool.status.toLowerCase()">{{ tool.error_message || tool.status }}</small></div></section>
        </div>
      </article>
      <div v-else class="audit-detail-placeholder"><FileSearch :size="30" /><p>选择一条记录查看检索详情</p></div>
    </section>
  </div>
</template>
