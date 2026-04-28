import { readFile } from "node:fs/promises"

export type PackageMetadata = {
  name: string
  version: string
}

let cachedMetadata: Promise<PackageMetadata> | null = null

export function readPackageMetadata(): Promise<PackageMetadata> {
  if (!cachedMetadata) {
    cachedMetadata = readFile(new URL("../../package.json", import.meta.url), "utf8")
      .then(raw => {
        const parsed = JSON.parse(raw) as Record<string, unknown>
        return {
          name: typeof parsed.name === "string" ? parsed.name : "unknown",
          version: typeof parsed.version === "string" ? parsed.version : "unknown",
        }
      })
      .catch(() => ({ name: "unknown", version: "unknown" }))
  }

  return cachedMetadata
}
