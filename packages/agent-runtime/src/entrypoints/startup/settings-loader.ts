import path from "node:path"

export type StartupSettings = {
  rootDir: string
}

export type StartupLoadResult = {
  settings: StartupSettings
  cliArgs: string[]
}

function parseRootDirFlag(
  inputArgs: string[],
): { rootDir?: string; cliArgs: string[] } {
  const args = [...inputArgs]
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (arg === "--root-dir") {
      const value = args[i + 1]
      if (!value || value.startsWith("--")) {
        throw new Error("missing value for --root-dir")
      }
      args.splice(i, 2)
      return { rootDir: value, cliArgs: args }
    }
    if (arg?.startsWith("--root-dir=")) {
      const value = arg.slice("--root-dir=".length).trim()
      if (!value) {
        throw new Error("missing value for --root-dir")
      }
      args.splice(i, 1)
      return { rootDir: value, cliArgs: args }
    }
  }
  return { cliArgs: args }
}

export function eagerLoadStartupSettings(inputArgs: string[]): StartupLoadResult {
  const { rootDir, cliArgs } = parseRootDirFlag(inputArgs)
  const normalizedRootDir = rootDir
    ? path.resolve(rootDir)
    : process.cwd()

  return {
    settings: { rootDir: normalizedRootDir },
    cliArgs,
  }
}

