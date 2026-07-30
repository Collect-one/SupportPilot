<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CheckCircle2, ClipboardPlus, LoaderCircle, MessageSquare, Plus, RotateCcw, Send, X } from '@lucide/vue'
import { api } from '../api'
import type { Ticket } from '../types'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tickets = ref<Ticket[]>([])
const active = ref<Ticket | null>(null)
const loading = ref(true)
const error = ref('')
const showCreate = ref(false)
const comment = ref('')
const submitting = ref(false)
const idempotencyKey = ref(crypto.randomUUID())
const form = ref({ title: '', description: '', product_module: '其他', category: 'OTHER', priority: 'NORMAL', workspace_id: '', environment: '', error_code: '', reproduction_steps: '', business_impact: '' })

const openCount = computed(() => tickets.value.filter(ticket => !['RESOLVED', 'CLOSED'].includes(ticket.status)).length)

async function load() {
  loading.value = true
  try {
    tickets.value = await api<Ticket[]>('/tickets')
    const routeId = typeof route.params.ticketId === 'string' ? route.params.ticketId : null
    if (routeId && active.value?.id !== routeId) active.value = await api<Ticket>(`/tickets/${routeId}`)
    if (active.value) active.value = await api<Ticket>(`/tickets/${active.value.id}`)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function openTicket(ticket: Ticket) {
  active.value = await api<Ticket>(`/tickets/${ticket.id}`)
  router.replace({ name: 'tickets', params: { ticketId: ticket.id } })
}

async function createTicket() {
  submitting.value = true
  error.value = ''
  try {
    const ticket = await api<Ticket>('/tickets', {
      method: 'POST',
      body: JSON.stringify({ ...form.value, idempotency_key: idempotencyKey.value }),
    })
    showCreate.value = false
    form.value = { title: '', description: '', product_module: '其他', category: 'OTHER', priority: 'NORMAL', workspace_id: '', environment: '', error_code: '', reproduction_steps: '', business_impact: '' }
    idempotencyKey.value = crypto.randomUUID()
    await load()
    await openTicket(ticket)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '工单创建失败'
  } finally {
    submitting.value = false
  }
}

async function addComment() {
  if (!active.value || !comment.value.trim()) return
  active.value = await api<Ticket>(`/tickets/${active.value.id}/comments`, {
    method: 'POST',
    body: JSON.stringify({ content: comment.value }),
  })
  comment.value = ''
  await load()
}

async function changeStatus(status: string) {
  if (!active.value) return
  active.value = await api<Ticket>(`/tickets/${active.value.id}`, { method: 'PATCH', body: JSON.stringify({ status }) })
  await load()
}

function statusLabel(status: string) {
  return { OPEN: '待处理', IN_PROGRESS: '处理中', WAITING_CUSTOMER: '待你补充', RESOLVED: '已解决', CLOSED: '已关闭' }[status] || status
}
function categoryLabel(category: string) {
  return { ACCOUNT: '账号', CONFIG: '产品配置', API: 'API / 集成', BILLING: '计费', INCIDENT: '故障', FEATURE: '功能建议', OTHER: '其他' }[category] || category
}
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
  <div class="page-stack">
    <section class="page-heading">
      <div><p class="eyebrow">客户支持</p><h2>我的工单</h2><p>查看人工支持进度，或不经过 Agent 直接提交问题。</p></div>
      <button class="primary-button" @click="showCreate = true"><Plus :size="17" />提交工单</button>
    </section>
    <div class="summary-strip"><div><strong>{{ tickets.length }}</strong><span>全部工单</span></div><div><strong>{{ openCount }}</strong><span>进行中</span></div><div><strong>{{ tickets.filter(t => t.status === 'RESOLVED').length }}</strong><span>待确认解决</span></div></div>
    <p v-if="error" class="form-error">{{ error }}</p>
    <section class="tickets-workspace" :class="{ 'detail-open': active }">
      <div class="ticket-list-panel">
        <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载工单</div>
        <button v-for="ticket in tickets" :key="ticket.id" class="ticket-row" :class="{ active: active?.id === ticket.id }" @click="openTicket(ticket)">
          <div class="ticket-row-top"><span class="ticket-number">{{ ticket.number }}</span><span :class="['status-pill', ticket.status.toLowerCase()]">{{ statusLabel(ticket.status) }}</span></div>
          <strong>{{ ticket.title }}</strong><p>{{ ticket.description }}</p>
          <div class="ticket-row-meta"><span>{{ categoryLabel(ticket.category) }}</span><span>{{ formatDate(ticket.updated_at) }}</span></div>
        </button>
        <div v-if="!loading && !tickets.length" class="empty-state compact-empty"><span><ClipboardPlus :size="23" /></span><h3>还没有工单</h3><p>需要人工协助时可以直接提交。</p></div>
      </div>
      <article v-if="active" class="ticket-detail">
        <header><button class="icon-button detail-back" title="返回列表" @click="active = null; router.replace({ name: 'tickets' })"><ArrowLeft :size="19" /></button><div><span class="ticket-number">{{ active.number }}</span><h2>{{ active.title }}</h2></div><span :class="['status-pill', active.status.toLowerCase()]">{{ statusLabel(active.status) }}</span></header>
        <div class="ticket-facts"><div><span>产品模块</span><strong>{{ active.product_module }}</strong></div><div><span>分类</span><strong>{{ categoryLabel(active.category) }}</strong></div><div><span>处理人</span><strong>{{ active.assignee_name || '等待认领' }}</strong></div><div><span>更新时间</span><strong>{{ formatDate(active.updated_at) }}</strong></div></div>
        <section class="ticket-description"><h3>问题描述</h3><p>{{ active.description }}</p><dl v-if="active.workspace_id || active.error_code"><template v-if="active.workspace_id"><dt>工作空间</dt><dd>{{ active.workspace_id }}</dd></template><template v-if="active.error_code"><dt>错误码</dt><dd>{{ active.error_code }}</dd></template></dl></section>
        <section class="event-timeline"><h3>处理记录</h3><article v-for="event in active.events" :key="event.id"><span class="timeline-dot"></span><div><header><strong>{{ event.author_name || '系统' }}</strong><time>{{ formatDate(event.created_at) }}</time></header><p>{{ event.content }}</p></div></article></section>
        <footer class="ticket-reply">
          <div class="ticket-actions"><button v-if="active.status === 'RESOLVED'" class="secondary-button" @click="changeStatus('OPEN')"><RotateCcw :size="16" />重新打开</button><button v-if="active.status === 'RESOLVED'" class="primary-button" @click="changeStatus('CLOSED')"><CheckCircle2 :size="16" />确认关闭</button><button v-if="active.status === 'CLOSED'" class="secondary-button" @click="changeStatus('OPEN')"><RotateCcw :size="16" />重新打开</button></div>
          <div class="reply-composer"><textarea v-model="comment" rows="2" placeholder="补充信息或回复人工支持"></textarea><button title="发送回复" :disabled="!comment.trim()" @click="addComment"><Send :size="17" /></button></div>
        </footer>
      </article>
    </section>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false">
      <form class="modal-panel ticket-form" @submit.prevent="createTicket">
        <header><div><p class="eyebrow">人工支持</p><h2>提交技术工单</h2></div><button type="button" class="icon-button" title="关闭" @click="showCreate = false"><X :size="19" /></button></header>
        <label class="full-span">标题<input v-model="form.title" required minlength="3" placeholder="简要概括问题" /></label>
        <label class="full-span">问题描述<textarea v-model="form.description" required minlength="5" rows="4" placeholder="说明发生了什么，以及你已经尝试过的操作"></textarea></label>
        <label>产品模块<input v-model="form.product_module" /></label>
        <label>问题分类<select v-model="form.category"><option value="ACCOUNT">账号</option><option value="CONFIG">产品配置</option><option value="API">API / 集成</option><option value="BILLING">计费</option><option value="INCIDENT">故障</option><option value="FEATURE">功能建议</option><option value="OTHER">其他</option></select></label>
        <label>工作空间编号<input v-model="form.workspace_id" placeholder="可选" /></label>
        <label>错误码<input v-model="form.error_code" placeholder="可选" /></label>
        <p class="form-safety full-span">请勿提交密码、完整 API Key、银行卡或身份证信息。</p>
        <footer class="full-span"><button type="button" class="ghost-button" @click="showCreate = false">取消</button><button class="primary-button" type="submit" :disabled="submitting"><LoaderCircle v-if="submitting" class="spin" :size="17" /><MessageSquare v-else :size="17" />提交工单</button></footer>
      </form>
    </div>
  </div>
</template>
