const hiddenKey = "quailHiddenMessages";
const themeStorageKey = "quailTheme";
const pauseKey = "quailInboxPaused";
const notifyKey = "quailInboxNotify";
const config = window.QUAIL_INBOX_CONFIG || {};
const wsEnabled = Boolean(config.wsEnabled);
const pollingIntervalMs = wsEnabled ? 15000 : 3000;
const wsHeartbeatIntervalMs = 30000;
const wsHeartbeatMaxSilenceMs = 65000;
const hasFilter = Boolean(config.hasFilter);
const currentInboxLabel = typeof config.currentInboxLabel === "string" ? config.currentInboxLabel : "";
const baseTitle = document.title;
const inboxQuery = config.inboxQuery || "";
const inboxParams = new URLSearchParams(inboxQuery ? inboxQuery.slice(1) : "");
const rawPageSize = Number(config.pageSize);
const pageSize =
  Number.isFinite(rawPageSize) && rawPageSize > 0 ? Math.min(rawPageSize, 200) : 20;
const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
const buildInboxQuery = (before, limit = pageSize) => {
  const params = new URLSearchParams(inboxParams);
  if (limit) {
    params.set("limit", String(limit));
  }
  if (before) {
    params.set("before", before);
  } else {
    params.delete("before");
  }
  const query = params.toString();
  return query ? `?${query}` : "";
};
const buildInboxApiUrl = (before, limit = pageSize) =>
  `/api/inbox${buildInboxQuery(before, limit)}`;
const wsUrl = `${wsProtocol}://${window.location.host}/ws/inbox${buildInboxQuery(
  null,
  pageSize
)}`;
const isAdmin = Boolean(config.isAdmin);
const tableElement = document.querySelector(".inbox-table--body");
const liveTbody = tableElement ? tableElement.querySelector("tbody") : null;
const olderTbody = tableElement ? document.createElement("tbody") : null;
if (tableElement && olderTbody) {
  tableElement.appendChild(olderTbody);
}
let rows = Array.from(document.querySelectorAll("tr[data-message-id]"));
let liveRows = liveTbody
  ? Array.from(liveTbody.querySelectorAll("tr[data-message-id]"))
  : [];
let emptyRow = document.querySelector("[data-empty-state]");
const listScrollBody = document.querySelector(".list-scroll-card--inbox .list-scroll-body");
const listScrollCard = document.querySelector(".list-scroll-card--inbox");
const trashButton = document.getElementById("trash-button");
const pauseButton = document.getElementById("pause-button");
let liveNextCursor = typeof config.nextCursor === "string" ? config.nextCursor : null;
let liveHasMore = Boolean(config.hasMore);
let pagingCursor = liveNextCursor;
let pagingHasMore = liveHasMore;
let hasLoadedOlder = false;
let loadingOlder = false;
let messageCache = new Map();
let refreshTimer = null;
let refreshIntervalMs = pollingIntervalMs;
let refreshInFlight = false;
let lastEtag = null;
let ws = null;
let wsRetryMs = 1000;
let wsRetryTimer = null;
let wsHeartbeatTimer = null;
let lastWsActivityAt = 0;
let reconnecting = false;
let reconnectingDots = ".";
let reconnectingTimer = null;
let hiddenBaselineIds = new Set();
let unseenIds = new Set();
let lastNotifiedCount = 0;
let lastNotifiedAt = 0;
const notifyCooldownMs = 5000;

const resetRows = () => {
  rows = Array.from(document.querySelectorAll("tr[data-message-id]"));
  liveRows = liveTbody
    ? Array.from(liveTbody.querySelectorAll("tr[data-message-id]"))
    : [];
  emptyRow = document.querySelector("[data-empty-state]");
};

const updateScrollCardState = () => {
  if (!listScrollBody || !listScrollCard) {
    return;
  }
  const hasScroll = listScrollBody.scrollHeight > listScrollBody.clientHeight + 1;
  listScrollCard.classList.toggle("list-scroll-card--scrollable", hasScroll);
};

const readHidden = () => {
  try {
    const raw = window.sessionStorage.getItem(hiddenKey);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
};

const writeHidden = (items) => {
  try {
    window.sessionStorage.setItem(hiddenKey, JSON.stringify(items));
  } catch (error) {
    // Ignore storage errors.
  }
};

const updateEmptyState = () => {
  if (!emptyRow) {
    return;
  }
  const visibleRows = rows.filter((row) => !row.classList.contains("row-hidden"));
  emptyRow.style.display = visibleRows.length ? "none" : "table-row";
};

const applyHidden = () => {
  const hidden = new Set(readHidden());
  rows.forEach((row) => {
    const id = row.dataset.messageId;
    if (hidden.has(id)) {
      row.classList.add("row-hidden");
    }
  });
  updateEmptyState();
};

const buildEmptyRow = () => {
  const row = document.createElement("tr");
  row.dataset.emptyState = "true";
  const cell = document.createElement("td");
  cell.colSpan = 4;
  const emptyState = document.createElement("div");
  emptyState.className = "empty-state";
  const title = document.createElement("div");
  const titleStrong = document.createElement("strong");
  titleStrong.textContent = hasFilter
    ? "Currently filtered inbox has no mail."
    : "This is an ephemeral inbox.";
  title.appendChild(titleStrong);
  emptyState.appendChild(title);
  const detail = document.createElement("div");
  detail.className = "row-muted";
  if (hasFilter) {
    detail.setAttribute("aria-hidden", "true");
    detail.textContent = "\u00a0";
  } else {
    detail.textContent = "Messages are only shown after you apply a filter.";
  }
  emptyState.appendChild(detail);
  cell.appendChild(emptyState);
  row.appendChild(cell);
  return row;
};

const updateLivePaging = (payload) => {
  if (!payload || typeof payload !== "object") {
    return;
  }
  if (typeof payload.next_cursor === "string") {
    liveNextCursor = payload.next_cursor;
  } else if (payload.next_cursor === null) {
    liveNextCursor = null;
  }
  if (typeof payload.has_more === "boolean") {
    liveHasMore = payload.has_more;
  }
  if (!hasLoadedOlder) {
    pagingCursor = liveNextCursor;
    pagingHasMore = liveHasMore;
  }
};

const updatePagingFromPayload = (payload) => {
  if (!payload || typeof payload !== "object") {
    return;
  }
  if (typeof payload.next_cursor === "string") {
    pagingCursor = payload.next_cursor;
  } else if (payload.next_cursor === null) {
    pagingCursor = null;
  }
  if (typeof payload.has_more === "boolean") {
    pagingHasMore = payload.has_more;
  }
};

const getExistingIds = () => new Set(rows.map((row) => String(row.dataset.messageId)));

const appendOlderMessages = (messages) => {
  if (!olderTbody || !Array.isArray(messages) || !messages.length) {
    return;
  }
  const existingIds = getExistingIds();
  const fragment = document.createDocumentFragment();
  messages.forEach((message) => {
    const id = String(message.id);
    if (existingIds.has(id)) {
      return;
    }
    fragment.appendChild(buildMessageRow(message));
  });
  if (!fragment.childNodes.length) {
    return;
  }
  olderTbody.appendChild(fragment);
  resetRows();
  applyHidden();
  applyReceivedFormatting();
  updateScrollCardState();
};

const prependOlderMessages = (messages) => {
  if (!olderTbody || !Array.isArray(messages) || !messages.length) {
    return;
  }
  const existingIds = getExistingIds();
  const fragment = document.createDocumentFragment();
  messages.forEach((message) => {
    const id = String(message.id);
    if (existingIds.has(id)) {
      return;
    }
    fragment.appendChild(buildMessageRow(message));
  });
  if (!fragment.childNodes.length) {
    return;
  }
  olderTbody.prepend(fragment);
  resetRows();
  applyHidden();
  applyReceivedFormatting();
  updateScrollCardState();
};

const shouldPrefetchOlder = () => {
  if (!listScrollBody) {
    return false;
  }
  return listScrollBody.scrollHeight <= listScrollBody.clientHeight + 1;
};

const loadOlderMessages = async () => {
  if (!pagingHasMore || !pagingCursor || loadingOlder) {
    return;
  }
  loadingOlder = true;
  try {
    const response = await fetch(buildInboxApiUrl(pagingCursor), { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    if (!payload || !Array.isArray(payload.messages)) {
      return;
    }
    if (payload.messages.length) {
      appendOlderMessages(payload.messages);
      hasLoadedOlder = true;
    }
    updatePagingFromPayload(payload);
  } catch (error) {
    // Ignore paging errors.
  } finally {
    loadingOlder = false;
    if (pagingHasMore && pagingCursor && shouldPrefetchOlder()) {
      loadOlderMessages();
    }
  }
};

const maybeLoadOlder = () => {
  if (!pagingHasMore || !pagingCursor || loadingOlder) {
    return;
  }
  loadOlderMessages();
};

const setupInfiniteScroll = () => {
  if (!listScrollBody || !tableElement) {
    return;
  }
  const sentinel = document.createElement("div");
  sentinel.setAttribute("aria-hidden", "true");
  sentinel.style.height = "1px";
  listScrollBody.appendChild(sentinel);
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          maybeLoadOlder();
        }
      });
    },
    { root: listScrollBody, rootMargin: "200px 0px", threshold: 0 }
  );
  observer.observe(sentinel);
  if (pagingHasMore && pagingCursor && shouldPrefetchOlder()) {
    loadOlderMessages();
  }
};

const getCurrentMessages = () => Array.from(messageCache.values());

const getCurrentIds = () => {
  if (messageCache.size) {
    return new Set(messageCache.keys());
  }
  const ids = new Set();
  rows.forEach((row) => {
    if (row.dataset.messageId) {
      ids.add(String(row.dataset.messageId));
    }
  });
  return ids;
};

const formatTitle = (count) => {
  if (reconnecting) {
    return `${baseTitle} | Reconnecting${reconnectingDots}`;
  }
  if (count <= 0) {
    return `${baseTitle} | No New Mail`;
  }
  if (count === 1) {
    return `${baseTitle} | 1 New Mail`;
  }
  return `${baseTitle} | ${count} New Mails`;
};

const updateTitle = () => {
  document.title = formatTitle(unseenIds.size);
};

const stopReconnectAnimation = () => {
  if (!reconnectingTimer) {
    return;
  }
  window.clearInterval(reconnectingTimer);
  reconnectingTimer = null;
};

const startReconnectAnimation = () => {
  stopReconnectAnimation();
  const frames = [".", "..", "..."];
  let index = 0;
  reconnectingDots = frames[index];
  reconnectingTimer = window.setInterval(() => {
    index = (index + 1) % frames.length;
    reconnectingDots = frames[index];
    updateTitle();
  }, 800);
};

const setReconnecting = (value) => {
  if (reconnecting === value) {
    return;
  }
  reconnecting = value;
  if (reconnecting) {
    startReconnectAnimation();
  } else {
    stopReconnectAnimation();
  }
  updateTitle();
};

const notificationSupported = () => "Notification" in window;

const getNotificationsEnabled = () => {
  try {
    return window.localStorage.getItem(notifyKey) === "true";
  } catch (error) {
    return false;
  }
};

const setNotificationsEnabled = (value) => {
  try {
    window.localStorage.setItem(notifyKey, String(value));
  } catch (error) {
    // Ignore storage errors.
  }
};

const resolveNotificationsEnabled = () => {
  if (!notificationSupported()) {
    return false;
  }
  if (Notification.permission !== "granted") {
    if (getNotificationsEnabled()) {
      setNotificationsEnabled(false);
    }
    return false;
  }
  return getNotificationsEnabled();
};

const shouldNotify = () => resolveNotificationsEnabled();

const maybeNotify = () => {
  if (!shouldNotify()) {
    return;
  }
  const now = Date.now();
  if (now - lastNotifiedAt < notifyCooldownMs) {
    return;
  }
  if (unseenIds.size === 0 || unseenIds.size === lastNotifiedCount) {
    return;
  }
  lastNotifiedAt = now;
  lastNotifiedCount = unseenIds.size;
  const inboxSuffix = currentInboxLabel ? ` in ${currentInboxLabel}` : "";
  const body =
    unseenIds.size === 1
      ? `1 new mail${inboxSuffix}`
      : `${unseenIds.size} new mails${inboxSuffix}`;
  const title = currentInboxLabel ? `Quail — ${currentInboxLabel}` : "Quail";
  try {
    new Notification(title, { body });
  } catch (error) {
    // Ignore notification errors.
  }
};

const noteNewMessages = (messages) => {
  if (!document.hidden || !Array.isArray(messages)) {
    return;
  }
  const nextIds = new Set(messages.map((message) => String(message.id)));
  let added = 0;
  nextIds.forEach((id) => {
    if (!hiddenBaselineIds.has(id) && !unseenIds.has(id)) {
      unseenIds.add(id);
      added += 1;
    }
  });
  if (added > 0) {
    updateTitle();
    maybeNotify();
  }
};

const markHidden = () => {
  hiddenBaselineIds = getCurrentIds();
  unseenIds = new Set();
  lastNotifiedCount = 0;
  updateTitle();
};

const resetUnread = () => {
  unseenIds = new Set();
  lastNotifiedCount = 0;
  updateTitle();
};

const buildMessageRow = (message) => {
  const row = document.createElement("tr");
  row.dataset.messageId = message.id;
  row.dataset.href = `/message/${message.id}${inboxQuery}`;

  const formatFrom = (rawValue) => {
    if (!rawValue) {
      return "Unknown";
    }
    const trimmed = String(rawValue).trim();
    if (!trimmed) {
      return "Unknown";
    }
    if (trimmed.includes("<")) {
      return trimmed.split("<")[0].replace(/"/g, "").trim() || "Unknown";
    }
    if (trimmed.includes("@")) {
      const localPart = trimmed.split("@")[0].trim();
      return localPart || "Unknown";
    }
    return trimmed;
  };

  const fromCell = document.createElement("td");
  fromCell.className = "from-col";
  const checkbox = document.createElement("input");
  checkbox.className = "message-select";
  checkbox.type = "checkbox";
  checkbox.setAttribute("aria-label", "Select message");
  fromCell.appendChild(checkbox);
  const fromText = document.createElement("span");
  fromText.className = "from-text";
  fromText.textContent = ` ${formatFrom(message.from_addr)}`;
  fromCell.appendChild(fromText);
  if (isAdmin && message.quarantined) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "Quarantined";
    fromCell.appendChild(badge);
  }

  const toCell = document.createElement("td");
  toCell.className = "to-col";
  const toValue = message.envelope_rcpt || "";
  const toDisplay = toValue.includes("@") ? toValue.split("@")[0] : toValue;
  toCell.textContent = toDisplay;

  const subjectCell = document.createElement("td");
  subjectCell.className = "subject-col";
  const link = document.createElement("a");
  link.href = `/message/${message.id}${inboxQuery}`;
  link.textContent = message.subject || "(No subject)";
  subjectCell.appendChild(link);

  const receivedCell = document.createElement("td");
  receivedCell.className = "received-col received-cell";
  receivedCell.className = "received-cell";
  receivedCell.dataset.receivedAt = message.received_at || "";
  receivedCell.textContent = formatReceivedAt(message.received_at || "");
  const parsedReceived = message.received_at
    ? parseReceivedDate(message.received_at)
    : null;
  if (parsedReceived) {
    receivedCell.title = formatAbsoluteTimestamp(parsedReceived);
  }

  row.appendChild(fromCell);
  row.appendChild(toCell);
  row.appendChild(subjectCell);
  row.appendChild(receivedCell);
  return row;
};

const renderMessagesFromCache = () => {
  const messages = Array.from(messageCache.values());
  messages.sort((a, b) => {
    const aTime = new Date(a.received_at || 0).getTime();
    const bTime = new Date(b.received_at || 0).getTime();
    return bTime - aTime;
  });
  renderMessages(messages);
  noteNewMessages(messages);
};

const setCache = (messages) => {
  const previousMessages = Array.from(messageCache.values());
  messageCache = new Map();
  messages.forEach((message) => {
    messageCache.set(String(message.id), message);
  });
  renderMessagesFromCache();
  if (hasLoadedOlder && previousMessages.length) {
    const nextIds = new Set(messages.map((message) => String(message.id)));
    const dropped = previousMessages.filter((message) => !nextIds.has(String(message.id)));
    if (dropped.length) {
      prependOlderMessages(dropped);
    }
  }
};

const applyDelta = (payload) => {
  let changed = false;
  if (Array.isArray(payload.added)) {
    payload.added.forEach((message) => {
      messageCache.set(String(message.id), message);
      changed = true;
    });
  }
  if (Array.isArray(payload.updated)) {
    payload.updated.forEach((message) => {
      messageCache.set(String(message.id), message);
      changed = true;
    });
  }
  if (Array.isArray(payload.deleted)) {
    payload.deleted.forEach((id) => {
      if (messageCache.delete(String(id))) {
        changed = true;
      }
    });
  }
  if (changed) {
    renderMessagesFromCache();
  }
};

const renderMessages = (messages) => {
  if (!liveTbody) {
    return;
  }
  const fragment = document.createDocumentFragment();
  messages.forEach((message) => {
    fragment.appendChild(buildMessageRow(message));
  });
  const emptyStateRow = buildEmptyRow();
  emptyStateRow.style.display = messages.length ? "none" : "table-row";
  fragment.appendChild(emptyStateRow);
  liveTbody.replaceChildren(fragment);
  resetRows();
  applyHidden();
  applyReceivedFormatting();
  updateScrollCardState();
};

const pad2 = (value) => String(value).padStart(2, "0");

const formatAbsoluteTimestamp = (date) =>
  `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(
    date.getSeconds()
  )} ${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;

const formatAbsoluteTimestampShort = (date) =>
  `${pad2(date.getHours())}:${pad2(date.getMinutes())} ${pad2(
    date.getDate()
  )}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;

const parseReceivedDate = (rawValue) => {
  const parsed = new Date(rawValue);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatReceivedAt = (rawValue) => {
  if (!rawValue) {
    return "";
  }
  const parsed = parseReceivedDate(rawValue);
  if (!parsed) {
    return rawValue;
  }
  const now = new Date();
  let diffMs = now.getTime() - parsed.getTime();
  const clockSkewMs = 60000;
  if (diffMs < -clockSkewMs) {
    return formatAbsoluteTimestampShort(parsed);
  }
  if (diffMs < 0) {
    diffMs = 0;
  }
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 45) {
    return "just now";
  }
  if (seconds < 90) {
    return "1 minute ago";
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} minutes ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days} ${days === 1 ? "day" : "days"} ago`;
  }
  return formatAbsoluteTimestampShort(parsed);
};

const applyReceivedFormatting = () => {
  const cells = document.querySelectorAll(".received-cell[data-received-at]");
  cells.forEach((cell) => {
    const rawValue = cell.dataset.receivedAt;
    const formatted = formatReceivedAt(rawValue);
    cell.textContent = formatted;
    const parsed = rawValue ? parseReceivedDate(rawValue) : null;
    if (parsed) {
      cell.title = formatAbsoluteTimestamp(parsed);
    }
  });
};

const startReceivedTicker = () => {
  window.setInterval(applyReceivedFormatting, 60000);
};

const hasSameMessages = (messages) => {
  if (liveRows.length !== messages.length) {
    return false;
  }
  return liveRows.every((row, index) => row.dataset.messageId == messages[index].id);
};

const isPaused = () => window.sessionStorage.getItem(pauseKey) === "true";

const setTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    window.localStorage.setItem(themeStorageKey, theme);
  } catch (error) {
    // Ignore storage errors.
  }
};

const getTheme = () => {
  const stored = window.localStorage.getItem(themeStorageKey);
  return stored || document.documentElement.dataset.theme || "light";
};

const updateThemeToggle = () => {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) {
    return;
  }
  const theme = getTheme();
  const isDark = theme === "dark";
  toggle.setAttribute("aria-pressed", isDark ? "true" : "false");
  toggle.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
};

const refreshInbox = async () => {
  if (refreshInFlight) {
    return;
  }
  if (isPaused()) {
    return;
  }
  refreshInFlight = true;
  try {
    const headers = {};
    if (lastEtag) {
      headers["If-None-Match"] = lastEtag;
    }
    const response = await fetch(buildInboxApiUrl(), { cache: "no-store", headers });
    if (response.status === 304) {
      return;
    }
    if (!response.ok) {
      return;
    }
    const nextEtag = response.headers.get("ETag");
    if (nextEtag) {
      lastEtag = nextEtag;
    }
    const payload = await response.json();
    if (isPaused()) {
      return;
    }
    if (!payload || !Array.isArray(payload.messages)) {
      return;
    }
    updateLivePaging(payload);
    if (!hasSameMessages(payload.messages)) {
      setCache(payload.messages);
    }
  } catch (error) {
    // Ignore refresh errors.
  } finally {
    refreshInFlight = false;
  }
};

const startPolling = (intervalMs = pollingIntervalMs) => {
  if (intervalMs <= 0) {
    return;
  }
  if (refreshTimer) {
    if (refreshIntervalMs === intervalMs) {
      return;
    }
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  refreshIntervalMs = intervalMs;
  refreshTimer = window.setInterval(refreshInbox, refreshIntervalMs);
};

const stopPolling = () => {
  if (!refreshTimer) {
    return;
  }
  window.clearInterval(refreshTimer);
  refreshTimer = null;
};

const noteWsActivity = () => {
  lastWsActivityAt = Date.now();
};

const stopWsHeartbeat = () => {
  if (!wsHeartbeatTimer) {
    return;
  }
  window.clearInterval(wsHeartbeatTimer);
  wsHeartbeatTimer = null;
};

const startWsHeartbeat = () => {
  stopWsHeartbeat();
  if (!ws) {
    return;
  }
  noteWsActivity();
  wsHeartbeatTimer = window.setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    const now = Date.now();
    if (now - lastWsActivityAt > wsHeartbeatMaxSilenceMs) {
      ws.close();
      return;
    }
    try {
      ws.send(JSON.stringify({ type: "ping" }));
    } catch (error) {
      ws.close();
    }
  }, wsHeartbeatIntervalMs);
};

const scheduleWsRetry = () => {
  if (!wsEnabled || wsRetryTimer) {
    return;
  }
  const jitter = 0.8 + Math.random() * 0.4;
  const delayMs = Math.round(wsRetryMs * jitter);
  wsRetryTimer = window.setTimeout(() => {
    wsRetryTimer = null;
    startWebSocket();
  }, delayMs);
  wsRetryMs = Math.min(wsRetryMs * 2, 10000);
};

const resetWsRetry = () => {
  wsRetryMs = 1000;
  if (wsRetryTimer) {
    window.clearTimeout(wsRetryTimer);
    wsRetryTimer = null;
  }
};

const forceSnapshotRefresh = async () => {
  try {
    const response = await fetch(buildInboxApiUrl(), { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    if (payload && Array.isArray(payload.messages)) {
      updateLivePaging(payload);
      setCache(payload.messages);
    }
  } catch (error) {
    // Ignore refresh errors.
  }
};

const handleWsMessage = (event) => {
  let payload = null;
  try {
    payload = JSON.parse(event.data);
  } catch (error) {
    return;
  }
  noteWsActivity();
  if (!payload || typeof payload.type !== "string") {
    return;
  }
  if (payload.type === "pong") {
    return;
  }
  if (isPaused()) {
    return;
  }
  if (payload.type === "snapshot") {
    if (Array.isArray(payload.messages)) {
      updateLivePaging(payload);
      setCache(payload.messages);
    }
    if (payload.etag) {
      lastEtag = payload.etag;
    }
    return;
  }
  if (payload.type === "delta") {
    const removed = Array.isArray(payload.deleted) ? payload.deleted : [];
    const updated = Array.isArray(payload.updated) ? payload.updated : [];
    const deletedMissing = removed.some((id) => !messageCache.has(String(id)));
    const updatedMissing = updated.some(
      (message) => !messageCache.has(String(message.id))
    );
    if (deletedMissing || updatedMissing) {
      if (ws) {
        ws.close();
      }
      forceSnapshotRefresh();
      return;
    }
    applyDelta(payload);
    if (payload.etag) {
      lastEtag = payload.etag;
    }
    return;
  }
};

const startWebSocket = () => {
  if (!wsEnabled || ws) {
    return;
  }
  setReconnecting(true);
  ws = new WebSocket(wsUrl);
  ws.addEventListener("open", () => {
    resetWsRetry();
    stopPolling();
    startWsHeartbeat();
    setReconnecting(false);
  });
  ws.addEventListener("message", handleWsMessage);
  ws.addEventListener("close", () => {
    ws = null;
    startPolling(pollingIntervalMs);
    scheduleWsRetry();
    stopWsHeartbeat();
    setReconnecting(true);
  });
  ws.addEventListener("error", () => {
    if (ws) {
      ws.close();
    }
  });
};

const updatePauseButton = () => {
  if (!pauseButton) {
    return;
  }
  const paused = isPaused();
  pauseButton.classList.toggle("paused", paused);
  pauseButton.textContent = paused ? "▶️" : "⏸️";
  pauseButton.setAttribute(
    "aria-label",
    paused ? "Resume refresh" : "Pause refresh"
  );
  pauseButton.setAttribute(
    "title",
    paused ? "Resume refresh (this session only)" : "Pause refresh (this session only)"
  );
};

if (trashButton) {
  trashButton.addEventListener("click", () => {
    const selected = rows.filter((row) =>
      row.querySelector(".message-select")?.checked
    );
    if (!selected.length) {
      return;
    }
    const hidden = new Set(readHidden());
    selected.forEach((row) => {
      const id = row.dataset.messageId;
      if (id) {
        hidden.add(id);
        row.classList.add("row-hidden");
      }
      const checkbox = row.querySelector(".message-select");
      if (checkbox) {
        checkbox.checked = false;
      }
    });
    writeHidden(Array.from(hidden));
    updateEmptyState();
  });
}

if (tableElement) {
  tableElement.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    if (target.closest("a, button, input, label, select, textarea")) {
      return;
    }
    const row = target.closest("tr[data-href]");
    if (!row) {
      return;
    }
    const href = row.dataset.href;
    if (href) {
      window.location.href = href;
    }
  });
}

const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const nextTheme = getTheme() === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    updateThemeToggle();
  });
  updateThemeToggle();
}

const notifyToggle = document.getElementById("notify-toggle");
const updateNotifyToggle = () => {
  if (!notifyToggle) {
    return;
  }
  if (!notificationSupported()) {
    notifyToggle.disabled = true;
    notifyToggle.setAttribute("aria-disabled", "true");
  }
  const enabled = resolveNotificationsEnabled();
  notifyToggle.classList.toggle("is-on", enabled);
  notifyToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
};

if (notifyToggle) {
  notifyToggle.addEventListener("click", async () => {
    if (!notificationSupported()) {
      return;
    }
    const enabled = getNotificationsEnabled();
    if (enabled) {
      setNotificationsEnabled(false);
      updateNotifyToggle();
      return;
    }
    if (Notification.permission === "granted") {
      setNotificationsEnabled(true);
      updateNotifyToggle();
      return;
    }
    if (Notification.permission === "denied") {
      setNotificationsEnabled(false);
      updateNotifyToggle();
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      setNotificationsEnabled(permission === "granted");
    } catch (error) {
      setNotificationsEnabled(false);
    }
    updateNotifyToggle();
  });
  updateNotifyToggle();
}

if (pauseButton) {
  pauseButton.addEventListener("click", () => {
    const paused = isPaused();
    window.sessionStorage.setItem(pauseKey, String(!paused));
    updatePauseButton();
  });
  updatePauseButton();
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    markHidden();
    return;
  }
  resetUnread();
  if (!wsEnabled) {
    return;
  }
  if (!ws) {
    startWebSocket();
  }
};

document.addEventListener("visibilitychange", handleVisibilityChange);

if (wsEnabled) {
  startWebSocket();
} else {
  startPolling();
}

if (document.hidden) {
  markHidden();
} else {
  resetUnread();
}

applyHidden();
applyReceivedFormatting();
updateScrollCardState();
startReceivedTicker();
setupInfiniteScroll();

window.addEventListener("resize", () => {
  updateScrollCardState();
  if (pagingHasMore && pagingCursor && shouldPrefetchOlder()) {
    loadOlderMessages();
  }
});
