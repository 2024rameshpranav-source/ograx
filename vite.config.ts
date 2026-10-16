import path from "node:path"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: Number(process.env.PORT || 5173),
  },
  preview: {
    host: "0.0.0.0",
    port: Number(process.env.PORT || 4173),
  },
  build: {
    sourcemap: true,
  },
})
