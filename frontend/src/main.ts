import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/fold.css'
import { initTheme } from './composables/theme'

initTheme()
createApp(App).use(createPinia()).use(router).mount('#app')
