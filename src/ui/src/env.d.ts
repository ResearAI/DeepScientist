export {}

declare module '*.md?raw' {
  const content: string
  export default content
}

declare global {
  interface Window {
    __DEEPSCIENTIST_RUNTIME__?: {
      surface?: string
      version?: string
      homePath?: string
      auth?: {
        enabled?: boolean
        tokenQueryParam?: string
        storageKey?: string
      }
      supports?: {
        productApis?: boolean
        socketIo?: boolean
        notifications?: boolean
        points?: boolean
        arxiv?: boolean
        cliFrontend?: boolean
      }
    }
  }
}
