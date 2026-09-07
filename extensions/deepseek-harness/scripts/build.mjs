import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = resolve(extensionRoot, "..", "..");
const distRoot = join(extensionRoot, "dist");
const buildRoot = join(extensionRoot, "build");

await rm(distRoot, { recursive: true, force: true });
await rm(buildRoot, { recursive: true, force: true });
await mkdir(distRoot, { recursive: true });
await mkdir(buildRoot, { recursive: true });

await build({
  entryPoints: [join(extensionRoot, "src", "index.ts")],
  outfile: join(distRoot, "index.js"),
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node22",
  external: ["@deepseek-ai/*"],
  sourcemap: false,
  legalComments: "none",
});

const pluginEntry = join(distRoot, "index.js").replaceAll("\\", "/").replaceAll("'", "''");
const patch = [
  "- insert:",
  "    - id: aia-hardware-dev",
  `      name: '${pluginEntry}'`,
  "      config:",
  "        endpoint: 'ws://127.0.0.1:49625'",
  `        secretFile: '${join(projectRoot, ".aia-secrets", "harness-hardware-psk.txt").replaceAll("\\", "/").replaceAll("'", "''")}'`,
  "",
].join("\n");
await writeFile(join(buildRoot, "cordis.dev.patch.yml"), patch, "utf8");
console.log("Harness plugin build complete: dist/index.js");
console.log("Development patch generated under ignored build/cordis.dev.patch.yml");
