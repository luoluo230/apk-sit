(function () {
  "use strict";

  function trim(text) {
    return String(text == null ? "" : text).trim();
  }

  function readOptions(textarea, options) {
    options = options || {};
    return {
      label: options.label || textarea.getAttribute("data-json-label") || "JSON",
      empty: options.empty || textarea.getAttribute("data-json-empty") || "object",
      expect: options.expect || textarea.getAttribute("data-json-type") || options.empty || textarea.getAttribute("data-json-empty") || "object",
    };
  }

  function parseJsonText(raw, emptyKind) {
    var text = trim(raw);
    if (!text) {
      if (emptyKind === "array") return [];
      if (emptyKind === "optional") return null;
      return {};
    }
    return JSON.parse(text);
  }

  function validateType(value, expect) {
    if (expect === "any" || expect === "optional") return "";
    if (expect === "object") {
      if (value === null || typeof value !== "object" || Array.isArray(value)) return "须为 JSON 对象 {}";
    }
    if (expect === "array") {
      if (!Array.isArray(value)) return "须为 JSON 数组 []";
    }
    return "";
  }

  function ensureWrap(textarea) {
    var parent = textarea.parentNode;
    if (parent && parent.classList && parent.classList.contains("baas-json-field")) return parent;
    var wrap = document.createElement("div");
    wrap.className = "baas-json-field";
    if (parent) parent.insertBefore(wrap, textarea);
    wrap.appendChild(textarea);
    var hint = document.createElement("div");
    hint.className = "baas-json-field__hint is-hidden";
    hint.setAttribute("role", "alert");
    wrap.appendChild(hint);
    return wrap;
  }

  function setState(textarea, ok, message, showOkHint) {
    var wrap = ensureWrap(textarea);
    var hint = wrap.querySelector(".baas-json-field__hint");
    textarea.classList.toggle("is-json-invalid", !ok);
    textarea.classList.toggle("is-json-valid", ok && trim(textarea.value) !== "");
    textarea.dataset.jsonValid = ok ? "1" : "0";
    if (hint) {
      if (!ok) {
        hint.textContent = message || "JSON 格式无效";
        hint.classList.remove("is-hidden", "is-ok");
        hint.classList.add("is-error");
      } else if (showOkHint && trim(textarea.value)) {
        hint.textContent = "格式正确";
        hint.classList.remove("is-hidden", "is-error");
        hint.classList.add("is-ok");
      } else {
        hint.textContent = "";
        hint.classList.add("is-hidden");
        hint.classList.remove("is-error", "is-ok");
      }
    }
  }

  function validate(textarea, options) {
    options = readOptions(textarea, options);
    if (textarea.disabled) {
      setState(textarea, true, "", false);
      return { ok: true, value: null, error: "" };
    }
    try {
      var value = parseJsonText(textarea.value, options.empty);
      if (value !== null) {
        var typeErr = validateType(value, options.expect === "optional" ? "any" : options.expect);
        if (typeErr) {
          var typeMsg = options.label + "：" + typeErr;
          setState(textarea, false, typeMsg, false);
          return { ok: false, value: null, error: typeMsg };
        }
      }
      setState(textarea, true, "", true);
      return { ok: true, value: value, error: "" };
    } catch (err) {
      var msg = options.label + "：JSON 格式无效";
      if (err && err.message) msg += "（" + err.message + "）";
      setState(textarea, false, msg, false);
      return { ok: false, value: null, error: msg };
    }
  }

  function bind(textarea, options) {
    if (!textarea) return;
    textarea.classList.add("baas-json-input");
    if (textarea.dataset.jsonBound !== "1") {
      textarea.dataset.jsonBound = "1";
      var run = function () {
        var result = validate(textarea, options);
        if (options && options.onChange) options.onChange(result.ok, textarea, result);
        refreshGuardedButtons(textarea);
      };
      textarea.addEventListener("input", run);
      textarea.addEventListener("blur", run);
    }
    validate(textarea, options);
    refreshGuardedButtons(textarea);
  }

  function bindScope(root, selector, options) {
    var scope = root || document;
    scope.querySelectorAll(selector || "[data-json-field], [data-cfg-json]").forEach(function (el) {
      bind(el, options);
    });
  }

  function guardedButtonsFor(textarea) {
    var pane = textarea.closest("[data-pane]") || textarea.closest(".delivery-app") || document;
    return Array.prototype.slice.call(pane.querySelectorAll('[data-json-guard="1"]'));
  }

  function paneIsJsonValid(pane) {
    var fields = pane.querySelectorAll("[data-json-field], [data-cfg-json]");
    for (var i = 0; i < fields.length; i += 1) {
      if (fields[i].dataset.jsonValid === "0") return false;
    }
    return true;
  }

  function refreshGuardedButtons(textarea) {
    var seen = {};
    guardedButtonsFor(textarea).forEach(function (btn) {
      if (seen[btn.id || btn]) return;
      seen[btn.id || btn] = true;
      updateGuardedButton(btn);
    });
  }

  function updateGuardedButton(button) {
    if (!button || button.dataset.jsonGuard !== "1") return;
    if (button.dataset.jsonLocked === "1") return;
    var pane = button.closest("[data-pane]") || button.closest(".delivery-app") || document;
    button.disabled = !paneIsJsonValid(pane);
  }

  function guardSubmit(button) {
    if (!button) return;
    button.dataset.jsonGuard = "1";
    if (button.disabled && button.hasAttribute("disabled")) {
      button.dataset.jsonLocked = "1";
    }
    var pane = button.closest("[data-pane]") || button.closest(".delivery-app") || document;
    bindScope(pane);
    updateGuardedButton(button);
  }

  function parseField(textarea, options) {
    var result = validate(textarea, options);
    if (!result.ok) throw new Error(result.error || "JSON 格式无效");
    return result.value;
  }

  function requireScope(root, selector) {
    var scope = root || document;
    var firstError = "";
    scope.querySelectorAll(selector || "[data-json-field], [data-cfg-json]").forEach(function (el) {
      var result = validate(el);
      if (!result.ok && !firstError) firstError = result.error;
    });
    if (firstError) throw new Error(firstError);
  }

  window.BaasJsonField = {
    bind: bind,
    bindScope: bindScope,
    validate: validate,
    parse: parseField,
    requireScope: requireScope,
    guardSubmit: guardSubmit,
    refreshGuardedButtons: refreshGuardedButtons,
  };
})();
