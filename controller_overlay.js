(function () {
  "use strict";

  const TEXT = {
    en: {
      launcher: "Controls",
      title: "Bindings & Personalization",
      subtitle: "Editable settings that persist across restarts.",
      bindings: "Current Bindings",
      settings: "Personalized Config",
      controller: "Controller",
      move_cursor: "Move Cursor",
      fine_adjust: "Fine Adjust",
      dictation: "Dictation",
      enter: "Enter",
      sensitivity_up: "Sensitivity Up",
      sensitivity_down: "Sensitivity Down",
      backspace: "Backspace",
      speech_profile: "Speech Profile",
      ui_language: "Default Language",
      ui_theme: "Default Theme",
      sensitivity_stages: "Sensitivity Stages",
      sensitivity_stage: "Current Stage",
      deadzone: "Deadzone",
      trigger_threshold: "Trigger Threshold",
      accel_power: "Acceleration Power",
      tick_rate: "Tick Rate",
      fine_move_pixels: "Fine Move Pixels",
      scroll_amount: "Scroll Amount",
      dictation_min_seconds: "Dictation Min Seconds",
      lt_axis_candidates: "LT Binding",
      rt_axis_candidates: "RT Binding",
      close: "Close",
      save: "Save",
      saving: "Saving...",
      saved: "Saved",
      failed: "Save failed",
      unavailable: "Unavailable",
      language_en: "English",
      language_zh: "Chinese",
      theme_light: "Light",
      theme_dark: "Dark",
      stage_hint: "Example: 30, 45, 60, 80, 105",
      shortcut_dictation: "Hold to Dictate",
      shortcut_enter: "Enter Key",
      shortcut_sensitivity_up: "Sensitivity Up",
      shortcut_sensitivity_down: "Sensitivity Down",
      shortcut_backspace: "Backspace",
    },
    zh: {
      launcher: "控制",
      title: "按键映射与个性化",
      subtitle: "这些设置会写入配置文件，重启后继续生效。",
      bindings: "当前映射",
      settings: "个性化配置",
      controller: "控制器",
      move_cursor: "移动光标",
      fine_adjust: "精细调整",
      dictation: "语音听写",
      enter: "回车",
      sensitivity_up: "提高灵敏度",
      sensitivity_down: "降低灵敏度",
      backspace: "退格",
      speech_profile: "语音模式",
      ui_language: "默认语言",
      ui_theme: "默认主题",
      sensitivity_stages: "灵敏度档位",
      sensitivity_stage: "当前档位",
      deadzone: "死区",
      trigger_threshold: "扳机阈值",
      accel_power: "加速度曲线",
      tick_rate: "轮询频率",
      fine_move_pixels: "微调像素",
      scroll_amount: "滚动步进",
      dictation_min_seconds: "听写最短时长",
      lt_axis_candidates: "LT 绑定",
      rt_axis_candidates: "RT 绑定",
      close: "关闭",
      save: "保存",
      saving: "保存中...",
      saved: "已保存",
      failed: "保存失败",
      unavailable: "不可用",
      language_en: "英文",
      language_zh: "中文",
      theme_light: "浅色",
      theme_dark: "深色",
      stage_hint: "例如: 30, 45, 60, 80, 105",
      shortcut_dictation: "按住听写",
      shortcut_enter: "回车键",
      shortcut_sensitivity_up: "提高灵敏度",
      shortcut_sensitivity_down: "降低灵敏度",
      shortcut_backspace: "退格",
    },
  };

  let overlayElements = null;
  let lastBindingsPayload = null;
  const EDITABLE_BINDING_ORDER = ["dictation", "enter", "sensitivity_up", "sensitivity_down", "backspace"];
  const SHORTCUT_DISPLAY_ORDER = ["sensitivity_up", "sensitivity_down", "dictation", "enter", "backspace"];

  function pageLang() {
    const path = (window.location.pathname || "").toLowerCase();
    if (path.includes("/ui/en")) return "en";
    const docLang = (document.documentElement.getAttribute("lang") || "").toLowerCase();
    return docLang.startsWith("en") ? "en" : "zh";
  }

  function t(key) {
    const lang = pageLang();
    return (TEXT[lang] && TEXT[lang][key]) || TEXT.en[key] || key;
  }

  function routeFor(lang, theme) {
    if (lang === "en") {
      return theme === "dark" ? "/ui/en-dark" : "/ui/en";
    }
    return theme === "dark" ? "/ui/zh-dark" : "/ui/zh";
  }

  function createField(id, type, textKey, extraAttrs) {
    const attrs = extraAttrs ? ` ${extraAttrs}` : "";
    return `
      <label class="block">
        <span class="block text-[11px] font-semibold text-on-surface-variant mb-1" data-overlay-text="${textKey}"></span>
        <input id="${id}" type="${type}"${attrs} class="w-full rounded-xl border border-outline-variant/40 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface">
      </label>
    `;
  }

  function createSelect(id, textKey) {
    return `
      <label class="block">
        <span class="block text-[11px] font-semibold text-on-surface-variant mb-1" data-overlay-text="${textKey}"></span>
        <select id="${id}" class="w-full rounded-xl border border-outline-variant/40 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface"></select>
      </label>
    `;
  }

  function createOverlay() {
    if (overlayElements) return overlayElements;

    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.className = "fixed right-6 bottom-6 z-[70] px-4 py-3 rounded-2xl bg-surface-container-lowest border border-outline-variant/50 shadow-xl text-xs font-bold text-on-surface hover:border-secondary transition-all";

    const panel = document.createElement("aside");
    panel.className = "fixed right-6 top-24 z-[75] hidden w-[430px] max-w-[calc(100vw-2rem)] rounded-[28px] border border-outline-variant/40 bg-surface-container-lowest shadow-2xl overflow-hidden";
    panel.innerHTML = `
      <div class="p-5 border-b border-outline-variant/30">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-base font-bold text-on-surface" data-overlay-text="title"></h3>
            <p class="mt-1 text-[11px] text-on-surface-variant" data-overlay-text="subtitle"></p>
          </div>
          <button type="button" data-overlay-close class="px-3 py-2 rounded-xl bg-surface-container border border-outline-variant/30 text-[11px] font-bold text-on-surface-variant hover:border-secondary transition-all"></button>
        </div>
      </div>
      <div class="max-h-[72vh] overflow-y-auto p-5 space-y-5">
        <section class="rounded-2xl border border-outline-variant/30 bg-surface-container p-4">
          <div class="flex items-center justify-between gap-3 mb-3">
            <h4 class="text-sm font-bold text-on-surface" data-overlay-text="bindings"></h4>
            <span class="text-[10px] text-on-surface-variant font-semibold" id="binding-controller-name">-</span>
          </div>
          <div id="binding-list" class="space-y-2 text-[11px] text-on-surface-variant"></div>
        </section>
        <section class="rounded-2xl border border-outline-variant/30 bg-surface-container p-4">
          <h4 class="text-sm font-bold text-on-surface mb-3" data-overlay-text="settings"></h4>
          <div class="space-y-3">
            ${createSelect("overlay-speech-profile", "speech_profile")}
            <div class="grid grid-cols-2 gap-3">
              ${createSelect("overlay-ui-language", "ui_language")}
              ${createSelect("overlay-ui-theme", "ui_theme")}
            </div>
            ${createField("overlay-sensitivity-stages", "text", "sensitivity_stages", `placeholder="${t("stage_hint")}"`)}
            ${createSelect("overlay-stage-index", "sensitivity_stage")}
            <div class="grid grid-cols-2 gap-3">
              ${createField("overlay-deadzone", "number", "deadzone", 'min="0" max="0.5" step="0.01"')}
              ${createField("overlay-trigger-threshold", "number", "trigger_threshold", 'min="0.1" max="0.99" step="0.01"')}
            </div>
            <div class="grid grid-cols-2 gap-3">
              ${createField("overlay-accel-power", "number", "accel_power", 'min="0.5" max="3.0" step="0.05"')}
              ${createField("overlay-tick-rate", "number", "tick_rate", 'min="30" max="1000" step="10"')}
            </div>
            <div class="grid grid-cols-2 gap-3">
              ${createField("overlay-fine-move", "number", "fine_move_pixels", 'min="1" max="20" step="1"')}
              ${createField("overlay-scroll-amount", "number", "scroll_amount", 'min="1" max="120" step="1"')}
            </div>
            ${createField("overlay-dictation-min-seconds", "number", "dictation_min_seconds", 'min="0.1" max="10" step="0.05"')}
            ${createField("overlay-lt-candidates", "text", "lt_axis_candidates", 'placeholder="4:+"')}
            ${createField("overlay-rt-candidates", "text", "rt_axis_candidates", 'placeholder="5:+"')}
          </div>
        </section>
      </div>
      <div class="p-5 border-t border-outline-variant/30 flex items-center justify-between gap-3">
        <div id="overlay-save-status" class="text-[11px] text-on-surface-variant"></div>
        <button type="button" data-overlay-save class="px-4 py-2 rounded-xl bg-secondary text-on-secondary text-sm font-bold shadow-sm hover:opacity-90 transition-opacity"></button>
      </div>
    `;

    document.body.appendChild(launcher);
    document.body.appendChild(panel);

    overlayElements = {
      launcher,
      panel,
      bindingList: panel.querySelector("#binding-list"),
      controllerName: panel.querySelector("#binding-controller-name"),
      speechProfile: panel.querySelector("#overlay-speech-profile"),
      uiLanguage: panel.querySelector("#overlay-ui-language"),
      uiTheme: panel.querySelector("#overlay-ui-theme"),
      sensitivityStages: panel.querySelector("#overlay-sensitivity-stages"),
      stageIndex: panel.querySelector("#overlay-stage-index"),
      deadzone: panel.querySelector("#overlay-deadzone"),
      triggerThreshold: panel.querySelector("#overlay-trigger-threshold"),
      accelPower: panel.querySelector("#overlay-accel-power"),
      tickRate: panel.querySelector("#overlay-tick-rate"),
      fineMove: panel.querySelector("#overlay-fine-move"),
      scrollAmount: panel.querySelector("#overlay-scroll-amount"),
      dictationMinSeconds: panel.querySelector("#overlay-dictation-min-seconds"),
      ltCandidates: panel.querySelector("#overlay-lt-candidates"),
      rtCandidates: panel.querySelector("#overlay-rt-candidates"),
      saveStatus: panel.querySelector("#overlay-save-status"),
      saveButton: panel.querySelector("[data-overlay-save]"),
      closeButton: panel.querySelector("[data-overlay-close]"),
    };

    launcher.addEventListener("click", async function () {
      applyOverlayText();
      panel.classList.toggle("hidden");
      if (!panel.classList.contains("hidden")) {
        await refreshBindingsOverlay();
      }
    });

    overlayElements.closeButton.addEventListener("click", function () {
      panel.classList.add("hidden");
    });
    overlayElements.saveButton.addEventListener("click", saveBindingsOverlay);
    applyOverlayText();
    return overlayElements;
  }

  function applyOverlayText() {
    const overlay = createOverlay();
    overlay.launcher.textContent = t("launcher");
    overlay.closeButton.textContent = t("close");
    overlay.saveButton.textContent = t("save");
    document.querySelectorAll("[data-overlay-text]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-overlay-text"));
    });
  }

  function editableBindingMarkup(bindings, bindingValues, bindingOptions) {
    return EDITABLE_BINDING_ORDER.map(function (key) {
      const options = (bindingOptions && bindingOptions[key]) || [];
      const currentValue = (bindingValues && bindingValues[key]) || "";
      const optionsMarkup = options.map(function (option) {
        const selected = option.value === currentValue ? " selected" : "";
        return `<option value="${option.value}"${selected}>${option.label}</option>`;
      }).join("");
      return `
        <div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] items-center gap-3 rounded-xl bg-surface-container-low px-3 py-2">
          <span class="font-semibold text-on-surface">${t(key)}</span>
          <select
            data-binding-key="${key}"
            class="w-full rounded-lg border border-outline-variant/35 bg-surface-container-lowest px-2.5 py-1.5 text-[11px] font-mono text-on-surface-variant"
          >${optionsMarkup}</select>
        </div>
      `;
    }).join("");
  }

  function bindingMarkup(bindings, bindingValues, bindingOptions) {
    return editableBindingMarkup(bindings, bindingValues, bindingOptions);
  }

  function bindingLabelFor(key, bindings, bindingValues, bindingOptions) {
    if (bindings && bindings[key]) {
      return String(bindings[key]);
    }
    const currentValue = bindingValues && bindingValues[key];
    const options = (bindingOptions && bindingOptions[key]) || [];
    const match = options.find(function (option) {
      return option.value === currentValue;
    });
    return match ? String(match.label) : String(currentValue || "");
  }

  function shortcutActionText(key) {
    return t(`shortcut_${key}`);
  }

  function shortcutBindingMarkup(label) {
    const tokens = String(label || "").split("+").map(function (part) {
      return part.trim();
    }).filter(Boolean);
    const content = tokens.map(function (token) {
      return `<span class="px-1.5 py-0.5 bg-white border border-outline-variant rounded-md text-[9px] font-bold text-on-surface-variant min-w-7 text-center">${token}</span>`;
    }).join('<span class="text-outline font-bold text-base">+</span>');
    return `<div class="flex items-center space-x-2">${content}</div>`;
  }

  function shortcutCardMarkup(key, label) {
    return `
      <div class="flex items-center justify-between bg-surface-container-low border border-outline-variant/30 rounded-xl p-2.5 px-3.5">
        <div class="grid grid-cols-[100px_1fr] items-center w-full">
          ${shortcutBindingMarkup(label)}
          <div class="flex items-center">
            <div class="w-7 flex justify-center text-outline/50">
              <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M13 7l5 5m0 0l-5 5m5-5H6" stroke-linecap="round" stroke-linejoin="round"></path></svg>
            </div>
            <span class="text-on-surface text-xs font-semibold">${shortcutActionText(key)}</span>
          </div>
        </div>
      </div>
    `;
  }

  function syncShortcutDisplay(bindings, bindingValues, bindingOptions) {
    const section = document.querySelector('[data-purpose="shortcuts-column"] .space-y-2\\.5');
    if (!section) return;
    section.innerHTML = SHORTCUT_DISPLAY_ORDER.map(function (key) {
      return shortcutCardMarkup(key, bindingLabelFor(key, bindings, bindingValues, bindingOptions));
    }).join("");
  }

  function fillSimpleSelect(select, options, selectedValue) {
    select.innerHTML = "";
    options.forEach(function (option) {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      node.selected = option.value === selectedValue;
      select.appendChild(node);
    });
  }

  function fillSpeechProfiles(select, profiles, selectedValue) {
    select.innerHTML = "";
    const lang = pageLang();
    profiles.forEach(function (profile) {
      const node = document.createElement("option");
      node.value = profile.id;
      node.textContent = lang === "zh" ? (profile.label_zh || profile.label || profile.id) : (profile.label || profile.id);
      node.selected = profile.id === selectedValue;
      select.appendChild(node);
    });
  }

  function fillStageSelect(select, stages, currentStage) {
    select.innerHTML = "";
    stages.forEach(function (speed, index) {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = `${index + 1}/${stages.length} · ${speed}`;
      option.selected = index === currentStage;
      select.appendChild(option);
    });
  }

  function syncPageAfterSave(cfg) {
    const route = routeFor(cfg.ui_language || "zh", cfg.ui_theme || "light");
    if ((window.location.pathname || "").toLowerCase() !== route.toLowerCase()) {
      window.location.href = route;
      return;
    }
    if (typeof window.refreshSpeechMode === "function") {
      window.refreshSpeechMode();
    }
    document.dispatchEvent(new CustomEvent("controller:personalization-updated", { detail: cfg }));
  }

  async function refreshBindingsOverlay() {
    const overlay = createOverlay();
    overlay.saveStatus.textContent = "";
    try {
      const response = await fetch("/bindings", { cache: "no-store" });
      const data = await response.json();
      lastBindingsPayload = data;
      const bindings = data.bindings || {};
      const bindingValues = data.binding_values || {};
      const bindingOptions = data.binding_options || {};
      const cfg = data.config || {};
      const speechProfiles = data.speech_profiles || [];
      const stages = Array.isArray(cfg.sensitivity_stages) ? cfg.sensitivity_stages : [];

      overlay.bindingList.innerHTML = bindingMarkup(bindings, bindingValues, bindingOptions);
      syncShortcutDisplay(bindings, bindingValues, bindingOptions);
      overlay.controllerName.textContent = `${t("controller")}: ${data.controller || t("unavailable")}`;
      fillSpeechProfiles(overlay.speechProfile, speechProfiles, cfg.speech_profile || "");
      fillSimpleSelect(overlay.uiLanguage, [
        { value: "zh", label: t("language_zh") },
        { value: "en", label: t("language_en") },
      ], cfg.ui_language || "zh");
      fillSimpleSelect(overlay.uiTheme, [
        { value: "light", label: t("theme_light") },
        { value: "dark", label: t("theme_dark") },
      ], cfg.ui_theme || "light");
      overlay.sensitivityStages.value = stages.join(", ");
      fillStageSelect(overlay.stageIndex, stages, Number(cfg.stage_index || 0));
      overlay.deadzone.value = cfg.deadzone ?? 0.1;
      overlay.triggerThreshold.value = cfg.trigger_threshold ?? 0.65;
      overlay.accelPower.value = cfg.accel_power ?? 1.35;
      overlay.tickRate.value = cfg.tick_rate ?? 240;
      overlay.fineMove.value = cfg.fine_move_pixels ?? 2;
      overlay.scrollAmount.value = cfg.scroll_amount ?? 12;
      overlay.dictationMinSeconds.value = cfg.dictation_min_seconds ?? 0.45;
      overlay.ltCandidates.value = (cfg.lt_axis_candidates || []).join(", ");
      overlay.rtCandidates.value = (cfg.rt_axis_candidates || []).join(", ");
    } catch (_error) {
      overlay.bindingList.innerHTML = `<div class="text-[11px] text-error">${t("unavailable")}</div>`;
      overlay.controllerName.textContent = `${t("controller")}: ${t("unavailable")}`;
    }
  }

  async function saveBindingsOverlay() {
    const overlay = createOverlay();
    overlay.saveButton.disabled = true;
    overlay.saveStatus.textContent = t("saving");
    try {
      const payload = {
        speech_profile: overlay.speechProfile.value,
        ui_language: overlay.uiLanguage.value,
        ui_theme: overlay.uiTheme.value,
        sensitivity_stages: overlay.sensitivityStages.value,
        stage_index: Number(overlay.stageIndex.value),
        deadzone: Number(overlay.deadzone.value),
        trigger_threshold: Number(overlay.triggerThreshold.value),
        accel_power: Number(overlay.accelPower.value),
        tick_rate: Number(overlay.tickRate.value),
        fine_move_pixels: Number(overlay.fineMove.value),
        scroll_amount: Number(overlay.scrollAmount.value),
        dictation_min_seconds: Number(overlay.dictationMinSeconds.value),
        lt_axis_candidates: overlay.ltCandidates.value,
        rt_axis_candidates: overlay.rtCandidates.value,
        control_bindings: Object.fromEntries(
          Array.from(overlay.bindingList.querySelectorAll("[data-binding-key]")).map(function (input) {
            return [input.getAttribute("data-binding-key"), String(input.value || "").trim()];
          })
        ),
      };
      const response = await fetch("/bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      lastBindingsPayload = data;
      await refreshBindingsOverlay();
      overlay.saveStatus.textContent = t("saved");
      syncPageAfterSave(data.config || {});
    } catch (_error) {
      overlay.saveStatus.textContent = t("failed");
    } finally {
      overlay.saveButton.disabled = false;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      createOverlay();
      refreshBindingsOverlay();
    });
  } else {
    createOverlay();
    refreshBindingsOverlay();
  }
})();
