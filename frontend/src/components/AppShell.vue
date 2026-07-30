<script setup lang="ts">
import { ref } from 'vue'
import {
  BookOpenText,
  BotMessageSquare,
  ClipboardList,
  LogOut,
  Menu,
  PanelLeftClose,
  ScrollText,
  Search,
  ShieldCheck,
  X,
} from '@lucide/vue'
import type { User } from '../types'

defineProps<{ user: User; view: string; title: string }>()
const emit = defineEmits<{ navigate: [view: string]; logout: [] }>()
const mobileOpen = ref(false)

function navigate(view: string) {
  emit('navigate', view)
  mobileOpen.value = false
}
</script>

<template>
  <div class="app-frame">
    <aside class="sidebar" :class="{ open: mobileOpen }">
      <div class="sidebar-brand">
        <span class="brand-mark compact"><ShieldCheck :size="19" /></span>
        <div><strong>SupportPilot</strong><small>{{ user.role === 'SUPPORT' ? '支持工作台' : '客户支持中心' }}</small></div>
        <button class="icon-button mobile-close" title="关闭导航" @click="mobileOpen = false"><X :size="19" /></button>
      </div>
      <nav class="sidebar-nav" aria-label="主导航">
        <template v-if="user.role === 'CUSTOMER'">
          <button :class="{ active: view === 'chat' }" @click="navigate('chat')"><BotMessageSquare :size="18" />智能支持</button>
          <button :class="{ active: view === 'tickets' }" @click="navigate('tickets')"><ClipboardList :size="18" />我的工单</button>
        </template>
        <template v-else>
          <button :class="{ active: view === 'support-tickets' }" @click="navigate('support-tickets')"><ClipboardList :size="18" />工单队列</button>
          <button :class="{ active: view === 'knowledge' }" @click="navigate('knowledge')"><BookOpenText :size="18" />知识库</button>
          <button :class="{ active: view === 'operations' }" @click="navigate('operations')"><ScrollText :size="18" />运行记录</button>
          <button :class="{ active: view === 'rag-audit' }" @click="navigate('rag-audit')"><Search :size="18" />RAG 验收</button>
        </template>
      </nav>
      <div class="sidebar-user">
        <span class="avatar">{{ user.display_name.slice(0, 1) }}</span>
        <div><strong>{{ user.display_name }}</strong><small>{{ user.organization_name || 'FlowPilot 支持团队' }}</small></div>
        <button class="icon-button" title="退出登录" @click="emit('logout')"><LogOut :size="17" /></button>
      </div>
    </aside>
    <div v-if="mobileOpen" class="sidebar-overlay" @click="mobileOpen = false"></div>
    <div class="app-main">
      <header class="topbar">
        <button class="icon-button menu-button" title="打开导航" @click="mobileOpen = true"><Menu :size="21" /></button>
        <div><p>SupportPilot /</p><h1>{{ title }}</h1></div>
        <span class="environment-badge"><span></span>演示环境</span>
      </header>
      <main class="content-area"><slot /></main>
    </div>
  </div>
</template>
