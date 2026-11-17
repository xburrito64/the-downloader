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
  finished: 0,         // downloads finished since the app opened; each one plays the finish moment
  sprouts: [],         // mushrooms on the forest floor, one per finished download this session
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

// When each download finished, by job number. Plain, not reactive: rows read it when their job changes.
export const finishedAt = new Map();
const MAX_SPROUTS = 40;

function celebrate(job) {
  finishedAt.set(job.id, Date.now());
  app.finished++;
  // Each one grows a mushroom somewhere on the floor. The oldest goes once there are too many.
  app.sprouts.push({ id: job.id, left: 2 + Math.random() * 94, lift: Math.floor(Math.random() * 6) * 3 });
  if (app.sprouts.length > MAX_SPROUTS) app.sprouts.shift();
}

export function putJob(job) {
  const index = app.jobs.findIndex((existing) => existing.id === job.id);
  const before = index >= 0 ? app.jobs[index].status : "";
  if (job.status === "done" && before !== "done") celebrate(job);   // before the row sees its new state
  if (index >= 0) app.jobs[index] = job;
  else app.jobs.push(job);
  // A paused or waiting download keeps its bar but not its old speed.
  if (job.status !== "running" && progress[job.id]) progress[job.id] = { ...progress[job.id], speed: 0, stage: "waiting" };
  if (!ACTIVE.includes(job.status)) {
    delete progress[job.id];
    if (before !== job.status && (job.status === "done" || job.status === "failed")) app.historyVersion++;
  }
}

/** Add a job the UI has not heard of yet. Never replaces one: a live update may already have newer news. */
export function addJob(job) {
  if (!app.jobs.some((existing) => existing.id === job.id)) app.jobs.push(job);
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
