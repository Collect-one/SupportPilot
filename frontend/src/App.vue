<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from './components/AppShell.vue'
import CustomerChat from './components/CustomerChat.vue'
import CustomerTickets from './components/CustomerTickets.vue'
import KnowledgeView from './components/KnowledgeView.vue'
import LoginView from './components/LoginView.vue'
import OperationsView from './components/OperationsView.vue'
import SupportTickets from './components/SupportTickets.vue'
import { clearSession, getStoredUser, SESSION_EVENT, SESSION_SYNC_KEY } from './api'
import type { User } from './types'

const route = useRoute()
const router = useRouter()
const user = ref<User | null>(getStoredUser())
const view = computed(() => String(route.name || 'login'))
const titles: Record<string, string> = {
  chat: '智能支持',
  tickets: '我的工单',
  'support-tickets': '工单队列',
  knowledge: '知识库',
  operations: '运行记录',
}
const title = computed(() => titles[view.value] || 'SupportPilot')

function onSession(event: Event) {
  user.value = (event as CustomEvent<User | null>).detail
  if (!user.value) router.replace({ name: 'login' })
}
function onStorage(event: StorageEvent) {
  if (event.key !== SESSION_SYNC_KEY) return
  const previousUserId = user.value?.id
  user.value = getStoredUser()
  if (!user.value) {
    router.replace({ name: 'login' })
  } else if (user.value.id !== previousUserId) {
    router.replace({ name: user.value.role === 'SUPPORT' ? 'support-tickets' : 'chat' })
  }
}
function authenticated(nextUser: User) {
  user.value = nextUser
  router.replace({ name: nextUser.role === 'SUPPORT' ? 'support-tickets' : 'chat' })
}
function logout() { clearSession() }
function navigate(nextView: string) { router.push({ name: nextView }) }
function openCustomerTicket(ticketId?: string) {
  router.push({ name: 'tickets', params: ticketId ? { ticketId } : {} })
}

onMounted(() => {
  window.addEventListener(SESSION_EVENT, onSession)
  window.addEventListener('storage', onStorage)
})
onBeforeUnmount(() => {
  window.removeEventListener(SESSION_EVENT, onSession)
  window.removeEventListener('storage', onStorage)
})
</script>

<template>
  <LoginView v-if="!user" @authenticated="authenticated" />
  <AppShell v-else :key="user.id" :user="user" :view="view" :title="title" @navigate="navigate" @logout="logout">
    <CustomerChat v-if="view === 'chat'" @open-tickets="openCustomerTicket" />
    <CustomerTickets v-else-if="view === 'tickets'" />
    <SupportTickets v-else-if="view === 'support-tickets'" />
    <KnowledgeView v-else-if="view === 'knowledge'" />
    <OperationsView v-else-if="view === 'operations'" />
  </AppShell>
</template>
