import {
  JlcEdaApiCallError,
  JlcEdaCapabilityUnavailableError,
  type CurrentDocumentDto,
  type CurrentDocumentReadDto,
  type CurrentSelectionDto,
  type SelectedObjectDto,
} from './jlc-eda-api-adapter.ts';


export type EdaOperationErrorCode =
  | 'capability_unsupported'
  | 'inconsistent_observation'
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
      readonly payload: Readonly<Record<string, unknown>>;
      readonly error?: undefined;
    }
  | {
      readonly status: 'error';
      readonly error: DispatchError;
      readonly payload?: undefined;
    };

export interface EdaObservationReader {
  readCurrentDocument(): Promise<CurrentDocumentReadDto>;
  readCurrentSelection?(): Promise<CurrentSelectionDto>;
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
  readonly #api: EdaObservationReader;
  readonly #environment: DispatcherEnvironment;

  constructor(
    api: EdaObservationReader,
    environment: DispatcherEnvironment = defaultEnvironment,
  ) {
    this.#api = api;
    this.#environment = environment;
  }

  async dispatch(
    request: Readonly<Record<string, unknown>>,
  ): Promise<DispatchOutcome> {
    if (request.operation === 'eda.document.get_active') {
      return this.#getActiveDocument();
    }
    if (request.operation === 'eda.selection.get') {
      return this.#getSelection();
    }
    return errorOutcome(
      'operation_not_allowed',
      'Operation is not present in the Phase 5B.3b static allowlist.',
    );
  }

  async #getActiveDocument(): Promise<DispatchOutcome> {
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
      return mapProviderError(error, 'document.read');
    }
  }

  async #getSelection(): Promise<DispatchOutcome> {
    try {
      const before = await this.#api.readCurrentDocument();
      if (before.document === null) {
        return errorOutcome(
          'no_active_document',
          'No active design document is available.',
        );
      }
      if (typeof this.#api.readCurrentSelection !== 'function') {
        return errorOutcome(
          'capability_unsupported',
          'The active JLCEDA runtime does not expose selection.read.',
        );
      }

      const selection = await this.#api.readCurrentSelection();
      const after = await this.#api.readCurrentDocument();
      if (
        after.document === null
        || after.document.provider !== before.document.provider
        || after.document.documentId !== before.document.documentId
      ) {
        return errorOutcome(
          'inconsistent_observation',
          'The active document changed while the selection was observed.',
        );
      }
      if (selection.truncated) {
        return errorOutcome(
          'provider_error',
          'The provider selection exceeds the bounded observation limit.',
        );
      }

      const snapshotId = this.#environment.randomUuid();
      return Object.freeze({
        status: 'success' as const,
        payload: Object.freeze({
          context: normalizeSelectionContext(
            before.document,
            selection,
            snapshotId,
          ),
        }),
      });
    }
    catch (error) {
      return mapProviderError(error, 'selection.read');
    }
  }
}

function normalizeDocument(
  document: CurrentDocumentDto,
  snapshotId: string,
  capturedAt: Date,
): Readonly<Record<string, unknown>> {
  return Object.freeze({
    model_version: '1.0',
    document_ref: normalizeDocumentRef(document, snapshotId),
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

function normalizeSelectionContext(
  document: CurrentDocumentDto,
  selection: CurrentSelectionDto,
  snapshotId: string,
): Readonly<Record<string, unknown>> {
  const selectedObjects = selection.objects.map((object) =>
    normalizeSelectedObject(document, object, snapshotId));
  const observedNetNames = [...new Set(
    selection.objects
      .filter((object) => object.primitiveType === 'Wire')
      .map((object) => object.netName)
      .filter((name): name is string => name !== undefined && name.length > 0),
  )];
  const nets = observedNetNames.map((netName) => Object.freeze({
    model_version: '1.0',
    ref: Object.freeze({
      model_version: '1.0',
      provider: document.provider,
      object_type: 'net',
      document_id: document.documentId,
      snapshot_id: snapshotId,
      native_id: null,
      canonical_id: canonicalId('net', document.documentId, netName),
      display_name: netName,
      provider_kind: 'Wire.net',
    }),
    endpoints: Object.freeze([]),
    source: null,
    signal_expectation: null,
  }));

  return Object.freeze({
    model_version: '1.0',
    selection: Object.freeze({
      model_version: '1.0',
      document_ref: normalizeDocumentRef(document, snapshotId),
      selected_objects: Object.freeze(selectedObjects),
      primary_object: null,
    }),
    nets: Object.freeze(nets),
  });
}

function normalizeDocumentRef(
  document: CurrentDocumentDto,
  snapshotId: string,
): Readonly<Record<string, unknown>> {
  return Object.freeze({
    model_version: '1.0',
    provider: document.provider,
    object_type: 'document',
    document_id: document.documentId,
    snapshot_id: snapshotId,
    native_id: document.documentId,
    canonical_id: `jlceda-pro:document:${document.documentId}`,
    display_name: null,
  });
}

function normalizeSelectedObject(
  document: CurrentDocumentDto,
  object: SelectedObjectDto,
  snapshotId: string,
): Readonly<Record<string, unknown>> {
  const objectType = object.primitiveType === 'Wire'
    ? 'wire'
    : object.primitiveType === 'Component'
      ? 'component'
      : 'other';
  const displayName = objectType === 'wire'
    ? object.netName ?? null
    : objectType === 'component'
      ? object.componentDesignator ?? null
      : null;
  return Object.freeze({
    model_version: '1.0',
    provider: document.provider,
    object_type: objectType,
    document_id: document.documentId,
    snapshot_id: snapshotId,
    native_id: object.primitiveId,
    canonical_id: canonicalId(objectType, document.documentId, object.primitiveId),
    display_name: displayName,
    provider_kind: object.primitiveType,
  });
}

function canonicalId(
  kind: string,
  documentId: string,
  identity: string,
): string {
  return `jlceda-pro:${kind}:${base64Url(documentId)}:${base64Url(identity)}`;
}

function base64Url(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

function mapProviderError(
  error: unknown,
  capability: 'document.read' | 'selection.read',
): DispatchOutcome {
  if (error instanceof JlcEdaCapabilityUnavailableError) {
    return errorOutcome(
      'capability_unsupported',
      `The active JLCEDA runtime does not expose ${capability}.`,
    );
  }
  if (error instanceof JlcEdaApiCallError) {
    return errorOutcome(
      'provider_error',
      `The JLCEDA ${capability} API failed.`,
    );
  }
  return errorOutcome('internal_error', 'EDA observation failed.');
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
