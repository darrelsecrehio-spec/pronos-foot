// ============================================================
// PronosFoot — app.js
// Se connecte à l'API Flask déployée sur Render pour afficher
// les prédictions de matchs du jour, ligue par ligue.
// ============================================================

const API_BASE = "https://pronos-foot.onrender.com";

const leagueTabsEl = document.getElementById("leagueTabs");
const matchListEl = document.getElementById("matchList");
const emptyStateEl = document.getElementById("emptyState");
const statusLineEl = document.getElementById("statusLine");
const statusTextEl = document.getElementById("statusText");

let currentLeague = null;

function setStatus(mode, text) {
  statusLineEl.classList.remove("ok", "error", "loading");
  statusLineEl.classList.add(mode);
  statusTextEl.textContent = text;
}

async function loadLeagues() {
  setStatus("loading", "Connexion au serveur… (peut prendre jusqu'à 1 min si l'app dormait)");
  try {
    const res = await fetch(`${API_BASE}/ligues`);
    if (!res.ok) throw new Error(`Erreur serveur (${res.status})`);
    const ligues = await res.json();

    if (!Array.isArray(ligues) || ligues.length === 0) {
      throw new Error("Aucune ligue disponible");
    }

    leagueTabsEl.innerHTML = "";
    ligues.forEach((nom, i) => {
      const btn = document.createElement("button");
      btn.className = "league-tab" + (i === 0 ? " active" : "");
      btn.textContent = nom;
      btn.type = "button";
      btn.addEventListener("click", () => selectLeague(nom, btn));
      leagueTabsEl.appendChild(btn);
    });

    currentLeague = ligues[0];
    await loadPredictions(currentLeague);
  } catch (err) {
    setStatus("error", "Impossible de joindre le serveur. Réessaie dans un instant.");
    console.error(err);
  }
}

function selectLeague(nom, btn) {
  if (nom === currentLeague) return;
  currentLeague = nom;
  [...leagueTabsEl.children].forEach((el) => el.classList.remove("active"));
  btn.classList.add("active");
  loadPredictions(nom);
}

async function loadPredictions(nomLigue) {
  setStatus("loading", `Calcul des prédictions — ${nomLigue}…`);
  matchListEl.innerHTML = "";
  emptyStateEl.classList.add("hidden");

  try {
    const url = `${API_BASE}/predictions?ligue=${encodeURIComponent(nomLigue)}`;
    const res = await fetch(url);
    const data = await res.json();

    if (!res.ok || data.erreur) {
      throw new Error(data.erreur || `Erreur serveur (${res.status})`);
    }

    const matchs = data.matchs || data.matches || [];

    if (matchs.length === 0) {
      emptyStateEl.classList.remove("hidden");
      setStatus("ok", `${nomLigue} — aucun match aujourd'hui`);
      return;
    }

    matchs.forEach((m) => matchListEl.appendChild(renderMatchCard(m)));
    setStatus("ok", `${nomLigue} — ${matchs.length} match${matchs.length > 1 ? "s" : ""} du jour`);
  } catch (err) {
    setStatus("error", "Erreur lors du calcul des prédictions.");
    console.error(err);
  }
}

function pick(obj, keys, fallback = "") {
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  }
  return fallback;
}

function renderMatchCard(m) {
  const domicile = pick(m, ["domicile", "equipe_domicile", "home", "home_team"], "Domicile");
  const exterieur = pick(m, ["exterieur", "equipe_exterieur", "away", "away_team"], "Extérieur");
  const heure = pick(m, ["heure", "date", "kickoff", "date_heure"], "");

  let pDom = Number(pick(m, ["proba_domicile", "prob_domicile", "p_home", "home_win"], 0));
  let pNul = Number(pick(m, ["proba_nul", "prob_nul", "p_draw", "draw"], 0));
  let pExt = Number(pick(m, ["proba_exterieur", "prob_exterieur", "p_away", "away_win"], 0));

  if (pDom + pNul + pExt <= 1.5) {
    pDom *= 100; pNul *= 100; pExt *= 100;
  }
  const total = pDom + pNul + pExt || 1;
  pDom = Math.round((pDom / total) * 100);
  pNul = Math.round((pNul / total) * 100);
  pExt = 100 - pDom - pNul;

  const card = document.createElement("article");
  card.className = "match-card";
  card.innerHTML = `
    <div class="match-teams">
      <span class="team home">${escapeHtml(domicile)}</span>
      <span class="vs">VS</span>
      <span class="team away">${escapeHtml(exterieur)}</span>
    </div>
    ${heure ? `<div class="kickoff">${escapeHtml(String(heure))}</div>` : ""}
    <div class="prob-bar">
      <div class="prob-seg home" style="flex-grow:${pDom || 1}"><span>${pDom}%</span></div>
      <div class="prob-seg draw" style="flex-grow:${pNul || 1}"><span>${pNul}%</span></div>
      <div class="prob-seg away" style="flex-grow:${pExt || 1}"><span>${pExt}%</span></div>
    </div>
    <div class="prob-labels">
      <span>1 · Domicile</span>
      <span>N · Nul</span>
      <span>2 · Extérieur</span>
    </div>
  `;
  return card;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

loadLeagues();
