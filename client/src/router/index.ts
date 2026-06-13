import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/LandingView.vue'),
    },
    {
      path: '/auth/callback',
      name: 'auth-callback',
      component: () => import('@/views/AuthCallbackView.vue'),
    },
    {
      path: '/connected',
      name: 'connected',
      component: () => import('@/views/ConnectedView.vue'),
      meta: { requiresAuth: true },
    },
    // Email/password views are kept as a fallback but are not part of the primary flow.
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // If user has a token but we haven't fetched their profile yet, try it
  if (auth.token && !auth.user) {
    try {
      await auth.fetchUser()
    } catch {
      // token is invalid, fetchUser already calls logout
    }
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'home' }
  }

  if ((to.name === 'login' || to.name === 'register') && auth.isAuthenticated) {
    return { name: 'connected' }
  }
})

export default router
