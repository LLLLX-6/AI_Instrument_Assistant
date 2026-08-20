import assert from 'node:assert/strict';
import { test } from 'node:test';

test('Node executes the TypeScript contract-test environment', () => {
  const protocolVersion: string = '1.0';
  assert.equal(protocolVersion, '1.0');
});

