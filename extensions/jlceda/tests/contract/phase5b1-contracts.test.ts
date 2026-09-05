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
const requiredSchemas = [
  join(protocolRoot, 'common', 'security.schema.json'),
  join(protocolRoot, 'messages', 'handshake.schema.json'),
  join(protocolRoot, 'messages', 'heartbeat.schema.json'),
  join(protocolRoot, 'message.schema.json'),
];

test('Phase 5B.1 schema files exist and root message compiles', () => {
  for (const path of requiredSchemas) {
    assert.equal(existsSync(path), true, `Phase 5B.1 schema is missing: ${path}`);
  }
  const validator = new SchemaValidator(SchemaLoader.loadDirectory(protocolRoot));
  assert.equal(validator.validate('aia://protocol/jlceda/v1/message', {}).isValid, false);
});
