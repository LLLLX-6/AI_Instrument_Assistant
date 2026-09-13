import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const root = resolve(import.meta.dirname, '../..');
const interaction = join(root, 'src', 'interaction');
const adapter = join(root, 'src', 'runtime', 'jlc-eda-api-adapter.ts');

function files(path: string): string[] {
  return readdirSync(path).flatMap((name) => {
    const child = join(path, name); return statSync(child).isDirectory() ? files(child) : [child];
  }).filter((value) => value.endsWith('.ts'));
}

test('JLCEDA interaction surface imports no execution or authority implementation', () => {
  const violations: string[] = [];
  const forbiddenImport = /(hardware|visa|scpi|deepseek|agent)/i;
  const forbiddenNames = new Set(['TrustedOperationScope', 'ProbeSetupConfirmation', 'ExecutePreparedMeasurement']);
  for (const path of files(interaction)) {
    const tree = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
    for (const node of walk(tree)) {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier) && forbiddenImport.test(node.moduleSpecifier.text)) violations.push(relative(root, path));
      if (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && forbiddenNames.has(node.expression.text)) violations.push(`${relative(root, path)}:${node.expression.text}`);
    }
  }
  assert.deepEqual(violations, []);
});

test('production source has no portal, spike auth, script injection, or direct eda access', () => {
  const violations: string[] = [];
  for (const path of files(join(root, 'src'))) {
    const source = readFileSync(path, 'utf8');
    if (/createDesignPortal|aia-interactive-auth-spike|insertScriptToDialog/.test(source)) violations.push(relative(root, path));
    if (path !== adapter) {
      const tree = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
      for (const node of walk(tree)) {
        if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'eda') violations.push(relative(root, path));
      }
    }
  }
  assert.deepEqual(violations, []);
});

test('interactive endpoint does not collide with frozen provider and Hardware ports', () => {
  const source = readFileSync(join(interaction, 'interactive-client.ts'), 'utf8');
  assert.match(source, /DEFAULT_INTERACTIVE_PORT\s*=\s*49_626/);
  assert.match(source, /49_624/); assert.match(source, /49_625/);
  assert.doesNotMatch(source, /endpoint:\s*\{[^}]*port:\s*49_62[45]/s);
});

test('production JLCEDA surface defers operation and physical authority to Harness', () => {
  const source = readFileSync(join(interaction, 'interaction-surface.ts'), 'utf8');
  assert.match(source, /OPERATION_AUTHORIZATION[^\n]*showHarnessDeferral/);
  assert.match(source, /PHYSICAL_SETUP[^\n]*showHarnessDeferral/);
  assert.match(source, /Continue authorization in DeepSeek Harness/);
  assert.doesNotMatch(source, /#operationAuthorization|#physicalSetup/);
  assert.doesNotMatch(source, /operation_plan_identity[\s\S]*answerChallenge/);
});

test('JLCEDA interaction runtime is created by activation and disposed by deactivation', () => {
  const path = join(root, 'src', 'index.ts');
  const tree = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const creations = walk(tree).filter((node): node is ts.NewExpression =>
    ts.isNewExpression(node)
    && ts.isIdentifier(node.expression)
    && node.expression.text === 'JlcEdaInteractionRuntime'
  );
  assert.equal(creations.length, 1);
  const owner = nearestFunction(creations[0]!);
  assert.ok(owner && ts.isFunctionDeclaration(owner) && owner.name?.text === 'activate');
  assert.match(owner.getText(tree), /if\s*\(interaction\s*===\s*null\)/);

  const deactivate = tree.statements.find((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && node.name?.text === 'deactivate'
  );
  assert.ok(deactivate);
  assert.match(deactivate.getText(tree), /interaction\?\.dispose\(\)/);

  const fallback = tree.statements.find((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && node.name?.text === 'activateForMenuIfNeeded'
  );
  assert.ok(fallback);
  assert.match(fallback.getText(tree), /activate\(\)/);
  assert.doesNotMatch(fallback.getText(tree), /new\s+JlcEdaInteractionRuntime/);
});

test('interactive configuration avoids unsupported nested input-dialog callbacks', () => {
  const path = join(root, 'src', 'index.ts');
  const tree = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const configure = tree.statements.find((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && node.name?.text === 'configureConnection'
  );
  assert.ok(configure);
  assert.match(configure.getText(tree), /readInteractivePort\(DEFAULT_INTERACTIVE_PORT\)/);
  assert.match(configure.getText(tree), /requestBackendSecret/);
  assert.doesNotMatch(configure.getText(tree), /requestInteractivePort/);
});

test('client completion diagnostics expose bounded counts and no raw transport values', () => {
  const clientPath = join(interaction, 'interactive-client.ts');
  const tree = ts.createSourceFile(clientPath, readFileSync(clientPath, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const diagnostics = tree.statements.find((node): node is ts.InterfaceDeclaration =>
    ts.isInterfaceDeclaration(node) && node.name.text === 'InteractiveClientDiagnostics'
  );
  assert.ok(diagnostics);
  const names = diagnostics.members.map((member) => member.name?.getText(tree) ?? '');
  assert.ok(names.length >= 12);
  assert.ok(names.every((name) => name.endsWith('Count')));
  assert.ok(names.every((name) => !/(payload|credential|secret|hmac|path|identifier|messageContent)/i.test(name)));

  const source = readFileSync(clientPath, 'utf8');
  assert.match(source, /#snapshotWaiter:\s*SnapshotWaiter\s*\|\s*null/);
  assert.doesNotMatch(source, /#snapshotWaiters:\s*Array/);
});

test('Status error projection uses an exact allowlist and never emits raw exception text', () => {
  const indexPath = join(root, 'src', 'index.ts');
  const tree = ts.createSourceFile(indexPath, readFileSync(indexPath, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const projection = tree.statements.find((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && node.name?.text === 'statusFailureMessage'
  );
  assert.ok(projection);
  const source = projection.getText(tree);
  assert.match(source, /SNAPSHOT_TRANSPORT_TIMEOUT/);
  assert.match(source, /SNAPSHOT_FRAME_INVALID/);
  assert.match(source, /SNAPSHOT_SESSION_MISMATCH/);
  assert.match(source, /STATUS_PRESENTATION_FAILED/);
  assert.doesNotMatch(source, /`[^`]*\$\{(?:error|code)/);
});

test('menu runtime commands use one closed private bridge and no module-local runtime', () => {
  const indexPath = join(root, 'src', 'index.ts');
  const source = readFileSync(indexPath, 'utf8');
  const tree = ts.createSourceFile(indexPath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const expected = new Map([
    ['showStatus', 'STATUS'],
    ['refreshDesignContext', 'REFRESH_DESIGN_CONTEXT'],
    ['resolveCurrentSelection', 'RESOLVE_CURRENT_SELECTION'],
    ['showCurrentTarget', 'CURRENT_TARGET'],
    ['showPendingAction', 'PENDING_ACTION'],
    ['showEvidenceSummary', 'EVIDENCE_SUMMARY'],
    ['highlightTarget', 'HIGHLIGHT_TARGET'],
    ['cancelWorkflow', 'CANCEL_WORKFLOW'],
    ['disconnect', 'DISCONNECT'],
    ['reconnect', 'RECONNECT'],
  ]);
  for (const [name, action] of expected) {
    const declaration = tree.statements.find((node): node is ts.FunctionDeclaration =>
      ts.isFunctionDeclaration(node) && node.name?.text === name
    );
    assert.ok(declaration, `${name} must exist`);
    assert.match(declaration.getText(tree), new RegExp(`delegateRuntimeAction\\('${action}'`));
    assert.doesNotMatch(declaration.getText(tree), /interactionOrUnavailable|new\s+JlcEdaInteractionRuntime/);
  }

  const bridge = readFileSync(join(interaction, 'runtime-command-bridge.ts'), 'utf8');
  assert.doesNotMatch(bridge, /rpcCallPublic|rpcServicePublic|removePrivateMessageBus|\beval\b|new\s+Function/);
  assert.doesNotMatch(bridge, /runtime\s*\[\s*action\s*\]/);
  assert.equal(source.match(/new JlcEdaWebSocketTransport/g)?.length, 1);
});

test('production selection keeps canonical object read and has no ID-resolution fallback', () => {
  const source = readFileSync(adapter, 'utf8');
  assert.match(source, /control\.getAllSelectedPrimitives\(\)/);
  assert.doesNotMatch(source, /getPrimitivesByPrimitiveId/);
  assert.doesNotMatch(source, /provider-selection-api-diagnostic|selection-api-diagnostic/);
});

function walk(rootNode: ts.Node): ts.Node[] {
  const values: ts.Node[] = [];
  const visit = (node: ts.Node): void => { values.push(node); ts.forEachChild(node, visit); };
  visit(rootNode); return values;
}

function nearestFunction(node: ts.Node): ts.Node | undefined {
  let current: ts.Node | undefined = node.parent;
  while (current !== undefined) {
    if (ts.isFunctionLike(current)) return current;
    current = current.parent;
  }
  return undefined;
}
