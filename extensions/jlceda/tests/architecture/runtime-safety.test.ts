import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const extensionRoot = resolve(import.meta.dirname, '../..');
const sourceRoot = join(extensionRoot, 'src');
const officialAdapter = join(sourceRoot, 'runtime', 'jlc-eda-api-adapter.ts');
const dispatcherPath = join(sourceRoot, 'runtime', 'eda-protocol-dispatcher.ts');

function sourceFiles(root: string): string[] {
  return readdirSync(root)
    .flatMap((name) => {
      const path = join(root, name);
      return statSync(path).isDirectory() ? sourceFiles(path) : [path];
    })
    .filter((path) => path.endsWith('.ts'));
}

function parse(path: string): ts.SourceFile {
  return ts.createSourceFile(
    path,
    readFileSync(path, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
}

test('all official eda property access stays inside JlcEdaApiAdapter', () => {
  const violations: string[] = [];
  for (const path of sourceFiles(sourceRoot)) {
    if (path === officialAdapter) continue;
    const tree = parse(path);
    const visit = (node: ts.Node): void => {
      if (ts.isPropertyAccessExpression(node)
        && ts.isIdentifier(node.expression)
        && node.expression.text === 'eda') {
        violations.push(`${relative(extensionRoot, path)}:${tree.getLineAndCharacterOfPosition(node.pos).line + 1}`);
      }
      ts.forEachChild(node, visit);
    };
    visit(tree);
  }
  assert.deepEqual(violations, []);
});

test('product source has no dynamic execution, raw dispatch, network API import, or design mutation', () => {
  const violations: string[] = [];
  const forbiddenCalls = new Set([
    'eval',
    'Function',
    'AsyncFunction',
    'executeScript',
    'fetch',
    'create',
    'modify',
    'delete',
    'save',
    'done',
  ]);

  for (const path of sourceFiles(sourceRoot)) {
    const tree = parse(path);
    const visit = (node: ts.Node): void => {
      if (ts.isCallExpression(node)) {
        if (ts.isElementAccessExpression(node.expression)) {
          violations.push(`${relative(extensionRoot, path)}:dynamic-method-dispatch`);
        }
        const calledName = ts.isIdentifier(node.expression)
          ? node.expression.text
          : ts.isPropertyAccessExpression(node.expression)
            ? node.expression.name.text
            : null;
        if (calledName && forbiddenCalls.has(calledName)) {
          violations.push(`${relative(extensionRoot, path)}:${calledName}`);
        }
      }
      if (ts.isNewExpression(node)
        && ts.isIdentifier(node.expression)
        && (node.expression.text === 'Function'
          || node.expression.text === 'AsyncFunction')) {
        violations.push(
          `${relative(extensionRoot, path)}:new-${node.expression.text}`,
        );
      }
      if (path !== officialAdapter
        && ts.isPropertyAccessExpression(node)
        && node.name.text === 'sys_WebSocket') {
        violations.push(`${relative(extensionRoot, path)}:sys_WebSocket`);
      }
      if (ts.isPropertyAccessExpression(node)
        && (node.name.text === 'innerHTML'
          || node.name.text === 'outerHTML'
          || node.name.text === 'insertAdjacentHTML')) {
        violations.push(`${relative(extensionRoot, path)}:${node.name.text}`);
      }
      if (ts.isImportDeclaration(node)
        && ts.isStringLiteral(node.moduleSpecifier)
        && /^(node:)?(http|https|net|tls|ws|websocket)/.test(
          node.moduleSpecifier.text,
        )) {
        violations.push(
          `${relative(extensionRoot, path)}:transport-import`,
        );
      }
      ts.forEachChild(node, visit);
    };
    visit(tree);
  }
  assert.deepEqual(violations, []);
});

test('official WebSocket calls are a static allowlist inside JlcEdaApiAdapter', () => {
  const tree = parse(officialAdapter);
  const allowed = new Set(['register', 'send', 'close']);
  const observed = new Set<string>();
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)
      && ts.isPropertyAccessExpression(node.expression)
      && ts.isIdentifier(node.expression.expression)
      && node.expression.expression.text === 'service') {
      const name = node.expression.name.text;
      if (allowed.has(name)) observed.add(name);
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  assert.deepEqual([...observed].sort(), [...allowed].sort());
});

test('remote EDA dispatcher exposes only active-document and selection static operations', () => {
  const tree = parse(dispatcherPath);
  const operationStrings = new Set<string>();
  let dynamicCallCount = 0;
  const visit = (node: ts.Node): void => {
    if (ts.isStringLiteral(node) && node.text.startsWith('eda.')) {
      operationStrings.add(node.text);
    }
    if (ts.isCallExpression(node) && ts.isElementAccessExpression(node.expression)) {
      dynamicCallCount += 1;
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  assert.deepEqual([...operationStrings].sort(), [
    'eda.document.get_active',
    'eda.selection.get',
  ]);
  assert.equal(dynamicCallCount, 0);
});
