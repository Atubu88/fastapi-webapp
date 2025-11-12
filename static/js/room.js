(() => {
  "use strict";

  const container = document.getElementById("game-screen");
  const roomError = document.getElementById("room-error");

  if (!container) {
    return;
  }

  const roomConfig = {
    roomId: container.dataset.roomId || "",
    joinUrl: container.dataset.joinUrl || "",
    quizTitle: container.dataset.quizTitle || "",
  };

  const templateCache = new Map();
  let currentState = null;
  let socket = null;
  let gameInProgress = false;
  let players = [];
  let lastQuestionContext = null;
  const responseStats = new Map();

  const serverClock = {
    offset: 0,
    sync(serverTimeIso) {
      if (!serverTimeIso) {
        return;
      }
      const serverTimestamp = Date.parse(serverTimeIso);
      if (Number.isNaN(serverTimestamp)) {
        return;
      }
      const localNow = Date.now();
      this.offset = serverTimestamp - localNow;
    },
    now() {
      return Date.now() + this.offset;
    },
  };

  const countdownTimer = (() => {
    let timerId = null;
    let endTime = 0;
    let element = null;

    const cancelTimer = () => {
      if (timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
    };

    const render = () => {
      if (!element || !endTime) {
        cancelTimer();
        return;
      }

      const remaining = endTime - serverClock.now();
      if (remaining <= 0) {
        element.textContent = "00:00";
        element.classList.add("is-warning");
        cancelTimer();
        return;
      }

      const totalSeconds = Math.max(0, Math.ceil(remaining / 1000));
      const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
      const seconds = String(totalSeconds % 60).padStart(2, "0");
      element.textContent = `${minutes}:${seconds}`;
      if (totalSeconds <= 10) {
        element.classList.add("is-warning");
      } else {
        element.classList.remove("is-warning");
      }
    };

    return {
      start(targetElement, startIso, durationSeconds) {
        element = targetElement ?? null;
        if (!element) {
          this.clear();
          return;
        }

        const start = Date.parse(startIso);
        const duration = Number(durationSeconds);
        if (Number.isNaN(start) || !duration || duration <= 0) {
          this.clear();
          return;
        }

        endTime = start + duration * 1000;
        element.hidden = false;
        element.classList.remove("is-warning");
        cancelTimer();
        render();
        timerId = window.setInterval(render, 250);
      },
      clear() {
        cancelTimer();
        endTime = 0;
        if (element) {
          element.textContent = "00:00";
          element.hidden = true;
          element.classList.remove("is-warning");
        }
        element = null;
      },
    };
  })();

  const buildQrUrl = (url) =>
    `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;

  const formatSeconds = (value, { emptyAsDash = false } = {}) => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return emptyAsDash ? "—" : "0.0 с";
    }
    const rounded = value >= 100 ? value.toFixed(0) : value.toFixed(1);
    return `${rounded} с`;
  };

  const buildScoreboardMeta = (entry) => {
    const answered = Number.isFinite(entry?.answered_count)
      ? Number(entry.answered_count)
      : 0;
    const hasAnswers = answered > 0;
    const average = hasAnswers
      ? formatSeconds(entry?.average_response_time, { emptyAsDash: true })
      : "—";
    const total = hasAnswers
      ? formatSeconds(entry?.total_response_time, { emptyAsDash: true })
      : "—";
    const best = Number.isFinite(entry?.best_response_time)
      ? formatSeconds(entry.best_response_time, { emptyAsDash: true })
      : null;
    const parts = [`ответов: ${answered}`];
    parts.push(`ср.: ${average}`);
    parts.push(`сумм.: ${total}`);
    if (best) {
      parts.push(`рекорд: ${best}`);
    }
    return parts.join(", ");
  };

  const resetResponseStats = () => {
    responseStats.clear();
  };

  const ensurePlayerStats = (player) => {
    if (!responseStats.has(player)) {
      responseStats.set(player, {
        count: 0,
        total: 0,
        best: null,
        worst: null,
      });
    }
    return responseStats.get(player);
  };

  const isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);

  const isSameTime = (a, b) =>
    isFiniteNumber(a) && isFiniteNumber(b) && Math.abs(a - b) <= 1e-6;

  const updateResponseStats = (results = []) => {
    let bestTime = null;
    const bestPlayers = new Set();

    results.forEach((item) => {
      const time = Number(item?.response_time);
      if (!Number.isFinite(time)) {
        return;
      }

      const stats = ensurePlayerStats(item.player);
      stats.count += 1;
      stats.total += time;
      stats.best = stats.best === null ? time : Math.min(stats.best, time);
      stats.worst = stats.worst === null ? time : Math.max(stats.worst, time);

      if (bestTime === null || time < bestTime - 1e-6) {
        bestTime = time;
        bestPlayers.clear();
        bestPlayers.add(item.player);
      } else if (isSameTime(time, bestTime)) {
        bestPlayers.add(item.player);
      }
    });

    return { bestTime, bestPlayers };
  };

  const buildTimingSummary = () => {
    const perPlayer = Array.from(responseStats.entries()).map(([player, stats]) => ({
      player,
      count: stats.count,
      total: stats.total,
      average: stats.count ? stats.total / stats.count : null,
      best: stats.best,
      worst: stats.worst,
    }));

    let fastest = null;
    perPlayer.forEach((item) => {
      if (!isFiniteNumber(item.best)) {
        return;
      }
      if (!fastest || item.best < fastest.value - 1e-6) {
        fastest = { player: item.player, value: item.best };
      } else if (fastest && isSameTime(item.best, fastest.value)) {
        fastest.players ??= new Set([fastest.player]);
        fastest.players.add(item.player);
      }
    });

    if (fastest?.players) {
      fastest.players = Array.from(fastest.players);
    }

    return { perPlayer, fastest };
  };

  const enhanceScoreboard = (scoreboard = [], summary) => {
    const fastestValue = summary?.fastest?.value;
    const fastestPlayers = summary?.fastest?.players || [];
    const fastestPlayer = summary?.fastest?.player;
    const fastestCandidates = new Set([
      ...(typeof fastestPlayer === "string" ? [fastestPlayer] : []),
      ...fastestPlayers,
    ]);

    return scoreboard.map((entry) => {
      const stats = responseStats.get(entry.player) ?? {
        count: entry.answered_count ?? 0,
        total: entry.total_response_time ?? 0,
        best: null,
        worst: null,
      };

      const count = Number.isFinite(stats.count) ? stats.count : 0;
      const total = Number.isFinite(stats.total) ? stats.total : 0;
      const best = isFiniteNumber(stats.best) ? stats.best : null;
      const worst = isFiniteNumber(stats.worst) ? stats.worst : null;
      const average = count ? total / count : null;

      const hasRecord =
        best !== null &&
        isFiniteNumber(fastestValue) &&
        (isSameTime(best, fastestValue) || fastestCandidates.has(entry.player));

      return {
        ...entry,
        answered_count: count,
        total_response_time: total,
        average_response_time: average,
        best_response_time: best,
        worst_response_time: worst,
        has_fastest_record: hasRecord,
      };
    });
  };

  const prepareResultsPayload = (payload = {}) => {
    const results = Array.isArray(payload.results) ? payload.results : [];
    const { bestTime, bestPlayers } = updateResponseStats(results);
    const summary = buildTimingSummary();

    const enhancedResults = results.map((item) => {
      const responseTime = Number(item?.response_time);
      const formattedTime = Number.isFinite(responseTime)
        ? formatSeconds(responseTime, { emptyAsDash: true })
        : "—";
      const isFastest =
        Number.isFinite(responseTime) &&
        (bestPlayers.has(item.player) || isSameTime(responseTime, bestTime));
      return {
        ...item,
        response_time: Number.isFinite(responseTime) ? responseTime : null,
        response_time_formatted: formattedTime,
        is_fastest: Boolean(isFastest),
      };
    });

    const enhancedScoreboard = enhanceScoreboard(payload.scoreboard || [], summary);

    return {
      ...payload,
      results: enhancedResults,
      results_fastest_time: bestTime,
      scoreboard: enhancedScoreboard,
      timing_summary: summary,
    };
  };

  const prepareFinalPayload = (payload = {}) => {
    const summary = buildTimingSummary();
    const enhancedScoreboard = enhanceScoreboard(payload.scoreboard || [], summary);
    return {
      ...payload,
      scoreboard: enhancedScoreboard,
      timing_summary: summary,
    };
  };

  const fetchTemplate = async (state) => {
    if (templateCache.has(state)) {
      return templateCache.get(state);
    }

    const response = await fetch(`/screen/fragments/${state}`);
    if (!response.ok) {
      throw new Error(`Не удалось загрузить экран: ${state}`);
    }
    const html = await response.text();
    templateCache.set(state, html);
    return html;
  };

  const waitForAnimation = (element, className) =>
    new Promise((resolve) => {
      if (!element) {
        resolve();
        return;
      }

      let resolved = false;
      const finalize = () => {
        if (!resolved) {
          resolved = true;
          element.removeEventListener("animationend", finalize);
          resolve();
        }
      };

      element.addEventListener("animationend", finalize, { once: true });
      requestAnimationFrame(() => {
        element.classList.add(className);
        const { animationDuration, animationDelay } = getComputedStyle(element);
        const duration = parseFloat(animationDuration) + parseFloat(animationDelay);
        if (!duration || Number.isNaN(duration)) {
          finalize();
        } else {
          setTimeout(finalize, duration * 1000 + 32);
        }
      });
    });

  const swapContent = async (html) => {
    const previous = container.firstElementChild;
    if (previous) {
      await waitForAnimation(previous, "is-leaving");
    }

    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const fragment = template.content.cloneNode(true);

    container.innerHTML = "";
    container.appendChild(fragment);

    const next = container.firstElementChild;
    if (next) {
      next.classList.remove("is-leaving");
      await waitForAnimation(next, "is-visible");
    }
  };

  const changeState = async (state) => {
    if (currentState === state) {
      return false;
    }

    const html = await fetchTemplate(state);
    await swapContent(html);
    currentState = state;
    return true;
  };

  const ensureState = async (state, data = {}) => {
    await changeState(state);
    stateHandlers[state]?.(data);
  };

  const safeEnsureState = (state, data = {}) =>
    ensureState(state, data).catch((error) => {
      console.error(`Не удалось отобразить экран "${state}"`, error);
      showError("Не удалось отобразить экран. Попробуйте обновить страницу.");
    });

  const renderPlayers = (playersList) => {
    players = playersList;
    safeEnsureState("lobby", { players });
  };

  const stateHandlers = {
    lobby(data) {
      countdownTimer.clear();
      const root = container.querySelector(".lobby-screen");
      if (!root) {
        return;
      }

      const codeEl = root.querySelector('[data-element="room-code"]');
      const linkEl = root.querySelector('[data-element="room-link"]');
      const qrEl = root.querySelector('[data-element="room-qr"]');
      const quizTitleEl = root.querySelector('[data-element="quiz-title"]');
      const playersEl = root.querySelector('[data-element="players"]');
      const startBtn = root.querySelector('[data-action="start-game"]');

      if (codeEl) {
        codeEl.textContent = roomConfig.roomId;
      }
      if (linkEl) {
        linkEl.href = roomConfig.joinUrl;
        linkEl.textContent = roomConfig.joinUrl;
      }
      if (qrEl) {
        qrEl.src = buildQrUrl(roomConfig.joinUrl);
        qrEl.alt = "QR-код для подключения";
      }
      if (quizTitleEl) {
        quizTitleEl.textContent = roomConfig.quizTitle;
      }

      if (playersEl) {
        playersEl.innerHTML = "";
        (data.players || []).forEach((player) => {
          const li = document.createElement("li");
          li.textContent = player;
          playersEl.appendChild(li);
        });
      }

      if (startBtn) {
        if (!startBtn.dataset.bound) {
          startBtn.addEventListener("click", handleStartGame);
          startBtn.dataset.bound = "true";
        }
        startBtn.disabled = gameInProgress || players.length === 0;
      }
    },
    question(data) {
      const root = container.querySelector(".question-screen");
      if (!root) {
        countdownTimer.clear();
        return;
      }

      const progressEl = root.querySelector('[data-element="progress"]');
      const titleEl = root.querySelector('[data-element="title"]');
      const subtitleEl = root.querySelector('[data-element="subtitle"]');
      const optionsList = root.querySelector('[data-element="options"]');
      const resultsSection = root.querySelector('[data-section="results"]');
      const answersList = root.querySelector('[data-element="answers"]');
      const scoreboardList = root.querySelector('[data-element="scoreboard"]');
      const timerEl = root.querySelector('[data-element="timer"]');
      const questionBestTimeEl = root.querySelector(
        '[data-element="question-best-time"]'
      );
      const quizBestTimeEl = root.querySelector('[data-element="quiz-best-time"]');

      if (data.question) {
        const { question, question_number: number, total_questions: total } = data;
        const questionTitle = question.title || question.text || "Вопрос";
        const subtitle = question.description || (question.title ? question.text : "");

        if (progressEl) {
          progressEl.textContent = `Вопрос ${number} из ${total}`;
        }
        if (titleEl) {
          titleEl.textContent = questionTitle;
        }
        if (subtitleEl) {
          subtitleEl.textContent = subtitle || "";
          subtitleEl.hidden = !subtitle;
        }

        if (optionsList) {
          optionsList.innerHTML = "";
          (question.options || []).forEach((option) => {
            const item = document.createElement("li");
            item.className = "question-screen__option";
            item.innerHTML = `<span class="question-screen__option-id">${option.id}</span>${option.text}`;
            optionsList.appendChild(item);
          });
        }

        lastQuestionContext = {
          progress: progressEl ? progressEl.textContent : "",
          title: questionTitle,
          subtitle,
          options: (question.options || []).map((option) => ({
            id: option.id,
            text: option.text,
          })),
        };
      } else if (lastQuestionContext) {
        if (progressEl) {
          progressEl.textContent = lastQuestionContext.progress;
        }
        if (titleEl) {
          titleEl.textContent = lastQuestionContext.title;
        }
        if (subtitleEl) {
          subtitleEl.textContent = lastQuestionContext.subtitle || "";
          subtitleEl.hidden = !lastQuestionContext.subtitle;
        }
        if (optionsList && optionsList.children.length === 0) {
          lastQuestionContext.options.forEach((option) => {
            const item = document.createElement("li");
            item.className = "question-screen__option";
            item.innerHTML = `<span class="question-screen__option-id">${option.id}</span>${option.text}`;
            optionsList.appendChild(item);
          });
        }
      }

      const startedAt = data?.question_started_at;
      const duration = data?.question_duration;
      const serverTime = data?.server_time;
      if (serverTime) {
        serverClock.sync(serverTime);
      } else if (startedAt) {
        serverClock.sync(startedAt);
      }

      if (resultsSection) {
        if (data.results) {
          resultsSection.classList.add("is-visible");
        } else {
          resultsSection.classList.remove("is-visible");
        }
      }

      if (timerEl) {
        if (data.results || !startedAt || !duration) {
          countdownTimer.clear();
          timerEl.hidden = true;
        } else {
          countdownTimer.start(timerEl, startedAt, duration);
        }
      } else if (data.results || !startedAt || !duration) {
        countdownTimer.clear();
      }

      if (answersList) {
        answersList.innerHTML = "";
        (data.results || []).forEach((item) => {
          const li = document.createElement("li");
          li.className = "question-screen__answer";
          if (item.is_fastest) {
            li.classList.add("is-fastest");
          }

          const status = document.createElement("span");
          status.className = "question-screen__answer-status";
          status.textContent = item.is_correct ? "✅" : "❌";

          const player = document.createElement("span");
          player.className = "question-screen__answer-player";
          player.textContent = item.player;

          const answer = document.createElement("span");
          answer.className = "question-screen__answer-value";
          answer.textContent = item.answer ?? "—";

          const time = document.createElement("span");
          time.className = "question-screen__answer-time";
          time.textContent = item.response_time_formatted ?? "—";

          const score = document.createElement("span");
          score.className = "question-screen__answer-score";
          score.textContent = item.score;

          li.append(status, player, answer, time, score);
          answersList.appendChild(li);
        });
      }

      if (scoreboardList) {
        scoreboardList.innerHTML = "";
        const fastestRecord = data?.timing_summary?.fastest?.value ?? null;
        (data.scoreboard || []).forEach((entry, index) => {
          const li = document.createElement("li");
          if (entry.has_fastest_record && fastestRecord !== null) {
            li.classList.add("has-record");
          }
          const meta = buildScoreboardMeta(entry);
          li.innerHTML = `
            <span>${index + 1}.</span>
            <strong>${entry.player}</strong>
            <span class="scoreboard__score">
              <span class="scoreboard__score-value">${entry.score}</span>
              <span class="scoreboard__meta">${meta}</span>
            </span>
          `.trim();
          scoreboardList.appendChild(li);
        });
      }

      if (questionBestTimeEl) {
        const bestTime = data?.results_fastest_time;
        questionBestTimeEl.textContent = isFiniteNumber(bestTime)
          ? formatSeconds(bestTime)
          : "—";
      }

      if (quizBestTimeEl) {
        const quizBest = data?.timing_summary?.fastest?.value;
        const quizBestPlayer = data?.timing_summary?.fastest?.player;
        const quizBestExtra = data?.timing_summary?.fastest?.players || [];
        if (isFiniteNumber(quizBest)) {
          const formatted = formatSeconds(quizBest);
          const players = new Set();
          if (quizBestPlayer) {
            players.add(quizBestPlayer);
          }
          quizBestExtra.forEach((player) => {
            if (typeof player === "string") {
              players.add(player);
            }
          });
          if (players.size > 0) {
            quizBestTimeEl.textContent = `${formatted} — ${Array.from(players).join(", ")}`;
          } else {
            quizBestTimeEl.textContent = formatted;
          }
        } else {
          quizBestTimeEl.textContent = "—";
        }
      }
    },
    final(data) {
      countdownTimer.clear();
      if (data?.server_time) {
        serverClock.sync(data.server_time);
      }
      const root = container.querySelector(".final-screen");
      if (!root) {
        return;
      }

      const quizTitleEl = root.querySelector('[data-element="quiz-title"]');
      const scoreboardList = root.querySelector('[data-element="final-scoreboard"]');
      const recordValueEl = root.querySelector('[data-element="timing-summary-best"]');
      const recordPlayerEl = root.querySelector('[data-element="timing-summary-best-player"]');

      if (quizTitleEl) {
        quizTitleEl.textContent = roomConfig.quizTitle;
      }

      if (scoreboardList && window.Leaderboard) {
        window.Leaderboard.render(scoreboardList, data.scoreboard || []);
      } else if (scoreboardList) {
        scoreboardList.innerHTML = "";
      }

      if (recordValueEl) {
        const best = data?.timing_summary?.fastest?.value;
        recordValueEl.textContent = isFiniteNumber(best)
          ? formatSeconds(best)
          : "—";
      }

      if (recordPlayerEl) {
        const bestPlayer = data?.timing_summary?.fastest?.player;
        const extraPlayers = data?.timing_summary?.fastest?.players || [];
        const players = new Set();
        if (bestPlayer) {
          players.add(bestPlayer);
        }
        extraPlayers.forEach((player) => {
          if (typeof player === "string") {
            players.add(player);
          }
        });

        if (players.size > 0) {
          recordPlayerEl.textContent = `— ${Array.from(players).join(", ")}`;
          recordPlayerEl.hidden = false;
        } else {
          recordPlayerEl.textContent = "";
          recordPlayerEl.hidden = true;
        }
      }
    },
  };

  const handleStartGame = () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      showError("Соединение с сервером не установлено.");
      return;
    }

    hideError();
    socket.send(
      JSON.stringify({
        action: "start_game",
      })
    );
    gameInProgress = true;
    const startBtn = container.querySelector('[data-action="start-game"]');
    if (startBtn) {
      startBtn.disabled = true;
    }
  };

  const showError = (message) => {
    if (!roomError) {
      return;
    }
    roomError.textContent = message;
    roomError.hidden = !message;
  };

  const hideError = () => {
    if (!roomError) {
      return;
    }
    roomError.textContent = "";
    roomError.hidden = true;
  };

  const connectHostSocket = (roomId) => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/screen/ws/host/${roomId}`);

    socket.addEventListener("open", () => {
      hideError();
    });

    socket.addEventListener("close", () => {
      showError("Соединение с сервером потеряно.");
    });

    socket.addEventListener("error", () => {
      showError("Произошла ошибка соединения.");
    });

    socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        const { event: eventName, payload } = data;

        switch (eventName) {
          case "player_joined":
            renderPlayers(payload?.players || []);
            break;
          case "show_question":
            if ((payload?.question_number ?? 0) <= 1) {
              resetResponseStats();
            }
            gameInProgress = true;
            safeEnsureState("question", payload || {});
            break;
          case "show_results":
            safeEnsureState("question", prepareResultsPayload(payload || {}));
            break;
          case "show_final":
            gameInProgress = false;
            lastQuestionContext = null;
            safeEnsureState("final", prepareFinalPayload(payload || {}));
            break;
          case "error":
            showError(payload?.message ?? "Неизвестная ошибка");
            break;
          default:
            break;
        }
      } catch (error) {
        console.error("Не удалось обработать сообщение", error);
      }
    });
  };

  // Инициализация
  Promise.all([fetchTemplate("lobby"), fetchTemplate("question"), fetchTemplate("final")])
    .catch(() => null)
    .finally(() => {
      safeEnsureState("lobby", { players });
      connectHostSocket(roomConfig.roomId);
    });
})();
