// AgentNet skill-fire plugin for opencode.
//
// Bundled by agentnet-cli and installed into ~/.config/opencode/plugins/agentnet.js by
// `agentnet connect opencode`, which substitutes the __AGENTNET_BIN__ placeholder below with the
// resolved absolute path to the `agentnet` CLI (so it doesn't depend on opencode's PATH).
//
// It shells out to the SAME `agentnet` CLI the Claude/Cursor/Hermes hooks use, so all skill
// discovery / gating / caching logic stays in Python (tools/skillfire) — this file is only the thin
// opencode I/O adapter. Three hooks (all best-effort: any failure degrades to a normal turn):
//   chat.message                       -> spawn the detached discovery worker for the new prompt
//   experimental.chat.system.transform -> inject the ready skill methodology into the system prompt
//   event (session.idle)               -> user-visible toast fallback for no-tool answers
import { createHash } from "node:crypto";
import { appendFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const AGENTNET_BIN = "__AGENTNET_BIN__";
const SENTINEL = "[AgentNet]";
// Guard against ARG_MAX for pathological prompts; the gist is plenty for relevance discovery.
const MAX_QUERY = 16000;

// Opt-in debug trace (set AGENTNET_OPENCODE_DEBUG=1). Writes to $TMPDIR/agentnet-opencode-debug.log.
const DEBUG = process.env.AGENTNET_OPENCODE_DEBUG;
function dbg(msg) {
  if (!DEBUG) return;
  try {
    appendFileSync(join(tmpdir(), "agentnet-opencode-debug.log"), `${new Date().toISOString()} ${msg}\n`);
  } catch {
    /* best-effort */
  }
}

// Mirror skillfire/session.py's cache path so the per-inference hook can cheaply skip the CLI when
// there's nothing to inject. Emit-once is still enforced authoritatively in Python (O_EXCL claim);
// this stat is a latency optimization only, so a convention drift degrades to "no steer", never a
// wrong one.
function cacheFiles(sessionID) {
  const key = createHash("sha1").update(sessionID || "default").digest("hex").slice(0, 16);
  const dir = join(tmpdir(), "agentnet-skill");
  return {
    json: join(dir, `${key}.json`),
    emitted: join(dir, `${key}.emitted`), // steer (methodology) once-claim
    toasted: join(dir, `${key}.toasted`), // toast (list) once-claim
  };
}

function promptText(parts) {
  try {
    return (parts || [])
      .filter((p) => p && p.type === "text" && typeof p.text === "string")
      .map((p) => p.text)
      .join("\n")
      .trim()
      .slice(0, MAX_QUERY);
  } catch {
    return "";
  }
}

export const AgentNet = async ({ $, client }) => {
  dbg("plugin loaded");
  // Run the agentnet CLI and return trimmed stdout ("" on any failure). Never throws.
  const run = async (args) => {
    try {
      const res = await $`${AGENTNET_BIN} ${args}`.quiet().nothrow();
      return res.exitCode === 0 ? res.stdout.toString().trim() : "";
    } catch (e) {
      dbg(`run failed: ${e}`);
      return "";
    }
  };

  // Show the skill list to the user (the system-prompt injection itself is invisible to them).
  // A long duration so it stays readable — the list is the only user-visible signal opencode gives.
  const showToast = async (message) => {
    if (!message || !client?.tui?.showToast) return;
    try {
      await client.tui.showToast({
        body: { title: "AgentNet", message, variant: "info", duration: 14000 },
      });
    } catch (e) {
      dbg(`toast failed: ${e}`);
    }
  };

  return {
    // New user prompt -> spawn the detached discovery worker (returns fast; work is detached).
    "chat.message": async (input, output) => {
      try {
        const session = input?.sessionID || "";
        const prompt = promptText(output?.parts);
        dbg(`chat.message session=${session} promptlen=${prompt.length}`);
        if (!session || !prompt || prompt.startsWith(SENTINEL)) return;
        await run(["opencode-hook", "--pre", "--session", session, "--query", prompt]);
        dbg("chat.message: --pre returned");
      } catch (e) {
        dbg(`chat.message error: ${e}`);
      }
    },

    // Fires before every inference -> if the worker's outcome is ready, steer the model by pushing
    // the skill methodology onto the system prompt, and toast the skill list so the user sees it.
    "experimental.chat.system.transform": async (input, output) => {
      try {
        const session = input?.sessionID || "";
        const hasSystem = Array.isArray(output?.system);
        if (!session || !hasSystem) {
          dbg(`system.transform SKIP session=${session} hasSystem=${hasSystem}`);
          return;
        }
        const { json, emitted, toasted } = cacheFiles(session);
        const ready = existsSync(json);
        const done = existsSync(emitted) && existsSync(toasted);
        dbg(`system.transform session=${session} cacheReady=${ready} done=${done}`);
        if (!ready || done) return; // nothing yet, or both toast + steer already fired
        const out = await run(["opencode-hook", "--peek", "--session", session]);
        dbg(`system.transform peek len=${out.length}`);
        if (!out) return;
        // Payload is "<toast-list>\x1e<system-prompt-text>": user sees the list, model gets the text.
        const sep = out.indexOf("\x1e");
        const toast = sep === -1 ? "" : out.slice(0, sep);
        const systemText = sep === -1 ? out : out.slice(sep + 1);
        if (systemText) output.system.push(systemText);
        await showToast(toast);
      } catch (e) {
        dbg(`system.transform error: ${e}`);
      }
    },

    // Turn end -> user-visible fallback (toast the skill list) for answers whose turn was shorter
    // than the worker, so the mid-run steer never fired.
    event: async ({ event }) => {
      try {
        if (!event || event.type !== "session.idle") return;
        const session = event.properties?.sessionID || "";
        dbg(`session.idle session=${session}`);
        if (!session) return;
        const text = await run(["opencode-hook", "--post", "--session", session]);
        dbg(`session.idle post len=${text.length} hasToast=${!!client?.tui?.showToast}`);
        await showToast(text);
      } catch (e) {
        dbg(`session.idle error: ${e}`);
      }
    },
  };
};

export default AgentNet;
