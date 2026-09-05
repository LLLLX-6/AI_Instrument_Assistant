import {
  JlcEdaApiCallError,
  JlcEdaCapabilityUnavailableError,
  type CurrentDocumentReadDto,
} from './jlc-eda-api-adapter.ts';


export type EdaOperationErrorCode =
  | 'capability_unsupported'
  | 'no_active_document'
  | 'operation_not_allowed'
  | 'provider_error'
  | 'internal_error';

export interface DispatchError {
  readonly code: EdaOperationErrorCode;
  readonly message: string;
}

export type DispatchOutcome =
  | {
      readonly status: 'success';
      readonly payload: Readonly<{ document: Readonly<Record<string, unknown>> }>;
      readonly error?: undefined;
    }
  | {
      readonly status: 'error';
      readonly error: DispatchError;
      readonly payload?: undefined;
    };

export interface ActiveDocumentReader {
  readCurrentDocument(): Promise<CurrentDocumentReadDto>;
}

export interface DispatcherEnvironment {
  readonly now: () => Date;
  readonly randomUuid: () => string;
}

const defaultEnvironment: DispatcherEnvironment = {
  now: () => new Date(),
  randomUuid: () => crypto.randomUUID(),
};

export class EdaProtocolDispatcher {
  readonly #api: ActiveDocumentReader;
  readonly #environment: DispatcherEnvironment;

  constructor(
    api: ActiveDocumentReader,
    environment: DispatcherEnvironment = defaultEnvironment,
  ) {
    this.#api = api;
    this.#environment = environment;
  }

  async dispatch(
    request: Readonly<Record<string, unknown>>,
  ): Promise<DispatchOutcome> {
    if (request.operation !== 'eda.document.get_active') {
      return errorOutcome(
        'operation_not_allowed',
        'Operation is not present in the Phase 5B.2b static allowlist.',
      );
    }

    try {
      const observation = await this.#api.readCurrentDocument();
      if (observation.document === null) {
        return errorOutcome(
          'no_active_document',
          'No active design document is available.',
        );
      }
      return Object.freeze({
        status: 'success' as const,
        payload: Object.freeze({
          document: normalizeDocument(
            observation.document,
            this.#environment.randomUuid(),
            this.#environment.now(),
          ),
        }),
      });
    }
    catch (error) {
      if (error instanceof JlcEdaCapabilityUnavailableError) {
        return errorOutcome(
          'capability_unsupported',
          'The active JLCEDA runtime does not expose document.read.',
        );
      }
      if (error instanceof JlcEdaApiCallError) {
        return errorOutcome(
          'provider_error',
          'The JLCEDA document API failed.',
        );
      }
      return errorOutcome('internal_error', 'Document observation failed.');
    }
  }
}

function normalizeDocument(
  document: NonNullable<CurrentDocumentReadDto['document']>,
  snapshotId: string,
  capturedAt: Date,
): Readonly<Record<string, unknown>> {
  const canonicalId = `jlceda-pro:document:${document.documentId}`;
  return Object.freeze({
    model_version: '1.0',
    document_ref: Object.freeze({
      model_version: '1.0',
      provider: 'jlceda-pro',
      object_type: 'document',
      document_id: document.documentId,
      snapshot_id: snapshotId,
      native_id: document.documentId,
      canonical_id: canonicalId,
      display_name: null,
    }),
    project_id: document.projectId,
    project_name: null,
    document_name: null,
    document_type: document.documentType,
    native_revision: null,
    fingerprint: null,
    is_dirty: null,
    captured_at: capturedAt.toISOString(),
  });
}

function errorOutcome(
  code: EdaOperationErrorCode,
  message: string,
): DispatchOutcome {
  return Object.freeze({
    status: 'error' as const,
    error: Object.freeze({ code, message }),
  });
}
