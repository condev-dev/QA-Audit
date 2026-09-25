/* ==========================================================================
   link_lab.js  |  بخش «استخراج لینک از متن» برای پنل QA Master
   --------------------------------------------------------------------------
   این فایل مستقل است و هیچ تغییری در app.py لازم ندارد؛ همان Flask
   آن را به‌صورت خودکار از مسیر /static/link_lab.js سرو می‌کند
   (کافی است فایل را کنار app.py داخل پوشه static بگذارید).

   از توابع سراسری خود پنل استفاده می‌کند: esc() و normKey()
   ========================================================================== */
(function () {
  "use strict";

  var LS_KEY = "qa_link_lab_items"; // نگه‌داشتن لیست بین رفرش‌ها
  var BIG_LIST = 40; // از این تعداد به بالا، فاصله باز کردن تب‌ها بیشتر می‌شود

  var state = { items: [], seq: 0, stats: null };

  /* ---------------------------------------------------------------- کمکی‌ها */
  function $(id) {
    return document.getElementById(id);
  }

  function escSafe(v) {
    return typeof esc === "function" ? esc(v) : String(v == null ? "" : v);
  }

  function keyOf(u) {
    try {
      return typeof normKey === "function" ? normKey(u) : String(u).toLowerCase();
    } catch (e) {
      return String(u).toLowerCase();
    }
  }

  function isOptOn(id, fallback) {
    var el = $(id);
    return el ? !!el.checked : !!fallback;
  }

  function countChar(s, c) {
    var n = 0;
    for (var i = 0; i < s.length; i++) if (s.charAt(i) === c) n++;
    return n;
  }

  function toast(msg, kind) {
    var el = $("ll-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "ll-toast";
      document.body.appendChild(el);
    }
    var err = kind === "err";
    el.style.cssText =
      "position:fixed;bottom:26px;left:50%;transform:translateX(-50%);z-index:9999;" +
      "padding:10px 18px;border-radius:8px;font-size:12px;font-weight:700;" +
      "font-family:Vazirmatn,sans-serif;max-width:80vw;text-align:center;line-height:1.7;" +
      "box-shadow:0 12px 34px rgba(0,0,0,.65);transition:opacity .25s;opacity:1;" +
      "border:1px solid " +
      (err ? "#7f1d1d" : "#27272a") +
      ";background:" +
      (err ? "#450a0a" : "#09090b") +
      ";color:" +
      (err ? "#fca5a5" : "#fafafa") +
      ";";
    el.textContent = msg;
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.style.opacity = "0";
    }, 2600);
  }

  // کپی با فالبک برای مرورگرهای قدیمی‌تر
  function copyText(text, okMsg) {
    var done = function () {
      if (okMsg) toast(okMsg);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(done)
        .catch(function () {
          legacyCopy(text) ? done() : toast("کپی نشد؛ دسترسی کلیپ‌بورد را بدهید.", "err");
        });
    } else {
      legacyCopy(text) ? done() : toast("کپی نشد؛ دسترسی کلیپ‌بورد را بدهید.", "err");
    }
  }

  function legacyCopy(text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;top:-1000px;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch (e) {
      return false;
    }
  }

  /* ------------------------------------------------------- موتور استخراج لینک */
  var TLD_SRC =
    "(?:ir|com|net|org|io|co|de|ru|uk|fr|nl|se|info|biz|xyz|me|dev|app|ai|site|online|shop|store|" +
    "blog|club|top|tv|cc|us|ca|au|it|es|tr|in|cn|jp|kr|br|pl|be|ch|at|dk|no|fi|cz|gr|pt|ro|hu|" +
    "ie|nz|za|ae|sa|eg|pk|id|my|sg|th|vn|ph|hk|tw|il|gov|edu|pro|live|news|media|agency|design|" +
    "work|space|tech|website|host|press|world|today|life)";

  var TRACK_KEYS = [
    /^utm_/i,
    /^fbclid$/i,
    /^gclid$/i,
    /^dclid$/i,
    /^msclkid$/i,
    /^yclid$/i,
    /^igshid$/i,
    /^_ga$/i,
    /^_gl$/i,
    /^mc_cid$/i,
    /^mc_eid$/i,
    /^ref_src$/i,
  ];

  // پیدا کردن همه نامزدهای لینک داخل متن قاطی
  function findCandidates(text, o) {
    var out = [];
    var work = String(text || "");

    // ۱) لینک‌های کامل (http/https یا شروع‌شده با www.)
    var re1 = /(?:https?:\/\/|www\.)[^\s<>"'`\u200c\u200e\u200f\\^{}|\[\]]+/gi;
    work = work.replace(re1, function (m) {
      out.push({ url: m, guessed: false });
      return " ";
    });

    // ۲) دامنه‌های بدون پروتکل مثل example.com/page (اختیاری)
    if (o && o.bare) {
      var re2 = new RegExp(
        "(^|[^0-9A-Za-z@._\\-\\/])((?:[0-9A-Za-z][0-9A-Za-z\\-]{0,62}\\.)+" +
          TLD_SRC +
          "(?!\\.[0-9A-Za-z]))((?:\\/[^\\s<>\"'`\\u200c\\[\\]]*)?)",
        "gi",
      );
      work = work.replace(re2, function (m, pre, host, path) {
        out.push({ url: host + (path || ""), guessed: true });
        return pre + " ";
      });
    }
    return out;
  }

  function isValidHost(h) {
    if (!h) return false;
    if (h === "localhost") return true;
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h)) return true; // IPv4
    if (h.indexOf(":") !== -1) return true; // IPv6
    return /^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/i.test(h);
  }

  function stripTrackers(p) {
    try {
      var keys = [];
      p.searchParams.forEach(function (v, k) {
        for (var i = 0; i < TRACK_KEYS.length; i++) {
          if (TRACK_KEYS[i].test(k)) {
            keys.push(k);
            break;
          }
        }
      });
      keys.forEach(function (k) {
        p.searchParams.delete(k);
      });
    } catch (e) {}
    return p;
  }

  // باز کردن لینک‌های ریدایرکت رایج (گوگل / فیسبوک)
  function unwrapRedirect(p) {
    try {
      var h = p.hostname.toLowerCase();
      if (/(^|\.)google\.[a-z.]+$/.test(h) && /^\/url\/?$/.test(p.pathname)) {
        var q = p.searchParams.get("q") || p.searchParams.get("url");
        if (q && /^https?:\/\//i.test(q)) return new URL(q);
      }
      if (h === "l.facebook.com" || h === "lm.facebook.com") {
        var u = p.searchParams.get("u");
        if (u && /^https?:\/\//i.test(u)) return new URL(u);
      }
    } catch (e) {}
    return p;
  }

  // تمیز کردن یک نامزد و تبدیل آن به لینک نهایی (یا null اگر معتبر نباشد)
  function cleanUrl(input, o) {
    var s = String(input == null ? "" : input).trim();
    if (!s) return null;

    s = s
      .replace(/&amp;/gi, "&")
      .replace(/&#0?38;/g, "&")
      .replace(/&quot;/gi, '"')
      .replace(/&#0?39;/g, "'")
      .replace(/&apos;/gi, "'")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">");

    s = s.replace(/^[<\[({«"'`\s\u200e\u200f]+/, "");
    var guard = 0;
    while (guard++ < 30) {
      var before = s;
      s = s.replace(/[>"'\]}»`\s\u200e\u200f]+$/, "");
      if (/[.,;:!?؟،؛…]$/.test(s)) s = s.slice(0, -1);
      if (s.slice(-1) === ")" && countChar(s, ")") > countChar(s, "(")) s = s.slice(0, -1);
      if (s.slice(-1) === "]" && countChar(s, "]") > countChar(s, "[")) s = s.slice(0, -1);
      if (s.slice(-1) === "}" && countChar(s, "}") > countChar(s, "{")) s = s.slice(0, -1);
      if (s === before) break;
    }
    if (!s) return null;

    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = "https://" + s.replace(/^\/\//, "");
    if (!/^https?:\/\//i.test(s)) return null;

    var p;
    try {
      p = new URL(s);
    } catch (e) {
      return null;
    }
    if (!p.hostname) return null;
    var h = p.hostname.replace(/\.$/, "").toLowerCase();
    if (!isValidHost(h)) return null;

    p = unwrapRedirect(p);
    if (o && o.utm) p = stripTrackers(p);

    var out = p.href;
    // اسلش انتهایی حذف می‌شود تا با کلید یکسان‌سازی خود پنل (normKey) هم‌خوان باشد
    if (!p.search && !p.hash) out = out.replace(/\/$/, "");
    return out;
  }

  /* ------------------------------------------------------------ ذخیره/بازیابی */
  function save() {
    try {
      localStorage.setItem(
        LS_KEY,
        JSON.stringify(
          state.items.map(function (it) {
            return it.url;
          }),
        ),
      );
    } catch (e) {}
  }

  function load() {
    try {
      var raw = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
      if (!Array.isArray(raw)) return;
      state.items = raw
        .filter(function (u) {
          return typeof u === "string" && u;
        })
        .map(function (u) {
          return { id: ++state.seq, url: u, key: keyOf(u), guessed: false };
        });
    } catch (e) {}
  }

  /* ------------------------------------------------------------- اکشن‌های اصلی */
  function extract() {
    var inp = $("ll-input");
    var text = inp ? inp.value : "";
    if (!text || !text.trim()) {
      toast("اول متن یا صفحه را داخل کادر پیست کنید.", "err");
      return;
    }
    var o = {
      dedupe: isOptOn("ll-opt-dedupe", true),
      bare: isOptOn("ll-opt-bare", false),
      utm: isOptOn("ll-opt-utm", false),
      sort: isOptOn("ll-opt-sort", false),
    };

    var raw = findCandidates(text, o);
    var out = [];
    var seen = Object.create(null);
    var dup = 0;
    var bad = 0;

    raw.forEach(function (c) {
      var u = cleanUrl(c.url, o);
      if (!u) {
        bad++;
        return;
      }
      var k = keyOf(u);
      if (o.dedupe) {
        if (seen[k]) {
          dup++;
          return;
        }
        seen[k] = 1;
      }
      out.push({ id: ++state.seq, url: u, key: k, guessed: !!c.guessed });
    });

    if (o.sort) {
      out.sort(function (a, b) {
        return a.url.localeCompare(b.url);
      });
    }

    state.items = out;
    state.stats = {
      total: raw.length,
      dup: dup,
      bad: bad,
      guessed: out.filter(function (i) {
        return i.guessed;
      }).length,
      hasUtm: o.utm,
    };

    save();
    render();
    if (!out.length) toast("در این متن لینکی پیدا نشد.", "err");
    else toast(out.length + " لینک تمیز و یکتا آماده شد.");
  }

  async function pasteAndExtract() {
    try {
      var t = await navigator.clipboard.readText();
      if (!t || !t.trim()) {
        toast("کلیپ‌بورد خالی است؛ متن را داخل کادر پیست کنید.", "err");
        return;
      }
      var inp = $("ll-input");
      if (inp) {
        var cur = (inp.value || "").replace(/\s+$/, "");
        inp.value = cur ? cur + "\n\n" + t : t;
      }
      extract();
    } catch (e) {
      toast("خواندن کلیپ‌بورد ممکن نشد؛ با Ctrl+V پیست کنید.", "err");
    }
  }

  function inputKey(e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      extract();
    }
  }

  function clearInput() {
    var i = $("ll-input");
    if (i) {
      i.value = "";
      i.focus();
    }
  }

  function handleFile(input) {
    var f = input.files && input.files[0];
    if (!f) return;
    var fr = new FileReader();
    fr.onload = function () {
      var i = $("ll-input");
      if (i) i.value = String(fr.result || "");
      extract();
    };
    fr.readAsText(f, "utf-8");
    input.value = "";
  }

  /* -------------------------------------------------------------- لیست و نمایش */
  function findById(id) {
    var n = Number(id);
    for (var i = 0; i < state.items.length; i++) if (state.items[i].id === n) return state.items[i];
    return null;
  }

  function statsText() {
    var s = state.stats;
    if (!s || !state.items.length) return "";
    var parts = [];
    if (s.total) parts.push("از " + s.total + " مورد پیدا‌شده");
    if (s.dup) parts.push(s.dup + " تکراری حذف شد");
    if (s.bad) parts.push(s.bad + " نامعتبر رد شد");
    if (s.guessed) parts.push(s.guessed + " بدون پروتکل");
    return parts.length ? " — " + parts.join(" • ") : "";
  }

  function render() {
    var listEl = $("ll-list");
    if (!listEl) return;

    var items = state.items;
    var q = ($("ll-search") ? $("ll-search").value : "").trim().toLowerCase();
    var shown = !q
      ? items
      : items.filter(function (it) {
          return it.url.toLowerCase().indexOf(q) !== -1;
        });

    if ($("ll-count")) $("ll-count").textContent = items.length;
    if ($("ll-stats")) $("ll-stats").textContent = statsText();

    if (!items.length) {
      listEl.innerHTML =
        '<div class="p-8 text-center text-zinc-500 text-sm font-medium">هنوز لینکی استخراج نشده است.</div>';
      return;
    }
    if (!shown.length) {
      listEl.innerHTML =
        '<div class="p-8 text-center text-zinc-500 text-sm font-medium">هیچ لینکی با این فیلتر پیدا نشد.</div>';
      return;
    }

    var order = Object.create(null);
    items.forEach(function (it, i) {
      order[it.id] = i + 1;
    });

    var html = "";
    shown.forEach(function (it) {
      var n = order[it.id];
      var badge = it.guessed
        ? '<span class="text-[9px] text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5 shrink-0">بدون پروتکل</span>'
        : "";
      html += `
                    <div class="flex justify-between items-center bg-white/[0.02] hover:bg-white/5 border border-transparent hover:border-brand-border rounded-md px-4 py-2.5 transition-colors group">
                        <div class="flex items-center gap-3 flex-1 overflow-hidden min-w-0" dir="ltr">
                            <span class="text-zinc-600 font-mono text-[10px] w-6 text-right shrink-0">${n}</span>
                            <span class="text-zinc-200 font-mono text-[13px] truncate text-left w-full" title="${escSafe(it.url)}">${escSafe(it.url)}</span>
                        </div>
                        <div class="flex items-center gap-1 shrink-0 mr-3">
                            ${badge}
                            <button onclick="llCopyOne(${it.id})" class="btn-subtle p-1.5 rounded text-zinc-400 hover:text-white" title="کپی همین لینک"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg></button>
                            <button onclick="llCopyDomain(${it.id})" class="btn-subtle p-1.5 rounded text-zinc-500 hover:text-white" title="کپی فقط دامنه"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 9a15.3 15.3 0 010-18m0 18a15.3 15.3 0 000-18M3.6 9h16.8M3.6 15h16.8"></path></svg></button>
                            <button onclick="llOpenOne(${it.id})" class="btn-subtle p-1.5 rounded text-zinc-400 hover:text-white" title="باز کردن این لینک در تب جدید"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg></button>
                            <div class="w-[1px] h-4 bg-zinc-800 mx-1"></div>
                            <button onclick="llRemove(${it.id})" class="btn-subtle p-1.5 rounded text-zinc-500 hover:text-red-500" title="حذف از لیست"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg></button>
                        </div>
                    </div>`;
    });
    listEl.innerHTML = html;
  }

  /* ------------------------------------------------------------- اکشن‌های تکی */
  function copyOne(id) {
    var it = findById(id);
    if (it) copyText(it.url, "لینک کپی شد.");
  }

  function copyDomain(id) {
    var it = findById(id);
    if (!it) return;
    var d = it.url;
    try {
      d = new URL(it.url).hostname.replace(/^www\./, "");
    } catch (e) {
      d = it.url
        .replace(/^(https?:\/\/)?(www\.)?/i, "")
        .split("/")[0];
    }
    copyText(d, "دامنه کپی شد: " + d);
  }

  function openOne(id) {
    var it = findById(id);
    if (it) window.open(it.url, "_blank");
  }

  function removeOne(id) {
    var n = Number(id);
    state.items = state.items.filter(function (it) {
      return it.id !== n;
    });
    save();
    render();
  }

  /* ------------------------------------------------------------ اکشن‌های گروهی */
  function urls() {
    return state.items.map(function (it) {
      return it.url;
    });
  }

  function copyAll() {
    var list = urls();
    if (!list.length) {
      toast("لیست خالی است.", "err");
      return;
    }
    copyText(list.join("\n"), list.length + " لینک کپی شد.");
  }

  function openAll() {
    var list = urls();
    if (!list.length) {
      toast("لیست خالی است.", "err");
      return;
    }
    var msg = "همه " + list.length + " لینک پشت سر هم در تب‌های جدید باز شوند؟\n(پاپ‌آپ بلاکر مرورگر باید خاموش باشد)";
    if (list.length > BIG_LIST) {
      msg += "\n\nتعداد لینک‌ها زیاد است؛ اگر مرورگر جلوی تب‌ها را گرفت، برای همین سایت پاپ‌آپ را اجازه بدهید.";
    }
    if (!confirm(msg)) return;
    var step = list.length > BIG_LIST ? 250 : 120;
    list.forEach(function (u, i) {
      setTimeout(function () {
        try {
          window.open(u, "_blank");
        } catch (e) {}
      }, i * step);
    });
    toast("در حال باز کردن " + list.length + " لینک ...");
  }

  function clearList() {
    if (!state.items.length) return;
    if (!confirm("کل لیست استخراج‌شده حذف شود؟")) return;
    state.items = [];
    state.stats = null;
    save();
    render();
    toast("لیست پاک شد.");
  }

  function downloadTxt() {
    var list = urls();
    if (!list.length) {
      toast("لیست خالی است.", "err");
      return;
    }
    try {
      var d = new Date();
      var p = function (n) {
        return String(n).padStart(2, "0");
      };
      var name =
        "links_" +
        d.getFullYear() +
        p(d.getMonth() + 1) +
        p(d.getDate()) +
        "_" +
        p(d.getHours()) +
        p(d.getMinutes()) +
        ".txt";
      var blob = new Blob([list.join("\n") + "\n"], { type: "text/plain;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () {
        URL.revokeObjectURL(a.href);
      }, 4000);
      toast("فایل " + name + " ساخته شد.");
    } catch (e) {
      toast("ساخت فایل ممکن نشد.", "err");
    }
  }

  // افزودن لینک‌ها به همان فایل لیست دامنه‌ها (urls.txt)
  async function sendToSettings() {
    var list = urls();
    if (!list.length) {
      toast("لیست خالی است.", "err");
      return;
    }
    if (!confirm(list.length + " لینک به فایل لیست دامنه‌ها (urls.txt) اضافه شود؟\nلینک‌های تکراری اضافه نمی‌شوند.")) return;
    try {
      var current = [];
      try {
        var r = await fetch("/api/urls/raw");
        if (r.ok) current = await r.json();
      } catch (e) {}
      if (!Array.isArray(current)) current = [];

      var seen = Object.create(null);
      var merged = [];
      current.forEach(function (u) {
        var k = keyOf(u);
        if (!seen[k]) {
          seen[k] = 1;
          merged.push(u);
        }
      });
      var added = 0;
      list.forEach(function (u) {
        var k = keyOf(u);
        if (!seen[k]) {
          seen[k] = 1;
          merged.push(u);
          added++;
        }
      });

      if (!added) {
        toast("همه این لینک‌ها از قبل در لیست دامنه‌ها بودند.");
        return;
      }
      var res = await fetch("/api/urls/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: merged }),
      });
      if (!res.ok) throw new Error();
      toast(added + " لینک به لیست دامنه‌ها اضافه شد.");
      if (typeof loadSettingsUrls === "function") loadSettingsUrls();
      if (typeof loadDashboard === "function") loadDashboard();
    } catch (e) {
      toast("ذخیره در فایل لیست دامنه‌ها انجام نشد.", "err");
    }
  }

  /* ------------------------------------------------------------------ راه‌اندازی */
  function init() {
    load();
    var ta = $("ll-input");
    if (ta) {
      // کشیدن و رها کردن فایل متنی روی کادر
      ["dragenter", "dragover"].forEach(function (ev) {
        ta.addEventListener(ev, function (e) {
          e.preventDefault();
          ta.classList.add("drag-over");
        });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        ta.addEventListener(ev, function (e) {
          e.preventDefault();
          ta.classList.remove("drag-over");
        });
      });
      ta.addEventListener("drop", function (e) {
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (!f) return;
        var fr = new FileReader();
        fr.onload = function () {
          ta.value = String(fr.result || "");
          extract();
        };
        fr.readAsText(f, "utf-8");
      });
    }
    render();
  }

  // در دسترس گذاشتن برای onclick های داخل HTML
  window.llExtract = extract;
  window.llPasteAndExtract = pasteAndExtract;
  window.llInputKey = inputKey;
  window.llClearInput = clearInput;
  window.llHandleFile = handleFile;
  window.llRender = render;
  window.llCopyOne = copyOne;
  window.llCopyDomain = copyDomain;
  window.llOpenOne = openOne;
  window.llRemove = removeOne;
  window.llCopyAll = copyAll;
  window.llOpenAll = openAll;
  window.llClearList = clearList;
  window.llDownload = downloadTxt;
  window.llSendToSettings = sendToSettings;
  window.llToast = toast;

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
