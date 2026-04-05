import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const uiRoot = path.resolve(__dirname, '..')
const publicDir = path.join(uiRoot, 'public')
const distDir = path.join(uiRoot, 'dist')

if (!fs.existsSync(publicDir)) {
  process.exit(0)
}

fs.mkdirSync(distDir, { recursive: true })
fs.cpSync(publicDir, distDir, {
  recursive: true,
  force: true,
})
