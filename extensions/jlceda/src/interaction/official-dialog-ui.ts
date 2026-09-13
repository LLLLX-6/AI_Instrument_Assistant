import type { JlcEdaApiAdapter } from '../runtime/jlc-eda-api-adapter.ts';
import type { OfficialDialogUi } from './interaction-surface.ts';

export class OfficialJlcEdaDialogUi implements OfficialDialogUi {
  readonly #api: JlcEdaApiAdapter;
  constructor(api: JlcEdaApiAdapter) { this.#api = api; }
  showInformation(content: string, title?: string): void { this.#api.showInformation(content, title); }
  confirm(content: string, title?: string, accept?: string, cancel?: string): Promise<boolean> {
    return this.#api.showConfirmation(content, title, accept, cancel);
  }
  select(
    options: ReadonlyArray<{ value: string; displayContent: string }>,
    before?: string, after?: string, title?: string,
  ): Promise<string | null> { return this.#api.showSelection(options, before, after, title); }
}
