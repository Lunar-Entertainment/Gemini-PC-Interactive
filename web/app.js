// Gemini PC Interactive - Client Application Logic
(function () {
  let ws = null;
  let agentStatus = "IDLE";
  let isAuthenticated = false;
  let screenNaturalWidth = 1920;
  let screenNaturalHeight = 1080;
  let isGridActive = true;

  // DOM Elements
  const agentStatusBadge = document.getElementById("agentStatusBadge");
  const agentStatusText = document.getElementById("agentStatusText");
  const statResolution = document.getElementById("statResolution");
  const statCpu = document.getElementById("statCpu");
  const statRam = document.getElementById("statRam");
  const valActiveWindow = document.getElementById("valActiveWindow");
  const statGoogleAccount = document.getElementById("statGoogleAccount");
  const pillGoogleOne = document.getElementById("pillGoogleOne");
  const inputGoogleEmail = document.getElementById("inputGoogleEmail");

  const desktopScreen = document.getElementById("desktopScreen");
  const viewportWrapper = document.getElementById("viewportWrapper");
  const crosshairMarker = document.getElementById("crosshairMarker");
  const clickPulse = document.getElementById("clickPulse");
  const liveMouseCoords = document.getElementById("liveMouseCoords");

  const inputGoal = document.getElementById("inputGoal");
  const selectModel = document.getElementById("selectModel");
  const checkRequireApproval = document.getElementById("checkRequireApproval");
  const btnStartAgent = document.getElementById("btnStartAgent");
  const btnPauseResume = document.getElementById("btnPauseResume");
  const btnStopAgent = document.getElementById("btnStopAgent");
  const btnEmergencyStop = document.getElementById("btnEmergencyStop");

  const approvalBanner = document.getElementById("approvalBanner");
  const approvalActionText = document.getElementById("approvalActionText");
  const btnApprove = document.getElementById("btnApprove");
  const btnReject = document.getElementById("btnReject");

  const feedList = document.getElementById("feedList");
  const stepCounter = document.getElementById("stepCounter");
  const btnClearFeed = document.getElementById("btnClearFeed");

  const btnToggleGrid = document.getElementById("btnToggleGrid");
  const btnRefreshScreenshot = document.getElementById("btnRefreshScreenshot");
  const btnToggleStream = document.getElementById("btnToggleStream");
  let isStreaming = true;

  const settingsModal = document.getElementById("settingsModal");
  const btnSettingsModal = document.getElementById("btnSettingsModal");
  const btnCloseModal = document.getElementById("btnCloseModal");

  const btnSaveSettings = document.getElementById("btnSaveSettings");
  const inputMaxSteps = document.getElementById("inputMaxSteps");

  // Live Stream Control - Locked to 1 FPS for low latency and minimal overhead
  function startStream() {
    isStreaming = true;
    if (btnToggleStream) {
      btnToggleStream.classList.add("active");
      btnToggleStream.innerHTML = '<span class="stream-dot"></span> Live Stream';
    }
    desktopScreen.src = `/api/stream?fps=1&t=${Date.now()}`;
  }

  function pauseStream() {
    isStreaming = false;
    if (btnToggleStream) {
      btnToggleStream.classList.remove("active");
      btnToggleStream.innerHTML = '<span class="stream-dot" style="background:#94a3b8;box-shadow:none;"></span> Stream Paused';
    }
    desktopScreen.src = `/api/screenshot?grid=${isGridActive ? 1 : 0}&t=${Date.now()}`;
  }

  // Connect WebSocket
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[WS] Connected to Gemini PC Interactive server");
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleServerMessage(payload);
      } catch (err) {
        console.error("[WS] Message parsing error:", err);
      }
    };

    ws.onclose = () => {
      console.warn("[WS] Disconnected, reconnecting in 2s...");
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
    };
  }

  function handleServerMessage(msg) {
    const type = msg.type;
    const data = msg.data || {};

    switch (type) {
      case "init":
        isAuthenticated = Boolean(data.authenticated || data.has_api_key || (data.google_oauth && data.google_oauth.authenticated));
        updateStatus(data.status);
        if (data.system_info) updateSystemStats(data.system_info);

        if (data.google_oauth && data.google_oauth.authenticated) {
          isAuthenticated = true;
          renderOauthProfile(data.google_oauth);
          hideSettingsModal();
        } else if (data.google_account) {
          statGoogleAccount.textContent = data.google_account;
          if (inputGoogleEmail) inputGoogleEmail.value = data.google_account;
          hideSettingsModal();
        } else if (isAuthenticated) {
          statGoogleAccount.textContent = "AI Pro: Active";
          hideSettingsModal();
        } else {
          statGoogleAccount.textContent = "AI Pro: Connect";
          showSettingsModal();
        }
        break;

      case "oauth_success":
        isAuthenticated = true;
        renderOauthProfile(data);
        hideSettingsModal();
        addFeedItem("system", "GOOGLE ONE CONNECTED", `Signed in as ${data.email || "Google One User"} via OAuth.`);
        break;

      case "status_change":
        updateStatus(data.status);
        if (data.status === "AWAITING_APPROVAL" && data.pending) {
          showApprovalBanner(data.pending);
        } else {
          hideApprovalBanner();
        }
        break;

      case "screen_update":
        if (data.data_url) {
          desktopScreen.src = data.data_url;
        }
        if (data.resolution) {
          const parts = data.resolution.split("x");
          if (parts.length === 2) {
            screenNaturalWidth = parseInt(parts[0], 10);
            screenNaturalHeight = parseInt(parts[1], 10);
            statResolution.textContent = data.resolution;
          }
        }
        break;

      case "step_start":
        stepCounter.textContent = `Step: ${data.step} / ${data.max_steps}`;
        break;

      case "reasoning":
        addFeedItem("thought", "GEMINI REASONING", data.thought);
        break;

      case "action_proposed":
        addFeedItem("action", `PROPOSED: ${data.tool}`, JSON.stringify(data.arguments, null, 2));
        break;

      case "action_executing":
        // Flash pulse if coordinate click
        if (data.args && data.args.x !== undefined && data.args.y !== undefined) {
          triggerVisualClick(data.args.x, data.args.y);
        }
        break;

      case "action_result":
        addFeedItem("result", `EXECUTED: ${data.tool}`, `${data.output} (Duration: ${data.duration}s)`);
        break;

      case "task_completed":
        addFeedItem("system", data.success ? "TASK COMPLETED" : "TASK FINISHED", data.summary);
        break;

      case "system_info":
        updateSystemStats(data);
        break;

      case "grid_toggled":
        isGridActive = data.grid_overlay;
        btnToggleGrid.classList.toggle("active", isGridActive);
        requestScreenshot();
        break;

      case "key_updated":
        isAuthenticated = Boolean(data.authenticated);
        break;

      case "alert":
      case "error":
        addFeedItem("error", "SYSTEM ALERT", data.message);
        if (data.open_settings) {
          showSettingsModal();
        }
        break;
    }
  }

  function updateStatus(status) {
    agentStatus = status || "IDLE";
    agentStatusText.textContent = agentStatus;

    agentStatusBadge.className = "status-indicator-pill";
    if (agentStatus === "RUNNING") {
      agentStatusBadge.classList.add("running");
      btnStartAgent.disabled = true;
      btnPauseResume.disabled = false;
      btnPauseResume.textContent = "Pause";
      btnStopAgent.disabled = false;
    } else if (agentStatus === "PAUSED") {
      agentStatusBadge.classList.add("paused");
      btnPauseResume.textContent = "Resume";
    } else if (agentStatus === "AWAITING_APPROVAL") {
      agentStatusBadge.classList.add("paused");
    } else if (agentStatus === "STOPPED" || agentStatus === "ERROR") {
      agentStatusBadge.classList.add("stopped");
      btnStartAgent.disabled = false;
      btnPauseResume.disabled = true;
      btnStopAgent.disabled = true;
    } else {
      btnStartAgent.disabled = false;
      btnPauseResume.disabled = true;
      btnStopAgent.disabled = true;
    }
  }

  function updateSystemStats(info) {
    if (info.screen_resolution) statResolution.textContent = info.screen_resolution;
    if (info.cpu_usage_pct !== undefined) statCpu.textContent = `CPU: ${info.cpu_usage_pct}%`;
    if (info.ram_percent !== undefined) statRam.textContent = `RAM: ${info.ram_percent}% (${info.ram_used_gb}GB)`;
    if (info.active_window) valActiveWindow.textContent = info.active_window;
  }

  function addFeedItem(category, title, content) {
    const item = document.createElement("div");
    item.className = "feed-item";

    const header = document.createElement("div");
    header.className = "item-header";

    const badge = document.createElement("span");
    badge.className = `badge badge-${category}`;
    badge.textContent = title;

    const time = document.createElement("span");
    time.className = "timestamp";
    time.textContent = new Date().toLocaleTimeString();

    header.appendChild(badge);
    header.appendChild(time);
    item.appendChild(header);

    const body = document.createElement("div");
    if (category === "thought") {
      body.className = "thought-content";
      body.textContent = content;
    } else if (category === "action") {
      body.className = "action-snippet";
      body.textContent = content;
    } else if (category === "result") {
      body.className = "result-snippet";
      body.textContent = content;
    } else {
      body.className = "item-body";
      body.textContent = content;
    }

    item.appendChild(body);
    feedList.appendChild(item);
    feedList.scrollTop = feedList.scrollHeight;
  }

  function showApprovalBanner(pending) {
    approvalActionText.textContent = `Gemini wants to: ${pending.tool}(${JSON.stringify(pending.args)})`;
    approvalBanner.classList.remove("hidden");
  }

  function hideApprovalBanner() {
    approvalBanner.classList.add("hidden");
  }

  function triggerVisualClick(actualX, actualY) {
    const rect = desktopScreen.getBoundingClientRect();
    const scaleX = rect.width / screenNaturalWidth;
    const scaleY = rect.height / screenNaturalHeight;

    const clientX = rect.left + actualX * scaleX;
    const clientY = rect.top + actualY * scaleY;

    clickPulse.style.left = `${clientX}px`;
    clickPulse.style.top = `${clientY}px`;
    clickPulse.classList.remove("animate");
    void clickPulse.offsetWidth; // Trigger reflow
    clickPulse.classList.add("animate");
  }

  // Viewport Mouse Tracking & Interactive Coordinates
  viewportWrapper.addEventListener("mousemove", (e) => {
    const rect = desktopScreen.getBoundingClientRect();
    if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
      const relX = (e.clientX - rect.left) / rect.width;
      const relY = (e.clientY - rect.top) / rect.height;

      const screenX = Math.round(relX * screenNaturalWidth);
      const screenY = Math.round(relY * screenNaturalHeight);

      liveMouseCoords.textContent = `X: ${screenX} | Y: ${screenY}`;
      crosshairMarker.style.left = `${e.clientX}px`;
      crosshairMarker.style.top = `${e.clientY}px`;
    }
  });

  // Direct Click interaction from UI (for manual testing)
  viewportWrapper.addEventListener("click", (e) => {
    const rect = desktopScreen.getBoundingClientRect();
    if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
      const relX = (e.clientX - rect.left) / rect.width;
      const relY = (e.clientY - rect.top) / rect.height;

      const screenX = Math.round(relX * screenNaturalWidth);
      const screenY = Math.round(relY * screenNaturalHeight);

      // Perform a direct click via API if Shift is pressed
      if (e.shiftKey) {
        fetch("/api/manual-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "click", params: { x: screenX, y: screenY } })
        }).then(() => requestScreenshot());
      }
    }
  });

  // Action Buttons
  btnStartAgent.addEventListener("click", () => {
    const goal = inputGoal.value.trim();
    if (!goal) {
      inputGoal.focus();
      return;
    }
    if (!isAuthenticated) {
      showSettingsModal();
      return;
    }

    sendWs({
      action: "start",
      goal: goal,
      model: selectModel.value,
      require_approval: checkRequireApproval.checked
    });
  });

  btnPauseResume.addEventListener("click", () => {
    if (agentStatus === "RUNNING") {
      sendWs({ action: "pause" });
    } else if (agentStatus === "PAUSED") {
      sendWs({ action: "resume" });
    }
  });

  btnStopAgent.addEventListener("click", () => {
    sendWs({ action: "stop" });
  });

  btnEmergencyStop.addEventListener("click", () => {
    sendWs({ action: "stop" });
  });

  // Global ESC key emergency stop
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && agentStatus === "RUNNING") {
      sendWs({ action: "stop" });
    }
  });

  btnApprove.addEventListener("click", () => {
    hideApprovalBanner();
    sendWs({ action: "approve", approved: true });
  });

  btnReject.addEventListener("click", () => {
    hideApprovalBanner();
    sendWs({ action: "approve", approved: false });
  });

  // Presets
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      inputGoal.value = chip.getAttribute("data-prompt");
      inputGoal.focus();
    });
  });

  // Quick App Launchers
  document.querySelectorAll(".btn-quick").forEach((btn) => {
    btn.addEventListener("click", () => {
      const app = btn.getAttribute("data-app");
      fetch("/api/manual-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "open", params: { target: app } })
      }).then(() => {
        setTimeout(requestScreenshot, 1200);
      });
    });
  });

  btnToggleGrid.addEventListener("click", () => {
    sendWs({ action: "toggle_grid" });
  });

  btnRefreshScreenshot.addEventListener("click", () => {
    requestScreenshot();
  });

  btnClearFeed.addEventListener("click", () => {
    feedList.innerHTML = "";
  });

  // Modal handlers
  function showSettingsModal() {
    settingsModal.classList.remove("hidden");
  }
  function hideSettingsModal() {
    settingsModal.classList.add("hidden");
  }

  btnSettingsModal.addEventListener("click", showSettingsModal);
  btnCloseModal.addEventListener("click", hideSettingsModal);

  btnSaveSettings.addEventListener("click", () => {
    hideSettingsModal();
  });

  // OAuth UI elements
  const oauthUserProfile = document.getElementById("oauthUserProfile");
  const oauthLoginPrompt = document.getElementById("oauthLoginPrompt");
  const oauthAvatar = document.getElementById("oauthAvatar");
  const oauthUserName = document.getElementById("oauthUserName");
  const oauthUserEmail = document.getElementById("oauthUserEmail");
  const btnGoogleLogout = document.getElementById("btnGoogleLogout");
  const btnToggleOauthConfig = document.getElementById("btnToggleOauthConfig");
  const oauthConfigForm = document.getElementById("oauthConfigForm");
  const inputOauthClientId = document.getElementById("inputOauthClientId");
  const inputOauthClientSecret = document.getElementById("inputOauthClientSecret");
  const btnSaveOauthCreds = document.getElementById("btnSaveOauthCreds");

  function renderOauthProfile(profile) {
    if (!profile || !profile.email) return;
    if (oauthUserProfile) oauthUserProfile.classList.remove("hidden");
    if (oauthLoginPrompt) oauthLoginPrompt.classList.add("hidden");
    if (oauthUserName) oauthUserName.textContent = profile.name || "Google One User";
    if (oauthUserEmail) oauthUserEmail.textContent = profile.email;
    if (statGoogleAccount) statGoogleAccount.textContent = profile.email;
    if (oauthAvatar) {
      if (profile.picture) {
        oauthAvatar.innerHTML = `<img src="${profile.picture}" style="width:100%;height:100%;border-radius:50%;" alt="avatar">`;
      } else {
        oauthAvatar.textContent = (profile.name || profile.email || "G").charAt(0).toUpperCase();
      }
    }
  }

  // Copy URI buttons
  document.querySelectorAll(".btn-copy-uri").forEach((btn) => {
    btn.addEventListener("click", () => {
      const uri = btn.getAttribute("data-uri");
      navigator.clipboard.writeText(uri).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = orig; }, 1500);
      });
    });
  });

  if (btnToggleOauthConfig) {
    btnToggleOauthConfig.addEventListener("click", () => {
      oauthConfigForm.classList.toggle("hidden");
    });
  }

  if (btnSaveOauthCreds) {
    btnSaveOauthCreds.addEventListener("click", async () => {
      const cid = inputOauthClientId.value.trim();
      const csec = inputOauthClientSecret.value.trim();
      if (!cid || !csec) {
        alert("Please enter both Client ID and Client Secret.");
        return;
      }
      try {
        const res = await fetch("/api/auth/google/credentials", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ client_id: cid, client_secret: csec })
        });
        if (res.ok) {
          alert("Google OAuth credentials saved! You can now click 'Sign in with Google'.");
          oauthConfigForm.classList.add("hidden");
        } else {
          const err = await res.json();
          alert("Error saving credentials: " + (err.detail || "Unknown error"));
        }
      } catch (err) {
        alert("Request error: " + err.message);
      }
    });
  }

  if (btnGoogleLogout) {
    btnGoogleLogout.addEventListener("click", async () => {
      await fetch("/api/auth/google/logout", { method: "POST" });
      isAuthenticated = false;
      oauthUserProfile.classList.add("hidden");
      oauthLoginPrompt.classList.remove("hidden");
      statGoogleAccount.textContent = "AI Pro: Connect";
      addFeedItem("system", "LOGGED OUT", "Disconnected Google account.");
    });
  }

  if (btnToggleStream) {
    btnToggleStream.addEventListener("click", () => {
      if (isStreaming) {
        pauseStream();
      } else {
        startStream();
      }
    });
  }



  if (pillGoogleOne) {
    pillGoogleOne.addEventListener("click", showSettingsModal);
  }

  function sendWs(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }

  function requestScreenshot() {
    sendWs({ action: "request_screenshot" });
  }

  // Request system stats periodically
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendWs({ action: "request_system_info" });
    }
  }, 4000);

  // Pre-fetch status REST API immediately so login status is remembered instantly
  fetch("/api/status")
    .then(r => r.json())
    .then(data => {
      handleServerMessage({ type: "init", data: data });
    })
    .catch(() => {});

  // Initialize
  connectWebSocket();
  startStream();
})();
