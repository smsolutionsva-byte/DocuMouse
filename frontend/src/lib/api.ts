import type {
  AssistantReply,
  DocType,
  DocumentDetail,
  DocumentSummary,
  Health,
  Operation,
  Preview,
  Validation,
  VersionInfo,
} from "./types";

function getToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(/(?:^|; )documouse_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init?.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  try {
    res = await fetch(path, {
      ...init,
      headers: { ...headers, ...init?.headers },
    });
  } catch {
    throw new ApiError("DocuMouse can't reach its server. Is the backend running?", 0);
  }
  if (!res.ok) {
    let message = "Something went wrong.";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  list: (params: Record<string, string | undefined> = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return request<{ documents: DocumentSummary[] }>(`/api/documents${qs.size ? `?${qs}` : ""}`);
  },
  stats: () => request<{ total: number; needs_review: number; processing: number; processed_today: number }>("/api/documents/stats"),
  get: (id: string) => request<DocumentDetail>(`/api/documents/${id}`),
  remove: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  retry: (id: string) => request<DocumentSummary>(`/api/documents/${id}/retry`, { method: "POST" }),
  apply: (id: string, operations: Operation[], opts: { base?: string; author?: "user" | "ai"; message?: string } = {}) =>
    request<DocumentDetail>(
      `/api/documents/${id}/operations`,
      json({ operations, base_version_id: opts.base, author: opts.author ?? "user", message: opts.message }),
    ),
  preview: (id: string, operations: Operation[]) =>
    request<{ message: string; changes: Preview; validation: Validation }>(
      `/api/documents/${id}/operations/preview`,
      json({ operations }),
    ),
  assistant: (id: string, message: string) => request<AssistantReply>(`/api/documents/${id}/assistant`, json({ message })),
  undo: (id: string) => request<DocumentDetail>(`/api/documents/${id}/undo`, { method: "POST" }),
  redo: (id: string) => request<DocumentDetail>(`/api/documents/${id}/redo`, { method: "POST" }),
  versions: (id: string) => request<{ versions: VersionInfo[] }>(`/api/documents/${id}/versions`),
  version: (id: string, versionId: string) =>
    request<VersionInfo & { changes_from_current: Preview | null }>(`/api/documents/${id}/versions/${versionId}`),
  restore: (id: string, versionId: string) =>
    request<DocumentDetail>(`/api/documents/${id}/versions/${versionId}/restore`, { method: "POST" }),
  setType: (id: string, docType: DocType) => request<DocumentDetail>(`/api/documents/${id}/type`, json({ doc_type: docType })),
  keepType: (id: string) => request<DocumentDetail>(`/api/documents/${id}/classification/dismiss`, { method: "POST" }),
  approve: (id: string) => request<DocumentDetail>(`/api/documents/${id}/approve`, { method: "POST" }),
};

/** Upload with progress events (fetch can't report upload progress). */
export function uploadFile(
  file: File,
  docType: DocType | "auto",
  onProgress: (fraction: number) => void,
): Promise<DocumentSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const uploadUrl = process.env.NEXT_PUBLIC_DOCUMOUSE_UPLOAD_URL || "/api/documents";
    xhr.open("POST", uploadUrl);
    const authToken = getToken();
    if (authToken) xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { detail?: string } | DocumentSummary | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body as DocumentSummary);
      else reject(new ApiError((body as { detail?: string })?.detail ?? "Upload failed.", xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("DocuMouse can't reach its server.", 0));
    const form = new FormData();
    form.append("file", file);
    if (docType !== "auto") form.append("doc_type", docType);
    xhr.send(form);
  });
}
