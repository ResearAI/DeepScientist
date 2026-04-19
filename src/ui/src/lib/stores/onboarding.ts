import { create } from 'zustand'
import { useUILanguageStore } from '@/lib/stores/ui-language'

export type OnboardingLanguage = 'en' | 'zh'
export type OnboardingStatus = 'idle' | 'choosing_language' | 'running'

type OnboardingPersistence = {
  firstRunHandled: boolean
  completed: boolean
  neverRemind: boolean
  language: OnboardingLanguage | null
}

type OnboardingState = OnboardingPersistence & {
  hydrated: boolean
  status: OnboardingStatus
  stepIndex: number
  startedFrom: 'auto' | 'manual' | null
  hydrate: () => void
  maybeOpenFirstRunChooser: (pathname: string) => void
  openChooser: (origin?: 'auto' | 'manual') => void
  startTutorial: (language: OnboardingLanguage, pathname: string, origin?: 'auto' | 'manual') => void
  restartTutorial: (pathname: string, language?: OnboardingLanguage | null) => void
  nextStep: () => void
  previousStep: () => void
  close: () => void
  skipFirstRun: () => void
  neverShowAgain: () => void
  completeTutorial: () => void
}

const ONBOARDING_STORAGE_KEY = 'ds:onboarding:v1'
export const PROJECT_ONBOARDING_START_STEP = 22

const defaultPersistence: OnboardingPersistence = {
  firstRunHandled: false,
  completed: false,
  neverRemind: false,
  language: null,
}

function readPersistence(): OnboardingPersistence {
  if (typeof window === 'undefined') {
    return defaultPersistence
  }

  try {
    const raw = window.localStorage.getItem(ONBOARDING_STORAGE_KEY)
    if (!raw) return defaultPersistence
    const parsed = JSON.parse(raw) as Partial<OnboardingPersistence>
    return {
      firstRunHandled: Boolean(parsed.firstRunHandled),
      completed: Boolean(parsed.completed),
      neverRemind: Boolean(parsed.neverRemind),
      language:
        parsed.language === 'zh' || parsed.language === 'en'
          ? parsed.language
          : null,
    }
  } catch {
    return defaultPersistence
  }
}

function writePersistence(value: OnboardingPersistence) {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Ignore storage write failures so onboarding never blocks the UI.
  }
}

function resolveLanguage(input: OnboardingLanguage | null | undefined): OnboardingLanguage {
  if (input === 'zh' || input === 'en') {
    return input
  }

  if (typeof window !== 'undefined') {
    const browserLanguage = String(window.navigator?.language || '').toLowerCase()
    if (browserLanguage.startsWith('zh')) {
      return 'zh'
    }
  }

  return 'en'
}

function resolveStartStepIndex(pathname: string) {
  return /^\/(projects\/[^/]+|tutorial\/demo\/[^/]+)$/.test(pathname)
    ? PROJECT_ONBOARDING_START_STEP
    : 0
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  ...defaultPersistence,
  hydrated: false,
  status: 'idle',
  stepIndex: 0,
  startedFrom: null,

  hydrate: () => {
    if (get().hydrated) return
    const persisted = readPersistence()
    set({
      ...persisted,
      hydrated: true,
    })
  },

  maybeOpenFirstRunChooser: (pathname) => {
    const state = get()
    if (!state.hydrated) return
    if (state.status !== 'idle') return
    if (pathname !== '/') return
    if (state.firstRunHandled || state.neverRemind) return
    set({
      status: 'choosing_language',
      startedFrom: 'auto',
    })
  },

  openChooser: (origin = 'manual') => {
    set({
      status: 'choosing_language',
      startedFrom: origin,
    })
  },

  startTutorial: (language, pathname, origin = 'manual') => {
    const nextPersistence: OnboardingPersistence = {
      firstRunHandled: true,
      completed: get().completed,
      neverRemind: get().neverRemind,
      language,
    }
    void useUILanguageStore.getState().saveLanguagePreference(language)
    writePersistence(nextPersistence)
    set({
      ...nextPersistence,
      status: 'running',
      stepIndex: resolveStartStepIndex(pathname),
      startedFrom: origin,
    })
  },

  restartTutorial: (pathname, language) => {
    const nextLanguage = resolveLanguage(language ?? get().language)
    void useUILanguageStore.getState().saveLanguagePreference(nextLanguage)
    const nextPersistence: OnboardingPersistence = {
      firstRunHandled: true,
      completed: get().completed,
      neverRemind: get().neverRemind,
      language: nextLanguage,
    }
    writePersistence(nextPersistence)
    set({
      ...nextPersistence,
      hydrated: true,
      status: 'running',
      stepIndex: resolveStartStepIndex(pathname),
      startedFrom: 'manual',
    })
  },

  nextStep: () => {
    set((state) => ({
      stepIndex: state.stepIndex + 1,
    }))
  },

  previousStep: () => {
    set((state) => ({
      stepIndex: Math.max(0, state.stepIndex - 1),
    }))
  },

  close: () => {
    set({
      status: 'idle',
      startedFrom: null,
    })
  },

  skipFirstRun: () => {
    const nextPersistence: OnboardingPersistence = {
      firstRunHandled: true,
      completed: get().completed,
      neverRemind: get().neverRemind,
      language: get().language,
    }
    writePersistence(nextPersistence)
    set({
      ...nextPersistence,
      status: 'idle',
      startedFrom: null,
    })
  },

  neverShowAgain: () => {
    const nextPersistence: OnboardingPersistence = {
      firstRunHandled: true,
      completed: get().completed,
      neverRemind: true,
      language: get().language,
    }
    writePersistence(nextPersistence)
    set({
      ...nextPersistence,
      status: 'idle',
      startedFrom: null,
    })
  },

  completeTutorial: () => {
    const nextPersistence: OnboardingPersistence = {
      firstRunHandled: true,
      completed: true,
      neverRemind: get().neverRemind,
      language: get().language,
    }
    writePersistence(nextPersistence)
    set({
      ...nextPersistence,
      status: 'idle',
      startedFrom: null,
    })
  },
}))
