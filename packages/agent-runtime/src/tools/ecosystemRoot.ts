import path from "node:path"

/**
 * Resolve the ecosystem root directory from ECOSYSTEM_ROOT env var.
 *
 * Called at tool invocation time (not module load time) so that tests and
 * callers can set the env var after the module is imported.
 *
 * Throws with a descriptive message if the env var is not set, consistent
 * with the ADA_ENGINE_DIR / ALPHAMU_PATH patterns used by the engine bridges.
 */
export function resolveEcosystemRoot(): string {
  const raw = process.env.ECOSYSTEM_ROOT
  if (!raw) {
    throw new Error(
      "ECOSYSTEM_ROOT is not set. Export the path to the ecosystem root directory:\n" +
      '  export ECOSYSTEM_ROOT="/path/to/Fusion"',
    )
  }
  return path.resolve(raw)
}
