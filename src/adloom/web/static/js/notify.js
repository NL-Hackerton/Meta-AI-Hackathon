"use strict";
// Read/unread state for notifications lives only in this browser (localStorage).
import { api } from "./core.js";

const KEY = "adloom.notifications.read";

export function readIds() {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "[]");
    return new Set(Array.isArray(value) ? value : []);
  } catch {
    return new Set();
  }
}

function save(ids) {
  try { localStorage.setItem(KEY, JSON.stringify([...ids])); } catch { /* storage unavailable: state stays in memory only */ }
}

export const isUnread = (item, read = readIds()) => !read.has(item.id);
export const unreadCount = (items, read = readIds()) => items.filter((n) => !read.has(n.id)).length;

export function markRead(ids) {
  const read = readIds();
  ids.forEach((id) => read.add(id));
  save(read);
}

// Keep only IDs that still exist so the stored set does not grow without bound.
export function markAllRead(items) {
  save(new Set(items.map((n) => n.id)));
}

export function setBell(items) {
  const dot = document.getElementById("bellDot");
  if (!dot) return;
  const count = unreadCount(items);
  dot.hidden = count === 0;
  dot.closest("a")?.setAttribute("aria-label", count ? `Notifications, ${count} unread` : "Notifications");
}

export async function refreshBell() {
  try { setBell(await api("/api/notifications")); } catch { /* bell stays as it was if the list cannot load */ }
}
