const promptEl = document.getElementById("prompt");
const inputEl = document.getElementById("input");
const wpmEl = document.getElementById("wpm");
const accEl = document.getElementById("accuracy");
const timeEl = document.getElementById("time");
const resultEl = document.getElementById("result");
const restartBtn = document.getElementById("restart");
const nameEl = document.getElementById("player_name");
const leaderboardEl = document.getElementById("leaderboard");

let currentPrompt = "";
let startTime = null;
let timerInterval = null;
let finished = false;

async function loadPrompt() {
  finished = false;
  resultEl.textContent = "";
  inputEl.value = "";
  inputEl.disabled = false;
  wpmEl.textContent = "0";
  accEl.textContent = "100";
  timeEl.textContent = "0";
  startTime = null;
  clearInterval(timerInterval);

  const res = await fetch("/api/prompt");
  const data = await res.json();
  currentPrompt = data.prompt;
  promptEl.textContent = currentPrompt;
  inputEl.focus();
}

function computeAccuracy(target, typed) {
  const len = Math.min(target.length, typed.length);
  let correct = 0;
  for (let i = 0; i < len; i++) {
    if (target[i] === typed[i]) correct++;
  }
  const denom = Math.max(target.length, typed.length) || 1;
  return Math.round((correct / denom) * 100);
}

inputEl.addEventListener("input", () => {
  if (finished) return;

  if (startTime === null) {
    startTime = Date.now();
    timerInterval = setInterval(() => {
      timeEl.textContent = ((Date.now() - startTime) / 1000).toFixed(1);
    }, 100);
  }

  const typed = inputEl.value;
  const accuracy = computeAccuracy(currentPrompt, typed);
  accEl.textContent = accuracy;

  const elapsedMin = (Date.now() - startTime) / 60000;
  const wordsTyped = typed.trim().split(/\s+/).filter(Boolean).length;
  const wpm = elapsedMin > 0 ? Math.round(wordsTyped / elapsedMin) : 0;
  wpmEl.textContent = wpm;

  if (typed.length >= currentPrompt.length) {
    finish(wpm, accuracy);
  }
});

async function finish(wpm, accuracy) {
  finished = true;
  inputEl.disabled = true;
  clearInterval(timerInterval);

  const player_name = nameEl.value.trim() || "anonymous";
  resultEl.textContent = `Done! ${wpm} WPM at ${accuracy}% accuracy.`;

  try {
    await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wpm, accuracy, player_name }),
    });
  } catch (e) {
    console.error("Failed to submit score", e);
  }
  loadLeaderboard();
}

async function loadLeaderboard() {
  try {
    const res = await fetch("/api/leaderboard");
    const rows = await res.json();
    leaderboardEl.innerHTML = rows
      .map(
        (r) =>
          `<li>${r.player_name} — ${Math.round(r.wpm)} WPM (${Math.round(
            r.accuracy
          )}% acc)</li>`
      )
      .join("");
  } catch (e) {
    console.error("Failed to load leaderboard", e);
  }
}

restartBtn.addEventListener("click", loadPrompt);

loadPrompt();
loadLeaderboard();
