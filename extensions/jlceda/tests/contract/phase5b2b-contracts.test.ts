import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { SchemaLoader } from '../../src/protocol/schema-loader.ts';
import { SchemaValidator } from '../../src/protocol/schema-validator.ts';


const repositoryRoot = resolve(
  dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..',
);
const protocolRoot = join(repositoryRoot, 'protocols', 'jlceda', 'v1');

test('Phase 5B.2b document operation schema exists and compiles', () => {
  const path = join(protocolRoot, 'messages', 'eda-document.schema.json');
  assert.equal(existsSync(path), true, `Missing operation schema: ${path}`);
  const validator = new SchemaValidator(SchemaLoader.loadDirectory(protocolRoot));
  assert.equal(validator.validate('aia://protocol/jlceda/v1/message', {}).isValid, false);
});
