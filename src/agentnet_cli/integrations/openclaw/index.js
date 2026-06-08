import { spawn } from "node:child_process";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

function runQuietUpdate() {
  const child = spawn("agentnet", ["update", "--quiet"], {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

export default definePluginEntry({
  register(api) {
    runQuietUpdate();
    api.logger.info("AgentNet marketplace plugin loaded");
  },
});
