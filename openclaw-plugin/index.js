import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  register(api) {
    api.logger.info("AgentNet marketplace plugin loaded");
  },
});
