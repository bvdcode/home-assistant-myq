/**
 * Shapes of the data the integration sends over `myq/panel/subscribe`, and of what a DoorCard needs
 * from the panel or dashboard card that shows it. `npm run typecheck` checks the modules against them;
 * panel.py defines the same payload as TypedDicts.
 */

/**
 * A door's saved look. Every field is optional; the drawing fills in the rest.
 * @typedef {object} DoorAppearance
 * @property {string} [width]
 * @property {string} [style]
 * @property {string} [color]
 * @property {string} [windows]
 * @property {string} [glass]
 * @property {boolean} [hardware]
 * @property {string} [trim]
 */

/**
 * Preferences shared by every user of the panel.
 * @typedef {object} PanelSettings
 * @property {boolean} [confirm] Doors move only after a second tap.
 * @property {string[]} [order] Device IDs in the order the panel lists the doors.
 * @property {number} [open_warning] Minutes before an open door is highlighted; 0 turns it off.
 */

/**
 * @typedef {object} DoorPayload
 * @property {string} device_id
 * @property {string} name
 * @property {string | null} model
 * @property {Record<string, string>} entities Entity IDs by role, such as cover, camera, and work_light.
 */

/**
 * @typedef {object} CameraPayload
 * @property {string} device_id
 * @property {string} name
 * @property {string | null} model
 * @property {string} entity_id
 */

/**
 * @typedef {object} AccountPayload
 * @property {string} entry_id
 * @property {string} state The config entry state, such as loaded or setup_error.
 * @property {string} [title] Only sent to administrators.
 */

/**
 * @typedef {object} PanelPayload
 * @property {DoorPayload[]} doors
 * @property {CameraPayload[]} cameras
 * @property {Record<string, DoorAppearance>} appearance Saved looks by device ID.
 * @property {PanelSettings} settings
 * @property {AccountPayload[]} accounts
 */

/**
 * What a DoorCard needs from the panel or dashboard card that shows it. The host is also the element
 * that dispatches Home Assistant UI events, such as opening the more-info dialog.
 * @typedef {HTMLElement & {
 *   hass: any,
 *   settings: PanelSettings,
 *   confirmCommands: boolean,
 *   openCustomize?: (deviceId: string) => void,
 * }} DoorCardHost
 */

export {};
