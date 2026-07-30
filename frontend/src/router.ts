import { createRouter, createWebHistory } from 'vue-router'
import { getStoredUser } from './api'

const routes = [
  { path: '/login', name: 'login', component: { template: '<span />' } },
  { path: '/chat/:conversationId?', name: 'chat', component: { template: '<span />' }, meta: { role: 'CUSTOMER' } },
  { path: '/tickets/:ticketId?', name: 'tickets', component: { template: '<span />' }, meta: { role: 'CUSTOMER' } },
  { path: '/support/tickets/:ticketId?', name: 'support-tickets', component: { template: '<span />' }, meta: { role: 'SUPPORT' } },
  { path: '/support/knowledge', name: 'knowledge', component: { template: '<span />' }, meta: { role: 'SUPPORT' } },
  { path: '/support/operations', name: 'operations', component: { template: '<span />' }, meta: { role: 'SUPPORT' } },
  { path: '/support/rag-audit', name: 'rag-audit', component: { template: '<span />' }, meta: { role: 'SUPPORT' } },
  { path: '/:pathMatch(.*)*', redirect: () => getStoredUser()?.role === 'SUPPORT' ? '/support/tickets' : '/chat' },
]

export const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const user = getStoredUser()
  if (!user && to.name !== 'login') return { name: 'login' }
  if (user && to.name === 'login') return user.role === 'SUPPORT' ? { name: 'support-tickets' } : { name: 'chat' }
  if (user && to.meta.role && to.meta.role !== user.role) {
    return user.role === 'SUPPORT' ? { name: 'support-tickets' } : { name: 'chat' }
  }
  return true
})
