import type { Tool } from "../core/contracts.js"
import { BashTool } from "./bashTool.js"
import { GlobTool } from "./globTool.js"
import { ReadTool } from "./readTool.js"
import { SwitchboardRouteTool } from "./switchboardRouteTool.js"
import { MythosTool } from "./mythosTool.js"
import { PantheonRouteTool } from "./pantheonRouteTool.js"

export const TOOLS: Record<string, Tool> = {
  [ReadTool.name]: ReadTool,
  [GlobTool.name]: GlobTool,
  [BashTool.name]: BashTool,
  [SwitchboardRouteTool.name]: SwitchboardRouteTool,
  [MythosTool.name]: MythosTool,
  [PantheonRouteTool.name]: PantheonRouteTool,
}
