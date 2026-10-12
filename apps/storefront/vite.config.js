import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { port: 5273, strictPort: true, proxy: { '/api': { target: process.env.COMMERCE_PROXY || 'http://127.0.0.1:19081', changeOrigin: true } } } })
