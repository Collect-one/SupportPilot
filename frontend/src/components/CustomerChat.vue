<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronRight,
  ClipboardCheck,
  LoaderCircle,
  Menu,
  MessageSquarePlus,
  Plus,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from '@lucide/vue'
import { api } from '../api'
import type { ActionProposal, Conversation, Message, Ticket } from '../types'

const emit = defineEmits<{ 'open-tickets': [ticketId?: string] }>()
const route = useRoute()
const router = useRouter()
const conversations = ref<Conversation[]>([])
const active = ref<Conversation | null>(null)
const input = ref('')
const sending = ref(false)
const error = ref('')
const confirming = ref(false)
const confirmedTickets = ref<Record<string, Ticket>>({})
const feedbackSent = ref<Record<string, boolean>>({})
const feedbackReasonFor = ref<string | null>(null)
const feedbackReason = ref('ANSWER_INCOMPLETE')
const feedbackSubmitting = ref<Record<string, boolean>>({})
const feedbackErrors = ref<Record<string, string>>({})
const conversationDrawerOpen = ref(false)
const thread = ref<HTMLElement | null>(null)

const starters = ['API 返回 40103 是什么意思？', '工作流为什么没有被触发？', 'Webhook 签名失败怎么排查？']

async function loadConversations(selectFirst = true) {
  conversations.value = await api<Conversation[]>('/conversations')
  const routeId = typeof route.params.conversationId === 'string' ? route.params.conversationId : null
  if (selectFirst && routeId) await selectConversation(routeId)
  else if (selectFirst && conversations.value.length && !active.value) await selectConversation(conversations.value[0].id)
}

async function selectConversation(id: string) {
  active.value = await api<Conversation>(`/conversations/${id}`)
  conversationDrawerOpen.value = false
  if (route.params.conversationId !== id) router.replace({ name: 'chat', params: { conversationId: id } })
  await nextTick()
  thread.value?.scrollTo({ top: thread.value.scrollHeight })
}

async function newConversation() {
  const conversation = await api<Conversation>('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: '新对话' }),
  })
  await loadConversations(false)
  await selectConversation(conversation.id)
}

async function send(content = input.value) {
  if (!content.trim() || sending.value) return
  if (!active.value) await newConversation()
  sending.value = true
  error.value = ''
  input.value = ''
  try {
    await api(`/conversations/${active.value!.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
    await selectConversation(active.value!.id)
    await loadConversations(false)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '消息发送失败'
    input.value = content
  } finally {
    sending.value = false
  }
}

async function confirmProposal(proposal: ActionProposal) {
  confirming.value = true
  error.value = ''
  try {
    confirmedTickets.value[proposal.id] = await api<Ticket>(`/action-proposals/${proposal.id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ payload: proposal.payload }),
    })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '工单创建失败'
  } finally {
    confirming.value = false
  }
}

async function feedback(message: Message, resolved: boolean, reason: string | null = null) {
  feedbackSubmitting.value[message.id] = true
  feedbackErrors.value[message.id] = ''
  try {
    await api(`/messages/${message.id}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ resolved, reason }),
    })
    feedbackSent.value[message.id] = true
    feedbackReasonFor.value = null
  } catch (cause) {
    feedbackErrors.value[message.id] = cause instanceof Error ? cause.message : '反馈提交失败，请重试'
  } finally {
    feedbackSubmitting.value[message.id] = false
  }
}

function openFeedbackReason(messageId: string) {
  feedbackReason.value = 'ANSWER_INCOMPLETE'
  feedbackErrors.value[messageId] = ''
  feedbackReasonFor.value = messageId
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

function statusLabel(status: string | null) {
  return {
    NEEDS_CLARIFICATION: '需要补充信息',
    ACTION_PROPOSED: '建议转人工',
    UNRESOLVED: '无法可靠确认',
    TOOL_RESULT: '工单查询结果',
    ERROR: '服务异常',
  }[status || ''] || ''
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

onMounted(async () => {
  try {
    await loadConversations()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载失败'
  }
})

watch(
  () => route.params.conversationId,
  async (conversationId) => {
    if (typeof conversationId === 'string') {
      if (active.value?.id !== conversationId) await selectConversation(conversationId)
    } else {
      active.value = null
    }
  },
)
</script>

<template>
  <div class="chat-layout">
    <aside class="conversation-rail" :class="{ 'mobile-open': conversationDrawerOpen }">
      <button class="secondary-button new-chat" @click="newConversation"><Plus :size="17" />新对话</button>
      <p class="rail-label">最近对话</p>
      <div class="conversation-list">
        <button
          v-for="conversation in conversations"
          :key="conversation.id"
          :class="{ active: active?.id === conversation.id }"
          @click="selectConversation(conversation.id)"
        >
          <span>{{ conversation.title }}</span>
          <small>{{ new Date(conversation.updated_at).toLocaleDateString('zh-CN') }}</small>
        </button>
        <p v-if="!conversations.length" class="empty-rail">还没有对话记录</p>
      </div>
      <button class="direct-ticket-link" @click="emit('open-tickets')"><ClipboardCheck :size="16" />直接提交工单<ChevronRight :size="15" /></button>
    </aside>
    <button v-if="conversationDrawerOpen" class="conversation-overlay" title="关闭会话列表" @click="conversationDrawerOpen = false"></button>

    <section class="chat-panel">
      <header class="chat-header">
        <button class="icon-button conversation-menu" title="打开会话列表" @click="conversationDrawerOpen = true"><Menu :size="19" /></button>
        <div><h2>{{ active?.title || '智能技术支持' }}</h2><p><span class="live-dot"></span>在线技术支持</p></div>
      </header>

      <div ref="thread" class="message-thread">
        <div v-if="!active?.messages?.length" class="chat-empty">
          <span class="empty-icon"><Sparkles :size="25" /></span>
          <h2>今天遇到了什么问题？</h2>
          <p>描述你遇到的产品问题；如果无法直接解决，可以转交人工支持。</p>
          <div class="starter-grid">
            <button v-for="starter in starters" :key="starter" @click="send(starter)"><BookOpen :size="16" /><span>{{ starter }}</span><ChevronRight :size="15" /></button>
          </div>
        </div>

        <article v-for="message in active?.messages || []" :key="message.id" class="message" :class="message.role.toLowerCase()">
          <div v-if="message.role === 'ASSISTANT'" class="assistant-avatar"><Sparkles :size="16" /></div>
          <div class="message-body">
            <div class="message-meta">
              <strong>{{ message.role === 'USER' ? '你' : 'SupportPilot' }}</strong>
              <span v-if="message.status && message.status !== 'ANSWERED'" :class="['answer-status', message.status.toLowerCase()]">{{ statusLabel(message.status) }}</span>
              <time>{{ formatTime(message.created_at) }}</time>
            </div>
            <p class="message-content">{{ message.content }}</p>
            <section v-if="message.action_proposal && !message.action_proposal.confirmed_ticket_id && !confirmedTickets[message.action_proposal.id]" class="action-proposal">
              <div class="proposal-heading"><span><ClipboardCheck :size="18" /></span><div><strong>转交人工支持</strong><p>提交前可以检查并修改工单内容</p></div></div>
              <label>标题<input v-model="message.action_proposal.payload.title" /></label>
              <label>问题描述<textarea v-model="message.action_proposal.payload.description" rows="3"></textarea></label>
              <div class="form-row"><label>产品模块<input v-model="message.action_proposal.payload.product_module" /></label><label>错误码<input v-model="message.action_proposal.payload.error_code" placeholder="可选" /></label></div>
              <button class="primary-button" :disabled="confirming" @click="confirmProposal(message.action_proposal)"><LoaderCircle v-if="confirming" class="spin" :size="17" /><Check v-else :size="17" />确认创建工单</button>
            </section>
            <section v-if="message.action_proposal && (message.action_proposal.confirmed_ticket_number || confirmedTickets[message.action_proposal.id])" class="ticket-created">
              <span><Check :size="18" /></span><div><strong>工单 {{ message.action_proposal.confirmed_ticket_number || confirmedTickets[message.action_proposal.id]?.number }} 已创建</strong><p>人工支持可以看到本次对话上下文。</p></div><button @click="emit('open-tickets', message.action_proposal.confirmed_ticket_id || confirmedTickets[message.action_proposal.id]?.id)">查看工单</button>
            </section>
            <div v-if="message.status === 'ANSWERED'" class="answer-feedback">
              <template v-if="!feedbackSent[message.id] && feedbackReasonFor !== message.id"><span>这解决了你的问题吗？</span><button title="已解决" :disabled="feedbackSubmitting[message.id]" @click="feedback(message, true)"><ThumbsUp :size="15" /></button><button title="未解决" :disabled="feedbackSubmitting[message.id]" @click="openFeedbackReason(message.id)"><ThumbsDown :size="15" /></button></template>
              <template v-else-if="!feedbackSent[message.id]"><select v-model="feedbackReason" aria-label="未解决原因"><option value="ANSWER_INCOMPLETE">回答不完整</option><option value="STEPS_DID_NOT_WORK">排查步骤无效</option><option value="CITATION_IRRELEVANT">回答与问题不相关</option><option value="NEED_HUMAN">需要人工处理</option></select><button class="secondary-button" :disabled="feedbackSubmitting[message.id]" @click="feedback(message, false, feedbackReason)"><LoaderCircle v-if="feedbackSubmitting[message.id]" class="spin" :size="14" />提交</button></template>
              <span v-else class="feedback-confirmed"><Check :size="14" />反馈已记录</span>
              <span v-if="feedbackErrors[message.id]" class="feedback-error">{{ feedbackErrors[message.id] }}</span>
            </div>
          </div>
        </article>
        <article v-if="sending" class="message assistant pending-message"><div class="assistant-avatar"><Sparkles :size="16" /></div><div class="message-body"><LoaderCircle class="spin" :size="18" /><span>正在核对官方资料</span></div></article>
      </div>

      <footer class="composer-area">
        <p v-if="error" class="inline-error">{{ error }}</p>
        <div class="composer">
          <textarea v-model="input" rows="1" placeholder="描述问题，请勿发送密码或完整 API Key" :disabled="sending" @keydown="handleKeydown"></textarea>
          <button class="send-button" title="发送消息" :disabled="!input.trim() || sending" @click="send()"><ArrowUp :size="19" /></button>
        </div>
        <small>请勿发送密码、完整 API Key 或其他敏感信息。</small>
      </footer>
    </section>

  </div>
</template>
