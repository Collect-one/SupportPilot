<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight, CheckCircle2, KeyRound, LoaderCircle, ShieldCheck } from '@lucide/vue'
import { api, setSession } from '../api'
import type { User } from '../types'

const emit = defineEmits<{ authenticated: [user: User] }>()
const email = ref('alice@nova.test')
const password = ref('customer123')
const loading = ref(false)
const error = ref('')

function useDemo(role: 'customer' | 'support') {
  if (role === 'customer') {
    email.value = 'alice@nova.test'
    password.value = 'customer123'
  } else {
    email.value = 'support@flowpilot.test'
    password.value = 'support123'
  }
}

async function login() {
  loading.value = true
  error.value = ''
  try {
    const result = await api<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: email.value, password: password.value }),
    })
    setSession(result.access_token, result.user)
    emit('authenticated', result.user)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="brand-lockup">
        <span class="brand-mark"><ShieldCheck :size="22" /></span>
        <div><strong>SupportPilot</strong><small>B2B SaaS 技术支持</small></div>
      </div>
      <div class="login-copy">
        <p class="eyebrow">安全支持入口</p>
        <h1 id="login-title">登录支持中心</h1>
        <p>使用企业邀请账号获取技术支持，未解决问题可以转交人工处理。</p>
      </div>
      <form @submit.prevent="login" class="login-form">
        <label>邮箱<input v-model="email" type="email" autocomplete="username" required /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <button class="primary-button full-button" type="submit" :disabled="loading">
          <LoaderCircle v-if="loading" class="spin" :size="18" />
          <KeyRound v-else :size="18" />
          {{ loading ? '正在登录' : '进入支持中心' }}
          <ArrowRight v-if="!loading" :size="18" />
        </button>
      </form>
      <div class="demo-divider"><span>演示账号</span></div>
      <div class="demo-accounts">
        <button type="button" @click="useDemo('customer')">
          <span><CheckCircle2 :size="16" />客户账号</span><small>星海数据科技</small>
        </button>
        <button type="button" @click="useDemo('support')">
          <span><CheckCircle2 :size="16" />人工支持</span><small>工单与知识库</small>
        </button>
      </div>
      <p class="security-note"><ShieldCheck :size="14" />演示环境仅使用虚构企业与产品数据</p>
    </section>
  </main>
</template>
