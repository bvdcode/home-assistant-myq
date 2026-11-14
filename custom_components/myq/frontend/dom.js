/** Small DOM and Home Assistant helpers shared by the panel components. */

/** Create an element. Props named on* add listeners; text sets textContent; booleans toggle attributes. */
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") element.className = value;
    else if (key === "text") element.textContent = value;
    else if (key === "style" && typeof value === "object") {
      for (const [name, rule] of Object.entries(value)) {
        if (name.startsWith("--")) element.style.setProperty(name, rule);
        else element.style[name] = rule;
      }
    }
    else if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2), value);
    } else if (key === "dataset") Object.assign(element.dataset, value);
    else element.setAttribute(key, value === true ? "" : String(value));
  }
  append(element, children);
  return element;
}

function append(element, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function icon(name, className) {
  const element = document.createElement("ha-icon");
  element.setAttribute("icon", name);
  if (className) element.className = className;
  return element;
}

export function fire(node, type, detail = {}) {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

export function toast(node, message) {
  fire(node, "hass-notification", { message });
}

export function moreInfo(node, entityId) {
  if (entityId) fire(node, "hass-more-info", { entityId });
}

/**
 * Ask the Home Assistant apps to vibrate: "success", "warning", "failure", "light", "medium",
 * "heavy", or "selection". Browsers without the apps ignore it.
 */
export function haptic(type) {
  window.dispatchEvent(new CustomEvent("haptic", { detail: type, bubbles: true, composed: true }));
}

export function navigate(path) {
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

/** Localized state text, using Home Assistant's own formatter when available. */
export function formatState(hass, stateObj, value) {
  if (!stateObj) return value ?? "";
  try {
    if (typeof hass.formatEntityState === "function") return hass.formatEntityState(stateObj, value);
  } catch {
    // Fall back to the raw state below.
  }
  return value ?? stateObj.state;
}

/** Readable MyQ activation sources; unknown values are shown as words. */
const ACTIVATION_SOURCES = { myq_app: "MyQ app" };

export function activationSource(value) {
  if (!value || value === "unknown" || value === "unavailable") return "";
  const text = ACTIVATION_SOURCES[value] ?? value.replaceAll("_", " ");
  return text.charAt(0).toLocaleUpperCase() + text.slice(1);
}

/** Entity name without the device name prefix that Home Assistant adds to friendly names. */
export function entityLabel(stateObj, deviceName) {
  const name = stateObj?.attributes?.friendly_name ?? "";
  if (deviceName && name.toLowerCase().startsWith(`${deviceName.toLowerCase()} `)) {
    const label = name.slice(deviceName.length + 1);
    return label.charAt(0).toLocaleUpperCase() + label.slice(1);
  }
  return name;
}

export function relativeTime(value, locale) {
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return "";
  const seconds = (time - Date.now()) / 1000;
  const abs = Math.abs(seconds);
  let formatter;
  try {
    formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  } catch {
    formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  }
  if (abs < 45) return formatter.format(0, "second");
  if (abs < 45 * 60) return formatter.format(Math.round(seconds / 60), "minute");
  if (abs < 22 * 3600) return formatter.format(Math.round(seconds / 3600), "hour");
  if (abs < 6 * 86400) return formatter.format(Math.round(seconds / 86400), "day");
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(time);
}

function unitFormatter(locale, unit) {
  try {
    return new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "short" });
  } catch {
    return new Intl.NumberFormat("en", { style: "unit", unit, unitDisplay: "short" });
  }
}

/** A short, localized length of time such as "25 min", "2 hr 5 min", or "3 days 4 hr". */
export function formatDuration(milliseconds, locale) {
  const minutes = Math.max(0, Math.floor(milliseconds / 60000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const rest = minutes % 60;
  const parts = [];
  if (days) parts.push(unitFormatter(locale, "day").format(days));
  if (hours) parts.push(unitFormatter(locale, "hour").format(hours));
  if (!days && (rest || !hours)) parts.push(unitFormatter(locale, "minute").format(rest));
  try {
    return new Intl.ListFormat(locale, { style: "narrow", type: "unit" }).format(parts);
  } catch {
    return parts.join(" ");
  }
}

/** When something happened: the time today, the weekday this week, or the date before that. */
export function formatEventTime(time, locale, timeFormat) {
  const date = new Date(time);
  const now = new Date();
  const clock = { hour: "numeric", minute: "2-digit" };
  if (timeFormat === "12") clock.hour12 = true;
  else if (timeFormat === "24") clock.hour12 = false;
  let options = clock;
  if (date.toDateString() !== now.toDateString()) {
    options = now - date < 6 * 86400000 ? { weekday: "short", ...clock } : { month: "short", day: "numeric", ...clock };
  }
  try {
    return new Intl.DateTimeFormat(locale, options).format(date);
  } catch {
    return new Intl.DateTimeFormat("en", options).format(date);
  }
}

export function supportsFeature(stateObj, feature) {
  return ((stateObj?.attributes?.supported_features ?? 0) & feature) !== 0;
}

export function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** Read a per-browser preference, tolerating storage that is blocked or unavailable. */
export function readPreference(key, fallback) {
  try {
    const value = window.localStorage.getItem(`myq-panel:${key}`);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function writePreference(key, value) {
  try {
    window.localStorage.setItem(`myq-panel:${key}`, JSON.stringify(value));
  } catch {
    // Preferences are a convenience; ignore storage that is unavailable.
  }
}
