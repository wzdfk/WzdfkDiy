import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vueDevtools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(),
  vueDevtools({
    launchEditor: 'cursor',
  })
  ],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8300',
        changeOrigin: true,
      },
    },
  },
})
