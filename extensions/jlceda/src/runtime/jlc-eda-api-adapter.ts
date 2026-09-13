import { HighlightPreflightError, type HighlightCommandDto, type HighlightExecutionContext } from './highlight-contract.ts';

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
  readonly status: 'accepted' | 'rejected';
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

export const RUNTIME_COMMAND_ACTIONS = [
  'STATUS',
  'REFRESH_DESIGN_CONTEXT',
  'RESOLVE_CURRENT_SELECTION',
  'CURRENT_TARGET',
  'PENDING_ACTION',
  'EVIDENCE_SUMMARY',
  'HIGHLIGHT_TARGET',
  'CANCEL_WORKFLOW',
  'DISCONNECT',
  'RECONNECT',
] as const;
export type RuntimeCommandAction = typeof RUNTIME_COMMAND_ACTIONS[number];

export type RuntimeCommandFailureCode =
  | 'runtime_owner_stale'
  | 'runtime_owner_unavailable'
  | 'runtime_not_connected'
  | 'runtime_action_failed'
  | 'SNAPSHOT_FRAME_INVALID'
  | 'SNAPSHOT_SESSION_MISMATCH'
  | 'SNAPSHOT_TRANSPORT_TIMEOUT'
  | 'SNAPSHOT_TRANSPORT_UNAVAILABLE'
  | 'SNAPSHOT_WAITER_ALREADY_PENDING'
  | 'STATUS_PRESENTATION_FAILED';

export type RuntimeCommandResult =
  | Readonly<{ status: 'COMPLETED'; reasonCode: null }>
  | Readonly<{ status: 'REJECTED'; reasonCode: RuntimeCommandFailureCode }>;

export type RuntimeCommandRpcErrorCode =
  | 'message_bus_unavailable'
  | 'message_bus_registration_failed'
  | 'message_bus_call_failed'
  | 'message_bus_response_invalid'
  | 'runtime_command_invalid'
  | RuntimeCommandFailureCode;

export class RuntimeCommandRpcError extends Error {
  readonly code: RuntimeCommandRpcErrorCode;
  constructor(code: RuntimeCommandRpcErrorCode) {
    super(code); this.name = 'RuntimeCommandRpcError'; this.code = code;
  }
}

const RUNTIME_COMMAND_TOPIC = 'aia.runtime.command';
const RUNTIME_COMMAND_ACTION_SET = new Set<string>(RUNTIME_COMMAND_ACTIONS);
const RUNTIME_COMMAND_FAILURE_CODES = new Set<RuntimeCommandFailureCode>([
  'runtime_owner_stale', 'runtime_owner_unavailable', 'runtime_not_connected',
  'runtime_action_failed', 'SNAPSHOT_FRAME_INVALID', 'SNAPSHOT_SESSION_MISMATCH',
  'SNAPSHOT_TRANSPORT_TIMEOUT', 'SNAPSHOT_TRANSPORT_UNAVAILABLE',
  'SNAPSHOT_WAITER_ALREADY_PENDING', 'STATUS_PRESENTATION_FAILED',
]);

export interface JlcEdaRuntimeBoundary {
  readonly sch_PrimitiveWire?: Partial<Pick<SCH_PrimitiveWire, 'get' | 'getAll'>>;
  readonly sch_PrimitiveComponent?: Partial<Pick<SCH_PrimitiveComponent, 'get' | 'getAll'>>;
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
  readonly sys_Dialog?: Partial<Pick<
    SYS_Dialog,
    'showInformationMessage' | 'showInputDialog' | 'showConfirmationMessage' | 'showSelectDialog'
  >>;
  readonly sys_Message?: Partial<Pick<SYS_Message, 'showToastMessage'>>;
  readonly sys_WebSocket?: Partial<Pick<SYS_WebSocket, 'register' | 'send' | 'close'>>;
  readonly sys_MessageBus?: Partial<Pick<SYS_MessageBus, 'rpcService' | 'rpcCall'>>;
  readonly sch_Event?: Partial<Pick<
    SCH_Event,
    'addMouseEventListener' | 'removeEventListener' | 'isEventListenerAlreadyExist'
  >>;
  readonly sys_Storage?: Partial<Pick<
    SYS_Storage,
    'getExtensionUserConfig' | 'setExtensionUserConfig'
  >>;
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

  registerRuntimeCommandService(
    dispatch: (action: RuntimeCommandAction) => Promise<RuntimeCommandResult>,
  ): void {
    const service = this.#runtime.sys_MessageBus;
    if (typeof service?.rpcService !== 'function') {
      throw new RuntimeCommandRpcError('message_bus_unavailable');
    }
    try {
      service.rpcService(RUNTIME_COMMAND_TOPIC, async (request: unknown) => {
        const action = normalizeRuntimeCommandRequest(request);
        return normalizeRuntimeCommandResult(await dispatch(action));
      });
    }
    catch {
      throw new RuntimeCommandRpcError('message_bus_registration_failed');
    }
  }

  async callRuntimeCommand(action: RuntimeCommandAction): Promise<RuntimeCommandResult> {
    const service = this.#runtime.sys_MessageBus;
    if (typeof service?.rpcCall !== 'function') {
      throw new RuntimeCommandRpcError('message_bus_unavailable');
    }
    let result: unknown;
    try {
      result = await service.rpcCall(
        RUNTIME_COMMAND_TOPIC,
        Object.freeze({ action }),
      );
    }
    catch (error) {
      if (error instanceof RuntimeCommandRpcError) throw error;
      throw new RuntimeCommandRpcError('message_bus_call_failed');
    }
    try { return normalizeRuntimeCommandResult(result); }
    catch { throw new RuntimeCommandRpcError('message_bus_response_invalid'); }
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

    let lastFailure: unknown;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const rawObjects = await control.getAllSelectedPrimitives();
        const primitiveIds = await control.getAllSelectedPrimitives_PrimitiveId();
        if (primitiveIds.length !== rawObjects.length) {
          throw new TypeError(
            'selection changed while reading primitive objects and identities',
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
        lastFailure = error;
        if (attempt === 0) await nextSelectionStabilizationTurn();
      }
    }
    throw apiCallError(operation, lastFailure);
  }

  highlightSelection(): Promise<HighlightSelectionResultDto>;
  highlightSelection(command: HighlightCommandDto, context: HighlightExecutionContext): Promise<Readonly<Record<string, unknown>>>;
  async highlightSelection(
    command?: HighlightCommandDto,
    context?: HighlightExecutionContext,
  ): Promise<HighlightSelectionResultDto | Readonly<Record<string, unknown>>> {
    if (command !== undefined) return this.#highlightCommand(command, context);
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
        status: 'rejected' as const,
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
        status: 'rejected' as const,
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
          status: 'rejected' as const,
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
        status: 'accepted' as const,
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


  async #highlightCommand(
    command: HighlightCommandDto,
    context: HighlightExecutionContext | undefined,
  ): Promise<Readonly<Record<string, unknown>>> {
    const requireLive = (): void => {
      if (context?.isActive() !== true) throw new HighlightPreflightError('session_invalid');
    };
    requireLive();
    if (command.guard_mode === 'strong_required') {
      throw new HighlightPreflightError('strong_guard_unavailable');
    }
    if (command.ttl_ms !== null || command.style !== 'provider_default'
      || command.replace_existing !== null) {
      throw new HighlightPreflightError('presentation_unsupported');
    }
    const control = this.#runtime.sch_SelectControl;
    if (typeof control?.doCrossProbeSelect !== 'function') {
      throw new HighlightPreflightError('capability_unsupported');
    }
    const requireDocument = async (): Promise<void> => {
      const observed = await this.readCurrentDocument();
      requireLive();
      if (observed.document === null) throw new HighlightPreflightError('no_active_document');
      if (observed.document.provider !== command.document_ref.provider
        || observed.document.documentId !== command.document_ref.document_id
        || command.document_ref.native_id !== observed.document.documentId) {
        throw new HighlightPreflightError('stale_design_snapshot');
      }
      if (observed.document.documentType !== 'schematic') {
        throw new HighlightPreflightError('unsupported_target');
      }
    };
    const components: string[] = [];
    const nets: string[] = [];
    let expansion = false;
    await requireDocument();
    for (const target of command.targets) {
      requireLive();
      if (target.provider !== command.document_ref.provider
        || target.document_id !== command.document_ref.document_id
        || target.snapshot_id !== command.expected_snapshot_id
        || command.document_ref.snapshot_id !== command.expected_snapshot_id) {
        throw new HighlightPreflightError('stale_design_snapshot');
      }
      if (target.object_type === 'wire') {
        const api = this.#runtime.sch_PrimitiveWire;
        if (typeof api?.get !== 'function') throw new HighlightPreflightError('capability_unsupported');
        if (target.native_id === null) throw new HighlightPreflightError('object_not_found');
        const wire = await api.get(target.native_id);
        if (wire === undefined) throw new HighlightPreflightError('object_not_found');
        if (wire.getState_PrimitiveType() !== 'Wire') throw new HighlightPreflightError('ambiguous_target');
        const name = exactSemanticText(wire.getState_Net());
        if (name === null) throw new HighlightPreflightError('unsupported_target');
        if (!command.allow_scope_expansion) throw new HighlightPreflightError('scope_expansion_required');
        nets.push(name);
        expansion = true;
      }
      else if (target.object_type === 'component') {
        const api = this.#runtime.sch_PrimitiveComponent;
        if (typeof api?.get !== 'function' || typeof api.getAll !== 'function') {
          throw new HighlightPreflightError('capability_unsupported');
        }
        if (target.native_id === null) throw new HighlightPreflightError('object_not_found');
        const component = await api.get(target.native_id);
        if (component === undefined) throw new HighlightPreflightError('object_not_found');
        if (component.getState_PrimitiveType() !== 'Component') throw new HighlightPreflightError('ambiguous_target');
        const name = exactSemanticText(component.getState_Designator());
        if (name === null) throw new HighlightPreflightError('unsupported_target');
        const all = await api.getAll(undefined, true);
        if (all.length > 4096) throw new HighlightPreflightError('ambiguous_target');
        const matching = all.filter((item) => item.getState_Designator() === name);
        if (matching.length !== 1) throw new HighlightPreflightError('ambiguous_target');
        components.push(name);
      }
      else if (target.object_type === 'net') {
        const name = exactSemanticText(target.display_name);
        if (name === null) throw new HighlightPreflightError('unsupported_target');
        const api = this.#runtime.sch_PrimitiveWire;
        if (typeof api?.getAll !== 'function') throw new HighlightPreflightError('capability_unsupported');
        const wires = await api.getAll(name);
        if (wires.length === 0) throw new HighlightPreflightError('object_not_found');
        if (wires.length > 4096 || wires.some((wire) => wire.getState_Net() !== name)) {
          throw new HighlightPreflightError('ambiguous_target');
        }
        nets.push(name);
      }
      else throw new HighlightPreflightError('unsupported_target');
    }
    await requireDocument();
    requireLive();
    let submission: 'accepted' | 'rejected' | 'indeterminate';
    try {
      // No await between the last liveness check and provider invocation.
      console.info('[AI Instrument Assistant] guarded cross-probe invocation');
      const accepted = await control.doCrossProbeSelect(
        [...new Set(components)], [], [...new Set(nets)], true, false,
      );
      submission = accepted === true ? 'accepted' : accepted === false ? 'rejected' : 'indeterminate';
    }
    catch {
      submission = 'indeterminate';
    }
    if (context?.isActive() !== true) submission = 'indeterminate';
    return Object.freeze({
      model_version: '1.0',
      submission_status: submission,
      verification_status: 'unverified',
      submitted_targets: command.targets,
      verified_applied_targets: Object.freeze([]),
      guard_mode_used: command.guard_mode,
      scope_expansion: expansion ? 'wire_to_net' : 'none',
      warnings: Object.freeze([
        'Weak identity checks do not provide strong stale protection.',
        submission === 'rejected' ? 'provider_rejected'
          : submission === 'indeterminate' ? 'Outcome unknown; do not replay automatically.'
            : 'Provider accepted cross-probe; visible rendering is unverified.',
      ]),
      expires_at: null,
    });
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

  showInformation(message: string, title = 'AI Instrument Assistant'): void {
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

  showConfirmation(
    message: string,
    title = 'AI Instrument Assistant',
    accept = 'Confirm',
    cancel = 'Cancel',
  ): Promise<boolean> {
    const operation = 'sys_Dialog.showConfirmationMessage';
    const dialog = this.#runtime.sys_Dialog;
    if (typeof dialog?.showConfirmationMessage !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    const show = dialog.showConfirmationMessage.bind(dialog);
    return new Promise((resolve) => {
      try {
        show(
          requiredFiniteText(message, 'message', 4_096),
          requiredFiniteText(title, 'title'), requiredFiniteText(accept, 'accept'),
          requiredFiniteText(cancel, 'cancel'), (value) => resolve(value === true),
        );
      }
      catch (error) { throw apiCallError(operation, error); }
    });
  }

  showSelection(
    options: ReadonlyArray<{ value: string; displayContent: string }>,
    before = 'Choose an option.',
    after = '',
    title = 'AI Instrument Assistant',
  ): Promise<string | null> {
    const operation = 'sys_Dialog.showSelectDialog';
    const dialog = this.#runtime.sys_Dialog;
    if (typeof dialog?.showSelectDialog !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    const show = dialog.showSelectDialog.bind(dialog);
    if (options.length < 1 || options.length > 16) throw new TypeError('select options must be bounded');
    const boundedOptions = options.map((value) => ({
      value: requiredFiniteText(value.value, 'option value', 192),
      displayContent: requiredFiniteText(value.displayContent, 'option label', 160),
    }));
    return new Promise((resolve) => {
      try {
        show(
          boundedOptions, before.slice(0, 1_024), after.slice(0, 1_024), title.slice(0, 120),
          boundedOptions[0]?.value, false,
          (value) => resolve(typeof value === 'string' && boundedOptions.some((item) => item.value === value) ? value : null),
        );
      }
      catch (error) { throw apiCallError(operation, error); }
    });
  }

  registerSelectionListener(id: string, callback: () => void | Promise<void>): boolean {
    const operation = 'sch_Event.addMouseEventListener';
    const events = this.#runtime.sch_Event;
    if (typeof events?.addMouseEventListener !== 'function'
      || typeof events.isEventListenerAlreadyExist !== 'function') {
      throw new JlcEdaCapabilityUnavailableError(operation);
    }
    const listenerId = requiredFiniteText(id, 'listener id', 80);
    try {
      if (events.isEventListenerAlreadyExist(listenerId)) {
        if (typeof events.removeEventListener !== 'function') return false;
        events.removeEventListener(listenerId);
        if (events.isEventListenerAlreadyExist(listenerId)) return false;
      }
      events.addMouseEventListener(
        listenerId, 'all', () => invokeHostCallbackSafely(callback, () => undefined), false,
      );
      return events.isEventListenerAlreadyExist(listenerId);
    }
    catch (error) { throw apiCallError(operation, error); }
  }

  removeSelectionListener(id: string): boolean {
    const operation = 'sch_Event.removeEventListener';
    const events = this.#runtime.sch_Event;
    if (typeof events?.removeEventListener !== 'function') return true;
    try {
      const listenerId = requiredFiniteText(id, 'listener id', 80);
      if (typeof events.isEventListenerAlreadyExist === 'function'
        && !events.isEventListenerAlreadyExist(listenerId)) return true;
      events.removeEventListener(listenerId);
      return typeof events.isEventListenerAlreadyExist !== 'function'
        || !events.isEventListenerAlreadyExist(listenerId);
    }
    catch (error) { throw apiCallError(operation, error); }
  }

  readInteractivePort(defaultPort: number): number {
    const value = this.#runtime.sys_Storage?.getExtensionUserConfig?.('aia_interactive_port');
    return validInteractivePort(value) ? value : validInteractivePort(defaultPort) ? defaultPort : 49_626;
  }

  async writeInteractivePort(port: number): Promise<boolean> {
    if (!validInteractivePort(port)) throw new TypeError('interactive port is invalid or reserved');
    const write = this.#runtime.sys_Storage?.setExtensionUserConfig;
    if (typeof write !== 'function') return false;
    try { return await write.call(this.#runtime.sys_Storage, 'aia_interactive_port', port); }
    catch (error) { throw apiCallError('sys_Storage.setExtensionUserConfig', error); }
  }

  requestInteractivePort(defaultPort: number, callback: (port: number | null) => void): void {
    const operation = 'sys_Dialog.showInputDialog';
    const dialog = this.#runtime.sys_Dialog;
    if (typeof dialog?.showInputDialog !== 'function') throw new JlcEdaCapabilityUnavailableError(operation);
    dialog.showInputDialog(
      'Interactive Host port on 127.0.0.1',
      '49624 is reserved for EDA; 49625 is reserved for Hardware.',
      'Configure AI Instrument Assistant Connection', 'number', defaultPort,
      { min: 1, max: 65_535, step: 1 },
      (value) => {
        const port = Number(value);
        callback(validInteractivePort(port) ? port : null);
      },
    );
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

function validInteractivePort(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 1 && Number(value) <= 65_535
    && Number(value) !== 49_624 && Number(value) !== 49_625;
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

function nextSelectionStabilizationTurn(): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, 0));
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

function normalizeRuntimeCommandRequest(value: unknown): RuntimeCommandAction {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new RuntimeCommandRpcError('runtime_command_invalid');
  }
  const object = value as Record<string, unknown>;
  if (Object.keys(object).join('\n') !== 'action'
    || typeof object.action !== 'string'
    || !RUNTIME_COMMAND_ACTION_SET.has(object.action)) {
    throw new RuntimeCommandRpcError('runtime_command_invalid');
  }
  return object.action as RuntimeCommandAction;
}

function normalizeRuntimeCommandResult(value: unknown): RuntimeCommandResult {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('runtime command result required');
  }
  const object = value as Record<string, unknown>;
  if (Object.keys(object).sort().join('\n') !== 'reasonCode\nstatus') {
    throw new TypeError('runtime command result fields invalid');
  }
  if (object.status === 'COMPLETED' && object.reasonCode === null) {
    return Object.freeze({ status: 'COMPLETED', reasonCode: null });
  }
  if (object.status === 'REJECTED' && typeof object.reasonCode === 'string'
    && RUNTIME_COMMAND_FAILURE_CODES.has(object.reasonCode as RuntimeCommandFailureCode)) {
    return Object.freeze({
      status: 'REJECTED',
      reasonCode: object.reasonCode as RuntimeCommandFailureCode,
    });
  }
  throw new TypeError('runtime command result invalid');
}

function exactSemanticText(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim() || value.length > 512) return null;
  // Routing keys must never be truncated into a different target.
  return value;
}
