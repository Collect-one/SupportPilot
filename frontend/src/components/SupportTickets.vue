<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CheckCircle2, Inbox, LoaderCircle, Send, UserCheck } from '@lucide/vue'
import { api } from '../api'
import type { Ticket } from '../types'

interface Organization { id: string; name: string; slug: string }
const route = useRoute()
const router = useRouter()
const tickets = ref<Ticket[]>([])
const organizations = ref<Organization[]>([])
const active = ref<Ticket | null>(null)
const overview = ref({ ticket_counts: { OPEN: 0, IN_PROGRESS: 0, WAITING_CUSTOMER: 0, RESOLVED: 0 }, published_documents: 0, failed_notifications: 0 })
const loading = ref(true)
const actionLoading = ref(false)
const error = ref('')
const filters = ref({ status: '', priority: '', category: '', organization: '' })
const reply = ref('')

const filtered = computed(() => tickets.value.filter(ticket =>
  (!filters.value.status || ticket.status === filters.value.status) &&
  (!filters.value.priority || ticket.priority === filters.value.priority) &&
  (!filters.value.category || ticket.category === filters.value.category) &&
  (!filters.value.organization || ticket.organization_id === filters.value.organization),
))

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[tickets.value, overview.value, organizations.value] = await Promise.all([
      api<Ticket[]>('/tickets'),
      api<typeof overview.value>('/support/overview'),
      api<Organization[]>('/support/organizations'),
    ])
    const routeId = typeof route.params.ticketId === 'string' ? route.params.ticketId : null
    if (routeId) active.value = await api<Ticket>(`/tickets/${routeId}`)
    else if (active.value) active.value = await api<Ticket>(`/tickets/${active.value.id}`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载失败'
  } finally { loading.value = false }
}
async function openTicket(ticket: Ticket) {
  active.value = await api<Ticket>(`/tickets/${ticket.id}`)
  router.replace({ name: 'support-tickets', params: { ticketId: ticket.id } })
}
function closeTicket() {
  active.value = null
  router.replace({ name: 'support-tickets' })
}
async function claim() {
  if (!active.value) return
  actionLoading.value = true
  try { active.value = await api<Ticket>(`/tickets/${active.value.id}/claim`, { method: 'POST' }); await load() }
  finally { actionLoading.value = false }
}
async function update(fields: Record<string, unknown>) {
  if (!active.value) return
  actionLoading.value = true
  error.value = ''
  try {
    active.value = await api<Ticket>(`/tickets/${active.value.id}`, { method: 'PATCH', body: JSON.stringify(fields) })
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '更新失败' }
  finally { actionLoading.value = false }
}
async function addReply() {
  if (!active.value || !reply.value.trim()) return
  active.value = await api<Ticket>(`/tickets/${active.value.id}/comments`, { method: 'POST', body: JSON.stringify({ content: reply.value }) })
  reply.value = ''
  await load()
}
function statusLabel(status: string) { return { OPEN: '待处理', IN_PROGRESS: '处理中', WAITING_CUSTOMER: '待客户补充', RESOLVED: '已解决', CLOSED: '已关闭' }[status] || status }
function categoryLabel(category: string) { return { ACCOUNT: '账号', CONFIG: '产品配置', API: 'API / 集成', BILLING: '计费', INCIDENT: '故障', FEATURE: '功能建议', OTHER: '其他' }[category] || category }
function priorityLabel(priority: string) { return { LOW: '低', NORMAL: '普通', HIGH: '高' }[priority] || priority }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
onMounted(load)
watch(
  () => route.params.ticketId,
  async (ticketId) => {
    if (typeof ticketId === 'string') {
      if (active.value?.id !== ticketId) active.value = await api<Ticket>(`/tickets/${ticketId}`)
    } else {
      active.value = null
    }
  },
)
</script>

<template>
  <div class="page-stack support-page">
    <section class="page-heading"><div><p class="eyebrow">人工支持</p><h2>工单队列</h2><p>优先处理影响客户业务的问题，所有操作都会写入审计记录。</p></div></section>
    <div class="metric-grid">
      <button v-for="status in ['OPEN','IN_PROGRESS','WAITING_CUSTOMER','RESOLVED']" :key="status" :class="{ active: filters.status === status }" @click="filters.status = filters.status === status ? '' : status"><span>{{ statusLabel(status) }}</span><strong>{{ overview.ticket_counts[status as keyof typeof overview.ticket_counts] }}</strong><small>{{ status === 'OPEN' ? '等待认领' : status === 'WAITING_CUSTOMER' ? '等待上下文' : '查看队列' }}</small></button>
    </div>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="support-filters">
      <label>企业<select v-model="filters.organization"><option value="">全部企业</option><option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
      <label>分类<select v-model="filters.category"><option value="">全部分类</option><option v-for="category in ['ACCOUNT','CONFIG','API','BILLING','INCIDENT','FEATURE','OTHER']" :key="category" :value="category">{{ categoryLabel(category) }}</option></select></label>
      <label>优先级<select v-model="filters.priority"><option value="">全部优先级</option><option value="HIGH">高</option><option value="NORMAL">普通</option><option value="LOW">低</option></select></label>
      <label>状态<select v-model="filters.status"><option value="">全部状态</option><option v-for="status in ['OPEN','IN_PROGRESS','WAITING_CUSTOMER','RESOLVED','CLOSED']" :key="status" :value="status">{{ statusLabel(status) }}</option></select></label>
    </div>
    <section class="support-workspace" :class="{ 'detail-open': active }">
      <div class="queue-panel">
        <header class="queue-toolbar"><div><strong>{{ filtered.length }} 个工单</strong><span>按更新时间排序</span></div></header>
        <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载队列</div>
        <button v-for="ticket in filtered" :key="ticket.id" class="queue-row" :class="{ active: active?.id === ticket.id }" @click="openTicket(ticket)">
          <div class="queue-priority" :class="ticket.priority.toLowerCase()"></div>
          <div class="queue-main"><div><span class="ticket-number">{{ ticket.number }}</span><span :class="['status-pill', ticket.status.toLowerCase()]">{{ statusLabel(ticket.status) }}</span></div><strong>{{ ticket.title }}</strong><p>{{ ticket.organization_name }} · {{ ticket.customer_name }} · {{ ticket.product_module }}</p></div>
          <div class="queue-end"><span :class="['priority-label', ticket.priority.toLowerCase()]">{{ priorityLabel(ticket.priority) }}</span><time>{{ formatDate(ticket.updated_at) }}</time></div>
        </button>
        <div v-if="!loading && !filtered.length" class="empty-state compact-empty"><span><Inbox :size="23" /></span><h3>当前筛选下没有工单</h3><p>调整筛选条件后再查看。</p></div>
      </div>
      <article v-if="active" class="support-detail">
        <header class="support-detail-header"><button class="icon-button detail-back" title="返回队列" @click="closeTicket"><ArrowLeft :size="19" /></button><div><span class="ticket-number">{{ active.number }}</span><h2>{{ active.title }}</h2><p>{{ active.organization_name }} · {{ active.customer_name }}</p></div><span :class="['status-pill', active.status.toLowerCase()]">{{ statusLabel(active.status) }}</span></header>
        <div class="support-detail-actions">
          <button v-if="!active.assignee_id" class="primary-button" :disabled="actionLoading" @click="claim"><UserCheck :size="16" />认领并开始处理</button>
          <template v-else><button v-if="active.status === 'IN_PROGRESS'" class="secondary-button" @click="update({ status: 'WAITING_CUSTOMER' })">等待客户补充</button><button v-if="!['RESOLVED','CLOSED'].includes(active.status)" class="primary-button" @click="update({ status: 'RESOLVED' })"><CheckCircle2 :size="16" />标记已解决</button></template>
          <label class="inline-select">分类<select :value="active.category" @change="update({ category: ($event.target as HTMLSelectElement).value })"><option v-for="category in ['ACCOUNT','CONFIG','API','BILLING','INCIDENT','FEATURE','OTHER']" :key="category" :value="category">{{ categoryLabel(category) }}</option></select></label>
          <label class="inline-select">优先级<select :value="active.priority" @change="update({ priority: ($event.target as HTMLSelectElement).value })"><option value="LOW">低</option><option value="NORMAL">普通</option><option value="HIGH">高</option></select></label>
        </div>
        <div class="support-detail-scroll">
          <section class="case-summary"><h3>问题上下文</h3><p>{{ active.description }}</p><dl><div><dt>产品模块</dt><dd>{{ active.product_module }}</dd></div><div><dt>分类 / 优先级</dt><dd>{{ categoryLabel(active.category) }} / {{ priorityLabel(active.priority) }}</dd></div><div><dt>工作空间</dt><dd>{{ active.workspace_id || '未提供' }}</dd></div><div><dt>运行环境</dt><dd>{{ active.environment || '未提供' }}</dd></div><div><dt>错误码</dt><dd>{{ active.error_code || '未提供' }}</dd></div><div><dt>复现步骤</dt><dd>{{ active.reproduction_steps || '未提供' }}</dd></div><div><dt>业务影响</dt><dd>{{ active.business_impact || '未提供' }}</dd></div></dl></section>
          <section v-if="active.handoff_context" class="handoff-context">
            <h3>Agent 转人工上下文</h3>
            <div class="handoff-messages"><article v-for="message in active.handoff_context.recent_messages" :key="message.id"><strong>{{ message.role === 'USER' ? '客户' : 'Agent' }}</strong><span v-if="message.status">{{ message.status }}</span><p>{{ message.content }}</p></article></div>
            <details v-if="active.handoff_context.citations.length"><summary>查看 {{ active.handoff_context.citations.length }} 条 Agent 引用</summary><blockquote v-for="citation in active.handoff_context.citations" :key="citation.message_id + citation.document_name"><strong>{{ citation.document_name }} v{{ citation.version }}</strong><p>{{ citation.excerpt }}</p></blockquote></details>
            <details v-if="active.handoff_context.tool_runs.length"><summary>查看排查工具摘要</summary><article v-for="run in active.handoff_context.tool_runs" :key="run.tool_name + run.duration_ms" class="tool-run-detail"><strong>{{ run.tool_name }} · {{ run.status }} · {{ run.duration_ms }} ms</strong><p v-if="run.error" class="tool-error">{{ run.error }}</p><pre v-if="Object.keys(run.output).length">{{ JSON.stringify(run.output, null, 2) }}</pre></article></details>
          </section>
          <section class="event-timeline support-timeline"><h3>处理记录</h3><article v-for="event in active.events" :key="event.id"><span class="timeline-dot"></span><div><header><strong>{{ event.author_name || '系统' }}</strong><time>{{ formatDate(event.created_at) }}</time></header><p>{{ event.content }}</p></div></article></section>
        </div>
        <footer class="support-reply"><textarea v-model="reply" rows="2" placeholder="回复客户，说明下一步或处理结果"></textarea><button class="send-button" title="发送回复" :disabled="!reply.trim()" @click="addReply"><Send :size="18" /></button></footer>
      </article>
    </section>
  </div>
</template>
