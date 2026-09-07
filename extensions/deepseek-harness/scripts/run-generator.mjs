import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = resolve(extensionRoot, "..", "..");
const candidates = process.platform === "win32"
  ? [join(projectRoot, ".venv", "Scripts", "python.exe"), "python"]
  : [join(projectRoot, ".venv", "bin", "python"), "python3", "python"];
const python = candidates.find((candidate) => !candidate.includes(".venv") || existsSync(candidate));
if (!python) throw new Error("A Python interpreter is required to project the canonical schema");
const result = spawnSync(
  python,
  [join(extensionRoot, "scripts", "generate-contracts.py"), ...process.argv.slice(2)],
  { cwd: projectRoot, stdio: "inherit" },
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
