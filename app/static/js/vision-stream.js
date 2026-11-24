/**
 * 图像对话：multipart 流式 SSE，发送后清空文字与文件选择。
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
      if (queue) el.textContent += queue;
      queue = "";
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (listEl) listEl.scrollTop = listEl.scrollHeight;
    },
  };
}

function parseSsePart(part) {
  const line = part
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.startsWith("data:"));
  if (!line) return null;
  return JSON.parse(line.slice(5).trim());
}

function bindVisionStreamForm(form, listEl) {
  if (!form || !listEl) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const textInput = form.querySelector('input[name="content"]');
    const fileInput = form.querySelector('input[name="image"]');
    const mode = form.querySelector('[name="mode"]')?.value || "vision_rag";
    let text = (textInput?.value || "").trim();
    const file = fileInput?.files?.[0];
    if (!file) return;
    if (!text) {
      text =
        mode === "vision_only"
          ? "请详细描述并解读这张图片中的内容。"
          : "请结合知识库资料，回答与这张图片相关的问题。";
    }

    const previewUrl = URL.createObjectURL(file);
    textInput.value = "";
    if (fileInput) fileInput.value = "";
    textInput.disabled = true;
    fileInput.disabled = true;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn?.setAttribute("disabled", "disabled");

    appendUserVisionBubble(listEl, text, previewUrl);
    const assistantBody = appendAssistantBubble(listEl);
    const writer = createTypewriter(assistantBody, listEl);

    const fd = new FormData(form);
    fd.set("content", text);
    fd.set("image", file);

    try {
      const res = await fetch(form.action, {
        method: "POST",
        body: fd,
        headers: { Accept: "text/event-stream" },
      });
      if (!res.ok || !res.body) {
        assistantBody.textContent = "请求失败，请稍后重试。";
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answerStarted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const json = parseSsePart(part);
          if (!json) continue;
          if (json.type === "start") {
            assistantBody.textContent = "正在分析图片与检索知识库…";
          }
          if (json.type === "token") {
            if (!answerStarted) {
              assistantBody.textContent = "";
              answerStarted = true;
            }
            writer.push(json.content);
          }
          if (json.type === "error") {
            writer.flush();
            assistantBody.textContent = json.message;
          }
          if (json.type === "done" && json.citations?.length) {
            writer.flush();
            const foot = document.createElement("p");
            foot.className = "muted small cite-foot";
            foot.textContent = "参考：" + json.citations.join("、");
            assistantBody.parentElement?.appendChild(foot);
          }
        }
      }
      writer.flush();
    } catch (err) {
      assistantBody.textContent = "网络错误：" + err;
    } finally {
      URL.revokeObjectURL(previewUrl);
      textInput.disabled = false;
      fileInput.disabled = false;
      submitBtn?.removeAttribute("disabled");
      textInput.focus();
    }
  });
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

function bootVisionStream() {
  const form = document.querySelector(
    "form.vision-form[data-stream-url]"
  );
  const list = document.getElementById("message-list");
  if (!form || !list) return;
  if (form.dataset.streamBound === "1") return;
  form.dataset.streamBound = "1";
  form.action = form.dataset.streamUrl || form.action;
  bindVisionStreamForm(form, list);
}

window.bootVisionStream = bootVisionStream;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootVisionStream);
} else {
  bootVisionStream();
}
