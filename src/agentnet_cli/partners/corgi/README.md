# Corgi specialist

Original rebuild of the public [Corgi](https://www.corgi.insure/) homepage plus a
Corgi-only chat bot. Same envelope as `composio.agentnet.it.com/chat`.

```bash
uv run agentnet corgi-serve --port 8765
# http://127.0.0.1:8765/          homepage
# http://127.0.0.1:8765/agent.txt coding-agent brief
# POST /chat                     {"text":"...","session":"..."}
```

This is not Corgi's production site. Bind and pay only on corgi.insure.
We did not vendor their Next.js bundle, licensed fonts, or customer logo files.
