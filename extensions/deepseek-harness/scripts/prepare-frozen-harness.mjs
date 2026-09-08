import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, realpathSync, symlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EXPECTED_COMMIT = "d347e703908d0406b7a7ef80e3a0e594d86b2215";
const EXPECTED_TOOLS_VERSION = "0.1.3-alpha.1";
const EXPECTED_CORDIS_VERSION = "4.0.2";
const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const suppliedRoot = process.env.DEEPSEEK_HARNESS_DEV_ROOT;

if (!suppliedRoot) {
  throw new Error("DEEPSEEK_HARNESS_DEV_ROOT must point to the frozen official checkout");
}

const harnessRoot = realpathSync(resolve(suppliedRoot));
const gitSafePath = harnessRoot.replaceAll("\\", "/");
const head = execFileSync(
  "git",
  ["-c", `safe.directory=${gitSafePath}`, "-C", harnessRoot, "rev-parse", "HEAD"],
  { encoding: "utf8" },
).trim();
if (head !== EXPECTED_COMMIT) {
  throw new Error(`Harness checkout mismatch: expected ${EXPECTED_COMMIT}, observed ${head}`);
}

const packages = [
  ["cordis", join(harnessRoot, "vendor", "cordis"), EXPECTED_CORDIS_VERSION],
  ["dsh-agent", join(harnessRoot, "packages", "core", "agent"), EXPECTED_TOOLS_VERSION],
  ["dsh-agent-loop", join(harnessRoot, "packages", "core", "agent-loop"), EXPECTED_TOOLS_VERSION],
  ["dsh-tools", join(harnessRoot, "packages", "core", "tools"), EXPECTED_TOOLS_VERSION],
  ["dsh-llm", join(harnessRoot, "packages", "llm", "llm"), EXPECTED_TOOLS_VERSION],
  ["dsh-session", join(harnessRoot, "packages", "core", "session"), EXPECTED_TOOLS_VERSION],
  ["dsh-session-projection", join(harnessRoot, "packages", "session", "session-projection"), EXPECTED_TOOLS_VERSION],
  ["dsh-system-prompt", join(harnessRoot, "packages", "core", "system-prompt"), EXPECTED_TOOLS_VERSION],
];

const scopeRoot = join(extensionRoot, "node_modules", "@deepseek-ai");
mkdirSync(scopeRoot, { recursive: true });
for (const [name, source, expectedVersion] of packages) {
  const manifestPath = join(source, "package.json");
  if (!existsSync(manifestPath)) throw new Error(`Frozen Harness package is missing: ${name}`);
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest.version !== expectedVersion) {
    throw new Error(`${name} version mismatch: expected ${expectedVersion}, observed ${manifest.version}`);
  }
  if (!existsSync(join(source, "lib", "index.js"))) {
    throw new Error(`${name} has not been built in the frozen Harness checkout`);
  }
  const destination = join(scopeRoot, name);
  if (existsSync(destination)) {
    if (realpathSync(destination) !== realpathSync(source)) {
      throw new Error(`Refusing to replace an existing non-frozen package link: ${name}`);
    }
    continue;
  }
  mkdirSync(dirname(destination), { recursive: true });
  symlinkSync(source, destination, "junction");
}

console.log(`Frozen Harness baseline verified: ${EXPECTED_COMMIT} / ${EXPECTED_TOOLS_VERSION}`);
