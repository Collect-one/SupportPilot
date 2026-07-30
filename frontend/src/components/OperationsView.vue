<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, BellOff, CheckCircle2, Clock3, LoaderCircle, RefreshCw, SearchX, Wrench } from '@lucide/vue'
import { api } from '../api'

interface ToolRun { id: string; tool_name: string; status: string; duration_ms: number; error_message: string | null; created_at: string }
interface Notification { id: string; ticket_id: string; status: string; attempt_count: number; error_message: string | null; created_at: string }
const tools = ref<ToolRun[]>([])
const notifications = ref<Notification[]>([])
const loading = ref(true)
const tab = ref<'tools' | 'notifications'>('tools')
const resendingTickets = ref<Set<string>>(new Set())
const failedTools = computed(() => tools.value.filter(item => item.status === 'FAILED').length)
const average = computed(() => tools.value.length ? Math.round(tools.value.reduce((sum, item) => sum + item.duration_ms, 0) / tools.value.length) : 0)
async function load() { loading.value = true; try { const data = await api<{ tool_runs: ToolRun[]; notifications: Notification[] }>('/support/operations'); tools.value = data.tool_runs; notifications.value = data.notifications } finally { loading.value = false } }
function canResend(item: Notification) {
  if (item.status !== 'FAILED' || resendingTickets.value.has(item.ticket_id)) return false
  const latest = notifications.value
    .filter(candidate => candidate.ticket_id === item.ticket_id)
    .sort((left, right) => right.attempt_count - left.attempt_count)[0]
  return latest?.id === item.id
}
async function resend(item: Notification) {
  if (!canResend(item)) return
  resendingTickets.value = new Set(resendingTickets.value).add(item.ticket_id)
  try {
    await api(`/tickets/${item.ticket_id}/notify?source_notification_id=${item.id}`, { method: 'POST' })
    await load()
  } finally {
    const pending = new Set(resendingTickets.value)
    pending.delete(item.ticket_id)
    resendingTickets.value = pending
  }
}
function toolLabel(value: string) { return { search_knowledge: '检索知识库', propose_ticket: '生成工单建议', get_ticket_status: '查询工单状态' }[value] || value }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value)) }
onMounted(load)
</script>

<template>
  <div class="page-stack"><section class="page-heading"><div><p class="eyebrow">可观测性</p><h2>运行记录</h2><p>只展示可审计的工具输入输出状态，不展示模型隐藏推理。</p></div><button class="secondary-button" @click="load"><RefreshCw :size="16" />刷新</button></section>
    <div class="operations-summary"><div><span><Activity :size="18" /></span><div><strong>{{ tools.length }}</strong><small>最近工具调用</small></div></div><div><span><Clock3 :size="18" /></span><div><strong>{{ average }} ms</strong><small>平均工具耗时</small></div></div><div><span><SearchX :size="18" /></span><div><strong>{{ failedTools }}</strong><small>失败调用</small></div></div><div><span><BellOff :size="18" /></span><div><strong>{{ notifications.filter(n => n.status === 'FAILED').length }}</strong><small>通知失败</small></div></div></div>
    <section class="operations-panel"><header><div class="segmented-control"><button :class="{ active: tab === 'tools' }" @click="tab = 'tools'"><Wrench :size="15" />工具调用</button><button :class="{ active: tab === 'notifications' }" @click="tab = 'notifications'"><BellOff :size="15" />通知记录</button></div></header><div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22" />正在加载运行记录</div>
      <div v-else-if="tab === 'tools'" class="operations-list"><article v-for="item in tools" :key="item.id"><span :class="['operation-icon', item.status.toLowerCase()]"><CheckCircle2 v-if="item.status === 'SUCCESS'" :size="18" /><SearchX v-else :size="18" /></span><div><strong>{{ toolLabel(item.tool_name) }}</strong><p>{{ item.error_message || '调用完成，输入输出摘要已记录' }}</p></div><span :class="['run-status', item.status.toLowerCase()]">{{ item.status }}</span><time>{{ item.duration_ms }} ms · {{ formatDate(item.created_at) }}</time></article><div v-if="!tools.length" class="empty-state compact-empty"><span><Activity :size="23" /></span><h3>暂无工具调用</h3><p>客户开始对话后，检索和工单工具记录会显示在这里。</p></div></div>
      <div v-else class="operations-list"><article v-for="item in notifications" :key="item.id"><span :class="['operation-icon', item.status.toLowerCase()]"><CheckCircle2 v-if="item.status === 'SENT'" :size="18" /><BellOff v-else :size="18" /></span><div><strong>飞书工单通知 · 第 {{ item.attempt_count }} 次</strong><p>{{ item.error_message || '通知已成功发送' }}</p></div><button v-if="item.status === 'FAILED'" class="secondary-button" :disabled="!canResend(item)" @click="resend(item)"><LoaderCircle v-if="resendingTickets.has(item.ticket_id)" class="spin" :size="14" /><RefreshCw v-else :size="14" />重发</button><span v-else :class="['run-status', item.status.toLowerCase()]">{{ item.status }}</span><time>{{ formatDate(item.created_at) }}</time></article><div v-if="!notifications.length" class="empty-state compact-empty"><span><BellOff :size="23" /></span><h3>暂无通知记录</h3><p>工单创建或重开后会产生通知记录。</p></div></div>
    </section>
  </div>
</template>
