import type { DocsIndexResponse, DocsSearchResponse } from './types'

const env = import.meta.env as Record<string, string | undefined>

export const API_BASE = env.VITE_API_URL || env.NEXT_PUBLIC_API_URL || ''

export function encodePathSegments(path: string): string {
  return path
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/')
}

export async function fetchDocsIndex(): Promise<DocsIndexResponse> {
  const response = await fetch(`${API_BASE}/api/v1/docs/index`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch docs index: ${response.statusText}`)
  }

  return response.json()
}

export async function searchDocs(query: string, limit = 20): Promise<DocsSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const response = await fetch(`${API_BASE}/api/v1/docs/search?${params.toString()}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`Failed to search docs: ${response.statusText}`)
  }

  return response.json()
}

export async function fetchDocContent(filePath: string): Promise<string> {
  const encoded = encodePathSegments(filePath)
  const response = await fetch(`${API_BASE}/api/v1/docs/${encoded}`, {
    method: 'GET',
    headers: { Accept: 'text/markdown' },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch document: ${response.statusText}`)
  }

  return response.text()
}

export function getDocAssetUrl(assetPath: string): string {
  const encoded = encodePathSegments(assetPath)
  return `${API_BASE}/api/v1/docs/assets/${encoded}`
}
