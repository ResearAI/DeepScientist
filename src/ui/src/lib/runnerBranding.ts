export type BuiltinRunnerName = "codex" | "claude" | "opencode"

export type RunnerBranding = {
  name: BuiltinRunnerName
  label: string
  shortLabel: string
  description: string
  logoSrc: string
  accentClassName: string
  chipClassName: string
}

export const RUNNER_BRANDING: Record<BuiltinRunnerName, RunnerBranding> = {
  codex: {
    name: "codex",
    label: "Codex",
    shortLabel: "Codex",
    description: "OpenAI Codex CLI with DeepScientist MCP injection and full local automation defaults.",
    logoSrc: "/assets/branding/runner-codex.svg",
    accentClassName: "from-slate-950 via-slate-900 to-sky-900 text-white",
    chipClassName: "bg-sky-100 text-sky-700",
  },
  claude: {
    name: "claude",
    label: "Claude Code",
    shortLabel: "Claude",
    description: "Anthropic Claude Code with dangerous local automation via bypassPermissions.",
    logoSrc: "/assets/branding/runner-claude.svg",
    accentClassName: "from-amber-500 via-amber-400 to-yellow-300 text-[#1f1302]",
    chipClassName: "bg-amber-100 text-amber-700",
  },
  opencode: {
    name: "opencode",
    label: "OpenCode",
    shortLabel: "OpenCode",
    description: "SST OpenCode with permission allow mode for no-confirm local execution.",
    logoSrc: "/assets/branding/runner-opencode.svg",
    accentClassName: "from-emerald-500 via-green-400 to-teal-300 text-[#052516]",
    chipClassName: "bg-emerald-100 text-emerald-700",
  },
}

export function normalizeBuiltinRunnerName(value: unknown): BuiltinRunnerName {
  const normalized = String(value || "").trim().toLowerCase()
  if (normalized === "claude") return "claude"
  if (normalized === "opencode") return "opencode"
  return "codex"
}

export function runnerLabel(value: unknown): string {
  return RUNNER_BRANDING[normalizeBuiltinRunnerName(value)].label
}
