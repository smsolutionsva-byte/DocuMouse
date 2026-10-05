export type DocStatus =
  | "queued"
  | "reading"
  | "understanding"
  | "extracting"
  | "checking"
  | "ready"
  | "failed";

export type DocType = "invoice" | "receipt" | "unknown";
export type FieldKind = "text" | "multiline" | "amount" | "date" | "time" | "currency" | "gstin";
export type FieldStatus = "verified" | "review" | "missing" | "empty";

export interface Source {
  page: number;
  bbox: [number, number, number, number];
}

export interface FieldValue {
  value: string | null;
  raw: string | null;
  confidence: number;
  source: Source | null;
  origin: "ocr" | "llm" | "ocr+llm" | "user" | "ai" | null;
  confirmed: boolean;
  suggestion: { value: string; reason: string } | null;
  notes: string[];
  /** What an independent second reader read for this field, when cross-checking is on. */
  second_opinion?: { reader: string; value: string | null; agrees: boolean; confirms: boolean } | null;
}

export interface Column {
  id: string;
  name: string;
  role: string | null;
}

export interface Row {
  id: string;
  cells: Record<string, string>;
  kind: "item" | "summary";
  source: Source | null;
}

export interface TableData {
  id: string;
  title: string;
  role: string | null;
  source: Source | null;
  columns: Column[];
  rows: Row[];
}

export interface DocumentData {
  doc_type: DocType;
  fields: Record<string, FieldValue>;
  tables: TableData[];
}

export interface Check {
  id: string;
  status: "pass" | "warn" | "fail" | "info";
  title: string;
  detail: string;
  fields: string[];
  table_id: string | null;
}

export interface Validation {
  checks: Check[];
  fields: Record<string, { status: FieldStatus; reasons: string[] }>;
  rows: Record<string, Record<string, string[]>>;
  summary: {
    verified: number;
    needs_review: number;
    flagged_rows: number;
    tables: number;
    checks_passed: number;
    checks_failed: number;
    issues: number;
  };
}

export interface FieldSchema {
  key: string;
  label: string;
  kind: FieldKind;
  group: string;
  required: boolean;
}

export interface Duplicate {
  id: string;
  filename: string;
  reason: string;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: DocStatus;
  error: string | null;
  doc_type: DocType | null;
  party: string | null;
  reference: string | null;
  doc_date: string | null;
  total: string | null;
  currency: string | null;
  review_count: number;
  approved: boolean;
  edited_after_approval: boolean;
  duplicate_of: Duplicate[];
  page_count: number;
  created_at: string | null;
  processed_at: string | null;
}

export interface Classification {
  detected_type: DocType;
  detected_label: string;
  confidence: number;
  scores: Record<DocType, number>;
  signals: Record<string, string[]>;
  current_type: DocType;
  mismatch: boolean;
  uncertain: boolean;
  mismatch_dismissed: boolean;
  requested_type: DocType | null;
}

export interface PageInfo {
  index: number;
  width: number;
  height: number;
  url: string;
}

export interface DocumentDetail extends DocumentSummary {
  error_detail: string | null;
  engine: string | null;
  pages: PageInfo[];
  file_url: string;
  classification: Classification | null;
  schema: FieldSchema[];
  type_labels: Record<DocType, string>;
  data: DocumentData | null;
  validation: Validation | null;
  version: { id: string; number: number; message: string } | null;
  can_undo: boolean;
  can_redo: boolean;
}

export type Operation = { op: string } & Record<string, unknown>;

export interface Preview {
  fields: { field: string; label: string; kind: FieldKind; before: string | null; after: string | null }[];
  tables: {
    table_id: string;
    before: { title: string; columns: Column[]; rows: { id: string; kind: string; cells: Record<string, string> }[] } | null;
    after: { title: string; columns: Column[]; rows: { id: string; kind: string; cells: Record<string, string> }[] } | null;
    changed_rows: string[];
  }[];
}

export interface AssistantReply {
  reply: string;
  source: "rules" | "llm";
  operations: Operation[];
  message?: string;
  preview: Preview | null;
  validation?: Validation;
}

export interface VersionInfo {
  id: string;
  number: number;
  parent_id: string | null;
  author: "system" | "user" | "ai";
  message: string;
  created_at: string | null;
  active: boolean;
  head: boolean;
}

export interface Health {
  status: string;
  engine: string;
  llm: { enabled: boolean; provider: string | null; model: string | null };
}
