import path from "node:path"

const _DEFAULT_BASH_PREFIXES: Array<[string, ...string[]]> = [
  ["git", "status"],
  ["git", "diff"],
  ["git", "log"],
  ["git", "branch"],
  ["git", "show"],
  ["git", "rev-parse"],
  ["git", "config", "--list"],
  ["npm", "test"],
  ["npm", "run", "typecheck"],
  ["npm", "run", "lint"],
  ["npm", "run", "build"],
  ["npm", "run", "dev"],
  ["npm", "ls"],
  ["npm", "view"],
  ["pnpm", "test"],
  ["pnpm", "run", "typecheck"],
  ["pnpm", "run", "lint"],
  ["pnpm", "run", "build"],
  ["pnpm", "ls"],
  ["python3", "--version"],
  ["python3", "-m", "pytest"],
  ["python3", "-m", "ruff", "check"],
  ["python3", "-m", "ruff", "format"],
  ["python3", "-m", "mypy"],
  ["node", "--version"],
  ["node", "-e"],
  ["ls", "-la"],
  ["ls", "-l"],
  ["pwd"],
  ["echo"],
  ["cat"],
  ["grep"],
  ["wc"],
  ["head"],
  ["tail"],
  ["find"],
  ["which"],
  ["stat"],
]

function _parseBashPrefixes(): Array<[string, ...string[]]> {
  const env = process.env.AGENT_RUNTIME_BASH_PREFIXES
  if (!env) return _DEFAULT_BASH_PREFIXES
  try {
    const parsed = JSON.parse(env) as unknown
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed as Array<[string, ...string[]]>
    }
  } catch {
    // fall through to defaults
  }
  return _DEFAULT_BASH_PREFIXES
}

export const BASH_ALLOW_PREFIXES: Array<[string, ...string[]]> = _parseBashPrefixes()

export function isPathInsideRoot(rootDir: string, filePath: string): boolean {
  try {
    const normalizedRoot = path.resolve(rootDir)
    const resolved = path.resolve(rootDir, filePath)
    return (
      resolved === normalizedRoot ||
      resolved.startsWith(`${normalizedRoot}${path.sep}`)
    )
  } catch {
    return false
  }
}

export function isAllowedBashPrefix(cmd: string, args: string[]): boolean {
  const sequence = [cmd, ...args]
  return BASH_ALLOW_PREFIXES.some(prefix => {
    if (prefix.length > sequence.length) return false
    for (let i = 0; i < prefix.length; i++) {
      if (sequence[i] !== prefix[i]) return false
    }
    return true
  })
}
