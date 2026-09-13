export class SelectionObserver {
  readonly #register: (callback: () => void) => boolean;
  readonly #remove: () => boolean;
  readonly #onDebouncedChange: () => void;
  readonly #schedule: (callback: () => void, delayMs: number) => unknown;
  readonly #clear: (handle: unknown) => void;
  #active = false;
  #pending: unknown = null;
  #generation = 0;

  constructor(options: {
    register(callback: () => void): boolean; remove(): boolean;
    onDebouncedChange?: () => void;
    schedule?: (callback: () => void, delayMs: number) => unknown;
    clear?: (handle: unknown) => void;
  }) {
    this.#register = options.register; this.#remove = options.remove;
    this.#onDebouncedChange = options.onDebouncedChange ?? (() => undefined);
    this.#schedule = options.schedule ?? ((callback, delay) => setTimeout(callback, delay));
    this.#clear = options.clear ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  }

  start(): boolean {
    if (this.#active) return false;
    const generation = ++this.#generation;
    this.#active = this.#register(() => this.#changed(generation));
    return this.#active;
  }
  dispose(): void {
    if (!this.#active) return;
    this.#active = false;
    this.#generation += 1;
    if (this.#pending !== null) this.#clear(this.#pending);
    this.#pending = null; this.#remove();
  }
  #changed(generation: number): void {
    if (!this.#active || generation !== this.#generation) return;
    if (this.#pending !== null) this.#clear(this.#pending);
    this.#pending = this.#schedule(() => {
      this.#pending = null;
      if (!this.#active || generation !== this.#generation) return;
      this.#onDebouncedChange();
    }, 150);
  }
}
