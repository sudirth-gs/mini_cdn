/**
 * script.js — client-side script for the Mini CDN test pages.
 *
 * Behaviours:
 *   1. Logs a "page loaded" message to the browser console once the DOM is ready.
 *   2. Appends the current timestamp to the document title so you can verify
 *      that the page content is fresh (not a stale browser cache hit).
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Console confirmation that the script was delivered (useful for CDN debugging).
  console.log("Page loaded from CDN");

  // 2. Stamp the document title with an ISO-8601 timestamp.
  //    e.g. "Mini CDN — Test Page [2026-10-25T14:13:12.000Z]"
  const timestamp = new Date().toISOString();
  document.title = document.title + " [" + timestamp + "]";
});
