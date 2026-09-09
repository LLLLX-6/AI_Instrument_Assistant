export type RunnerFailureCategory =
  | "COMPATIBILITY_STOP"
  | "MULTIPLE_TOOL_SELECTION"
  | "SEMANTIC_TOOL_MISMATCH"
  | "POLICY_MISMATCH"
  | "EGRESS_VALIDATION_FAILED"
  | "GROUNDING_VALIDATION_FAILED"
  | "PRECONDITION_FAILED"
  | "UNEXPECTED_RUNNER_FAILURE";

export type HardwareExecutionState = "NOT_OCCURRED" | "MAY_HAVE_OCCURRED" | "CONFIRMED";
export type BackendShutdownState = "COMPLETED" | "FAILED";

export interface BoundedScenarioCounts {
  readonly semanticToolCallCount: number;
  readonly ipcDispatchCount: number;
  readonly physicalExecutionCount: number;
  readonly modelRetryCount: number;
  readonly toolRetryCount: number;
}

export interface BoundedRunnerResult {
  readonly status: "COMPLETED" | "STOPPED";
  readonly phase: string;
  readonly scenario: string;
  readonly failureCategory: RunnerFailureCategory | null;
  readonly counts: BoundedScenarioCounts;
  readonly ipcDispatchOccurred: boolean;
  readonly hardwareExecution: HardwareExecutionState;
  readonly modelRetryOccurred: boolean;
  readonly toolRetryOccurred: boolean;
  readonly backendShutdown: BackendShutdownState;
}

export class CompatibilityStop extends Error {
  readonly category: Exclude<RunnerFailureCategory, "UNEXPECTED_RUNNER_FAILURE">;

  constructor(
    category: Exclude<RunnerFailureCategory, "UNEXPECTED_RUNNER_FAILURE">,
    internalDiagnostic?: string,
  ) {
    super(internalDiagnostic ?? category);
    this.name = "CompatibilityStop";
    this.category = category;
  }
}

export class BoundedScenarioState {
  private semanticToolCallCount = 0;
  private ipcDispatchCount = 0;
  private physicalExecutionCount = 0;
  private modelRetryCount = 0;
  private toolRetryCount = 0;
  private hardwareExecution: HardwareExecutionState = "NOT_OCCURRED";

  recordToolSelection(): void { this.semanticToolCallCount += 1; }

  recordIpcDispatch(execution: "NOT_OCCURRED" | "MAY_HAVE_OCCURRED" = "MAY_HAVE_OCCURRED"): void {
    this.ipcDispatchCount += 1;
    if (execution === "MAY_HAVE_OCCURRED" && this.hardwareExecution === "NOT_OCCURRED") {
      this.hardwareExecution = "MAY_HAVE_OCCURRED";
    }
  }

  recordHardwareExecution(isPhysicalMeasurement = true): void {
    if (isPhysicalMeasurement) this.physicalExecutionCount += 1;
    this.hardwareExecution = "CONFIRMED";
  }

  recordPhysicalExecution(): void { this.recordHardwareExecution(true); }

  recordModelRetry(): void { this.modelRetryCount += 1; }
  recordToolRetry(): void { this.toolRetryCount += 1; }

  snapshot(): Readonly<{ counts: BoundedScenarioCounts; hardwareExecution: HardwareExecutionState }> {
    return Object.freeze({
      counts: Object.freeze({
        semanticToolCallCount: this.semanticToolCallCount,
        ipcDispatchCount: this.ipcDispatchCount,
        physicalExecutionCount: this.physicalExecutionCount,
        modelRetryCount: this.modelRetryCount,
        toolRetryCount: this.toolRetryCount,
      }),
      hardwareExecution: this.hardwareExecution,
    });
  }
}

export interface BoundedFailureBoundaryOptions {
  readonly phase: string;
  readonly scenario: string;
  readonly state: BoundedScenarioState;
  readonly execute: () => void | Promise<void>;
  readonly shutdown: () => void | Promise<void>;
}

export async function runWithBoundedFailureBoundary(
  options: BoundedFailureBoundaryOptions,
): Promise<BoundedRunnerResult> {
  let failureCategory: RunnerFailureCategory | null = null;
  try {
    await options.execute();
  } catch (error: unknown) {
    failureCategory = error instanceof CompatibilityStop
      ? error.category
      : "UNEXPECTED_RUNNER_FAILURE";
  }

  let backendShutdown: BackendShutdownState = "COMPLETED";
  try {
    await options.shutdown();
  } catch {
    backendShutdown = "FAILED";
    failureCategory ??= "UNEXPECTED_RUNNER_FAILURE";
  }

  const snapshot = options.state.snapshot();
  return Object.freeze({
    status: failureCategory === null ? "COMPLETED" : "STOPPED",
    phase: boundedIdentifier(options.phase, "phase"),
    scenario: boundedIdentifier(options.scenario, "scenario"),
    failureCategory,
    counts: snapshot.counts,
    ipcDispatchOccurred: snapshot.counts.ipcDispatchCount > 0,
    hardwareExecution: snapshot.hardwareExecution,
    modelRetryOccurred: snapshot.counts.modelRetryCount > 0,
    toolRetryOccurred: snapshot.counts.toolRetryCount > 0,
    backendShutdown,
  });
}

function boundedIdentifier(value: string, field: string): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value)) {
    return field === "phase" ? "invalid-phase" : "invalid-scenario";
  }
  return value;
}
