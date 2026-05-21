import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const SERVER_IP = process.env.VITE_API_SERVER_IP || '127.0.0.1'
const SERVER_PORT = process.env.VITE_API_SERVER_PORT || '60801'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    host: '0.0.0.0',
    port: 61088,
    proxy: {
      '/api': {
        target: `http://${SERVER_IP}:${SERVER_PORT}`,
        changeOrigin: true
      }
    }
  }
})
