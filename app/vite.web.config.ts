// Interface no navegador, sem Electron, para desenvolver e testar a UI contra um
// motor rodando com `clipator serve --token dev`. Abra http://localhost:5173/?porta=8765&token=dev
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  plugins: [react()],
  server: { port: 5173, strictPort: true }
})
