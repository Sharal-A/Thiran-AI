/**
 * Thiran AI — Client Application
 * MarketIQ Aesthetic & Deterministic Learning Flow
 */

// State
const state = {
  currentLearner: null,
  activeView: "learning", // 'learning' | 'analytics'
  currentRun: null,
  activePipelineStage: 1, // 1: Assess, 2: Cognitive, 3: Intervention, 4: Practice/Gate, 5: Update
  topic: "recursion",
  familiarity: "beginner",
  streak: 0,
  confidence: "learning",
  isSidebarCollapsed: false,
  pomodoro: {
    mode: "focus", // 'focus' (25m) | 'short' (5m) | 'long' (15m)
    timeLeft: 25 * 60,
    timerId: null,
    isRunning: false,
  },
};

// Mode times in seconds
const POMO_TIMES = {
  focus: 25 * 60,
  short: 5 * 60,
  long: 15 * 60,
};

// API Client
const api = {
  async listLearners() {
    const res = await fetch("/api/learners");
    return res.json();
  },
  async login(username) {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Login failed");
    }
    return res.json();
  },
  async register(username, name) {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, name }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }
    return res.json();
  },
  async startSession(learnerId, topic, familiarity, sessionNumber = 1) {
    const res = await fetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        learner_id: learnerId,
        topic,
        familiarity,
        session_number: sessionNumber,
        stub: false,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start session");
    }
    return res.json();
  },
  async submitAnswer(runId, answer) {
    const res = await fetch("/api/session/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        answer,
        stub: false,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to submit answer");
    }
    return res.json();
  },
  async getAnalytics(learnerId) {
    const res = await fetch(`/api/analytics/${encodeURIComponent(learnerId)}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to load analytics");
    }
    return res.json();
  },
  async getRecentQuestions(learnerId) {
    const res = await fetch(`/api/recent-questions/${encodeURIComponent(learnerId)}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to load recent questions");
    }
    return res.json();
  },
  async getSession(runId) {
    const res = await fetch(`/api/session/${encodeURIComponent(runId)}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to load session details");
    }
    return res.json();
  },
};

// ============================================================================
// Initialization & Authentication
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  initUI();
  initPomodoro();
  checkPersistedLearner();
});

function initUI() {
  // Sidebar Collapse Toggle
  const collapseBtn = document.getElementById("collapse-sidebar-btn");
  if (collapseBtn) {
    collapseBtn.addEventListener("click", toggleSidebar);
  }

  // Navigation Items
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const view = item.getAttribute("data-view");
      switchView(view);
    });
  });

  // Logout Button
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", handleLogout);
  }

  // Auth Form Tabs
  const loginTab = document.getElementById("tab-login");
  const registerTab = document.getElementById("tab-register");
  if (loginTab && registerTab) {
    loginTab.addEventListener("click", () => setAuthTab("login"));
    registerTab.addEventListener("click", () => setAuthTab("register"));
  }

  // Auth Submit Button
  const authSubmitBtn = document.getElementById("auth-submit-btn");
  if (authSubmitBtn) {
    authSubmitBtn.addEventListener("click", handleAuthSubmit);
  }

  // Topic and Familiarity Selectors
  const startLearningBtn = document.getElementById("start-learning-btn");
  if (startLearningBtn) {
    startLearningBtn.addEventListener("click", startNewSession);
  }

  // Code Editor Submit Button
  const submitCodeBtn = document.getElementById("submit-code-btn");
  if (submitCodeBtn) {
    submitCodeBtn.addEventListener("click", handleSubmitAnswer);
  }

  // Exit Chat / New Topic Button
  const exitChatBtn = document.getElementById("exit-chat-btn");
  if (exitChatBtn) {
    exitChatBtn.addEventListener("click", handleExitChat);
  }

  // Quick reset / next actions
  const postNewTopicBtn = document.getElementById("post-action-new-topic");
  if (postNewTopicBtn) {
    postNewTopicBtn.addEventListener("click", () => {
      document.getElementById("post-session-modal").style.display = "none";
      document.getElementById("setup-session-card").style.display = "block";
      document.getElementById("active-interaction-card").style.display = "none";
      setPipelineStage(1);
    });
  }

  const postDepthBtn = document.getElementById("post-action-depth");
  if (postDepthBtn) {
    postDepthBtn.addEventListener("click", () => {
      document.getElementById("post-session-modal").style.display = "none";
      // Elevate familiarity
      const currentFam = state.familiarity.toLowerCase();
      if (currentFam.includes("begin") || currentFam.includes("easy")) {
        state.familiarity = "intermediate";
      } else if (currentFam.includes("inter") || currentFam.includes("medium")) {
        state.familiarity = "advanced";
      } else {
        state.familiarity = "mastery";
      }
      const famInput = document.getElementById("familiarity-input");
      if (famInput) famInput.value = state.familiarity;
      startNewSession();
    });
  }

  // Quick Preset Chips (Topic & Familiarity)
  document.querySelectorAll(".quick-chip-btn[data-fill]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const fillTarget = chip.getAttribute("data-fill");
      const val = chip.getAttribute("data-val");
      if (fillTarget === "topic") {
        const topicInput = document.getElementById("topic-input");
        if (topicInput) topicInput.value = val;
      } else if (fillTarget === "familiarity") {
        const famInput = document.getElementById("familiarity-input");
        if (famInput) famInput.value = val;
      }
    });
  });

  // Load quick learner profile pills into login modal
  loadQuickLearners();
}

function toggleSidebar() {
  const sidebar = document.querySelector(".app-sidebar");
  state.isSidebarCollapsed = !state.isSidebarCollapsed;
  if (state.isSidebarCollapsed) {
    sidebar.classList.add("collapsed");
  } else {
    sidebar.classList.remove("collapsed");
  }
}

async function loadQuickLearners() {
  try {
    const data = await api.listLearners();
    const container = document.getElementById("quick-pills-container");
    if (!container || !data.learners) return;

    container.innerHTML = "";
    data.learners.forEach((l) => {
      const btn = document.createElement("button");
      btn.className = "quick-pill";
      btn.textContent = `${l.name} (${l.learner_id})`;
      btn.addEventListener("click", () => {
        document.getElementById("auth-username-input").value = l.learner_id;
        handleAuthSubmit();
      });
      container.appendChild(btn);
    });
  } catch (err) {
    console.warn("Could not fetch quick learners:", err);
  }
}

function checkPersistedLearner() {
  const saved = localStorage.getItem("thiran_learner");
  if (saved) {
    try {
      state.currentLearner = JSON.parse(saved);
      applyLearnerProfile();
      document.getElementById("auth-overlay").style.display = "none";
      switchView("learning");
      return;
    } catch (e) {
      localStorage.removeItem("thiran_learner");
    }
  }
  // Show login overlay if not logged in
  document.getElementById("auth-overlay").style.display = "flex";
}

function setAuthTab(tab) {
  const loginTab = document.getElementById("tab-login");
  const registerTab = document.getElementById("tab-register");
  const nameGroup = document.getElementById("auth-name-group");
  const submitBtn = document.getElementById("auth-submit-btn");

  if (tab === "login") {
    loginTab.classList.add("active");
    registerTab.classList.remove("active");
    nameGroup.style.display = "none";
    submitBtn.textContent = "Log In & Continue";
  } else {
    loginTab.classList.remove("active");
    registerTab.classList.add("active");
    nameGroup.style.display = "flex";
    submitBtn.textContent = "Create Account";
  }
}

async function handleAuthSubmit() {
  const username = document.getElementById("auth-username-input").value.trim();
  const isRegister = document.getElementById("tab-register").classList.contains("active");
  const authErr = document.getElementById("auth-error-msg");
  authErr.style.display = "none";

  if (!username) {
    authErr.textContent = "Please enter your username.";
    authErr.style.display = "block";
    return;
  }

  try {
    let res;
    if (isRegister) {
      const name = document.getElementById("auth-name-input").value.trim() || username;
      res = await api.register(username, name);
    } else {
      res = await api.login(username);
    }

    state.currentLearner = res.profile;
    localStorage.setItem("thiran_learner", JSON.stringify(res.profile));
    applyLearnerProfile();
    document.getElementById("auth-overlay").style.display = "none";
    switchView("learning");
  } catch (err) {
    authErr.textContent = err.message || "Authentication error.";
    authErr.style.display = "block";
  }
}

function handleLogout() {
  state.currentLearner = null;
  state.currentRun = null;
  localStorage.removeItem("thiran_learner");
  document.getElementById("auth-overlay").style.display = "flex";
  document.getElementById("auth-username-input").value = "";
  setAuthTab("login");
}

function applyLearnerProfile() {
  if (!state.currentLearner) return;

  const nameEl = document.getElementById("sidebar-user-name");
  const idEl = document.getElementById("sidebar-user-id");
  const avatarEl = document.getElementById("sidebar-user-avatar");

  if (nameEl) nameEl.textContent = state.currentLearner.name;
  if (idEl) idEl.textContent = `@${state.currentLearner.learner_id}`;
  if (avatarEl) avatarEl.textContent = state.currentLearner.name.charAt(0).toUpperCase();

  // Update streak widget from profile or analytics
  fetchAndUpdateStreak();
  loadRecentQuestions();
}

async function fetchAndUpdateStreak() {
  if (!state.currentLearner) return;
  try {
    const data = await api.getAnalytics(state.currentLearner.learner_id);
    const streakVal = document.getElementById("sidebar-streak-value");
    if (streakVal) {
      streakVal.textContent = `${data.daily_streak} Day${data.daily_streak === 1 ? "" : "s"}`;
    }
  } catch (e) {
    console.warn("Could not fetch streak:", e);
  }
}

// ============================================================================
// View Management (Learning vs Analytics)
// ============================================================================

function switchView(viewName) {
  state.activeView = viewName;

  // Sidebar item active classes
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
    if (el.getAttribute("data-view") === viewName) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });

  const breadcrumb = document.getElementById("nav-breadcrumb-current");
  const learningView = document.getElementById("learning-view");
  const analyticsView = document.getElementById("analytics-view");

  if (viewName === "learning") {
    breadcrumb.textContent = "Adaptive Learning";
    learningView.style.display = "block";
    analyticsView.style.display = "none";
  } else if (viewName === "analytics") {
    breadcrumb.textContent = "Deterministic Analytics";
    learningView.style.display = "none";
    analyticsView.style.display = "block";
    loadAnalytics();
  }
}

// ============================================================================
// Learning Pipeline & Session Controller
// ============================================================================

function setPipelineStage(stageNum) {
  state.activePipelineStage = stageNum;

  // 1: Assess, 2: Cognitive, 3: Intervention, 4: Practice/Gate, 5: Update
  for (let i = 1; i <= 5; i++) {
    const stepEl = document.getElementById(`pipeline-step-${i}`);
    if (!stepEl) continue;

    stepEl.classList.remove("active", "completed");
    if (i < stageNum) {
      stepEl.classList.add("completed");
    } else if (i === stageNum) {
      stepEl.classList.add("active");
    }
  }

  // Update connector line width
  const connector = document.getElementById("step-connector-progress");
  if (connector) {
    const pct = ((stageNum - 1) / 4) * 100;
    connector.style.width = `${pct}%`;
  }
}

async function startNewSession() {
  if (!state.currentLearner) return;

  const topicInput = document.getElementById("topic-input");
  const famInput = document.getElementById("familiarity-input");
  const topic = (topicInput ? topicInput.value.trim() : "") || "recursion";
  const familiarity = (famInput ? famInput.value.trim() : "") || "beginner";
  state.topic = topic;
  state.familiarity = familiarity;

  const btn = document.getElementById("start-learning-btn");
  btn.disabled = true;
  btn.textContent = "Calibrating Assessment...";

  try {
    const res = await api.startSession(state.currentLearner.learner_id, topic, familiarity);
    state.currentRun = res;
    state.streak = res.streak || 0;
    state.confidence = res.confidence || "learning";

    // Update UI headers
    document.getElementById("active-topic-badge").textContent = topic.replace("_", " ");
    document.getElementById("topic-streak-badge").textContent = `Streak: ${state.streak}`;
    document.getElementById("topic-confidence-badge").textContent = `[${state.confidence.toUpperCase()}]`;

    // Switch view cards
    document.getElementById("setup-session-card").style.display = "none";
    document.getElementById("active-interaction-card").style.display = "block";
    document.getElementById("backward-loop-banner").classList.remove("active");
    document.getElementById("post-session-modal").style.display = "none";

    // Set stage to 1: Assess
    setPipelineStage(1);

    // Render Diagnostic Challenge
    renderDiagnosticChallenge(res.diagnostic_challenge);

    // Refresh Recent Questions list in sidebar
    loadRecentQuestions();

    // Clear and focus code editor
    const codeEditor = document.getElementById("student-code-input");
    codeEditor.value = "";
    codeEditor.focus();
  } catch (err) {
    alert("Error starting session: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Start Adaptive Session";
  }
}

async function loadRecentQuestions() {
  if (!state.currentLearner) return;
  try {
    const data = await api.getRecentQuestions(state.currentLearner.learner_id);
    renderRecentQuestions(data.recent_questions || []);
  } catch (err) {
    console.warn("Could not load recent questions:", err);
  }
}

function handleExitChat() {
  state.currentRun = null;
  document.getElementById("active-interaction-card").style.display = "none";
  document.getElementById("post-session-modal").style.display = "none";
  document.getElementById("backward-loop-banner").classList.remove("active");
  const setupCard = document.getElementById("setup-session-card");
  if (setupCard) {
    setupCard.style.display = "block";
    setupCard.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  setPipelineStage(1);
  const codeEditor = document.getElementById("student-code-input");
  if (codeEditor) codeEditor.value = "";
  loadRecentQuestions();
}

function renderRecentQuestions(questions) {
  const container = document.getElementById("recent-questions-list");
  const countBadge = document.getElementById("recent-questions-count");
  if (!container) return;

  if (countBadge) {
    countBadge.textContent = questions.length;
  }

  if (!questions || questions.length === 0) {
    container.innerHTML = `
      <div class="recent-empty-state">
        <span>No questions searched yet. Start a topic to practice!</span>
      </div>
    `;
    return;
  }

  container.innerHTML = questions
    .map((q) => {
      const topicDisplay = escapeHtml(q.topic.replace("_", " "));
      const questionSnippet = escapeHtml(q.question);
      let timeStr = "Recent";
      if (q.created_at) {
        const d = new Date(q.created_at * 1000);
        timeStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      }

      const isComplete = q.state === "complete" || q.verdict_status === "PASS";
      const statusPill = isComplete
        ? `<span class="recent-card-status complete">Done</span>`
        : `<span class="recent-card-status in-progress">In Progress</span>`;

      return `
        <div class="recent-question-card" data-run-id="${escapeHtml(q.run_id)}" data-topic="${escapeHtml(q.topic)}" title="Click to continue studying ${topicDisplay}">
          <div class="recent-card-top">
            <span class="recent-card-topic">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="12" r="10"/>
              </svg>
              ${topicDisplay}
            </span>
            <div style="display: flex; align-items: center; gap: 0.35rem;">
              ${statusPill}
              <span class="recent-card-time">${timeStr}</span>
            </div>
          </div>
          <div class="recent-card-question">${questionSnippet}</div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".recent-question-card").forEach((card) => {
    card.addEventListener("click", () => {
      const runId = card.getAttribute("data-run-id");
      const topic = card.getAttribute("data-topic");
      if (runId) {
        resumePreviousSession(runId, topic);
      } else if (topic) {
        selectRecentTopic(topic);
      }
    });
  });
}

async function resumePreviousSession(runId, topic) {
  if (!state.currentLearner) return;

  switchView("learning");
  try {
    const res = await api.getSession(runId);
    state.currentRun = res;
    state.topic = res.topic || topic || "recursion";
    state.familiarity = res.familiarity || "beginner";
    state.streak = res.streak || 0;
    state.confidence = res.confidence || "learning";

    // Update UI headers
    document.getElementById("active-topic-badge").textContent = state.topic.replace("_", " ");
    document.getElementById("topic-streak-badge").textContent = `Streak: ${state.streak}`;
    document.getElementById("topic-confidence-badge").textContent = `[${state.confidence.toUpperCase()}]`;

    // Switch view cards
    document.getElementById("setup-session-card").style.display = "none";
    document.getElementById("active-interaction-card").style.display = "block";
    document.getElementById("post-session-modal").style.display = "none";

    // Check backward loop state
    const backwardBanner = document.getElementById("backward-loop-banner");
    if (res.backward_loops && res.backward_loops.length > 0) {
      const latestLoop = res.backward_loops[res.backward_loops.length - 1];
      document.getElementById("backward-loop-strategy").textContent =
        `Escalated Strategy #${res.backward_loops.length}: ${latestLoop.escalated_strategy || "execution_trace_guard"}`;
      document.getElementById("backward-loop-detail").textContent =
        latestLoop.reason || "Student code blocked by Gating Judge. The system adaptively shifts instructional scaffolding.";
      backwardBanner.classList.add("active");
    } else {
      backwardBanner.classList.remove("active");
    }

    const codeEditor = document.getElementById("student-code-input");

    if (res.current_phase === "AWAIT_DIAGNOSTIC") {
      setPipelineStage(1);
      if (res.diagnostic_challenge) {
        renderDiagnosticChallenge(res.diagnostic_challenge);
      }
      codeEditor.value = (res.learner_answers && res.learner_answers[0] && res.learner_answers[0].text) || "";
      codeEditor.focus();
    } else if (res.current_phase === "AWAIT_SOCRATIC") {
      setPipelineStage(3);
      if (res.cognitive_analysis && res.intervention) {
        renderIntervention(res.cognitive_analysis, res.intervention);
      }
      const lastAnswer = res.learner_answers && res.learner_answers.length > 0
        ? res.learner_answers[res.learner_answers.length - 1].text
        : "";
      codeEditor.value = lastAnswer;
      codeEditor.focus();
    } else if (res.current_phase === "COMPLETE" || res.state === "complete") {
      setPipelineStage(5);
      if (res.verdict) {
        renderPassVerdict(res);
      } else {
        renderPassVerdict({ verdict: { status: "PASS", score: 4, feedback: "Concept mastered successfully." } });
      }
      document.getElementById("post-session-modal").style.display = "block";
      codeEditor.value = (res.learner_answers && res.learner_answers.length > 0 && res.learner_answers[res.learner_answers.length - 1].text) || "";
    } else {
      setPipelineStage(1);
      if (res.diagnostic_challenge) {
        renderDiagnosticChallenge(res.diagnostic_challenge);
      }
      codeEditor.focus();
    }
  } catch (err) {
    console.error("Error resuming session:", err);
    alert("Could not resume session: " + err.message);
  }
}

function selectRecentTopic(topic) {
  switchView("learning");
  const topicInput = document.getElementById("topic-input");
  if (topicInput) {
    topicInput.value = topic;
    topicInput.focus();
    const setupCard = document.getElementById("setup-session-card");
    if (setupCard) {
      setupCard.style.display = "block";
      document.getElementById("active-interaction-card").style.display = "none";
      document.getElementById("post-session-modal").style.display = "none";
      setupCard.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

function renderDiagnosticChallenge(diag) {
  const contentArea = document.getElementById("prompt-content-area");
  contentArea.innerHTML = `
    <div class="challenge-box">
      <div class="stage-badge-group" style="margin-bottom: 0.5rem;">
        <span class="badge badge-teal">Stage 1: Quick Concept Check</span>
        <span class="badge badge-gold">Estimated Competency: ${diag.prior_score}/4</span>
      </div>
      <h2 class="challenge-question-title">Diagnostic Challenge</h2>
      <p class="challenge-question-body">${escapeHtml(diag.challenge_question)}</p>
    </div>
  `;

  document.getElementById("card-stage-label").textContent = "Diagnostic Challenge";
  document.getElementById("editor-prompt-label").textContent = "Type your code / reasoning below:";
}

async function handleSubmitAnswer() {
  if (!state.currentRun) return;

  const codeInput = document.getElementById("student-code-input");
  const answer = codeInput.value.trim();
  if (!answer) {
    alert("Please write code or an explanation before submitting.");
    return;
  }

  const submitBtn = document.getElementById("submit-code-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Evaluating...</span>`;

  try {
    const res = await api.submitAnswer(state.currentRun.run_id, answer);

    if (res.stage === "INTERVENTION") {
      // Advance to Intervention / Practice Stage (Pipeline stage 3)
      setPipelineStage(3);
      renderIntervention(res.analysis, res.intervention);
      codeInput.value = "";
      codeInput.focus();
    } else if (res.status === "PASS") {
      // Completed successfully! Pipeline stage 5
      setPipelineStage(5);
      renderPassVerdict(res);
    } else if (res.status === "BLOCK") {
      // Backward Adaptation Loop Triggered!
      // Animate transition: Practice -> Fail -> ↩ Back to Assess/Intervene
      triggerBackwardAdaptationAnimation(res);
      codeInput.value = "";
      codeInput.focus();
    }
  } catch (err) {
    alert("Submission error: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Submit Solution</span> &rarr;`;
  }
}

function renderIntervention(analysis, intervention) {
  const contentArea = document.getElementById("prompt-content-area");

  let misconceptionsHtml = "";
  if (analysis.misconceptions && analysis.misconceptions.length > 0) {
    misconceptionsHtml = analysis.misconceptions
      .map((m) => `<strong>• Diagnosed Gap:</strong> ${escapeHtml(m.description)} (Concept: <code>${escapeHtml(m.concept)}</code>)`)
      .join("<br>");
  }

  let vizHtml = "";
  if (intervention.visualization) {
    vizHtml = `
      <div style="margin-top: 1rem;">
        <div style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">
          What Happened vs. What Should Happen:
        </div>
        <div class="ascii-visualization-box">${escapeHtml(intervention.visualization)}</div>
      </div>
    `;
  }

  contentArea.innerHTML = `
    <div class="intervention-grid">
      <div class="stage-badge-group">
        <span class="badge badge-teal">Stage 2 & 3: Cognitive Analysis & Targeted Practice</span>
        <span class="badge badge-gold">Strategy: ${escapeHtml(intervention.teaching_strategy_used || "analogy")}</span>
      </div>

      <div class="info-banner info-banner-mistake">
        <strong>Diagnosed Mistake:</strong> ${escapeHtml(intervention.mistake_diagnosis)}
        ${misconceptionsHtml ? `<div style="margin-top: 0.4rem;">${misconceptionsHtml}</div>` : ""}
      </div>

      <div class="info-banner info-banner-concept">
        <strong>Core Algorithmic Invariant:</strong> ${escapeHtml(intervention.core_dsa_concept)}
      </div>

      ${intervention.simple_example ? `
      <div class="info-banner info-banner-trace">
        <strong>Minimal Execution Trace:</strong><br>
        <code>${escapeHtml(intervention.simple_example)}</code>
      </div>` : ""}

      ${vizHtml}

      <div style="margin-top: 1rem; padding: 1.15rem; background: var(--gold-light); border: 1px solid var(--gold-border); border-radius: var(--radius-sm);">
        <h3 style="font-size: 1.1rem; color: #78350F; margin-bottom: 0.35rem; font-weight: 600;">
          Targeted Practice Challenge
        </h3>
        <p style="font-size: 0.95rem; color: #451A03; line-height: 1.5;">
          ${escapeHtml(intervention.problem_statement)}
        </p>
        ${intervention.buggy_code_or_prompt ? `
        <pre style="margin-top: 0.75rem; background: #FFFFFF; padding: 0.75rem; border-radius: 4px; font-family: var(--font-mono); font-size: 0.82rem; border: 1px solid var(--gold-border);">${escapeHtml(intervention.buggy_code_or_prompt)}</pre>
        ` : ""}
      </div>
    </div>
  `;

  document.getElementById("card-stage-label").textContent = "Personalized Intervention";
  document.getElementById("editor-prompt-label").textContent = "Write the corrected solution for the targeted practice:";
}

/**
 * Flagship Animated Backward Adaptation Feature:
 * Practice → Fail/Reassess → ↩ Back to Assess/Intervene → Strategy Escalation
 */
function triggerBackwardAdaptationAnimation(res) {
  const banner = document.getElementById("backward-loop-banner");
  const backwardDetail = document.getElementById("backward-loop-detail");
  const strategyPill = document.getElementById("backward-loop-strategy");

  const loopCount = res.backward_loop ? res.backward_loop.loop_count : 1;
  const strategy = res.backward_loop ? res.backward_loop.escalated_strategy : "execution_trace_guard";
  const reason = res.backward_loop ? res.backward_loop.reason : "Evaluation blocked.";

  backwardDetail.innerHTML = `
    <strong>Practice Blocked:</strong> ${escapeHtml(reason)}<br>
    The system deterministically adapts instructional scaffolding and routes ↩ backwards to <strong>Assess/Intervene</strong>.
  `;
  strategyPill.textContent = `Escalated Strategy #${loopCount}: ${strategy}`;

  // Trigger CSS pulse and display
  banner.classList.remove("active");
  void banner.offsetWidth; // trigger reflow
  banner.classList.add("active");

  // Visually route stepper back to Step 3 (Intervention/Scaffold)
  setPipelineStage(3);

  // Update streaks in UI
  document.getElementById("topic-streak-badge").textContent = `Streak: 0`;

  // Render the escalated intervention and ASCII diagram
  const escalated = res.escalated_intervention || {};
  renderIntervention({ misconceptions: [] }, {
    teaching_strategy_used: strategy,
    mistake_diagnosis: res.verdict ? res.verdict.feedback : "Mistake identified in practice code.",
    core_dsa_concept: escalated.core_dsa_concept || "Refined algorithmic invariant applied.",
    simple_example: escalated.simple_example || "",
    problem_statement: escalated.problem_statement || "Please debug and provide the correct invariant:",
    buggy_code_or_prompt: escalated.buggy_code_or_prompt || "",
    visualization: res.visualization || escalated.visualization || "",
  });
}

function renderPassVerdict(res) {
  const contentArea = document.getElementById("prompt-content-area");
  const verdict = res.verdict || {};

  contentArea.innerHTML = `
    <div class="verdict-box pass">
      <div class="verdict-title">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
        Session Passed! Mastered with Score ${verdict.score || 4}/4
      </div>
      <p style="font-size: 0.95rem; margin-top: 0.5rem; line-height: 1.5;">
        ${escapeHtml(verdict.feedback || "Excellent work! The core invariant has been successfully verified.")}
      </p>
      <div style="margin-top: 1rem; display: flex; gap: 0.75rem; align-items: center;">
        <span class="badge badge-green">Consecutive Streak: ${res.streak || 1}</span>
        <span class="badge badge-gold">Confidence: ${escapeHtml((res.confidence || "confident").toUpperCase())}</span>
      </div>
    </div>
  `;

  document.getElementById("card-stage-label").textContent = "Session Complete";
  document.getElementById("post-session-modal").style.display = "block";
  document.getElementById("topic-streak-badge").textContent = `Streak: ${res.streak || 1}`;

  // Refresh daily streak in sidebar
  fetchAndUpdateStreak();
}

// ============================================================================
// Deterministic Analytics Engine & BEFORE vs AFTER EVIDENCE Flagship
// ============================================================================

async function loadAnalytics() {
  if (!state.currentLearner) return;

  const container = document.getElementById("analytics-content-container");
  container.innerHTML = `<div style="text-align: center; padding: 3rem; color: var(--text-muted);">Loading deterministic analytics from SQLite...</div>`;

  try {
    const data = await api.getAnalytics(state.currentLearner.learner_id);
    renderAnalyticsDashboard(data);
  } catch (err) {
    container.innerHTML = `<div class="info-banner info-banner-mistake">Failed to load analytics: ${escapeHtml(err.message)}</div>`;
  }
}

function renderAnalyticsDashboard(data) {
  const container = document.getElementById("analytics-content-container");

  // 1. Calculate max minutes for 7-day chart scaling
  const maxMins = Math.max(...data.last_7_days.map((d) => d.minutes), 10);

  // 2. Build 7-day bars HTML
  const chartBarsHtml = data.last_7_days
    .map((d) => {
      const heightPct = Math.min(100, Math.max(8, (d.minutes / maxMins) * 100));
      return `
      <div class="day-bar-col">
        <div class="day-bar ${d.active ? "active" : ""}" style="height: ${heightPct}%;">
          <div class="day-bar-tooltip">${d.minutes} min</div>
        </div>
        <div class="day-label">${escapeHtml(d.label)}</div>
      </div>
    `;
    })
    .join("");

  // 3. Build Topics Cards HTML
  const topicsCardsHtml = data.topics
    .map((t) => {
      const confBadgeClass = t.confidence === "confident" ? "badge-gold" : t.confidence === "revisiting" ? "badge-amber" : "badge-teal";
      return `
      <div class="topic-card" onclick="selectTopicEvidence('${escapeHtml(t.topic)}')">
        <div class="topic-card-header">
          <div class="topic-name">${escapeHtml(t.topic.replace("_", " "))}</div>
          <span class="badge ${confBadgeClass}">[${escapeHtml(t.confidence.toUpperCase())}]</span>
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted);">
          Competency Score: <strong>${t.score}/4</strong> &bull; Resolved Gaps: <strong>${t.resolved_count}/${t.misconceptions_count || 1}</strong>
        </div>
        <div class="topic-stats-row">
          <div class="topic-stat-item">
            <span class="topic-stat-label">Streak</span>
            <span class="topic-stat-value">${t.streak}</span>
          </div>
          <div class="topic-stat-item">
            <span class="topic-stat-label">Attempts</span>
            <span class="topic-stat-value">${t.attempts}</span>
          </div>
          <div class="topic-stat-item">
            <span class="topic-stat-label">View Evidence</span>
            <span class="topic-stat-value" style="color: var(--teal-primary); font-size: 0.85rem;">Inspect &rarr;</span>
          </div>
        </div>
      </div>
    `;
    })
    .join("");

  container.innerHTML = `
    <!-- Quick Statistics (MarketIQ Style) -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-card-top">
          <span class="stat-card-label">Total Study Time</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        </div>
        <div class="stat-card-val">${escapeHtml(data.total_study_time_formatted)}</div>
        <div class="stat-card-sub">Recorded across all sessions</div>
      </div>

      <div class="stat-card">
        <div class="stat-card-top">
          <span class="stat-card-label">Daily Streak</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2c0 4-4 6-4 10a4 4 0 0 0 8 0c0-4-4-6-4-10z"/></svg>
        </div>
        <div class="stat-card-val">${data.daily_streak} Days</div>
        <div class="stat-card-sub">Consecutive active study</div>
      </div>

      <div class="stat-card">
        <div class="stat-card-top">
          <span class="stat-card-label">Study Sessions</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        </div>
        <div class="stat-card-val">${data.study_sessions}</div>
        <div class="stat-card-sub">Interactive learning runs</div>
      </div>

      <div class="stat-card">
        <div class="stat-card-top">
          <span class="stat-card-label">Topics Tracked</span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
        </div>
        <div class="stat-card-val">${data.topics.length}</div>
        <div class="stat-card-sub">In persistent SQLite memory</div>
      </div>
    </div>

    <!-- 7-Day Activity Chart Card -->
    <div class="chart-card">
      <div class="chart-header">
        <div>
          <h3 class="chart-title">Last 7 Days Study Activity</h3>
          <p style="font-size: 0.82rem; color: var(--text-muted);">Real session duration aggregated by date</p>
        </div>
        <span class="badge badge-teal">Live SQLite Timestamps</span>
      </div>
      <div class="seven-day-bars">
        ${chartBarsHtml}
      </div>
    </div>

    <!-- Topics Studied Grid -->
    <div style="margin-top: 2.5rem;">
      <h3 class="topics-section-title">Topics Studied & Progress</h3>
      <p style="font-size: 0.88rem; color: var(--text-muted); margin-bottom: 1.25rem;">
        Select any topic to inspect its <strong>Before vs After Evidence</strong> audit trail:
      </p>
      <div class="topics-grid">
        ${topicsCardsHtml}
      </div>
    </div>

    <!-- Evidence Container Anchor -->
    <div id="topic-evidence-container"></div>
  `;

  // Auto-select first topic to showcase Before vs After Evidence immediately
  window._analyticsData = data;
  if (data.topics && data.topics.length > 0) {
    selectTopicEvidence(data.topics[0].topic);
  }
}

/**
 * Flagship Feature: BEFORE vs AFTER EVIDENCE
 * Shows real SQLite proof of what the student could do before vs after Thiran
 */
window.selectTopicEvidence = function (topic) {
  const data = window._analyticsData;
  if (!data) return;

  const container = document.getElementById("topic-evidence-container");
  if (!container) return;

  const topicEvidence = (data.before_after_evidence && data.before_after_evidence[topic]) || [];
  const topicMeta = data.topics.find((t) => t.topic === topic) || { topic, score: 4, confidence: "confident", streak: 1, attempts: 1 };

  if (topicEvidence.length === 0) {
    container.innerHTML = `
      <div class="evidence-section">
        <div class="evidence-header">
          <div class="evidence-header-title">
            <h3>Evidence Audit Trail: ${escapeHtml(topic.replace("_", " "))}</h3>
          </div>
        </div>
        <p style="color: var(--text-muted); font-size: 0.92rem;">
          No direct before/after evidence recorded for this topic yet. Complete a learning run to generate persistent evidence.
        </p>
      </div>
    `;
    return;
  }

  const evidenceCardsHtml = topicEvidence
    .map((ev, idx) => {
      let vizBox = "";
      if (ev.after.visualization) {
        vizBox = `
        <div style="margin-top: 0.75rem;">
          <div style="font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase;">Correct Trace Model:</div>
          <div class="ascii-visualization-box" style="max-height: 180px; font-size: 0.75rem;">${escapeHtml(ev.after.visualization)}</div>
        </div>`;
      }

      const loopsBadge = ev.backward_loops_count > 0
        ? `<span class="badge badge-amber">↩ ${ev.backward_loops_count} Backward Loop(s)</span>`
        : `<span class="badge badge-green">Direct Resolution</span>`;

      return `
      <div class="evidence-card">
        <div class="evidence-card-bar">
          <div>
            <strong>Session Run:</strong> <code>${escapeHtml(ev.run_id)}</code> &bull; ${escapeHtml(ev.date || "Completed")}
          </div>
          <div style="display: flex; gap: 0.5rem;">
            ${loopsBadge}
            <span class="badge badge-teal">Verdict: ${escapeHtml(ev.after.verdict_status)} (${ev.after.verdict_score}/4)</span>
          </div>
        </div>

        <div class="evidence-split-grid">
          <!-- BEFORE: Flawed Code & Diagnosed Misconceptions -->
          <div class="evidence-col evidence-col-before">
            <div class="col-header">
              <span class="col-title before">1. BEFORE THIRAN</span>
              <span class="badge badge-amber">Initial Flawed Attempt</span>
            </div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem;">
              <strong>Diagnostic Task:</strong> ${escapeHtml(ev.before.challenge)}
            </p>
            <div class="code-snippet-box flawed">${escapeHtml(ev.before.code || "# No code provided")}</div>
            <div class="evidence-insight gap">
              <strong>Diagnosed Cognitive Gap:</strong><br>
              ${escapeHtml(ev.before.diagnosed_gap)}
            </div>
          </div>

          <!-- AFTER: Improved Code & Mastered Invariant -->
          <div class="evidence-col evidence-col-after">
            <div class="col-header">
              <span class="col-title after">2. AFTER INTERVENTION</span>
              <span class="badge badge-green">Mastery Verified</span>
            </div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem;">
              <strong>Instructional Scaffolding:</strong> ${escapeHtml(ev.after.strategy_used || "Conceptual Analogy & Guard Trace")}
            </p>
            <div class="code-snippet-box passed">${escapeHtml(ev.after.code || "# Mastered solution recorded")}</div>
            <div class="evidence-insight gain">
              <strong>Evaluation Proof:</strong><br>
              ${escapeHtml(ev.after.feedback)}
            </div>
            ${vizBox}
          </div>
        </div>
      </div>
    `;
    })
    .join("");

  container.innerHTML = `
    <div class="evidence-section">
      <div class="evidence-header">
        <div class="evidence-header-title">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--teal-primary)" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <h3>BEFORE vs. AFTER EVIDENCE: <span style="text-transform: capitalize;">${escapeHtml(topic.replace("_", " "))}</span></h3>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <span class="badge badge-gold">Score: ${topicMeta.score}/4</span>
          <span class="badge badge-teal">Streak: ${topicMeta.streak}</span>
        </div>
      </div>
      <p style="font-size: 0.88rem; color: var(--text-muted); margin-bottom: 1.5rem;">
        Audited historical progression extracted deterministically from SQLite <code>versions</code> table.
        Shows exact verbatim code evidence comparing opening diagnostic misconceptions with post-intervention breakthroughs.
      </p>
      ${evidenceCardsHtml}
    </div>
  `;

  // Smoothly scroll into evidence section
  container.scrollIntoView({ behavior: "smooth", block: "start" });
};

// ============================================================================
// Pomodoro Timer Controller
// ============================================================================

function initPomodoro() {
  const startBtn = document.getElementById("pomo-start-btn");
  const resetBtn = document.getElementById("pomo-reset-btn");
  const modeBtns = document.querySelectorAll(".pomo-mode-btn");

  if (startBtn) {
    startBtn.addEventListener("click", togglePomodoroTimer);
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", resetPomodoroTimer);
  }

  modeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-mode");
      setPomodoroMode(mode);
    });
  });

  updatePomodoroDisplay();
}

function setPomodoroMode(mode) {
  if (state.pomodoro.isRunning) {
    clearInterval(state.pomodoro.timerId);
    state.pomodoro.isRunning = false;
    document.getElementById("pomo-start-btn").textContent = "Start";
  }

  state.pomodoro.mode = mode;
  state.pomodoro.timeLeft = POMO_TIMES[mode] || POMO_TIMES.focus;

  document.querySelectorAll(".pomo-mode-btn").forEach((b) => {
    if (b.getAttribute("data-mode") === mode) {
      b.classList.add("active");
    } else {
      b.classList.remove("active");
    }
  });

  updatePomodoroDisplay();
}

function togglePomodoroTimer() {
  const startBtn = document.getElementById("pomo-start-btn");
  if (state.pomodoro.isRunning) {
    clearInterval(state.pomodoro.timerId);
    state.pomodoro.isRunning = false;
    startBtn.textContent = "Start";
  } else {
    state.pomodoro.isRunning = true;
    startBtn.textContent = "Pause";
    state.pomodoro.timerId = setInterval(() => {
      if (state.pomodoro.timeLeft > 0) {
        state.pomodoro.timeLeft--;
        updatePomodoroDisplay();
      } else {
        clearInterval(state.pomodoro.timerId);
        state.pomodoro.isRunning = false;
        startBtn.textContent = "Start";
        playChime();
        alert(`Pomodoro ${state.pomodoro.mode === "focus" ? "Focus" : "Break"} Session Complete! Take a rest.`);
      }
    }, 1000);
  }
}

function resetPomodoroTimer() {
  if (state.pomodoro.isRunning) {
    clearInterval(state.pomodoro.timerId);
    state.pomodoro.isRunning = false;
    document.getElementById("pomo-start-btn").textContent = "Start";
  }
  state.pomodoro.timeLeft = POMO_TIMES[state.pomodoro.mode] || POMO_TIMES.focus;
  updatePomodoroDisplay();
}

function updatePomodoroDisplay() {
  const display = document.getElementById("pomodoro-time-display");
  if (!display) return;
  const mins = Math.floor(state.pomodoro.timeLeft / 60);
  const secs = state.pomodoro.timeLeft % 60;
  display.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function playChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.2);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 1.2);
  } catch (e) {
    // AudioContext blocked or not supported
  }
}

// Utility
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
