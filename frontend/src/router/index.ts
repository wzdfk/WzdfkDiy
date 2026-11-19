import { createRouter, createWebHistory } from 'vue-router'
import StudioView from '../views/StudioView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/studio' },
    { path: '/studio', component: StudioView },
  ],
})

export default router
