import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://localhost:8000',
      '/repos': 'http://localhost:8000',
      '/reviews': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
