const logEl = document.getElementById("chat-log");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const panel = document.getElementById("chat-panel");
const launch = document.getElementById("chat-launch");
const banner = document.getElementById("banner");
const bannerClose = document.getElementById("banner-close");

let session = "";

function addBubble(text, who) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

launch.addEventListener("click", () => {
  panel.classList.toggle("open");
  if (panel.classList.contains("open") && !logEl.childElementCount) {
    addBubble(
      "Corgi specialist. Tell me who you are and what you ship — or ask for a package, policy, or AgentNet solutions.",
      "bot",
    );
  }
});

if (bannerClose) {
  bannerClose.addEventListener("click", () => {
    banner.remove();
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addBubble(text, "me");
  const body = { text };
  if (session) body.session = session;
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    session = data.session || session;
    addBubble(data.lastText || data.error || "No reply", "bot");
  } catch (err) {
    addBubble("Chat is unreachable. Retry, or POST /chat yourself.", "bot");
  }
});

document.querySelectorAll("[data-ask]").forEach((el) => {
  el.addEventListener("click", (event) => {
    event.preventDefault();
    panel.classList.add("open");
    input.value = el.getAttribute("data-ask");
    form.dispatchEvent(new Event("submit"));
  });
});
