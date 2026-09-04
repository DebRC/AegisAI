export interface AegisUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface AegisTokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface AegisLoginResponse extends AegisTokenPair {
  user: AegisUser;
  tenant_id?: number | null;
}

export interface SessionStatus {
  authenticated: boolean;
  user?: AegisUser;
}

export interface AegisDocument {
  id: number;
  uploader_user_id: number;
  title: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: "pending" | "processing" | "ready" | "failed";
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  items: AegisDocument[];
  offset: number;
  limit: number;
  total: number;
}

export interface DocumentDetailData {
  document: AegisDocument;
  extraction: { character_count: number; extractor_version: string; extracted_at: string } | null;
  indexing: { total_chunks: number; indexed_chunks: number; indexing_status: string; indexing_error: string | null } | null;
  jobs: { id: number; job_type: string; status: string; attempt_count: number; error_message: string | null }[];
}

export interface RetrievalResult { document_id: number; document_title: string; content_type: string; chunk_id: number; chunk_ordinal: number; content: string; source_locations: Record<string, string | number>[] | null; score: number; }
export interface RetrievalResponse { items: RetrievalResult[]; limit: number; }
export interface AdminOverview { total_users: number; active_users: number; documents_by_status: Record<string, number>; jobs_by_status: Record<string, number>; recent_event_count: number; }
export interface AdminUser { id: number; email: string; full_name: string; is_active: boolean; roles: { id: number; name: string }[]; }
export interface AdminUserPage { items: AdminUser[]; offset: number; limit: number; total: number; }
export interface AdminRole { id: number; name: string; description: string | null; permission_codes: string[]; user_count: number; }
export interface AdminPermission { id: number; code: string; description: string; role_count: number; }
export interface AdminDocument { id: number; title: string; original_filename: string; content_type: string; status: string; uploader_user_id: number; processing_error: string | null; deleted_at: string | null; }
export interface AdminDocumentPage { items: AdminDocument[]; offset: number; limit: number; total: number; }
export interface AdminJob { id: number; document_id: number; job_type: string; status: string; attempt_count: number; error_message: string | null; }
export interface AuditEvent { id: number; event_type: string; outcome: string; actor_user_id: number | null; occurred_at: string; }
export interface Tenant { id: number; slug: string; name: string; is_active: boolean; }
export interface TenantMembership { tenant: Tenant; is_active: boolean; }
export interface ManagedApiKey { id: number; name: string; key_prefix: string; scopes: string[]; expires_at: string | null; revoked_at: string | null; last_used_at: string | null; created_at: string; }
export interface RetentionPolicy { document_retention_days: number | null; updated_at: string | null; }
