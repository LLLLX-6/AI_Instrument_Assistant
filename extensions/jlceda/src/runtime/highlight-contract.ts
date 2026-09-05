// Extension transport types. Runtime validation derives solely from JSON Schema.
export interface HighlightTargetDto {
  readonly model_version: string;
  readonly provider: string;
  readonly object_type: string;
  readonly document_id: string;
  readonly snapshot_id: string;
  readonly native_id: string | null;
  readonly canonical_id: string;
  readonly display_name: string | null;
  readonly provider_kind?: string | null;
}
export interface HighlightCommandDto {
  readonly document_ref: HighlightTargetDto;
  readonly expected_snapshot_id: string;
  readonly expected_fingerprint: unknown;
  readonly targets: readonly HighlightTargetDto[];
  readonly idempotency_key: string;
  readonly guard_mode: 'strong_required' | 'weak_identity_check';
  readonly allow_scope_expansion: boolean;
  readonly ttl_ms: number | null;
  readonly style: string;
  readonly replace_existing: boolean | null;
}
export interface HighlightExecutionContext {
  // Tested again immediately before the synchronous provider invocation.
  isActive(): boolean;
}
export class HighlightPreflightError extends Error {
  readonly code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
    this.name = 'HighlightPreflightError';
  }
}
