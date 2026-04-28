export function printUsage(): void {
  console.log(`Usage:
  node dist/index.js [--root-dir <path>] <command> [subcommand] [args]

Global flag:
  --root-dir <path>   Set runtime root and session storage root (default: cwd)

━━━ Core commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  list-tools
      Print all registered tools as JSON.

  run <tool> '<json-input>'
      Execute a tool by name with a JSON input object.
      Tools: read, glob, bash, switchboard.route, mythos, pantheon.route

  meta report [target]
      Emit a JSON diagnostic report: runtime info, loaded tools,
      session counts, and startup prefetch state.
      target defaults to "agent-runtime".

  version
      Print version information.

  status
      Print runtime health status.

━━━ Session commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  session create [session-id]
      Create a new session. Auto-generates an ID if omitted.

  session list
      List all sessions with snapshot metadata as JSON.

  session show <session-id> [limit]
      Print snapshot + event log for a session. limit caps event count.

  session resume <session-id>
      Print the last 5 events and a session summary — useful for resuming work.

  session run <session-id> <tool> '<json-input>'
      Run a tool within a session context. Appends the event to the session log.

  session delete <session-id>
      Permanently delete a session and its event log.

  session prune <keep-count>
      Delete all but the most recent <keep-count> sessions.

  session export <session-id> [output-file]
      Export a session to a versioned JSON bundle.
      Prints to stdout if output-file is omitted.

  session import <input-file> [session-id] [--force]
      Import a session bundle. Optionally rename the session.
      --force overwrites an existing session with the same ID.

━━━ MCTS / ADA engine commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Forwarded to the ADA engine (ADA_ENGINE_DIR env var, or default path).

  mcts memory recall
      Load startup recall context from the engine memory store.

  mcts memory append [--id <id>] [--tags <t1,t2>] [--body "<text>"]
      Append a new entry to the engine memory store.

  mcts memory search [--query "<text>"] [--tags <t1,t2>] [--limit <n>]
      Search memory entries by semantic query or tag filter.

  mcts trimmer analyze "<prompt>" [--json]
      Classify a prompt into a task tier (fast/smart/deep).
      --json returns structured output.

  mcts select [--prompt "<text>"] [--framework <fw>] [--language <lang>]
      Run MCTS model selection with learned PUCT priors.
      Returns selected model, UCB score, value estimates, and ranked alternatives.

  mcts agents select [--prompt "<text>"] [--language <lang>]
      Run ensemble agent negotiation (weighted_vote strategy).
      Returns winning model, per-agent votes, and worker contracts.

  mcts compare <modelA> <modelB> [--prompt "<text>"] [--framework <fw>]
      Head-to-head comparison of two models on a task.
      Returns relative quality, cost, and latency estimates.

  mcts score --model <model> --score <0.0-1.0> --outcome <success|failure>
             [--framework <fw>] [--language <lang>] [--session-id <id>]
      Record a quality score for a model/action pair.
      Feeds into the training pipeline to shift future selections.

  mcts train
      Retrain MCTS routing priors from all recorded score events.
      Filters synthetic/test entries before training.

  mcts run --prompt "<text>" [--framework <fw>] [--language <lang>]
      Run the full ADA pipeline: select -> execute -> score.

  mcts status [--neural]
      Print engine health: loaded adapters, prior scores, transposition table stats.
      --neural adds model weight diagnostics.

  Override the engine path:
      ADA_ENGINE_DIR="/path/to/ADA 03" node dist/index.js mcts status

━━━ AlphaMu commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Forwarded to the AlphaMu Python engine (ALPHAMU_PATH env var, or default path).
  Returns JSON to stdout; progress logs go to stderr.

  alphamu selfplay [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
                   [--episodes <n>] [--simulations <n>]
      Run self-play episodes using MCTS + policy/value network.
      Defaults: backend=alpha_zero, game=tictactoe, episodes=10, simulations=50.

  alphamu train [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
                [--steps <n>] [--batch-size <n>]
      Train the policy+value network. Loads model.json if present.
      Saves updated weights to model.json on completion.
      Defaults: steps=100, batch-size=32.

  alphamu eval [--backend <alpha_zero|mu_zero>] [--game <tictactoe|stub>]
               [--checkpoint <path>] [--episodes <n>]
      Evaluate a trained network in greedy (temperature=0) play.
      Returns win/loss/draw counts and win rate.

  alphamu arena [--backend-a <backend>] [--backend-b <backend>]
                [--game <tictactoe|stub>] [--games <n>]
      Head-to-head match between AlphaZero and MuZero backends.
      Loads model_az.json and model_mz.json if available.
      Defaults: backend-a=alpha_zero, backend-b=mu_zero, games=20.

  Override the engine path:
      ALPHAMU_PATH="/path/to/alphamu-engine" node dist/index.js alphamu selfplay

━━━ Examples ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  node dist/index.js version
  node dist/index.js status
  node dist/index.js run read '{"path":"README.md"}'
  node dist/index.js run glob '{"pattern":"src/**/*.ts"}'
  node dist/index.js run bash '{"cmd":"git","args":["status","--short"]}'
  node dist/index.js meta report agent-runtime
  node dist/index.js session create dev-loop
  node dist/index.js session run dev-loop read '{"path":"README.md"}'
  node dist/index.js session show dev-loop 20
  node dist/index.js session export dev-loop ./dev-loop.session.json
  node dist/index.js session import ./dev-loop.session.json dev-loop-copy
  node dist/index.js session import ./dev-loop.session.json dev-loop --force
  node dist/index.js session prune 10
  node dist/index.js mcts select --prompt "build a REST API" --framework coder --language typescript
  node dist/index.js mcts agents select --prompt "refactor auth module" --language typescript
  node dist/index.js mcts score --model claude-sonnet-4-6 --score 0.9 --outcome success
  node dist/index.js mcts train
  node dist/index.js mcts status --neural
  node dist/index.js mcts memory search --query "auth JWT" --limit 5
  node dist/index.js mcts trimmer analyze "implement rate limiting middleware" --json
  node dist/index.js alphamu selfplay --episodes 20 --simulations 100
  node dist/index.js alphamu train --steps 200 --batch-size 64
  node dist/index.js alphamu eval --episodes 50
  node dist/index.js alphamu arena --games 50
  node dist/index.js alphamu selfplay --backend mu_zero --game stub --episodes 10
`)
}
