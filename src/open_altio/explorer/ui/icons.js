/* Open Altio's icons, each a line drawing on a 24 px square, and the mark beside its name.
   SPDX-License-Identifier: Apache-2.0 */

const PATHS = {
  admin: '<path d="M12 3.5 5.5 6v5.2c0 4 2.7 7.6 6.5 8.8 3.8-1.2 6.5-4.8 6.5-8.8V6z"/>',
  arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  bin: '<path d="M5 7h14M10 7V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/><path d="M6.5 7l1 12a1 1 0 0 0 1 .9h7a1 1 0 0 0 1-.9l1-12M10 11v5M14 11v5"/>',
  bullets: '<path d="M9.5 7h10M9.5 12h10M9.5 17h10"/><circle cx="4.8" cy="7" r="1.3" fill="currentColor" stroke="none"/><circle cx="4.8" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="4.8" cy="17" r="1.3" fill="currentColor" stroke="none"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  chevronDown: '<path d="M6 10l6 6 6-6"/>',
  chevronRight: '<path d="M10 6l6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  database: '<ellipse cx="12" cy="6" rx="8" ry="2.5"/><path d="M4 6v12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5V6"/><path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
  document: '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
  dots: '<circle cx="12" cy="5.5" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="18.5" r="1.4" fill="currentColor" stroke="none"/>',
  download: '<path d="M12 5v11M8 12l4 4 4-4"/><path d="M5 15v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  filter: '<path d="M4 8h5M13 8h7M4 16h7M15 16h5"/><circle cx="11" cy="8" r="2"/><circle cx="13" cy="16" r="2"/>',
  folder: '<path d="M4 7a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>',
  home: '<path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z"/>',
  improve: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2"/><circle cx="12" cy="12" r="3"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5 12 13l8.5-6.5"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  minus: '<path d="M6.5 12h11"/>',
  numbers: '<path d="M10 7h10M10 12h10M10 17h10"/><path d="M4.2 5.4 5.4 4.6v4"/><path d="M3.9 10.6c.3-.6 2.3-.8 2.3.4 0 1-2.3 1.7-2.3 3h2.4"/><path d="M3.9 15.6h2.3l-1.2 1.4c.9 0 1.4.5 1.4 1.1s-.6 1.2-1.3 1.2c-.5 0-1-.2-1.2-.5"/>',
  panelLeftClose: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M10 5v14"/><path d="m16.2 9.6-2.6 2.4 2.6 2.4"/>',
  panelLeftOpen: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M10 5v14"/><path d="m13.6 9.6 2.6 2.4-2.6 2.4"/>',
  pencil: '<path d="M5 19h3.2L18.5 8.7a2.1 2.1 0 0 0-3-3L5.2 16z"/><path d="M13.6 7.6l3 3"/>',
  // a push pin; pressed, its head is filled (.oa-pin)
  pin: '<path class="pin-head" d="M10 4.5v5L7 13.5h10l-3-4v-5z"/><path d="M8.5 4.5h7M12 13.5V20"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  pointer: '<path d="M6 3l12 9-5.5 1.2L15 20l-2.6 1.2-2.6-6.6L6 18z"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5 20 20"/>',
  // a gear: eight square teeth round a body, a small hole in the middle
  settings: '<path d="M18.4 10.5 L21.1 10.7 L21.1 13.3 L18.4 13.5 L17.6 15.5 L19.3 17.5 L17.5 19.3 L15.5 17.6 L13.5 18.4 L13.3 21.1 L10.7 21.1 L10.5 18.4 L8.5 17.6 L6.5 19.3 L4.7 17.5 L6.4 15.5 L5.6 13.5 L2.9 13.3 L2.9 10.7 L5.6 10.5 L6.4 8.5 L4.7 6.5 L6.5 4.7 L8.5 6.4 L10.5 5.6 L10.7 2.9 L13.3 2.9 L13.5 5.6 L15.5 6.4 L17.5 4.7 L19.3 6.5 L17.6 8.5z"/><circle cx="12" cy="12" r="2.6"/>',
  signOut: '<path d="M13 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h7"/><path d="M10 12h10M16.5 8.5 20 12l-3.5 3.5"/>',
  upload: '<path d="M12 16V5M8 9l4-4 4 4"/><path d="M5 15v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
};

const MARK =
  '<path d="M37.6,21.3c0,1.3-1.3,2.3-2.6,1.7l-15-6.5c-1.2-.5-1.5-2.2-.5-3L34.1.5c1.2-1,3-.2,3.1,1.3l.4,19.5Z"/>' +
  '<path d="M38.1,44.4L2.3,28.8c.1,0,.2-.1.3-.2l9.1-8.1c.5-.5,1.3-.6,2-.3l23,10c.7.3,1.1.9,1.1,1.6l.3,12.2c0,.1,0,.3,0,.4Z"/>' +
  '<path d="M18.8,65.4l-14.6,13c-1.2,1-3,.2-3.1-1.3l-.4-19.5c0-1.3,1.3-2.3,2.6-1.7l15,6.5c1.2.5,1.5,2.2.5,3Z"/>' +
  '<path d="M36.1,50.1c-.1,0-.2.1-.3.2l-9.1,8.1c-.5.5-1.3.6-2,.3L1.7,48.7c-.7-.3-1.1-.9-1.1-1.6l-.3-12.2c0-.1,0-.3,0-.4l35.8,15.6Z"/>';

export const icon = (name) => `<span class="icon" aria-hidden="true"><svg viewBox="0 0 24 24">${PATHS[name] || ''}</svg></span>`;
export const markSvg = () => `<span class="mark" aria-hidden="true"><svg viewBox="0 0 38.5 79">${MARK}</svg></span>`;
