// What every screen shares: which screen is open, the engine's status, the settings and the list of downloads.
import { api, openEvents } from "./api.js";

export const ACTIVE = ["queued", "running", "paused"];

export const app = $state({
  screen: "home",
  status: null,        // result of the startup checks
  settings: null,
  jobs: [],            // waiting, running and paused downloads, plus the ones that finished since the app opened
  historyVersion: 0,   // goes up whenever a download finishes, so the Library knows to reload
  notice: null,        // { text, kind } shown in the status bar for a few seconds
  loadError: "",
});

// Download progress, by job number. Kept apart from the job list so a progress tick redraws one bar, not the list.
export const progress = $state({});

let noticeTimer = 0;
export function notify(text, kind = "info") {
  clearTimeout(noticeTimer);
  app.notice = { text, kind };
  noticeTimer = setTimeout(() => (app.notice = null), kind === "problem" ? 9000 : 4500);
}

/** Run something that talks to the engine; a failure becomes a message instead of a silent nothing. */
export async function attempt(action) {
  try {
    return await action();
  } catch (error) {
    notify(error.message, "problem");
    return undefined;
  }
}

export function activeCount() {
  let count = 0;
  for (const job of app.jobs) if (ACTIVE.includes(job.status)) count++;
  return count;
}

export function putJob(job) {
  const index = app.jobs.findIndex((existing) => existing.id === job.id);
  const before = index >= 0 ? app.jobs[index].status : "";
  if (index >= 0) app.jobs[index] = job;
  else app.jobs.push(job);
  if (!ACTIVE.includes(job.status)) {
    delete progress[job.id];
    if (before !== job.status && (job.status === "done" || job.status === "failed")) app.historyVersion++;
  }
}

export function clearFinished() {
  app.jobs = app.jobs.filter((job) => ACTIVE.includes(job.status));
}

export async function refreshStatus() {
  app.status = await api.status();
}

export async function saveSettings(changes) {
  app.settings = await api.saveSettings(changes);
  applyMotion();
  return app.settings;
}

function applyMotion() {
  document.documentElement.classList.toggle("calm", Boolean(app.settings?.reduce_motion));
}

async function reloadQueue() {
  const fresh = await api.queue();
  const finished = app.jobs.filter((job) => !ACTIVE.includes(job.status) && !fresh.some((f) => f.id === job.id));
  app.jobs = [...finished, ...fresh];
}

export async function start() {
  try {
    const [status, settings, jobs] = await Promise.all([api.status(), api.settings(), api.queue()]);
    app.status = status;
    app.settings = settings;
    app.jobs = jobs;
    applyMotion();
  } catch (error) {
    app.loadError = error.message;
    return;
  }
  openEvents({
    job: (event) => putJob(event.job),
    progress: (event) => (progress[event.id] = event),
    spotify: (event) => {
      refreshStatus();
      if (event.logged_in) notify("Logged in to Spotify.", "good");
      else if (event.state !== "idle" && event.state !== "waiting") notify(event.state, "problem");
    },
    reconnected: () => attempt(reloadQueue),
  });
}
