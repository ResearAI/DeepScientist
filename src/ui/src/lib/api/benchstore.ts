import { apiClient, buildApiAssetUrl } from "@/lib/api/client";
import type {
  BenchCatalogPayload,
  BenchEntryDetailPayload,
  BenchSetupPacketPayload,
} from "@/lib/types/benchstore";
import type { AdminTask } from "@/lib/types/admin";

export async function listBenchStoreEntries(locale?: "en" | "zh") {
  const response = await apiClient.get<BenchCatalogPayload>(
    "/api/benchstore/entries",
    { params: locale ? { locale } : undefined },
  );
  return response.data;
}

export async function getBenchStoreEntry(
  entryId: string,
  locale?: "en" | "zh",
) {
  const response = await apiClient.get<BenchEntryDetailPayload>(
    `/api/benchstore/entries/${encodeURIComponent(entryId)}`,
    { params: locale ? { locale } : undefined },
  );
  return response.data;
}

export async function installBenchStoreEntry(entryId: string) {
  const response = await apiClient.post<{
    ok: boolean;
    entry_id: string;
    task: AdminTask;
  }>(`/api/benchstore/entries/${encodeURIComponent(entryId)}/install`, {});
  return response.data;
}

export async function getBenchStoreSetupPacket(
  entryId: string,
  locale?: "en" | "zh",
) {
  const response = await apiClient.get<BenchSetupPacketPayload>(
    `/api/benchstore/entries/${encodeURIComponent(entryId)}/setup-packet`,
    { params: locale ? { locale } : undefined },
  );
  return response.data;
}

export function buildBenchStoreEntryImageUrl(
  entryId: string,
  locale?: "en" | "zh",
) {
  const suffix = locale ? `?locale=${encodeURIComponent(locale)}` : "";
  return buildApiAssetUrl(
    `/api/benchstore/entries/${encodeURIComponent(entryId)}/image${suffix}`,
  );
}

export async function launchBenchStoreEntry(
  entryId: string,
  locale?: "en" | "zh",
) {
  const response = await apiClient.post<{
    ok: boolean;
    entry_id: string;
    snapshot: { quest_id: string };
  }>(
    `/api/benchstore/entries/${encodeURIComponent(entryId)}/launch${locale ? `?locale=${encodeURIComponent(locale)}` : ""}`,
    {},
  );
  return response.data;
}
