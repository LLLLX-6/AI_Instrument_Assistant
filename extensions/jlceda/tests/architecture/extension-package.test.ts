import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const extensionRoot = resolve(import.meta.dirname, '../..');

function jsonFile(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>;
}

test('extension manifest pins the reviewed engine and static menu allowlist', () => {
  const manifest = jsonFile(join(extensionRoot, 'extension.json'));
  assert.deepEqual(manifest.engines, { eda: '^3.2.0' });
  assert.equal(manifest.entry, './dist/index');
  assert.deepEqual(manifest.activationEvents, { onStartupFinished: true });

  const menus = manifest.headerMenus as {
    sch: Array<{ title: string; menuItems: Array<{ registerFn: string }> }>;
  };
  assert.equal(menus.sch[0].title, 'AI Instrument Assistant');
  assert.deepEqual(
    menus.sch[0].menuItems.map((item) => item.registerFn),
    [
      'showStatus',
      'refreshDesignContext',
      'resolveCurrentSelection',
      'showCurrentTarget',
      'showPendingAction',
      'showEvidenceSummary',
      'highlightTarget',
      'cancelWorkflow',
      'configureConnection',
      'configureProviderConnection',
      'disconnect',
      'reconnect',
      'about',
    ],
  );
});

test('SDK compatibility and API types are exact pins', () => {
  const packageJson = jsonFile(join(extensionRoot, 'package.json'));
  const compatibility = packageJson.aiaJlcEdaCompatibility as Record<string, string>;
  const devDependencies = packageJson.devDependencies as Record<string, string>;
  assert.deepEqual(compatibility, {
    proApiSdk: '1.6.17',
    edaEngine: '^3.2.0',
    proApiTypes: '0.4.14',
  });
  assert.equal(devDependencies['@jlceda/pro-api-types'], '0.4.14');
  assert.equal((packageJson.engines as Record<string, string>).node, '>=20.17.0');
});

test('contract tests, adapter tests, and extension build have separate scripts', () => {
  const packageJson = jsonFile(join(extensionRoot, 'package.json'));
  const scripts = packageJson.scripts as Record<string, string>;
  assert.ok(scripts['test:contracts']);
  assert.ok(scripts['test:adapter']);
  assert.ok(scripts.build);
  assert.notEqual(scripts['test:contracts'], scripts.build);
  assert.notEqual(scripts['test:adapter'], scripts.build);
});

test('extension bundle exposes menu functions through the official runtime global', () => {
  const buildScriptPath = join(extensionRoot, 'scripts', 'build-extension.mjs');
  const source = ts.createSourceFile(
    buildScriptPath,
    readFileSync(buildScriptPath, 'utf8'),
    ts.ScriptTarget.ESNext,
    true,
    ts.ScriptKind.JS,
  );
  let buildOptions: ts.ObjectLiteralExpression | undefined;

  function visit(node: ts.Node): void {
    if (
      ts.isCallExpression(node)
      && ts.isIdentifier(node.expression)
      && node.expression.text === 'build'
      && node.arguments.length === 1
      && ts.isObjectLiteralExpression(node.arguments[0])
    ) {
      buildOptions = node.arguments[0];
    }
    ts.forEachChild(node, visit);
  }
  visit(source);

  assert.ok(buildOptions, 'esbuild build options were not found');
  const values = new Map<string, string>();
  for (const property of buildOptions.properties) {
    if (
      ts.isPropertyAssignment(property)
      && ts.isIdentifier(property.name)
      && ts.isStringLiteral(property.initializer)
    ) {
      values.set(property.name.text, property.initializer.text);
    }
  }
  assert.equal(values.get('format'), 'iife');
  assert.equal(values.get('globalName'), 'edaEsbuildExportName');
});
