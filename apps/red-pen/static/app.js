/* 红笔改稿 · 前端。
   只做三件事：把稿件送出去、显示引擎给出的真实阶段、按引擎的定位结果排版。
   任何「批注能不能显示」的判断都不在这里——过不了校验器就没有结果可显示。 */

(function () {
  "use strict";

  var S = {
    model: null,
    engine: null,
    sample: "",
    state: null,
    view: null,
    stats: [],
    jobId: null,
    pendingRequest: null,
    selected: null,
    backTo: null,
    timer: null
  };

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "req-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function toast(message) {
    var node = $("#toast");
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { node.hidden = true; }, 4200);
  }

  async function api(path, options) {
    options = options || {};
    var init = { method: options.method || "GET", credentials: "same-origin", headers: {} };
    if (options.body) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    var res = await fetch(path, init);
    var data = null;
    try { data = await res.json(); } catch (e) { /* 非 JSON 响应 */ }
    if (!res.ok) {
      var err = new Error((data && data.message) || ("请求失败（HTTP " + res.status + "）"));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  // ───────────────────────────────────── 视图切换
  function show(name) {
    ["compose", "brief", "run", "result"].forEach(function (key) {
      var view = $("#view-" + key);
      if (view) view.hidden = key !== name;
    });
    var step = name === "compose" ? 1 : name === "brief" ? 2 : 3;
    $$(".step").forEach(function (node) {
      var n = Number(node.dataset.step);
      node.classList.toggle("is-current", n === step);
      node.classList.toggle("is-done", n < step);
    });
    window.scrollTo(0, 0);
    $("#back-jump").hidden = true;
    S.backTo = null;
  }

  // ───────────────────────────────────── 交稿
  function wireCompose() {
    var input = $("#draft-input");
    var count = $("#char-count");

    function refresh() {
      count.textContent = input.value.length + " 字";
    }
    input.addEventListener("input", refresh);

    $("#btn-sample").addEventListener("click", function () {
      input.value = S.sample;
      refresh();
      $("#sample-hint").hidden = false;
      input.focus();
      input.setSelectionRange(0, 0);
      input.scrollTop = 0;
    });

    $("#btn-upload").addEventListener("click", function () { $("#file-input").click(); });
    $("#file-input").addEventListener("change", function (event) {
      var file = event.target.files && event.target.files[0];
      if (!file) return;
      if (!/\.txt$/i.test(file.name)) {
        toast("先只收 TXT。别的格式导出成纯文本再来。");
        event.target.value = "";
        return;
      }
      var reader = new FileReader();
      reader.onload = function () {
        input.value = String(reader.result || "");
        refresh();
        $("#sample-hint").hidden = true;
        toast("已读入 " + file.name);
      };
      reader.onerror = function () { toast("这个文件读不出来，换个 TXT 试试。"); };
      reader.readAsText(file, "utf-8");
      event.target.value = "";
    });

    $("#btn-start").addEventListener("click", async function () {
      var text = input.value;
      if (!text.trim()) { toast("先把稿子贴进来。"); input.focus(); return; }
      var button = this;
      button.disabled = true;
      button.textContent = "收稿中……";
      try {
        var data = await api("/api/draft", { method: "POST", body: { text: text } });
        S.state = (await api("/api/state")).state;
        renderBrief(data);
        show("brief");
      } catch (err) {
        toast(err.message);
      } finally {
        button.disabled = false;
        button.textContent = "交稿，开始批注";
      }
    });
  }

  // ───────────────────────────────────── 确认目的
  function renderBrief(draftInfo) {
    var brief = (draftInfo && draftInfo.brief) || {};
    var text = $("#draft-input").value.trim();
    $("#recap-text").textContent = text.length > 220 ? text.slice(0, 220) + "……" : text;
    var meta = [];
    if (draftInfo && draftInfo.version) meta.push("第 " + draftInfo.version + " 版");
    if (draftInfo && draftInfo.chars) meta.push(draftInfo.chars + " 字");
    $("#recap-label").textContent = meta.length ? "这一稿 · " + meta.join(" · ") : "这一稿";

    $("#q-audience").value = brief.audience || "";
    $("#q-purpose").value = brief.purpose || "";
    $("#q-worries").value = (brief.worries || []).join("、");

    var generic = $("#q-generic");
    var fields = ["#q-audience", "#q-purpose", "#q-worries"];
    // 默认不勾「按通用标准」：一进来就能写，勾选是用户自己做的选择。
    generic.checked = false;
    fields.forEach(function (sel) { $(sel).disabled = false; });

    var disclosure = $("#disclosure");
    if (S.model && S.model.configured && !S.model.simulated) {
      disclosure.innerHTML = "这次会把稿件正文和上面三条标准发送给你配置的模型服务（<strong>" +
        escapeHtml(S.model.model) + "</strong>）生成批注。密钥只在服务端，浏览器里没有。" +
        "校验在本机服务端完成，红笔稿不会上传。";
    } else if (S.model && S.model.simulated) {
      disclosure.innerHTML = "<strong>当前是模拟通道。</strong>批注由本地模板生成，不是模型写的，" +
        "只用来跑通「收稿 → 校验 → 出报告」这条链路，不能当作真实批注。";
    } else {
      disclosure.innerHTML = "<strong>还没有配置模型。</strong>" +
        escapeHtml((S.model && S.model.note) || "服务端缺模型配置。") +
        " 现在点下去会如实报错，不会伪造批注。";
    }
  }

  function wireBrief() {
    var generic = $("#q-generic");
    var fields = ["#q-audience", "#q-purpose", "#q-worries"];
    generic.addEventListener("change", function () {
      fields.forEach(function (sel) {
        $(sel).disabled = generic.checked;
        if (generic.checked) $(sel).value = "";
      });
    });

    $("#btn-back-compose").addEventListener("click", function () {
      show("compose");
      $("#draft-input").focus();
    });

    $("#brief-form").addEventListener("submit", async function (event) {
      event.preventDefault();
      var worries = generic.checked ? [] : $("#q-worries").value
        .split(/[、,，;；\n]/).map(function (s) { return s.trim(); })
        .filter(function (s) { return s.length > 0; }).slice(0, 5);
      var payload = {
        audience: generic.checked ? "" : $("#q-audience").value.trim(),
        purpose: generic.checked ? "" : $("#q-purpose").value.trim(),
        worries: worries
      };
      var button = $("#btn-generate");
      button.disabled = true;
      button.textContent = "提交中……";
      try {
        var data = await api("/api/brief", { method: "POST", body: payload });
        if (data.invalidated) {
          toast("写作目的改过了，之前那一轮的批注已作废，现在重新批。");
        }
        S.state = (await api("/api/state")).state;
        startGeneration();
      } catch (err) {
        toast(err.message);
        button.disabled = false;
        button.textContent = "开始批注";
      }
    });
  }

  // ───────────────────────────────────── 生成
  async function startGeneration() {
    var requestId = S.pendingRequest || uuid();
    S.pendingRequest = requestId;
    renderStages([], "running");
    renderRunContext();
    show("run");
    $("#run-error").hidden = true;

    try {
      var data = await api("/api/generate", { method: "POST", body: { request_id: requestId } });
      S.jobId = data.job.id;
      renderStages(data.job.stages, data.job.status);
      pollJob();
    } catch (err) {
      S.pendingRequest = null;
      failRun(err.message, [], err.data && err.data.model ? err.data.model : null);
    }
  }

  function pollJob() {
    clearTimeout(S.timer);
    S.timer = setTimeout(async function () {
      if (!S.jobId) return;
      try {
        var data = await api("/api/job?id=" + encodeURIComponent(S.jobId));
        var job = data.job;
        renderStages(job.stages, job.status);
        if (job.status === "running") {
          pollJob();
          return;
        }
        S.jobId = null;
        S.pendingRequest = null;
        if (job.status === "done") {
          S.state = (await api("/api/state")).state;
          renderResult(job.result, job.result.stats || []);
          show("result");
        } else {
          var err = job.error || {};
          failRun(err.message || "这次没有批成。", err.errors || [], null, err.warnings || []);
        }
      } catch (err) {
        S.jobId = null;
        S.pendingRequest = null;
        failRun("查不到这个任务的进度了：" + err.message);
      }
    }, 700);
  }

  function renderRunContext() {
    var box = $("#run-context");
    box.innerHTML = "";
    var state = S.state || {};
    var brief = state.brief || {};
    var lines = [];
    if (brief.audience) lines.push(["给谁看", brief.audience]);
    if (brief.purpose) lines.push(["要达到", brief.purpose]);
    if (brief.worries && brief.worries.length) lines.push(["最怕", brief.worries.join("、")]);
    if (!lines.length) lines.push(["标准", "按通用标准批，没有指定受众"]);
    lines.forEach(function (row) {
      var p = el("p");
      p.appendChild(el("span", "run-label", row[0]));
      p.appendChild(document.createTextNode(row[1]));
      box.appendChild(p);
    });
    var head = (state.raw || "").split("\n").filter(function (line) { return line.trim(); })[0] || "";
    if (head) box.appendChild(el("p", "run-head", "稿件：" + (head.length > 40 ? head.slice(0, 40) + "……" : head)));
  }

  function renderStages(stages, status) {
    var list = $("#stages");
    list.innerHTML = "";
    var names = ["读取稿件", "分析表达", "校验引用", "整理红笔稿"];
    names.forEach(function (name, index) {
      var stage = stages && stages[index] ? stages[index] : { state: "pending", detail: "" };
      var li = el("li", "stage is-" + stage.state);
      var dot = el("span", "stage-dot");
      var body = el("span", "stage-body");
      body.appendChild(document.createTextNode(name));
      if (stage.detail) body.appendChild(el("span", "stage-detail", stage.detail));
      li.appendChild(dot);
      li.appendChild(body);
      list.appendChild(li);
    });
  }

  function failRun(message, errors, model, warnings) {
    show("run");
    var box = $("#run-error");
    box.innerHTML = "";
    box.hidden = false;
    box.appendChild(el("h3", null, "这次没有批成"));
    box.appendChild(el("p", null, message));
    if (errors && errors.length) {
      var ul = el("ul");
      errors.slice(0, 12).forEach(function (line) { ul.appendChild(el("li", null, line)); });
      box.appendChild(ul);
    }
    if (warnings && warnings.length) {
      box.appendChild(el("p", "hint", "校验器另有提醒：" + warnings.slice(0, 3).join("；")));
    }
    if (model) {
      box.appendChild(el("p", "hint", "模型状态：" + (model.note || "")));
    }
    box.appendChild(el("p", "hint", "稿件和写作目的都还在，可以直接重试；也可以回去改写作目的。"));

    var actions = el("div", "run-actions");
    var retry = el("button", "primary", "重试这一遍");
    retry.type = "button";
    retry.addEventListener("click", function () {
      box.hidden = true;
      startGeneration();
    });
    var back = el("button", "ghost", "改写作目的");
    back.type = "button";
    back.addEventListener("click", function () {
      show("brief");
      renderBrief({
        brief: S.state ? S.state.brief : {},
        version: S.state && S.state.version,
        chars: S.state && S.state.chars
      });
    });
    actions.appendChild(retry);
    actions.appendChild(back);
    box.appendChild(actions);
  }

  // ───────────────────────────────────── 红笔稿
  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  // 桌面双栏：把两栏的高度压到「刚好放得进一屏」，避免出现两层滚动条
  function fitPanes() {
    var root = document.documentElement;
    if (window.innerWidth < 900) {
      root.style.removeProperty("--pane-h");
      return;
    }
    var pane = $("#draft-pane");
    if (!pane) return;
    var top = pane.getBoundingClientRect().top;
    var height = Math.max(320, window.innerHeight - top - 20);
    root.style.setProperty("--pane-h", Math.round(height) + "px");
  }

  function renderResult(view, stats) {
    S.view = view;
    S.stats = stats || [];
    S.selected = null;

    var version = view.version;
    var ratio = Math.round((view.anchored_ratio || 0) * 100);
    var counts = view.counts || {};
    var meta = $("#result-meta");
    meta.innerHTML = "第 <b>" + version + "</b> 版 · 共 <b>" + view.total + "</b> 条批注 · 钉住 <b>" +
      view.anchored_count + "</b> 条（" + ratio + "%）" +
      (view.unlocated.length ? " · <b>" + view.unlocated.length + "</b> 条未能定位" : "") +
      "<br>需要处理 " + (counts.major || 0) + " · 可以改进 " + (counts.minor || 0) +
      " · 供你参考 " + (counts.remark || 0);

    var sim = $("#sim-banner");
    if (view.simulated) {
      sim.hidden = false;
      sim.className = "banner";
      sim.innerHTML = "<b>这一份是模拟批注。</b>当前没有配置模型，批注由本地模板生成，" +
        "只用来验证「收稿 → 校验 → 定位 → 下载」这条链路。它不是模型读你的稿子写出来的意见，不能当验收结果。";
    } else {
      sim.hidden = true;
    }
    $("#stale-banner").hidden = true;

    renderSplit(view);
    renderMobile(view);
    renderUnlocated(view);
    renderCompare(view, stats);
    resetRevise(view);
    $("#btn-download").dataset.version = version;
    $("#btn-open-report").dataset.version = version;
    requestAnimationFrame(fitPanes);
  }

  function priorityBlock(view) {
    if (!view.priority || !view.priority.length) return null;
    var box = el("div", "priority");
    box.appendChild(el("h3", null, "先看这几条"));
    var list = el("ul");
    view.priority.forEach(function (id) {
      var mark = view.marks.filter(function (m) { return m.id === id; })[0];
      if (!mark) return;
      var li = el("li");
      var button = el("button");
      button.type = "button";
      button.appendChild(el("span", "num", String(mark.id)));
      button.appendChild(el("span", "tag", mark.level_text));
      button.appendChild(el("span", "priority-text",
        mark.note.length > 68 ? mark.note.slice(0, 68) + "……" : mark.note));
      button.addEventListener("click", function () { select(mark.id, "priority"); });
      li.appendChild(button);
      list.appendChild(li);
    });
    box.appendChild(list);
    return box;
  }

  function marksByBlock(view) {
    var map = {};
    view.marks.forEach(function (m) {
      if (m.block === null || m.block === undefined) return;
      (map[m.block] = map[m.block] || []).push(m);
    });
    Object.keys(map).forEach(function (key) {
      map[key].sort(function (a, b) { return a.start - b.start; });
    });
    return map;
  }

  function blockNode(text, marks) {
    var p = el("p", "block");
    var cursor = 0;
    marks.forEach(function (m) {
      if (m.start > cursor) p.appendChild(document.createTextNode(text.slice(cursor, m.start)));
      var hit = el("span", "hit level-" + m.level, text.slice(m.start, m.end));
      hit.dataset.markId = String(m.id);
      hit.tabIndex = 0;
      hit.setAttribute("role", "button");
      hit.setAttribute("aria-label", "第 " + m.id + " 条批注定位：" + m.level_text);
      hit.addEventListener("click", function () { select(m.id, "draft"); });
      hit.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select(m.id, "draft");
        }
      });
      p.appendChild(hit);
      cursor = Math.max(cursor, m.end);
    });
    if (cursor < text.length) p.appendChild(document.createTextNode(text.slice(cursor)));
    return p;
  }

  function cardNode(mark) {
    var card = el("article", "card level-" + mark.level);
    card.dataset.markId = String(mark.id);
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", "第 " + mark.id + " 条，" + mark.level_text);

    var head = el("div", "card-head");
    head.appendChild(el("span", "num", String(mark.id)));
    head.appendChild(el("span", "tag", mark.level_text));
    if (mark.partial) head.appendChild(el("span", "partial-flag", "只对上头尾，仅供参考"));
    card.appendChild(head);

    card.appendChild(el("blockquote", "quote", mark.quote));
    card.appendChild(el("p", "note", mark.note));
    if (mark.fix) {
      var fix = el("p", "fix");
      fix.appendChild(el("span", "fix-label", "改法"));
      fix.appendChild(document.createTextNode(mark.fix));
      card.appendChild(fix);
    }

    card.addEventListener("click", function () { select(mark.id, "card"); });
    card.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(mark.id, "card");
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        var cards = $$(".pane-notes .card, .mobile-flow .card")
          .filter(function (node) { return node.offsetParent !== null; });
        var index = cards.indexOf(card);
        var next = cards[index + (event.key === "ArrowDown" ? 1 : -1)];
        if (next) next.focus();
      }
    });
    return card;
  }

  function renderSplit(view) {
    var map = marksByBlock(view);
    var draft = $("#draft-pane");
    var notes = $("#notes-pane");
    draft.innerHTML = "";
    notes.innerHTML = "";

    view.blocks.forEach(function (block, index) {
      draft.appendChild(blockNode(block.text, map[index] || []));
    });
    var priority = priorityBlock(view);
    if (priority) notes.appendChild(priority);
    view.marks.forEach(function (mark) { notes.appendChild(cardNode(mark)); });
    if (!view.marks.length) {
      notes.appendChild(el("p", "hint", "这一轮没有批注能钉在原文上。"));
    }
  }

  function renderMobile(view) {
    var map = marksByBlock(view);
    var flow = $("#flow-pane");
    flow.innerHTML = "";
    var priority = priorityBlock(view);
    if (priority) flow.appendChild(priority);
    view.blocks.forEach(function (block, index) {
      flow.appendChild(blockNode(block.text, map[index] || []));
      (map[index] || []).forEach(function (mark) { flow.appendChild(cardNode(mark)); });
    });
  }

  function renderUnlocated(view) {
    var box = $("#unlocated");
    var list = $("#unlocated-list");
    list.innerHTML = "";
    if (!view.unlocated.length) { box.hidden = true; return; }
    box.hidden = false;
    $("#unlocated-title").textContent = "未能定位（" + view.unlocated.length + " 条）";
    view.unlocated.forEach(function (mark) {
      var li = el("li");
      li.appendChild(el("blockquote", "quote", mark.quote));
      li.appendChild(el("p", "note", mark.note));
      li.appendChild(el("p", "reason", "为什么没定位：" + (mark.reason || "引擎没有给出原因")));
      list.appendChild(li);
    });
  }

  function renderCompare(view, stats) {
    var box = $("#compare");
    var list = $("#compare-list");
    list.innerHTML = "";
    var start = -1;
    (stats || []).forEach(function (line, index) {
      if (/^(与上一版|这是第 1 版)/.test(line)) start = index;
    });
    if (start < 0 || /^这是第 1 版/.test((stats || [])[start])) { box.hidden = true; return; }
    box.hidden = false;
    (stats || []).slice(start).forEach(function (line, index) {
      var trimmed = line.trim();
      if (!trimmed) return;
      var li = el("li", index === 0 ? "is-head" : null, trimmed);
      list.appendChild(li);
    });
    list.appendChild(el("li", "is-head", "本轮新写了 " + view.total + " 条批注，就是上面这些。"));
  }

  // ───────────────────────────────────── 选择与定位
  function paneScroller(node) {
    var pane = node.closest ? node.closest(".pane") : null;
    return pane || null;
  }

  function scrollWithin(container, node) {
    if (!container || !node) return;
    var c = container.getBoundingClientRect();
    var n = node.getBoundingClientRect();
    if (n.top >= c.top && n.bottom <= c.bottom) return;
    container.scrollTop += (n.top - c.top) - (container.clientHeight - n.height) / 2;
  }

  function select(id, source) {
    var key = String(id);
    if (S.selected === key && source !== "priority") {
      S.selected = null;
      $$("[data-mark-id]").forEach(function (node) { node.classList.remove("is-active"); });
      return;
    }
    S.selected = key;
    $$("[data-mark-id]").forEach(function (node) {
      node.classList.toggle("is-active", node.dataset.markId === key);
    });

    var cardDesktop = $('.pane-notes .card[data-mark-id="' + key + '"]');
    var cardMobile = $('.mobile-flow .card[data-mark-id="' + key + '"]');
    var hitDesktop = $('.pane-draft .hit[data-mark-id="' + key + '"]');
    var hitMobile = $('.mobile-flow .hit[data-mark-id="' + key + '"]');
    var card = (cardDesktop && cardDesktop.offsetParent !== null) ? cardDesktop : cardMobile;
    var hit = (hitDesktop && hitDesktop.offsetParent !== null) ? hitDesktop : hitMobile;

    var remember = null;
    if (source === "draft") {
      if (card) {
        var scroller = paneScroller(card);
        remember = { node: scroller, top: scroller ? scroller.scrollTop : window.scrollY };
        if (scroller) scrollWithin(scroller, card);
        else card.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    } else if (source === "card") {
      if (hit) {
        var scroller2 = paneScroller(hit);
        remember = { node: scroller2, top: scroller2 ? scroller2.scrollTop : window.scrollY };
        if (scroller2) scrollWithin(scroller2, hit);
        else {
          var rect = hit.getBoundingClientRect();
          if (rect.top < 60 || rect.bottom > window.innerHeight - 40) {
            hit.scrollIntoView({ block: "center", behavior: "smooth" });
          }
        }
      }
    } else if (source === "priority") {
      if (card) {
        var scroller3 = paneScroller(card);
        remember = { node: scroller3, top: scroller3 ? scroller3.scrollTop : window.scrollY };
        if (scroller3) scrollWithin(scroller3, card);
        else card.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }

    if (remember) {
      S.backTo = remember;
      $("#back-jump").hidden = false;
    }
  }

  function wireBackJump() {
    $("#btn-back-jump").addEventListener("click", function () {
      if (!S.backTo) { $("#back-jump").hidden = true; return; }
      if (S.backTo.node) S.backTo.node.scrollTop = S.backTo.top;
      else window.scrollTo({ top: S.backTo.top, behavior: "smooth" });
      $("#back-jump").hidden = true;
    });
  }

  // ───────────────────────────────────── 下载 / 原页
  function wireResultActions() {
    $("#btn-download").addEventListener("click", function () {
      var version = this.dataset.version || (S.view && S.view.version) || "";
      window.location.href = "/api/download?version=" + encodeURIComponent(version);
    });
    $("#btn-open-report").addEventListener("click", function () {
      var version = this.dataset.version || (S.view && S.view.version) || "";
      window.open("/api/report?version=" + encodeURIComponent(version), "_blank", "noopener");
    });
    $("#btn-change-brief").addEventListener("click", function () {
      show("brief");
      renderBrief({
        brief: (S.state && S.state.brief) || (S.view && S.view.brief) || {},
        version: S.state && S.state.version,
        chars: S.state && S.state.chars
      });
    });
    $("#btn-revise").addEventListener("click", function () {
      var panel = $("#revise-panel");
      panel.hidden = false;
      panel.scrollIntoView({ block: "start", behavior: "smooth" });
      $("#revise-input").focus();
    });
  }

  function resetRevise(view) {
    var panel = $("#revise-panel");
    panel.hidden = true;
    var raw = (S.state && S.state.raw) || "";
    $("#revise-input").value = raw;
    $("#revise-next").textContent = String((view.version || 1) + 1);
    $("#revise-note").textContent = "";
    updateReviseCount();
  }

  function updateReviseCount() {
    var value = $("#revise-input").value;
    $("#revise-count").textContent = value.length + " 字";
  }

  function wireRevise() {
    $("#revise-input").addEventListener("input", updateReviseCount);
    $("#btn-revise-cancel").addEventListener("click", function () {
      $("#revise-panel").hidden = true;
    });
    $("#btn-revise-submit").addEventListener("click", async function () {
      var text = $("#revise-input").value;
      if (!text.trim()) { toast("改完的稿子是空的。"); return; }
      var button = this;
      button.disabled = true;
      button.textContent = "提交中……";
      try {
        var data = await api("/api/draft", { method: "POST", body: { text: text } });
        if (!data.created_version) {
          $("#revise-note").textContent = "和第 " + (S.view ? S.view.version : 1) +
            " 版逐字相同，没有生成新版本——原样提交不会虚增一版。";
          toast("稿子没变，没有生成新版本。");
          return;
        }
        S.state = (await api("/api/state")).state;
        $("#revise-panel").hidden = true;
        toast("收到第 " + data.version + " 版，重新批一遍。");
        startGeneration();
      } catch (err) {
        toast(err.message);
      } finally {
        button.disabled = false;
        button.textContent = "提交新一版";
      }
    });
  }

  // ───────────────────────────────────── 作废状态
  function renderStale(lines) {
    show("result");
    $("#sim-banner").hidden = true;
    $("#draft-pane").innerHTML = "";
    $("#notes-pane").innerHTML = "";
    $("#flow-pane").innerHTML = "";
    $("#unlocated").hidden = true;
    $("#compare").hidden = true;
    $("#revise-panel").hidden = true;
    $("#result-meta").textContent = "";
    var banner = $("#stale-banner");
    banner.hidden = false;
    banner.className = "banner warn";
    banner.innerHTML = "<b>这一版的红笔稿已经作废。</b>稿件或写作目的改过了，旧批注不能继续算作当前有效的评审。" +
      (lines && lines.length ? "<br>" + lines.map(escapeHtml).join("<br>") : "") +
      "<br>按新的稿子重新批一遍。";
    $("#btn-download").dataset.version = "";
    $("#btn-open-report").dataset.version = "";
  }

  // ───────────────────────────────────── 启动
  async function boot() {
    wireCompose();
    wireBrief();
    wireRevise();
    wireResultActions();
    wireBackJump();
    window.addEventListener("resize", function () {
      if (S.view && !$("#view-result").hidden) fitPanes();
    });

    try {
      var data = await api("/api/bootstrap");
      S.model = data.model;
      S.engine = data.engine;
      S.sample = data.sample || "";
      S.state = data.state;
    } catch (err) {
      toast("服务端没有响应：" + err.message);
      return;
    }

    if (!S.engine.ready) {
      toast("服务端缺校验器脚本，先跑 scripts/sync_engine.py。");
    }
    if (S.model && S.model.simulated) {
      $("#sim-chip").hidden = false;
      $("#compose-note").textContent = "当前是模拟通道：批注由本地模板生成，不是模型读你的稿子写的。";
    }

    var state = S.state || {};
    if (state.review && state.review.exists) {
      if (state.review.stale) {
        renderStale(state.review.stats_lines || []);
      } else if (state.view) {
        renderResult(state.view, state.review.stats_lines || []);
        show("result");
      } else {
        show("compose");
      }
    } else if (state.has_draft) {
      $("#draft-input").value = state.raw || "";
      $("#char-count").textContent = ($("#draft-input").value.length) + " 字";
      renderBrief({ brief: state.brief });
      show("brief");
    } else {
      show("compose");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
