import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_POKER_BACKEND ?? 'http://localhost:8002'
const backendWsTarget = backendTarget.replace(/^http/, 'ws')

export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/poker/api': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/poker/ws': {
        target: backendWsTarget,
        ws: true,
      },
      '/werewolf/api': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/werewolf/ws': {
        target: backendWsTarget,
        ws: true,
      },
    },
  },
})
