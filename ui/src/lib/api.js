// The only file that talks to the engine. Screens call these functions and know nothing about addresses.

// The engine hands the window a one-time session token after the # in the address.
// It is kept for this session only and removed from the address bar right away.
let token = "";
try {
  const fromAddress = new URLSearchParams(location.hash.slice(1)).get("token");
  if (fromAddress) {
    sessionStorage.setItem("token", fromAddress);
    history.replaceState(null, "", location.pathname);
  }
  token = fromAddress || sessionStorage.getItem("token") || "";
} catch {
  token = "";
}

async function call(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? { "X-Token": token } : { "X-Token": token, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("The engine is not answering. Close the app and open it again.");
  }
  let data = null;
  try { data = await response.json(); } catch { /* no body */ }
  if (!response.ok) throw new Error((data && data.detail) || `Something went wrong (${response.status}).`);
  return data;
}

export const api = {
  status: () => call("GET", "/api/status"),
  settings: () => call("GET", "/api/settings"),
  saveSettings: (changes) => call("PUT", "/api/settings", changes),
  spotifyLogin: () => call("POST", "/api/spotify/login"),
  spotifyLogout: () => call("POST", "/api/spotify/logout"),
  resolve: (link) => call("POST", "/api/resolve", { link }),
  enqueue: (request) => call("POST", "/api/queue", request),
  queue: () => call("GET", "/api/queue"),
  pauseAll: () => call("POST", "/api/queue/pause-all"),
  resumeAll: () => call("POST", "/api/queue/resume-all"),
  job: (id, action) => call("POST", `/api/jobs/${id}/${action}`),
  matches: (id) => call("GET", `/api/jobs/${id}/matches`),
  rematch: (id, videoId) => call("POST", `/api/jobs/${id}/rematch`, { video_id: videoId }),
  listen: (videoId) => call("POST", "/api/listen", { video_id: videoId }),
  history: (search, offset, limit) =>
    call("GET", `/api/history?search=${encodeURIComponent(search)}&offset=${offset}&limit=${limit}`),
  forget: (id) => call("DELETE", `/api/history/${id}`),
};

/** Address of the small on-disk copy of a cover. The engine fetches and shrinks it once. */
export function coverSrc(url, wide = false) {
  return url ? `/api/cover?u=${encodeURIComponent(url)}${wide ? "&shape=wide" : ""}&token=${token}` : "";
}

/** Live updates from the engine. The browser reconnects by itself if the stream drops. */
export function openEvents(handlers) {
  const source = new EventSource(`/api/events?token=${token}`);
  let opened = false;
  source.onopen = () => {
    if (opened) handlers.reconnected?.();
    opened = true;
  };
  for (const type of ["job", "progress", "spotify"]) {
    source.addEventListener(type, (event) => handlers[type]?.(JSON.parse(event.data)));
  }
  return source;
}

/** The window itself (minimise, close, folder picker). Missing when the UI is opened in a normal browser. */
export function windowApi() {
  return window.pywebview?.api ?? null;
}
