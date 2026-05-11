export type ScienceNodeType =
  | 'science.package_check'
  | 'science.computational_run'
  | 'science.dataset_analysis'
  | 'science.parameter_sweep'
  | 'science.validation_result'
  | 'science.claim'

export type ScienceKeyResult = {
  label: string
  value?: unknown
  unit?: string | null
  [key: string]: unknown
}

export type ScienceNodeData = {
  artifactId: string
  nodeId: string
  nodeType: string
  title: string
  summary: string
  status: string
  domain: string | null
  packageId: string | null
  taskType: string | null
  keyResults: ScienceKeyResult[]
  evidencePaths: string[]
  inputPaths: string[]
  outputPaths: string[]
  logPaths: string[]
  validationPaths: string[]
  parentNodeIds: string[]
  relatedNodeIds: string[]
  claimType: string | null
  trust: string | null
}
