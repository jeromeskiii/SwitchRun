import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

/**
 * Directory of the AlphaMu Python engine. Must be set via ALPHAMU_PATH env var.
 */
const ALPHAMU_DIR = process.env.ALPHAMU_PATH

async function runAlphamuCommand(
  args: string[],
): Promise<{ stdout: string; stderr: string }> {
  if (!ALPHAMU_DIR) {
    throw new Error(
      "ALPHAMU_PATH is not set. Export the path to your AlphaMu engine directory:\n" +
      '  export ALPHAMU_PATH="/path/to/alphamu-engine"',
    )
  }
  return execFileAsync("python", ["-m", "engine", ...args], {
    cwd: ALPHAMU_DIR,
    maxBuffer: 8 * 1024 * 1024,
    env: { ...process.env },
  })
}

function forwardOutput(stdout: string, stderr: string): void {
  if (stdout) process.stdout.write(stdout)
  if (stderr) process.stderr.write(stderr)
}

export async function handleAlphamuCommand(
  args: string[],
  printUsage: () => void,
): Promise<boolean> {
  const [subcommand, ...rest] = args

  if (!subcommand) {
    printUsage()
    process.exitCode = 1
    return true
  }

  let engineArgs: string[]

  switch (subcommand) {
    // alphamu selfplay [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
    //                  [--episodes <n>] [--simulations <n>]
    case "selfplay": {
      engineArgs = ["run", ...rest]
      break
    }

    // alphamu train [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
    //               [--steps <n>] [--batch-size <n>]
    case "train": {
      engineArgs = ["train", ...rest]
      break
    }

    // alphamu eval [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
    //              [--checkpoint <path>] [--episodes <n>]
    case "eval": {
      engineArgs = ["eval", ...rest]
      break
    }

    // alphamu arena [--backend-a <backend>] [--backend-b <backend>]
    //               [--game <tictactoe|stub>] [--games <n>]
    case "arena": {
      engineArgs = ["arena", ...rest]
      break
    }

    default:
      console.error(`unknown alphamu subcommand: ${subcommand}`)
      printUsage()
      process.exitCode = 1
      return true
  }

  try {
    const { stdout, stderr } = await runAlphamuCommand(engineArgs)
    forwardOutput(stdout, stderr)
    process.exitCode = 0
  } catch (error: unknown) {
    if (
      error &&
      typeof error === "object" &&
      "stdout" in error &&
      "stderr" in error
    ) {
      const e = error as { stdout?: string; stderr?: string; code?: number }
      forwardOutput(e.stdout ?? "", e.stderr ?? "")
      process.exitCode = typeof e.code === "number" ? e.code : 1
    } else {
      const message = error instanceof Error ? error.message : String(error)
      console.error(`alphamu engine error: ${message}`)
      process.exitCode = 1
    }
  }

  return true
}
