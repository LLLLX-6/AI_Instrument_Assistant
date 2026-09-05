import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');

test('Phase 5B.3 selection operation schema exists', () => {
  assert.equal(
    existsSync(join(root, 'protocols/jlceda/v1/messages/eda-selection.schema.json')),
    true,
  );
});
