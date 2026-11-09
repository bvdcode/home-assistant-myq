/** Panel and dashboard card styles. Colors come from Home Assistant theme variables so custom themes apply. */

/** Home Assistant theme values shared by the panel and the dashboard card. */
const theme = `
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, "Noto Sans", system-ui, sans-serif);
  -webkit-font-smoothing: antialiased;
  --myq-radius: var(--ha-card-border-radius, 12px);
  --myq-card: var(--ha-card-background, var(--card-background-color, #fff));
  --myq-border: var(--ha-card-border-color, var(--divider-color, rgba(0, 0, 0, 0.12)));
  --myq-muted: var(--secondary-text-color, #6f6f6f);
  --myq-primary: var(--primary-color, #03a9f4);
  --myq-on-primary: var(--text-primary-color, #fff);
  --myq-closed: var(--success-color, #43a047);
  --myq-open: var(--warning-color, #ffa600);
  --myq-moving: var(--info-color, #039be5);
  --myq-error: var(--error-color, #db4437);
  --myq-neutral: #9aa0a6;
  --myq-tint: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
  /* Plain backdrop behind a door's trim, in the card's own tone. */
  --myq-backdrop: linear-gradient(
    color-mix(in srgb, var(--primary-text-color) 4%, var(--myq-card)),
    color-mix(in srgb, var(--primary-text-color) 9%, var(--myq-card))
  );
  --myq-alert-text: color-mix(in srgb, var(--myq-open) 62%, var(--primary-text-color));
`;

/** Components shared by the panel and the dashboard card. */
const components = `
[hidden] { display: none !important; }
*, *::before, *::after { box-sizing: border-box; }
button { font: inherit; color: inherit; -webkit-tap-highlight-color: transparent; }
button:focus-visible, input:focus-visible, label:focus-within:has(input[type="color"]:focus-visible) {
  outline: 2px solid var(--myq-primary);
  outline-offset: 2px;
}
.spacer { flex: 1 1 auto; }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip-path: inset(50%); white-space: nowrap;
}

/* Toolbar */
.toolbar {
  position: sticky; top: 0; z-index: 5; flex: none;
  display: flex; align-items: center; gap: 4px;
  height: var(--header-height, 56px);
  padding: 0 8px 0 max(12px, env(safe-area-inset-left));
  background: var(--app-header-background-color, var(--primary-background-color));
  color: var(--app-header-text-color, var(--primary-text-color));
  border-bottom: var(--app-header-border-bottom, 1px solid var(--divider-color, transparent));
}
.toolbar .title {
  margin-inline-start: 12px; font-size: 20px; font-weight: 400;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.toolbar .menu + .title { margin-inline-start: 4px; }
.icon-button {
  width: 48px; height: 48px; flex: none; border: 0; border-radius: 50%;
  display: inline-grid; place-items: center; background: none; cursor: pointer;
  color: inherit; --mdc-icon-size: 24px;
}
.icon-button.small { width: 36px; height: 36px; --mdc-icon-size: 20px; }
.icon-button:hover:not(:disabled) { background: var(--myq-tint); }
.icon-button:disabled { opacity: 0.35; cursor: default; }

/* Layout */
.scroller { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior-y: contain; }
.content { max-width: 1500px; margin: 0 auto; padding: 24px 24px 48px; }
@media (max-width: 600px) { .content { padding: 16px 12px 40px; } }

.summary { display: flex; align-items: center; gap: 16px; margin: 0 4px 24px; flex-wrap: wrap; }
.summary-icon {
  width: 48px; height: 48px; flex: none; border-radius: 50%;
  display: grid; place-items: center; --mdc-icon-size: 26px;
  color: var(--tone); background: color-mix(in srgb, var(--tone) 15%, transparent);
}
.summary-text { flex: 1 1 220px; min-width: 0; }
.summary-title { font-size: 22px; font-weight: 500; line-height: 1.25; letter-spacing: -0.005em; }
.summary-sub { margin-top: 2px; font-size: 14px; color: var(--myq-muted); }
.summary[data-tone="closed"] { --tone: var(--myq-closed); }
.summary[data-tone="open"], .summary[data-tone="left_open"] { --tone: var(--myq-open); }
.summary-sub.alert { color: var(--myq-alert-text); font-weight: 500; }
.summary[data-tone="moving"] { --tone: var(--myq-moving); }
.summary[data-tone="unavailable"] { --tone: var(--myq-neutral); }

.banner {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin: 0 0 16px; padding: 12px 16px; border-radius: var(--myq-radius);
  background: color-mix(in srgb, var(--tone) 12%, var(--myq-card));
  border: 1px solid color-mix(in srgb, var(--tone) 35%, transparent);
  --mdc-icon-size: 22px;
}
.banner > ha-icon { color: var(--tone); flex: none; }
.banner-text { flex: 1 1 240px; min-width: 0; font-size: 14px; line-height: 1.4; }
.banner-text strong { font-weight: 500; margin-inline-end: 6px; }
.banner[data-tone="info"] { --tone: var(--myq-moving); }
.banner[data-tone="warning"] { --tone: var(--myq-open); }
.banner[data-tone="error"] { --tone: var(--myq-error); }

/* Buttons */
.filled-button, .text-button, .tonal-button {
  height: 40px; padding: 0 20px; border: 0; border-radius: 20px;
  font-size: 14px; font-weight: 500; letter-spacing: 0.01em; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  white-space: nowrap; --mdc-icon-size: 18px; transition: background 0.15s, color 0.15s;
}
.filled-button { background: var(--myq-primary); color: var(--myq-on-primary); }
.filled-button:hover:not(:disabled) { background: color-mix(in srgb, var(--myq-primary) 88%, #000); }
.filled-button:disabled { opacity: 0.6; cursor: default; }
.text-button { background: none; color: var(--myq-primary); padding: 0 14px; }
.text-button:hover { background: color-mix(in srgb, var(--myq-primary) 10%, transparent); }
.text-button.inline { height: 32px; padding: 0 10px; margin-inline-start: -10px; }
.tonal-button { background: color-mix(in srgb, var(--tone, var(--myq-primary)) 14%, transparent); color: var(--tone, var(--myq-primary)); }
.tonal-button:hover { background: color-mix(in srgb, var(--tone, var(--myq-primary)) 22%, transparent); }
.tonal-button.confirming { background: var(--myq-open); color: #241700; }

/* Door grid */
.doors { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 20px; justify-content: center; }
.door-card {
  flex: 1.236 1 330px; max-width: 540px; min-width: 0;
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--myq-card);
  border: var(--ha-card-border-width, 1px) solid var(--myq-border);
  border-radius: var(--myq-radius);
  box-shadow: var(--ha-card-box-shadow, none);
}
.door-card[data-width="double"] { flex: 2 1 534px; max-width: 874px; }
@media (max-width: 760px) {
  .door-card, .door-card[data-width="double"] { flex-basis: 100%; max-width: 100%; }
}

.media { position: relative; overflow: hidden; background: #26282b; isolation: isolate; }
/* The scene stays in flow and sizes the media; door cards add room above it for the controls. */
.media > .camera { position: absolute; inset: 0; }
.door-card .media { padding-top: 40px; }
.door-card .media, .empty .media, .preview-frame { background: var(--myq-backdrop); }
.media-top {
  position: absolute; z-index: 3; inset: 10px 10px auto 10px;
  display: flex; align-items: center; gap: 8px; pointer-events: none;
}
.media-top > * { pointer-events: auto; }
.camera-slot, .camera-controls { display: contents; }
.pill {
  display: inline-flex; align-items: center; gap: 8px; height: 30px; min-width: 0;
  padding: 0 13px 0 11px; border-radius: 15px;
  background: rgba(16, 17, 19, 0.6); color: #fff;
  font-size: 13px; font-weight: 500; letter-spacing: 0.01em; white-space: nowrap;
  backdrop-filter: blur(12px) saturate(1.3); -webkit-backdrop-filter: blur(12px) saturate(1.3);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}
.dot {
  width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--dot, var(--myq-neutral));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--dot, var(--myq-neutral)) 35%, transparent);
}
[data-state="closed"] > .dot { --dot: var(--myq-closed); }
[data-state="open"] > .dot { --dot: var(--myq-open); }
:is([data-state="opening"], [data-state="closing"]) > .dot { --dot: var(--myq-moving); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 2px color-mix(in srgb, var(--dot) 55%, transparent); }
  50% { box-shadow: 0 0 0 6px transparent; }
}
.glass-button {
  height: 36px; min-width: 36px; flex: none; padding: 0; border: 0; border-radius: 18px;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  background: rgba(16, 17, 19, 0.52); color: #fff; cursor: pointer;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  --mdc-icon-size: 20px; transition: background 0.15s, color 0.15s;
}
.glass-button:hover { background: rgba(16, 17, 19, 0.72); }
.glass-button.wide { padding: 0 14px 0 10px; font-size: 13px; font-weight: 500; }
.glass-button[aria-pressed="true"] { background: rgba(255, 255, 255, 0.94); color: #1b1c1e; }
.glass-button:disabled { opacity: 0.5; cursor: default; }

.offline {
  position: absolute; inset: 0; z-index: 2; display: grid; place-content: center; justify-items: center;
  gap: 6px; color: #fff; font-size: 14px; font-weight: 500; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  background: linear-gradient(rgba(20, 21, 24, 0.35), rgba(20, 21, 24, 0.55));
  --mdc-icon-size: 32px;
}
.door-card.unavailable .media > .scene { filter: grayscale(0.85) brightness(0.8); }
:host([dark]) .media > .scene { filter: brightness(0.93) saturate(0.95); }
:host([dark]) .door-card.unavailable .media > .scene { filter: grayscale(0.85) brightness(0.7); }

.body { display: flex; flex-direction: column; gap: 14px; padding: 16px 16px 10px; }
.heading { min-width: 0; }
.heading .name {
  margin: 0; font-size: 18px; font-weight: 500; line-height: 1.3;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.heading-row { display: flex; align-items: center; gap: 2px; min-width: 0; }
.heading-row .name { flex: 1 1 auto; min-width: 0; }
.heading-row .icon-button { margin: -6px -6px -6px 0; color: var(--myq-muted); }
.icon-button.busy ha-icon { animation: spin 0.9s linear infinite; }
/* Inline so a long line wraps between words rather than between parts. */
.heading .subtitle { margin-top: 2px; font-size: 13.5px; line-height: 1.4; color: var(--myq-muted); }
.subtitle .alert-icon { display: inline-block; vertical-align: -3px; margin-inline-end: 5px; --mdc-icon-size: 16px; }
.subtitle.alert { color: var(--myq-alert-text); font-weight: 500; }
.status { color: var(--primary-text-color); font-weight: 500; }
.status .dot {
  display: inline-block; vertical-align: 1px; margin-inline-end: 7px; width: 7px; height: 7px;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--dot, var(--myq-neutral)) 30%, transparent);
}
.status .separator { margin: 0 6px; color: var(--myq-muted); font-weight: 400; }
/* A door left open past the panel's limit gets an amber outline. */
.door-card.left-open {
  border-color: color-mix(in srgb, var(--myq-open) 80%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--myq-open) 80%, transparent), var(--ha-card-box-shadow, 0 0 0 transparent);
}

.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.action {
  position: relative; overflow: hidden; height: 48px; min-width: 0; padding: 0 14px;
  border: 0; border-radius: 24px;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 15px; font-weight: 500; letter-spacing: 0.01em; cursor: pointer;
  background: color-mix(in srgb, var(--myq-primary) 13%, transparent); color: var(--myq-primary);
  --mdc-icon-size: 20px; transition: background 0.2s, color 0.2s, box-shadow 0.2s, transform 0.08s;
}
.action:hover:not(:disabled) { background: color-mix(in srgb, var(--myq-primary) 20%, transparent); }
.action.primary { background: var(--myq-primary); color: var(--myq-on-primary); box-shadow: 0 2px 6px color-mix(in srgb, var(--myq-primary) 35%, transparent); }
.action.primary:hover:not(:disabled) { background: color-mix(in srgb, var(--myq-primary) 88%, #000); }
.action:active:not(:disabled) { transform: scale(0.98); }
.action:disabled {
  cursor: default; box-shadow: none;
  background: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
  color: color-mix(in srgb, var(--primary-text-color) 38%, transparent);
}
.action .label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action.confirming { background: var(--myq-open); color: #241700; box-shadow: 0 2px 8px color-mix(in srgb, var(--myq-open) 45%, transparent); }
/* Confirmation prompts are longer in many languages: drop the icon and allow two short lines. */
.action.confirming .action-icon { display: none; }
.action.confirming .label {
  white-space: normal; text-align: center; font-size: 13.5px; line-height: 1.15;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2;
}
.action .countdown {
  position: absolute; inset: auto 0 0 0; height: 3px; background: currentColor; opacity: 0.45;
  transform-origin: left center; transform: scaleX(0);
}
.action.confirming .countdown { animation: countdown 4s linear forwards; }
@keyframes countdown { from { transform: scaleX(1); } to { transform: scaleX(0); } }
.action .spinner {
  display: none; width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite;
}
.action.busy .spinner { display: block; }
.action.busy .action-icon { display: none; }
@keyframes spin { to { transform: rotate(360deg); } }

.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  height: 30px; padding: 0 12px 0 9px; border: 0; border-radius: 15px;
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  font-size: 13px; font-weight: 500; color: var(--primary-text-color);
  background: color-mix(in srgb, var(--tone) 14%, transparent); --mdc-icon-size: 17px;
}
.chip ha-icon { flex: none; color: var(--tone); }
.chip { max-width: 100%; white-space: nowrap; }
.chip span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.chip:hover { background: color-mix(in srgb, var(--tone) 22%, transparent); }
.chip.light { --tone: #e9a10f; }
.chip.vacation { --tone: var(--myq-moving); }
.chip.fault { --tone: var(--myq-error); }
.chip.warning { --tone: var(--myq-open); }
.chip.neutral { --tone: var(--myq-muted); }

.details-toggle {
  display: flex; align-items: center; justify-content: space-between; width: 100%;
  margin-top: 2px; padding: 10px 2px 4px; border: 0; border-top: 1px solid var(--divider-color);
  background: none; color: var(--myq-muted); font-size: 13.5px; cursor: pointer; --mdc-icon-size: 20px;
}
.details-toggle .chevron { transition: transform 0.2s; }
.details-toggle[aria-expanded="true"] .chevron { transform: rotate(180deg); }
.details { display: flex; flex-direction: column; margin: -6px -8px 0; }
.detail-rows { display: flex; flex-direction: column; }
.details-customize { align-self: flex-start; margin: 2px 0 6px; }
.detail-row {
  display: grid; grid-template-columns: 22px minmax(0, 1fr) auto 18px; align-items: center; gap: 12px;
  padding: 9px 8px; border: 0; border-radius: 8px; background: none; text-align: start; cursor: pointer;
  font-size: 14px; --mdc-icon-size: 20px;
}
.detail-row:hover { background: var(--myq-tint); }
.detail-icon { color: var(--state-icon-color, var(--myq-muted)); }
.detail-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.detail-value { color: var(--myq-muted); font-variant-numeric: tabular-nums; text-align: end; }
.detail-chevron { color: var(--disabled-text-color, #bdbdbd); --mdc-icon-size: 18px; }

.activity { margin: 10px 8px 6px; }
.activity-title {
  margin: 0 0 4px; font-size: 12px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--myq-muted);
}
.activity-list { list-style: none; margin: 0; padding: 0; }
.activity-row {
  display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; align-items: center; column-gap: 12px;
  padding: 7px 0; font-size: 14px; --mdc-icon-size: 20px;
}
.activity-row + .activity-row { border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
.activity-icon { grid-row: span 2; align-self: start; margin-top: 1px; color: var(--myq-muted); }
.activity-time { color: var(--myq-muted); font-size: 13px; font-variant-numeric: tabular-nums; text-align: end; }
.activity-by { grid-column: 2 / -1; margin-top: 1px; font-size: 12.5px; color: var(--myq-muted); }
.activity-empty { margin: 4px 0 6px; font-size: 13.5px; color: var(--myq-muted); }

/* A fresh camera image after the door stops moving. */
.peek {
  position: absolute; z-index: 2; right: 10px; bottom: 10px; width: min(40%, 220px); aspect-ratio: 16 / 9;
  padding: 0; border: 0; border-radius: 10px; overflow: hidden; cursor: pointer; background: #0e0f11;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.92), 0 8px 22px rgba(0, 0, 0, 0.35);
  animation: peek-in 0.35s cubic-bezier(0.2, 0.9, 0.3, 1);
}
.peek-image { display: block; width: 100%; height: 100%; object-fit: cover; }
.peek-badge {
  position: absolute; left: 6px; top: 6px; width: 24px; height: 24px; border-radius: 50%;
  display: grid; place-items: center; color: #fff; --mdc-icon-size: 15px;
  background: rgba(16, 17, 19, 0.6); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
@keyframes peek-in { from { opacity: 0; transform: translateY(8px) scale(0.96); } }

/* Compact cards: the door picture beside the name and buttons, so several doors fit on a phone. */
.doors.compact { gap: 12px; }
.door-card.compact {
  display: grid; grid-template-columns: minmax(92px, 30%) minmax(0, 1fr); column-gap: 14px;
  align-items: center; padding: 12px 12px 2px;
}
.door-card.compact[data-width="double"] { grid-template-columns: minmax(120px, 40%) minmax(0, 1fr); }
.door-card.compact .body { display: contents; }
.door-card.compact .media { grid-column: 1; grid-row: 1 / span 3; padding-top: 0; border-radius: 10px; }
.door-card.compact .media-top { display: none; }
.door-card.compact :is(.heading, .actions, .chips) { grid-column: 2; }
.door-card.compact .heading .name { font-size: 16px; }
.door-card.compact .heading .subtitle { font-size: 13px; }
.door-card.compact .actions { display: flex; margin-top: 10px; gap: 8px; }
.door-card.compact .action { flex: 1 1 0; height: 40px; padding: 0 12px; border-radius: 20px; font-size: 14px; }
.door-card.compact .chips { margin-top: 10px; }
.door-card.compact .chip { height: 26px; font-size: 12.5px; }
.door-card.compact .details-toggle { grid-column: 1 / -1; margin-top: 12px; }
.door-card.compact .details { grid-column: 1 / -1; margin: 0 -8px 6px; }
.door-card.compact .peek { inset: 0; width: auto; aspect-ratio: auto; border-radius: 0; box-shadow: none; }
.door-card.compact .offline { font-size: 12px; --mdc-icon-size: 22px; }

/* Scene layers */
.scene { position: relative; overflow: hidden; }
.scene.covered { visibility: hidden; }
.scene img {
  position: absolute; inset: 0; display: block; width: 100%; height: 100%;
  pointer-events: none; user-select: none; -webkit-user-drag: none;
}
.scene .opening { position: absolute; overflow: hidden; }
.scene .door-layer { position: absolute; inset: 0; will-change: transform; }
.scene .light, .scene .door-lit { opacity: 0; transition: opacity 0.9s ease; }
.scene.lit .light, .scene.lit .door-lit { opacity: 1; }

/* Camera */
.camera { display: grid; place-items: center; background: #0e0f11; }
.camera .camera-image, .camera .camera-player {
  position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;
}
.camera .camera-image { opacity: 0; transition: opacity 0.35s; }
.camera.has-image .camera-image { opacity: 1; }
.camera.live .camera-image { visibility: hidden; }
.camera-message { position: relative; z-index: 1; color: rgba(255, 255, 255, 0.72); font-size: 14px; }
.camera-updated {
  position: absolute; z-index: 2; left: 10px; bottom: 10px;
  padding: 4px 10px; border-radius: 12px; font-size: 12px; color: #fff;
  background: rgba(16, 17, 19, 0.55); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}

.section-title { margin: 36px 4px 14px; font-size: 16px; font-weight: 500; color: var(--myq-muted); }
.camera-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 20px; }
.camera-card {
  overflow: hidden; background: var(--myq-card);
  border: var(--ha-card-border-width, 1px) solid var(--myq-border);
  border-radius: var(--myq-radius); box-shadow: var(--ha-card-box-shadow, none);
}
.camera-card .media { aspect-ratio: 16 / 9; }
.camera-card .body { padding: 12px 16px 14px; gap: 2px; }

/* Loading and empty states */
.skeleton {
  border-radius: var(--myq-radius); overflow: hidden; background: var(--myq-card);
  border: var(--ha-card-border-width, 1px) solid var(--myq-border);
  flex: 1.236 1 330px; max-width: 540px; height: 420px;
}
.skeleton::before {
  content: ""; display: block; height: 62%;
  background: linear-gradient(100deg, var(--myq-tint) 30%, color-mix(in srgb, var(--primary-text-color) 11%, transparent) 50%, var(--myq-tint) 70%);
  background-size: 300% 100%; animation: shimmer 1.6s ease-in-out infinite;
}
@keyframes shimmer { from { background-position: 100% 0; } to { background-position: 0 0; } }
.empty {
  max-width: 460px; margin: 6vh auto 0; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
}
.empty .media { width: min(100%, 360px); border-radius: var(--myq-radius); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); }
.empty .media > .scene { filter: saturate(0.6) brightness(0.9); }
.empty-icon {
  width: 88px; height: 88px; border-radius: 50%; display: grid; place-items: center;
  background: var(--myq-tint); color: var(--myq-muted); --mdc-icon-size: 44px;
}
.empty h2 { margin: 12px 0 0; font-size: 22px; font-weight: 500; }
.empty p { margin: 0 0 8px; color: var(--myq-muted); line-height: 1.5; }

/* Dialogs */
dialog.sheet {
  width: min(1000px, calc(100vw - 48px)); max-width: none; max-height: min(880px, calc(100dvh - 48px));
  padding: 0; border: 0; border-radius: 24px; overflow: hidden;
  background: var(--mdc-theme-surface, var(--card-background-color, #fff));
  color: var(--primary-text-color);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}
dialog.sheet.settings { width: min(520px, calc(100vw - 48px)); }
dialog.sheet[open] { display: flex; flex-direction: column; }
dialog.sheet::backdrop { background: rgba(0, 0, 0, 0.5); backdrop-filter: blur(2px); }
dialog.sheet[open] { animation: rise 0.22s cubic-bezier(0.2, 0.9, 0.3, 1); }
@keyframes rise { from { opacity: 0; transform: translateY(12px) scale(0.98); } }
.sheet-header {
  display: flex; align-items: center; gap: 8px; flex: none;
  padding: 10px 8px 10px 24px; border-bottom: 1px solid var(--divider-color);
}
.sheet-header h2 {
  flex: 1; min-width: 0; margin: 0; font-size: 20px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sheet-header h2:focus { outline: none; }
.sheet-body { flex: 1 1 auto; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.sheet-footer {
  display: flex; align-items: center; gap: 8px; flex: none; flex-wrap: wrap;
  padding: 12px 16px; border-top: 1px solid var(--divider-color);
}
@media (max-width: 640px) {
  dialog.sheet, dialog.sheet.settings {
    width: 100vw; height: 100dvh; max-height: 100dvh; margin: 0; border-radius: 0;
  }
}

.customize-body { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); }
.preview { position: sticky; top: 0; align-self: start; padding: 24px; }
.preview-frame { overflow: hidden; border-radius: 16px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22); }
.preview-controls { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 10px; margin-top: 16px; }
.controls {
  display: flex; flex-direction: column; gap: 22px; min-width: 0;
  padding: 22px 24px 26px; border-inline-start: 1px solid var(--divider-color);
}
@media (max-width: 760px) {
  .customize-body { grid-template-columns: minmax(0, 1fr); }
  .preview {
    z-index: 2; padding: 12px 16px; background: var(--mdc-theme-surface, var(--card-background-color, #fff));
    border-bottom: 1px solid var(--divider-color);
  }
  .preview-frame { max-width: min(100%, 360px); margin: 0 auto; border-radius: 12px; }
  .preview-controls { margin-top: 10px; }
  .controls { padding: 18px 16px 24px; border: 0; }
}
.field-help { margin: 8px 0 0; font-size: 13px; line-height: 1.4; color: var(--myq-muted); }
.field-label {
  margin-bottom: 10px; font-size: 12px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--myq-muted);
}
.segmented {
  display: inline-flex; flex-wrap: wrap; gap: 3px; max-width: 100%;
  padding: 3px; border-radius: 14px; background: var(--myq-tint);
}
.segment {
  min-height: 36px; padding: 6px 14px; border: 0; border-radius: 11px;
  background: none; font-size: 14px; cursor: pointer; color: var(--primary-text-color);
}
.segment:hover { background: var(--myq-tint); }
.segment[aria-pressed="true"] {
  background: var(--myq-card); font-weight: 500;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18), 0 0 0 1px color-mix(in srgb, var(--primary-text-color) 6%, transparent);
}
.segment-toggle {
  min-height: 42px; padding: 0 16px 0 12px; border: 0; border-radius: 14px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 8px; font-size: 14px;
  background: var(--myq-tint); --mdc-icon-size: 20px;
}
.segment-toggle[aria-pressed="true"] { background: color-mix(in srgb, #f2a516 22%, transparent); }
.segment-toggle[aria-pressed="true"] ha-icon { color: #e09a10; }

.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(98px, 1fr)); gap: 10px; }
.tile {
  display: flex; flex-direction: column; align-items: stretch; gap: 7px;
  padding: 7px 7px 8px; border: 2px solid transparent; border-radius: 14px;
  background: var(--myq-tint); cursor: pointer; text-align: center;
  font-size: 12.5px; line-height: 1.25; transition: border-color 0.15s, background 0.15s;
}
.tile:hover { background: color-mix(in srgb, var(--primary-text-color) 9%, transparent); }
.tile[aria-pressed="true"] {
  border-color: var(--myq-primary); background: color-mix(in srgb, var(--myq-primary) 10%, var(--myq-card));
}
.tile-art img { display: block; width: 100%; height: auto; aspect-ratio: 108 / 84; border-radius: 6px; }

.swatch-group + .swatch-group { margin-top: 14px; }
.swatch-group-label { margin-bottom: 8px; font-size: 12.5px; color: var(--myq-muted); }
.swatches { display: flex; flex-wrap: wrap; gap: 10px; }
.swatch {
  position: relative; width: 34px; height: 34px; flex: none; padding: 0; border: 0; border-radius: 50%;
  cursor: pointer; background: var(--swatch);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.16), inset 0 -8px 12px rgba(0, 0, 0, 0.1), inset 0 6px 10px rgba(255, 255, 255, 0.12);
  transition: transform 0.12s;
}
.swatch:hover { transform: scale(1.08); }
.swatch[aria-pressed="true"] { outline: 2px solid var(--myq-primary); outline-offset: 3px; }
.swatch.wood {
  background-image:
    repeating-linear-gradient(97deg, rgba(0, 0, 0, 0.13) 0 1.5px, transparent 1.5px 4px, rgba(0, 0, 0, 0.07) 4px 5px, transparent 5px 8px),
    linear-gradient(var(--swatch), var(--swatch));
}
.swatch.custom {
  display: grid; place-items: center; color: #fff; --mdc-icon-size: 16px;
  background: conic-gradient(from 210deg, #e5534b, #f0b429, #3fb950, #2f81f7, #a371f7, #e5534b);
}
.swatch.custom.filled { background: var(--swatch); color: color-mix(in srgb, var(--swatch) 20%, #fff); }
.swatch.custom input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; border: 0; padding: 0; }
.swatch.custom ha-icon { pointer-events: none; filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.5)); }

.switch-row { display: flex; align-items: center; gap: 16px; cursor: pointer; }
.switch-text { flex: 1; display: flex; flex-direction: column; gap: 3px; font-size: 15px; }
.switch-text small { font-size: 13px; color: var(--myq-muted); line-height: 1.4; }
.switch {
  appearance: none; -webkit-appearance: none; position: relative; flex: none; margin: 0;
  width: 44px; height: 26px; border-radius: 13px; cursor: pointer;
  background: color-mix(in srgb, var(--primary-text-color) 28%, transparent); transition: background 0.2s;
}
.switch::after {
  content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35); transition: transform 0.2s;
}
.switch:checked { background: var(--myq-primary); }
.switch:checked::after { transform: translateX(18px); }
:host(:dir(rtl)) .switch:checked::after { transform: translateX(-18px); }

.settings-body { display: flex; flex-direction: column; gap: 24px; padding: 22px 24px 26px; }
.order-list { list-style: none; margin: 0; padding: 0; border: 1px solid var(--divider-color); border-radius: 14px; overflow: hidden; }
.order-row { display: flex; align-items: center; gap: 10px; padding: 4px 6px 4px 14px; }
.order-row + .order-row { border-top: 1px solid var(--divider-color); }
.order-index {
  width: 24px; height: 24px; flex: none; border-radius: 50%; display: grid; place-items: center;
  font-size: 12px; font-weight: 600; background: var(--myq-tint); color: var(--myq-muted);
}
.order-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; }
.note {
  display: flex; gap: 12px; padding: 14px 16px; border-radius: 14px; background: var(--myq-tint);
  color: var(--myq-muted); font-size: 13.5px; line-height: 1.45; --mdc-icon-size: 20px;
}
.note p { margin: 0 0 6px; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
`;

export const styles = `
:host {
  display: flex;
  flex-direction: column;
  /* ha-panel-custom has no height of its own and pads itself for safe areas, so size to the
     viewport the way Home Assistant sizes iframe panels, and scroll inside. */
  height: calc(100vh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px));
  height: calc(100dvh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px));
  overflow: hidden;
  background: var(--primary-background-color);
  ${theme}
}
${components}`;

export const cardStyles = `
:host { display: block; ${theme} }
${components}
/* On a dashboard the card fills the space the dashboard gives it. */
.door-card { max-width: none; width: 100%; height: 100%; }
.card-message {
  display: flex; align-items: center; gap: 12px; padding: 16px;
  background: var(--myq-card); border-radius: var(--myq-radius);
  border: var(--ha-card-border-width, 1px) solid var(--myq-border);
  color: var(--myq-muted); font-size: 14px; line-height: 1.4; --mdc-icon-size: 22px;
}
`;
