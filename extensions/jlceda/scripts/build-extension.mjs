import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { build } from 'esbuild';
import JSZip from 'jszip';

const extensionRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDirectory = join(extensionRoot, 'dist');
const packageDirectory = join(extensionRoot, 'build', 'dist');
const manifestPath = join(extensionRoot, 'extension.json');
const compiledEntryPath = join(distDirectory, 'index.js');

const manifestText = await readFile(manifestPath, 'utf8');
const manifest = JSON.parse(manifestText);
if (manifest.entry !== './dist/index') {
  throw new Error('extension.json entry must remain ./dist/index');
}

await rm(distDirectory, { recursive: true, force: true });
await rm(packageDirectory, { recursive: true, force: true });
await mkdir(distDirectory, { recursive: true });
await mkdir(packageDirectory, { recursive: true });

await build({
  absWorkingDir: extensionRoot,
  entryPoints: ['./src/index.ts'],
  outfile: 'dist/index.js',
  bundle: true,
  format: 'iife',
  globalName: 'edaEsbuildExportName',
  platform: 'browser',
  target: 'es2022',
  treeShaking: true,
  ignoreAnnotations: true,
  sourcemap: false,
  legalComments: 'none',
});

const zip = new JSZip();
zip.file('extension.json', manifestText);
zip.file('dist/index.js', await readFile(compiledEntryPath));
const archive = await zip.generateAsync({
  type: 'nodebuffer',
  compression: 'DEFLATE',
  compressionOptions: { level: 9 },
});
const outputPath = join(
  packageDirectory,
  `${manifest.name}_v${manifest.version}.eext`,
);
await writeFile(outputPath, archive);
console.log(`Packaging complete: ${outputPath}`);
