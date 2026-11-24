/**
 * 流式聊天：SSE + 打字机；AI 页支持粘贴/附带图片走识图流式接口。
 */
function createTypewriter(el, listEl) {
  let queue = "";
  let timer = null;

  function tick() {
    if (!queue.length) {
      timer = null;
      return;
    }
    const take = queue.length > 80 ? 3 : 1;
    el.textContent += queue.slice(0, take);
    queue = queue.slice(take);
    if (listEl) listEl.scrollTop = listEl.scrollHeight;
    timer = window.setTimeout(tick, 18);
  }

  return {
    push(chunk) {
      queue += chunk;
      if (!timer) tick();
    },
    flush() {
      if (queue) {
        el.textContent += queue;
        queue = "";
      }
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (listEl) listEl.scrollTop = listEl.scrollHeight;
    },
  };
}

function parseSseData(part) {
  const line = part
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.startsWith("data:"));
  if (!line) return null;
  return JSON.parse(line.slice(5).trim());
}

function appendUserBubble(listEl, text) {
  const wrap = document.createElement("div");
  wrap.className = "message message-user";
  wrap.innerHTML =
    '<div class="message-role">你</div><div class="message-body"></div>';
  wrap.querySelector(".message-body").textContent = text;
  listEl.appendChild(wrap);
  listEl.scrollTop = listEl.scrollHeight;
}

function appendUserVisionBubble(listEl, text, imgUrl) {
  const wrap = document.createElement("div");
  wrap.className = "message message-user";
  wrap.innerHTML =
    '<div class="message-role">你</div>' +
    '<img src="" alt="上传图片" class="msg-thumb">' +
    '<div class="message-body"></div>';
  wrap.querySelector(".msg-thumb").src = imgUrl;
  wrap.querySelector(".message-body").textContent = text;
  listEl.appendChild(wrap);
  listEl.scrollTop = listEl.scrollHeight;
}

function appendAssistantBubble(listEl) {
  const wrap = document.createElement("div");
  wrap.className = "message message-assistant";
  wrap.innerHTML =
    '<div class="message-role">助手</div><div class="message-body streaming"></div>';
  listEl.appendChild(wrap);
  listEl.scrollTop = listEl.scrollHeight;
  return wrap.querySelector(".message-body");
}

async function consumeSseStream(res, assistantBody, listEl, writer, vision) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answerStarted = false;
  const thinkTimer = window.setTimeout(() => {
    if ((assistantBody.textContent || "").trim() === "正在思考…") {
      assistantBody.textContent =
        "大模型响应较慢，请稍候；若超过 20 秒仍无内容将自动切换离线回答。";
    }
  }, 8000);

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const json = parseSseData(part);
      if (!json) continue;
      if (json.type === "start") {
        if (vision) {
          assistantBody.textContent = "正在分析图片与检索知识库…";
        } else if (!answerStarted) {
          assistantBody.textContent = "正在思考…";
        }
      }
      if (json.type === "token") {
        if (!answerStarted) {
          window.clearTimeout(thinkTimer);
          assistantBody.textContent = "";
          answerStarted = true;
        }
        writer.push(json.content);
      }
      if (json.type === "error") {
        window.clearTimeout(thinkTimer);
        writer.flush();
        assistantBody.textContent = json.message;
        answerStarted = true;
      }
      if (json.type === "done") {
        writer.flush();
      }
    }
  }
  window.clearTimeout(thinkTimer);
  writer.flush();
  const trimmed = (assistantBody.textContent || "").trim();
  if (!trimmed || trimmed === "正在思考…") {
    assistantBody.textContent =
      "未收到回复。多为大模型超时或不可用，请稍后重试，或检查 .env 中的 LLM_API_KEY。";
  }
}

function setComposerPendingImage(form, file) {
  const preview = form.querySelector("[data-paste-preview]");
  const fileInput = form.querySelector('input[type="file"][name="image"]');
  if (!file) {
    form._pendingImage = null;
    if (preview) {
      preview.hidden = true;
      preview.innerHTML = "";
    }
    if (fileInput) fileInput.value = "";
    return;
  }
  form._pendingImage = file;
  if (preview) {
    preview.hidden = false;
    const url = URL.createObjectURL(file);
    preview.innerHTML =
      '<img src="" alt="待发送图片" class="msg-thumb">' +
      '<button type="button" class="btn composer-clear-img">移除图片</button>';
    preview.querySelector("img").src = url;
    preview.querySelector(".composer-clear-img")?.addEventListener("click", () => {
      URL.revokeObjectURL(url);
      setComposerPendingImage(form, null);
    });
  }
}

function bindComposerPasteAndFile(form) {
  const textEl = form.querySelector('[name="content"]');
  const fileInput = form.querySelector('input[type="file"][name="image"]');
  if (textEl) {
    textEl.addEventListener("paste", (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith("image/")) {
          e.preventDefault();
          const file = item.getAsFile();
          if (file) setComposerPendingImage(form, file);
          break;
        }
      }
    });
  }
  fileInput?.addEventListener("change", () => {
    const f = fileInput.files?.[0];
    setComposerPendingImage(form, f || null);
  });
}

async function refreshMessageList(form) {
  const url = form.dataset.messagesUrl;
  const list = document.getElementById("message-list");
  if (!url || !list) return;
  try {
    const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
    if (!res.ok) return;
    list.innerHTML = await res.text();
    list.scrollTop = list.scrollHeight;
  } catch (_) {
    /* ignore */
  }
}

function bindChatStreamForm(form, listEl) {
  if (!form || !listEl) return;

  bindComposerPasteAndFile(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = form.querySelector('[name="content"]');
    const text = (input?.value || "").trim();
    const file = form._pendingImage || form.querySelector('input[type="file"]')?.files?.[0];
    const visionUrl = form.dataset.visionStreamUrl;
    const mode =
      form.querySelector('[name="mode"]')?.value ||
      form.dataset.visionMode ||
      "vision_rag";

    if (!text && !file) return;

    input.disabled = true;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn?.setAttribute("disabled", "disabled");

    let visionText = text;
    if (file && !visionText) {
      visionText =
        mode === "vision_only"
          ? "请详细描述并解读这张图片中的内容。"
          : "请结合知识库资料，回答与这张图片相关的问题。";
    }

    let previewUrl = null;
    if (file) {
      previewUrl = URL.createObjectURL(file);
      appendUserVisionBubble(listEl, visionText, previewUrl);
    } else {
      appendUserBubble(listEl, text);
    }

    input.value = "";
    setComposerPendingImage(form, null);

    const assistantBody = appendAssistantBubble(listEl);
    const writer = createTypewriter(assistantBody, listEl);

    const fd = new FormData();
    fd.append("content", file ? visionText : text);
    if (file) {
      fd.append("image", file, file.name || "paste.png");
      fd.append("mode", mode);
    }

    const url = file && visionUrl ? visionUrl : form.action;

    try {
      const res = await fetch(url, {
        method: "POST",
        body: fd,
        headers: { Accept: "text/event-stream" },
        signal: AbortSignal.timeout(120000),
      });
      if (!res.ok || !res.body) {
        assistantBody.textContent = "请求失败，请稍后重试。";
        return;
      }
      await consumeSseStream(res, assistantBody, listEl, writer, Boolean(file));
      await refreshMessageList(form);
    } catch (err) {
      writer.flush();
      const msg = err instanceof Error ? err.message : String(err);
      const cur = (assistantBody.textContent || "").trim();
      if (cur && cur !== "正在思考…" && !cur.startsWith("大模型响应较慢")) {
        assistantBody.textContent =
          cur + "\n\n（连接中断：" + msg + "。若内容不完整请重试。）";
      } else {
        assistantBody.textContent =
          "无法连接大模型（DeepSeek 等）。请检查 .env：LLM_BASE_URL=https://api.deepseek.com/v1、LLM_MODEL=deepseek-chat、LLM_API_KEY 是否有效，以及本机网络。";
      }
    } finally {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      input.disabled = false;
      submitBtn?.removeAttribute("disabled");
      input.focus();
    }
  });
}

function bootChatStream() {
  const form = document.querySelector(
    "form.chat-input[data-stream-url]:not(.vision-form)"
  );
  const list = document.getElementById("message-list");
  if (!form || !list) return;
  if (form.dataset.streamBound === "1") return;
  form.dataset.streamBound = "1";
  form.action = form.dataset.streamUrl || form.action;
  bindChatStreamForm(form, list);
}

window.bindChatStreamForm = bindChatStreamForm;
window.bootChatStream = bootChatStream;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootChatStream);
} else {
  bootChatStream();
}
