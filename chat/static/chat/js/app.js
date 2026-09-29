(() => {
  const csrfToken = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

  function scrollFeed(feed) {
    feed.scrollTop = feed.scrollHeight;
  }

  function renderMarkdown(element, source) {
    if (!window.marked || !window.DOMPurify) {
      element.textContent = source;
      return;
    }
    const html = window.marked.parse(source, { breaks: true, gfm: true });
    element.innerHTML = window.DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
    });

    element.querySelectorAll("pre > code").forEach((code) => {
      if (window.hljs) window.hljs.highlightElement(code);
      const pre = code.parentElement;
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy-code-button";
      copy.textContent = "Copy";
      copy.setAttribute("aria-label", "Copy code block");
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(code.innerText);
          copy.textContent = "Copied";
          window.setTimeout(() => { copy.textContent = "Copy"; }, 1100);
        } catch {
          copy.textContent = "Unavailable";
        }
      });
      pre.append(copy);
    });
  }

  function enhanceExistingMessages(root = document) {
    root.querySelectorAll("[data-markdown-source]").forEach((element) => {
      renderMarkdown(element, element.textContent || "");
    });
  }

  function removeEmptyState(feed) {
    feed.querySelector("[data-empty-state]")?.remove();
  }

  function appendUserMessage(feed, content) {
    removeEmptyState(feed);
    const row = document.createElement("article");
    row.className = "message-row message-user";
    row.dataset.optimisticMessage = "user";

    const column = document.createElement("div");
    column.className = "message-column";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const label = document.createElement("span");
    label.textContent = "You";
    meta.append(label);
    const bubble = document.createElement("div");
    bubble.className = "message-bubble plain-message";
    bubble.textContent = content;
    column.append(meta, bubble);
    row.append(column);
    feed.append(row);
    scrollFeed(feed);
    return row;
  }

  function appendAssistantMessage(feed) {
    removeEmptyState(feed);
    const row = document.createElement("article");
    row.className = "message-row message-assistant message-streaming";
    row.dataset.optimisticMessage = "assistant";

    const mark = document.createElement("div");
    mark.className = "assistant-mark";
    mark.textContent = "H";
    mark.setAttribute("aria-hidden", "true");
    const column = document.createElement("div");
    column.className = "message-column";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const label = document.createElement("span");
    label.textContent = "HeavyChat";
    const status = document.createElement("span");
    status.className = "stream-status-label";
    status.textContent = "thinking";
    meta.append(label, status);
    const bubble = document.createElement("div");
    bubble.className = "message-bubble markdown-body";
    column.append(meta, bubble);
    row.append(mark, column);
    feed.append(row);
    scrollFeed(feed);
    return { row, bubble, status };
  }

  function updateBalances(detail) {
    const credits = Number(detail.credit_balance);
    if (!Number.isFinite(credits)) return;
    const dollars = (credits / 100).toFixed(2);
    document.querySelectorAll("[data-balance-badge]").forEach((badge) => {
      const creditNode = badge.querySelector("[data-credit-balance]");
      const dollarNode = badge.querySelector("[data-usd-balance]");
      if (creditNode) creditNode.textContent = String(credits);
      if (dollarNode) dollarNode.textContent = dollars;
    });
  }

  function parseEventBlock(block) {
    let eventName = "message";
    const dataLines = [];
    for (const line of block.split(/\r?\n/)) {
      if (!line || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") eventName = value;
      if (field === "data") dataLines.push(value);
    }
    if (!dataLines.length) return null;
    try {
      return { event: eventName, data: JSON.parse(dataLines.join("\n")) };
    } catch {
      throw new Error("The server sent an invalid streaming event.");
    }
  }

  async function consumeSSE(response, onEvent) {
    if (!response.body) throw new Error("The server did not return a stream.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        let boundary;
        while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
          const block = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary[0].length);
          const parsed = parseEventBlock(block);
          if (parsed) onEvent(parsed);
        }
        if (done) break;
      }
      if (buffer.trim()) {
        const parsed = parseEventBlock(buffer);
        if (parsed) onEvent(parsed);
      }
    } finally {
      reader.releaseLock();
    }
  }

  async function submitChat(form) {
    if (form.dataset.busy === "true") return;
    const textarea = form.querySelector("[data-chat-input]");
    const send = form.querySelector("[data-send-button]");
    const sendLabel = form.querySelector("[data-send-label]");
    const status = document.querySelector("[data-chat-status]");
    const feed = document.querySelector("[data-message-feed]");
    const content = textarea?.value || "";
    if (!content.trim() || !feed) return;

    form.dataset.busy = "true";
    textarea.disabled = true;
    send.disabled = true;
    sendLabel.textContent = "Working…";
    if (status) {
      status.textContent = "Connecting to your selected model…";
      status.classList.remove("is-error");
    }
    appendUserMessage(feed, content);
    const assistant = appendAssistantMessage(feed);
    textarea.value = "";

    let answer = "";
    let sawSettlement = false;
    let streamError = null;
    let streamingResponseStarted = false;
    try {
      const response = await fetch(form.dataset.streamUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ content }),
      });
      if (!response.ok && !response.headers.get("content-type")?.includes("text/event-stream")) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Request failed (${response.status}).`);
      }
      streamingResponseStarted = true;

      await consumeSSE(response, ({ event, data }) => {
        if (event === "delta" && typeof data.content === "string") {
          answer += data.content;
          renderMarkdown(assistant.bubble, answer);
          scrollFeed(feed);
        } else if (event === "settled") {
          sawSettlement = true;
          updateBalances(data);
          assistant.row.classList.remove("message-streaming");
          assistant.status.textContent = "complete";
          if (status) {
            status.textContent = data.is_estimated
              ? "Complete · usage estimated"
              : "Complete · usage settled";
          }
        } else if (event === "error") {
          streamError = data;
          assistant.row.classList.remove("message-streaming");
          assistant.status.textContent = data.code || "error";
          if (data.code === "insufficient_credits") {
            assistant.row.remove();
            feed.querySelector("[data-optimistic-message='user']")?.remove();
            textarea.value = content;
          }
          if (status) {
            status.textContent = data.message || "The response could not be completed.";
            status.classList.add("is-error");
          }
        }
      });
      if (!sawSettlement && !streamError && status) {
        status.textContent = "Stream ended before settlement was confirmed.";
        status.classList.add("is-error");
      }
      if (streamError?.code === "upstream_failed" && status) {
        status.classList.add("is-error");
      }
    } catch (error) {
      assistant.row.classList.remove("message-streaming");
      if (!streamingResponseStarted) {
        feed.querySelector("[data-optimistic-message='user']")?.remove();
        assistant.row.remove();
        textarea.value = content;
      }
      assistant.status.textContent = "error";
      if (status) {
        status.textContent = error.message || "Unable to connect to HeavyChat.";
        status.classList.add("is-error");
      }
    } finally {
      form.dataset.busy = "false";
      textarea.disabled = false;
      send.disabled = false;
      sendLabel.textContent = "Send message";
      textarea.focus();
      scrollFeed(feed);
    }
  }

  function bindPageInteractions() {
    document.querySelectorAll("[data-markdown-source]").forEach((element) => {
      renderMarkdown(element, element.textContent || "");
    });

    document.addEventListener("submit", (event) => {
      const form = event.target.closest("[data-chat-form]");
      if (!form) return;
      event.preventDefault();
      submitChat(form);
    });

    document.addEventListener("keydown", (event) => {
      const textarea = event.target.closest("[data-chat-input]");
      if (!textarea || event.isComposing || event.key !== "Enter" || event.shiftKey) return;
      event.preventDefault();
      textarea.form?.requestSubmit();
    });

    document.addEventListener("click", (event) => {
      const toggle = event.target.closest("[data-sidebar-toggle]");
      const sidebar = document.querySelector("#app-sidebar");
      const scrim = document.querySelector("[data-sidebar-scrim]");
      if (toggle && sidebar && scrim) {
        const open = sidebar.classList.toggle("is-open");
        scrim.classList.toggle("is-visible", open);
        toggle.setAttribute("aria-expanded", String(open));
      }
      if (event.target.closest("[data-sidebar-scrim]")) {
        sidebar?.classList.remove("is-open");
        scrim?.classList.remove("is-visible");
        document.querySelector("[data-sidebar-toggle]")?.setAttribute("aria-expanded", "false");
      }
      const layoutButton = event.target.closest("[data-model-layout]");
      if (layoutButton) {
        const grid = document.querySelector("[data-model-grid]");
        if (!grid) return;
        grid.dataset.layout = layoutButton.dataset.modelLayout;
        document.querySelectorAll("[data-model-layout]").forEach((button) => {
          button.classList.toggle("is-selected", button === layoutButton);
        });
      }
      if (event.target.closest("[data-close-modal]")) {
        document.querySelector("[data-model-modal]")?.remove();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") document.querySelector("[data-model-modal]")?.remove();
    });
  }

  if (window.marked) window.marked.setOptions({ breaks: true, gfm: true });
  document.addEventListener("DOMContentLoaded", bindPageInteractions);
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target?.id === "model-modal-host") {
      document.querySelector("[data-model-modal] select")?.focus();
    }
  });
})();
