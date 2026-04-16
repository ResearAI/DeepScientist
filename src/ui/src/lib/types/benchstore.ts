export type BenchResourceSpec = {
  cpu_cores?: number | null;
  ram_gb?: number | null;
  disk_gb?: number | null;
  gpu_count?: number | null;
  gpu_vram_gb?: number | null;
};

export type BenchCompatibility = {
  minimum_ok?: boolean;
  recommended_ok?: boolean;
  minimum_reasons?: string[];
  recommended_reasons?: string[];
  score?: number;
  recommendation_tier?: "recommended" | "minimum" | "unsupported" | string;
  device_summary?: string;
  resource_confidence?: "full" | "partial" | "none" | string;
};

export type BenchRecommendation = {
  score?: number;
  affinity_score?: number;
  capacity_class?: "low" | "medium" | "high" | string;
  shelf_bucket?:
    | "best_match"
    | "runnable"
    | "installed"
    | "needs_stronger_device"
    | "risk_flagged"
    | string;
  reasons?: string[];
  cost_rank?: number | null;
  difficulty_rank?: number | null;
  time_upper_hours?: number | null;
};

export type BenchPaper = {
  title?: string | null;
  venue?: string | null;
  year?: number | null;
  url?: string | null;
};

export type BenchDownload = {
  url?: string | null;
  archive_type?: string | null;
  local_dir_name?: string | null;
};

export type BenchDatasetSource = {
  kind?: string | null;
  url?: string | null;
  access?: string | null;
  note?: string | null;
};

export type BenchDatasetDownload = {
  primary_method?: string | null;
  sources?: BenchDatasetSource[];
  notes?: string[];
};

export type BenchCredentialRequirements = {
  mode?: string | null;
  items?: string[];
  notes?: string[];
};

export type BenchLaunchProfile = {
  id?: string | null;
  label?: string | null;
  description?: string | null;
};

export type BenchCommercial = {
  annual_fee?: string | number | null;
};

export type BenchDisplay = {
  palette_seed?: string | null;
  art_style?: string | null;
  accent_priority?: string | null;
};

export type BenchEnvironment = {
  python?: string | null;
  cuda?: string | null;
  pytorch?: string | null;
  flash_attn?: string | null;
  key_packages?: string[];
  notes?: string[];
};

export type BenchInstallState = {
  entry_id?: string | null;
  entry_name?: string | null;
  status?:
    | "not_installed"
    | "installing"
    | "installed"
    | "failed"
    | "missing"
    | string;
  task_id?: string | null;
  local_path?: string | null;
  download_url?: string | null;
  archive_type?: string | null;
  archive_path?: string | null;
  archive_sha256?: string | null;
  expected_sha256?: string | null;
  bytes_downloaded?: number | null;
  bytes_total?: number | null;
  installed_at?: string | null;
  updated_at?: string | null;
};

export type BenchEntry = {
  schema_version?: number;
  id: string;
  name: string;
  version?: string | null;
  one_line?: string | null;
  task_description?: string | null;
  capability_tags?: string[];
  aisb_direction?: string | null;
  track_fit?: string[];
  task_mode?: string | null;
  requires_execution?: boolean | null;
  requires_paper?: boolean | null;
  integrity_level?: string | null;
  snapshot_status?: string | null;
  support_level?: string | null;
  primary_outputs?: string[];
  launch_profiles?: BenchLaunchProfile[];
  cost_band?: string | null;
  time_band?: string | null;
  difficulty?: string | null;
  data_access?: string | null;
  risk_flags?: string[];
  risk_notes?: string[];
  recommended_when?: string | null;
  not_recommended_when?: string | null;
  paper?: BenchPaper | null;
  download?: BenchDownload | null;
  dataset_download?: BenchDatasetDownload | null;
  credential_requirements?: BenchCredentialRequirements | null;
  resources?: {
    minimum?: BenchResourceSpec | null;
    recommended?: BenchResourceSpec | null;
  } | null;
  environment?: BenchEnvironment | null;
  commercial?: BenchCommercial | null;
  display?: BenchDisplay | null;
  image_path?: string | null;
  image_url?: string | null;
  install_state?: BenchInstallState | null;
  source_file?: string | null;
  compatibility?: BenchCompatibility | null;
  recommendation?: BenchRecommendation | null;
  setup_prompt_preview?: string | null;
  search_text?: string | null;
  raw_payload?: Record<string, unknown> | null;
};

export type BenchCatalogPayload = {
  ok: boolean;
  catalog_root?: string;
  device_profile?: BenchResourceSpec | null;
  device_capacity?: {
    score?: number;
    capacity_class?: "low" | "medium" | "high" | string;
  } | null;
  device_summary?: string | null;
  invalid_entries?: Array<{
    source_file: string;
    message: string;
  }>;
  filter_options?: {
    aisb_direction?: string[];
    task_mode?: string[];
    cost_band?: string[];
    difficulty?: string[];
    data_access?: string[];
    track_fit?: string[];
    requires_execution?: string[];
    requires_paper?: string[];
  };
  shelves?: {
    best_match_ids?: string[];
    runnable_ids?: string[];
    installed_ids?: string[];
    needs_stronger_device_ids?: string[];
  };
  items: BenchEntry[];
  total: number;
};

export type BenchEntryDetailPayload = {
  ok: boolean;
  device_profile?: BenchResourceSpec | null;
  device_summary?: string | null;
  entry: BenchEntry;
};

export type BenchSetupPacket = {
  entry_id: string;
  assistant_label?: string | null;
  project_title?: string | null;
  benchmark_local_path?: string | null;
  local_dataset_paths?: string[];
  latex_markdown_path?: string | null;
  device_summary?: string | null;
  device_fit?: string | null;
  requires_paper?: boolean | null;
  benchmark_goal?: string | null;
  constraints?: string[];
  suggested_form?: Record<string, unknown> | null;
  startup_instruction?: string | null;
  launch_payload?: {
    title?: string | null;
    goal?: string | null;
    initial_message?: string | null;
    startup_contract?: Record<string, unknown> | null;
  } | null;
};

export type BenchSetupPacketPayload = {
  ok: boolean;
  entry_id: string;
  setup_packet: BenchSetupPacket;
};
