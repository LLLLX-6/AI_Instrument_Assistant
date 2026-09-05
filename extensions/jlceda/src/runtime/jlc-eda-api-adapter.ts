const MAX_TEXT_LENGTH = 512;
const MAX_SELECTION_OBJECTS = 128;
const DOCUMENT_SHAPE_KEYS = new Set([
  'documentType',
  'uuid',
  'tabId',
  'parentProjectUuid',
  'parentLibraryUuid',
]);

export type DocumentTypeDto =
  | 'schematic'
  | 'pcb'
  | 'symbol'
  | 'footprint'
  | 'home'
  | 'blank'
  | 'other';

export interface RawShapeSummaryDto {
  readonly kind: 'object' | 'null' | 'undefined' | 'other';
  readonly ownKeyCount: number;
  readonly ownKeys: readonly string[];
  readonly unknownKeyCount: number;
}

export interface CurrentDocumentDto {
  readonly provider: 'jlceda-pro';
  readonly documentId: string;
  readonly documentType: DocumentTypeDto;
  readonly projectId: string | null;
  readonly libraryId: string | null;
}

export interface CurrentDocumentReadDto {
  readonly document: CurrentDocumentDto | null;
  readonly rawShape: RawShapeSummaryDto;
}

export interface SelectedObjectDto {
  readonly primitiveId: string;
  readonly primitiveType: string;
  readonly netName?: string;
  readonly componentDesignator?: string;
}

export interface CurrentSelectionDto {
  readonly objects: readonly SelectedObjectDto[];
  readonly totalSelected: number;
  readonly truncated: boolean;
  readonly primitiveTypeSummary: Readonly<Record<string, number>>;
}

export interface HighlightSelectionResultDto {
  readonly status: 'applied' | 'noop';
  readonly componentCount: number;
  readonly pinCount: number;
  readonly netCount: number;
  readonly warnings: readonly string[];
}

export interface RuntimeDiagnosticsDto {
  readonly editorVersion: string | null;
  readonly editorCompiledDate: string | null;
  readonly environment: 'client' | 'web' | 'unknown';
  readonly edition: 'jlceda-pro' | 'easyeda-pro' | 'unknown';
  readonly capabilities: {
    readonly documentRead: boolean;
    readonly selectionRead: boolean;
    readonly crossProbeHighlight: boolean;
  };
}

export interface JlcEdaRuntimeBoundary {
  readonly dmt_SelectControl?: Partial<
    Pick<DMT_SelectControl, 'getCurrentDocumentInfo'>
  >;
  readonly sch_SelectControl?: Partial<
    Pick<
      SCH_SelectControl,
      | 'getAllSelectedPrimitives'
      | 'getAllSelectedPrimitives_PrimitiveId'
      | 'clearSelected'
      | 'doSelectPrimitives'
      | 'doCrossProbeSelect'
    >
  >;
  readonly sys_Environment?: Partial<
    Pick<
      SYS_Environment,
      | 'getEditorCurrentVersion'
      | 'getEditorCompliedDate'
      | 'isClient'
      | 'isWeb'
      | 'isJLCEDAProEdition'
      | 'isEasyEDAProEdition'
    >
  >;
  readonly sys_Dialog?: Partial<Pick<SYS_Dialog, 'showInformationMessage' | 'showInputDialog'>>;
  readonly sys_Message?: Partial<Pick<SYS_Message, 'showToastMessage'>>;
  readonly sys_WebSocket?: Partial<Pick<SYS_WebSocket, 'register' | 'send' | 'close'>>;
}

export class JlcEdaCapabilityUnavailableError extends Error {
  readonly operation: string;

  constructor(operation: string) {
    super(`JLCEDA capability is unavailable: ${operation}`);
    this.name = 'JlcEdaCapabilityUnavailableError';
    this.operation = operation;
  }
}

export class JlcEdaApiCallError extends Error {
  readonly operation: string;

  constructor(operation: string, detail: string) {
    super(`JLCEDA API call failed (${operation}): ${detail}`);
    this.name = 'JlcEdaApiCallError';
    this.operation = operation;
  }
}

export class JlcEdaApiAdapter {
  readonly #runtime: JlcEdaRuntimeBoundary;

  constructor(runtime: JlcEdaRuntimeBoundary) {
    this.#runtime = runtime;
  }

  async readCurrentDocument(): Promise<CurrentDocumentReadDto> {
    const operation = 'dmt_SelectControl.getCurrentDocumentInfo';
    const control = this.#runtime.dmt_SelectControl;
    if (typeof control?.getCurrentDocumentInfo !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }

    try {
      const raw = await control.getCurrentDocumentInfo();
      const rawShape = summarizeDocumentShape(raw);
      if (raw === undefined) {
        return Object.freeze({ document: null, rawShape });
      }
      return Object.freeze({
        document: Object.freeze({
          provider: 'jlceda-pro' as const,
          documentId: requiredFiniteText(raw.uuid, 'document uuid'),
          documentType: normalizeDocumentType(raw.documentType),
          projectId: optionalFiniteText(raw.parentProjectUuid),
          libraryId: optionalFiniteText(raw.parentLibraryUuid),
        }),
        rawShape,
      });
    }
    catch (error) {
      if (error instanceof JlcEdaCapabilityUnavailableError) throw error;
      throw apiCallError(operation, error);
    }
  }

  async readCurrentSelection(): Promise<CurrentSelectionDto> {
    const operation = 'sch_SelectControl.getAllSelectedPrimitives';
    const control = this.#runtime.sch_SelectControl;
    if (typeof control?.getAllSelectedPrimitives !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    const identityOperation =
      'sch_SelectControl.getAllSelectedPrimitives_PrimitiveId';
    if (typeof control.getAllSelectedPrimitives_PrimitiveId !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(identityOperation);
    }

    try {
      const primitiveIds =
        await control.getAllSelectedPrimitives_PrimitiveId();
      const rawObjects = await control.getAllSelectedPrimitives();
      if (primitiveIds.length !== rawObjects.length) {
        throw new TypeError(
          'selection changed while reading primitive identities and objects',
        );
      }
      const objects = rawObjects
        .slice(0, MAX_SELECTION_OBJECTS)
        .map((primitive, index) => normalizePrimitive(
          primitive,
          primitiveIds[index],
        ));
      const primitiveTypeSummary: Record<string, number> = {};
      for (const object of objects) {
        primitiveTypeSummary[object.primitiveType] =
          (primitiveTypeSummary[object.primitiveType] ?? 0) + 1;
      }
      return Object.freeze({
        objects: Object.freeze(objects),
        totalSelected: rawObjects.length,
        truncated: rawObjects.length > objects.length,
        primitiveTypeSummary: Object.freeze(primitiveTypeSummary),
      });
    }
    catch (error) {
      if (error instanceof JlcEdaCapabilityUnavailableError) throw error;
      throw apiCallError(operation, error);
    }
  }

  async highlightSelection(): Promise<HighlightSelectionResultDto> {
    const operation = 'sch_SelectControl.doCrossProbeSelect';
    const control = this.#runtime.sch_SelectControl;
    if (typeof control?.doCrossProbeSelect !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    const clearOperation = 'sch_SelectControl.clearSelected';
    if (typeof control.clearSelected !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(clearOperation);
    }
    const restoreOperation = 'sch_SelectControl.doSelectPrimitives';
    if (typeof control.doSelectPrimitives !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(restoreOperation);
    }
    const restoreSelected = control.doSelectPrimitives.bind(control);

    const selection = await this.readCurrentSelection();
    const components = uniqueFiniteValues(
      selection.objects.map((object) => object.componentDesignator),
    );
    const nets = uniqueFiniteValues(
      selection.objects.map((object) => object.netName),
    );
    const pins: string[] = [];
    if (components.length === 0 && pins.length === 0 && nets.length === 0) {
      return Object.freeze({
        status: 'noop' as const,
        componentCount: 0,
        pinCount: 0,
        netCount: 0,
        warnings: Object.freeze([
          'Selected primitive types have no supported semantic highlight key.',
        ]),
      });
    }

    let selectionCleared: boolean;
    try {
      selectionCleared = await control.clearSelected();
    }
    catch (error) {
      throw apiCallError(clearOperation, error);
    }
    if (!selectionCleared) {
      return Object.freeze({
        status: 'noop' as const,
        componentCount: components.length,
        pinCount: pins.length,
        netCount: nets.length,
        warnings: Object.freeze([
          'Selected overlay could not be cleared; highlight was not attempted.',
        ]),
      });
    }

    try {
      const applied = await control.doCrossProbeSelect(
        components,
        pins,
        nets,
        true,
        false,
      );
      if (!applied) {
        const restored = await restoreSelection(
          restoreSelected,
          selection.objects.map((object) => object.primitiveId),
        );
        return Object.freeze({
          status: 'noop' as const,
          componentCount: components.length,
          pinCount: pins.length,
          netCount: nets.length,
          warnings: Object.freeze([
            'Official cross-probe API returned false.',
            restored
              ? 'Original selection was restored.'
              : 'Original selection could not be restored.',
          ]),
        });
      }
      return Object.freeze({
        status: 'applied' as const,
        componentCount: components.length,
        pinCount: pins.length,
        netCount: nets.length,
        warnings: Object.freeze([
          'Official API accepted the request after clearing the selected overlay; visual rendering cannot be verified through the API.',
        ]),
      });
    }
    catch (error) {
      await restoreSelection(
        restoreSelected,
        selection.objects.map((object) => object.primitiveId),
      );
      throw apiCallError(operation, error);
    }
  }

  readRuntimeDiagnostics(): RuntimeDiagnosticsDto {
    const environment = this.#runtime.sys_Environment;
    return Object.freeze({
      editorVersion: safeEnvironmentText(
        () => environment?.getEditorCurrentVersion?.(),
      ),
      editorCompiledDate: safeEnvironmentText(
        () => environment?.getEditorCompliedDate?.(),
      ),
      environment: safeEnvironmentBoolean(() => environment?.isClient?.())
        ? 'client'
        : safeEnvironmentBoolean(() => environment?.isWeb?.())
          ? 'web'
          : 'unknown',
      edition: safeEnvironmentBoolean(
        () => environment?.isJLCEDAProEdition?.(),
      )
        ? 'jlceda-pro'
        : safeEnvironmentBoolean(
            () => environment?.isEasyEDAProEdition?.(),
          )
          ? 'easyeda-pro'
          : 'unknown',
      capabilities: Object.freeze({
        documentRead:
          typeof this.#runtime.dmt_SelectControl?.getCurrentDocumentInfo
          === 'function',
        selectionRead:
          typeof this.#runtime.sch_SelectControl?.getAllSelectedPrimitives
          === 'function'
          && typeof this.#runtime.sch_SelectControl
            ?.getAllSelectedPrimitives_PrimitiveId === 'function',
        crossProbeHighlight:
          typeof this.#runtime.sch_SelectControl?.doCrossProbeSelect
          === 'function'
          && typeof this.#runtime.sch_SelectControl?.clearSelected
            === 'function'
          && typeof this.#runtime.sch_SelectControl?.doSelectPrimitives
            === 'function',
      }),
    });
  }

  showInformation(message: string, title: string): void {
    const operation = 'sys_Dialog.showInformationMessage';
    const dialog = this.#runtime.sys_Dialog;
    if (typeof dialog?.showInformationMessage !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    try {
      void dialog.showInformationMessage(
        requiredFiniteText(message, 'message', 4_096),
        requiredFiniteText(title, 'title'),
      );
    }
    catch (error) {
      throw apiCallError(operation, error);
    }
  }

  showToast(message: string): void {
    const operation = 'sys_Message.showToastMessage';
    const service = this.#runtime.sys_Message;
    if (typeof service?.showToastMessage !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    try {
      service.showToastMessage(requiredFiniteText(message, 'message', 1_024));
    }
    catch (error) {
      throw apiCallError(operation, error);
    }
  }

  registerWebSocket(
    id: string,
    serviceUri: string,
    onMessage: (data: string) => void | Promise<void>,
    onConnected: () => void | Promise<void>,
    onBoundaryFailure: (detail: string) => void = () => undefined,
  ): void {
    const operation = 'sys_WebSocket.register';
    const service = this.#runtime.sys_WebSocket;
    if (typeof service?.register !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    try {
      service.register(
        requiredFiniteText(id, 'WebSocket id'),
        requiredLoopbackWebSocketUri(serviceUri),
        (event) => {
          if (typeof event.data !== 'string') {
            reportHostCallbackFailure(
              onBoundaryFailure, 'AIA-JLCEDA accepts text messages only',
            );
            return;
          }
          invokeHostCallbackSafely(
            () => onMessage(event.data), onBoundaryFailure,
          );
        },
        () => invokeHostCallbackSafely(onConnected, onBoundaryFailure),
      );
    }
    catch (error) {
      throw apiCallError(operation, error);
    }
  }

  sendWebSocket(id: string, data: string): void {
    const operation = 'sys_WebSocket.send';
    const service = this.#runtime.sys_WebSocket;
    if (typeof service?.send !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    try {
      service.send(
        requiredFiniteText(id, 'WebSocket id'),
        requiredFiniteText(data, 'WebSocket message', 65_536),
      );
    }
    catch (error) {
      throw apiCallError(operation, error);
    }
  }

  closeWebSocket(id: string, code?: number, reason?: string): void {
    const operation = 'sys_WebSocket.close';
    const service = this.#runtime.sys_WebSocket;
    if (typeof service?.close !== 'function') return;
    try {
      service.close(
        requiredFiniteText(id, 'WebSocket id'),
        validClientCloseCode(code),
        reason === undefined ? undefined : requiredFiniteText(reason, 'close reason', 123),
      );
    }
    catch (error) {
      throw apiCallError(operation, error);
    }
  }

  requestBackendSecret(callback: (secret: string | null) => void): void {
    const operation = 'sys_Dialog.showInputDialog';
    const dialog = this.#runtime.sys_Dialog;
    if (typeof dialog?.showInputDialog !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    dialog.showInputDialog(
      'Paste the 43-character backend secret.',
      'It is kept in memory only and is never placed in the URL or logs.',
      'AI Instrument Assistant — Backend Authentication',
      'password',
      '',
      { minlength: 43, maxlength: 43, placeholder: 'Base64url secret' },
      (value) => callback(typeof value === 'string' ? value.trim() : null),
    );
  }
}

async function restoreSelection(
  restore: (primitiveIds: string | string[]) => Promise<boolean>,
  primitiveIds: readonly string[],
): Promise<boolean> {
  try {
    return await restore([...primitiveIds]);
  }
  catch {
    return false;
  }
}

function normalizePrimitive(
  raw: ISCH_Primitive,
  primitiveId: string | undefined,
): SelectedObjectDto {
  const primitiveType = requiredFiniteText(
    raw.getState_PrimitiveType(),
    'primitive type',
  );
  const base = {
    primitiveId: requiredFiniteText(primitiveId, 'primitive id'),
    primitiveType,
  };

  if (primitiveType === 'Wire') {
    const wire = raw as ISCH_PrimitiveWire;
    const netName = optionalFiniteText(wire.getState_Net());
    return Object.freeze(netName === null ? base : { ...base, netName });
  }
  if (primitiveType === 'Component') {
    const component = raw as ISCH_PrimitiveComponent;
    const componentDesignator = optionalFiniteText(
      component.getState_Designator(),
    );
    return Object.freeze(
      componentDesignator === null ? base : { ...base, componentDesignator },
    );
  }
  return Object.freeze(base);
}

function normalizeDocumentType(value: EDMT_EditorDocumentType): DocumentTypeDto {
  switch (Number(value)) {
    case -1: return 'home';
    case 0: return 'blank';
    case 1: return 'schematic';
    case 2: return 'symbol';
    case 3: return 'pcb';
    case 4: return 'footprint';
    default: return 'other';
  }
}

function summarizeDocumentShape(value: unknown): RawShapeSummaryDto {
  if (value === undefined) {
    return Object.freeze({
      kind: 'undefined', ownKeyCount: 0, ownKeys: [], unknownKeyCount: 0,
    });
  }
  if (value === null) {
    return Object.freeze({
      kind: 'null', ownKeyCount: 0, ownKeys: [], unknownKeyCount: 0,
    });
  }
  if (typeof value !== 'object') {
    return Object.freeze({
      kind: 'other', ownKeyCount: 0, ownKeys: [], unknownKeyCount: 0,
    });
  }
  const keys = Object.keys(value);
  const documentedKeys = keys
    .filter((key) => DOCUMENT_SHAPE_KEYS.has(key))
    .sort();
  return Object.freeze({
    kind: 'object',
    ownKeyCount: keys.length,
    ownKeys: Object.freeze(documentedKeys),
    unknownKeyCount: keys.length - documentedKeys.length,
  });
}

function requiredFiniteText(
  value: unknown,
  fieldName: string,
  maxLength = MAX_TEXT_LENGTH,
): string {
  const normalized = optionalFiniteText(value, maxLength);
  if (normalized === null) {
    throw new TypeError(`${fieldName} must be a non-empty finite string`);
  }
  return normalized;
}

function optionalFiniteText(
  value: unknown,
  maxLength = MAX_TEXT_LENGTH,
): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  if (normalized.length === 0) return null;
  return normalized.slice(0, maxLength);
}

function requiredLoopbackWebSocketUri(value: unknown): string {
  const uri = requiredFiniteText(value, 'WebSocket service URI');
  if (!/^ws:\/\/127\.0\.0\.1:\d{1,5}$/.test(uri)) {
    throw new TypeError('WebSocket service URI must use explicit 127.0.0.1');
  }
  return uri;
}

function validClientCloseCode(value: number | undefined): number | undefined {
  if (value === undefined) return undefined;
  if (!Number.isInteger(value) || (value !== 1000 && (value < 3000 || value > 4999))) {
    throw new RangeError('Client WebSocket close code must be 1000 or 3000-4999');
  }
  return value;
}

function invokeHostCallbackSafely(
  callback: () => void | Promise<void>,
  onFailure: (detail: string) => void,
): void {
  try {
    const result = callback();
    if (result !== undefined) {
      void Promise.resolve(result).catch((error: unknown) => {
        reportHostCallbackFailure(onFailure, errorDetail(error));
      });
    }
  }
  catch (error) {
    reportHostCallbackFailure(onFailure, errorDetail(error));
  }
}

function reportHostCallbackFailure(
  onFailure: (detail: string) => void,
  detail: string,
): void {
  try {
    onFailure(detail.slice(0, 256));
  }
  catch {
    // The official host callback boundary must never throw or return rejection.
  }
}

function errorDetail(error: unknown): string {
  return error instanceof Error
    ? optionalFiniteText(error.message, 256) ?? 'unknown callback error'
    : 'unknown callback error';
}

function uniqueFiniteValues(values: readonly (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => value !== undefined))];
}

function apiCallError(operation: string, error: unknown): JlcEdaApiCallError {
  const detail = error instanceof Error
    ? optionalFiniteText(error.message, 256) ?? 'unknown official runtime error'
    : 'unknown official runtime error';
  return new JlcEdaApiCallError(operation, detail);
}

function safeEnvironmentText(
  read: () => unknown,
): string | null {
  try {
    return optionalFiniteText(read());
  }
  catch {
    return null;
  }
}

function safeEnvironmentBoolean(
  read: () => boolean | undefined,
): boolean {
  try {
    return read() === true;
  }
  catch {
    return false;
  }
}
