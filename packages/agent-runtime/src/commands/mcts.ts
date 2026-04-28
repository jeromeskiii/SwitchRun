import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

/**
 * Directory of the ADA 03 engine. Must be set via ADA_ENGINE_DIR env var.
 */
const ADA_ENGINE_DIR = process.env.ADA_ENGINE_DIR

async function runAdaCommand(
  args: string[],
): Promise<{ stdout: string; stderr: string }> {
  if (!ADA_ENGINE_DIR) {
    throw new Error(
      "ADA_ENGINE_DIR is not set. Export the path to your ADA 03 engine directory:\n" +
      '  export ADA_ENGINE_DIR="/path/to/ADA 03"',
    )
  }
  return execFileAsync("npx", ["tsx", "src/index.ts", ...args], {
    cwd: ADA_ENGINE_DIR,
    maxBuffer: 4 * 1024 * 1024,
    env: { ...process.env },
  })
}

function forwardOutput(stdout: string, stderr: string): void {
  if (stdout) process.stdout.write(stdout)
  if (stderr) process.stderr.write(stderr)
}

export async function handleMctsCommand(
  args: string[],
  printUsage: () => void,
): Promise<boolean> {
  const [subcommand, ...rest] = args

  if (!subcommand) {
    printUsage()
    process.exitCode = 1
    return true
  }

  let adaArgs: string[]

  switch (subcommand) {
    // mcts memory <recall|append|search> [options]
    case "memory": {
      const [action, ...memArgs] = rest
      if (!action || !["recall", "append", "search"].includes(action)) {
        console.error("usage: mcts memory <recall|append|search> [options]")
        process.exitCode = 1
        return true
      }
      adaArgs = ["memory", action, ...memArgs]
      break
    }

    // mcts trimmer analyze "<prompt>" [--json]
    case "trimmer": {
      const [action, ...trimArgs] = rest
      if (!action) {
        console.error("usage: mcts trimmer analyze \"<prompt>\" [--json]")
        process.exitCode = 1
        return true
      }
      adaArgs = ["trimmer", action, ...trimArgs]
      break
    }

    // mcts select [--prompt "..."] [--framework <fw>] [--language <lang>]
    case "select": {
      adaArgs = ["select", ...rest]
      break
    }

    // mcts agents <select|list|stats|match> [task]
    case "agents": {
      const [action, ...agentArgs] = rest
      if (!action || !["select", "list", "stats", "match"].includes(action)) {
        console.error("usage: mcts agents <select|list|stats|match> [task]")
        process.exitCode = 1
        return true
      }
      adaArgs = ["agents", action, ...agentArgs]
      break
    }

    // mcts compare <modelA> <modelB> [--prompt "..."] [--framework <fw>]
    case "compare": {
      const [modelA, modelB] = rest
      if (!modelA || !modelB) {
        console.error("usage: mcts compare <modelA> <modelB> [options]")
        process.exitCode = 1
        return true
      }
      adaArgs = ["compare", ...rest]
      break
    }

    // mcts score --model <model> --score <0-1> --outcome <success|failure> [options]
    case "score": {
      adaArgs = ["score", ...rest]
      break
    }

    // mcts train
    case "train": {
      adaArgs = ["train", ...rest]
      break
    }

    // mcts run --prompt "..." [--framework <fw>] [--language <lang>]
    case "run": {
      if (rest.length === 0) {
        console.error("usage: mcts run --prompt \"<prompt>\" [options]")
        process.exitCode = 1
        return true
      }
      adaArgs = ["run", ...rest]
      break
    }

    // mcts status [--neural]
    case "status": {
      adaArgs = ["status", ...rest]
      break
    }

    default:
      console.error(`unknown mcts subcommand: ${subcommand}`)
      printUsage()
      process.exitCode = 1
      return true
  }

  try {
    const { stdout, stderr } = await runAdaCommand(adaArgs)
    forwardOutput(stdout, stderr)
    process.exitCode = 0
  } catch (error: unknown) {
    // execFile rejects when exit code != 0; still forward output
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
      console.error(`mcts engine error: ${message}`)
      process.exitCode = 1
    }
  }

  return true
}
