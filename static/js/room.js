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
    quizDescription: container.dataset.quizDescription || "",
  };

  const templateCache = new Map();
  let currentState = null;
  let socket = null;
  let gameInProgress = false;
  let players = [];
  let lastQuestionContext = null;

  const buildQrUrl = (url) =>
    `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;

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
      const root = container.querySelector(".lobby-screen");
      if (!root) {
        return;
      }

      const codeEl = root.querySelector('[data-element="room-code"]');
      const linkEl = root.querySelector('[data-element="room-link"]');
      const qrEl = root.querySelector('[data-element="room-qr"]');
      const quizTitleEl = root.querySelector('[data-element="quiz-title"]');
      const quizDescEl = root.querySelector('[data-element="quiz-description"]');
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
      if (quizDescEl) {
        quizDescEl.textContent = roomConfig.quizDescription;
        quizDescEl.hidden = !roomConfig.quizDescription;
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
        return;
      }

      const progressEl = root.querySelector('[data-element="progress"]');
      const titleEl = root.querySelector('[data-element="title"]');
      const subtitleEl = root.querySelector('[data-element="subtitle"]');
      const optionsList = root.querySelector('[data-element="options"]');
      const resultsSection = root.querySelector('[data-section="results"]');
      const answersList = root.querySelector('[data-element="answers"]');
      const scoreboardList = root.querySelector('[data-element="scoreboard"]');

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

      if (resultsSection) {
        if (data.results) {
          resultsSection.classList.add("is-visible");
        } else {
          resultsSection.classList.remove("is-visible");
        }
      }

      if (answersList) {
        answersList.innerHTML = "";
        (data.results || []).forEach((item) => {
          const li = document.createElement("li");
          const status = item.is_correct ? "✅" : "❌";
          const answerText = item.answer ?? "—";
          li.textContent = `${status} ${item.player}: ${answerText} (${item.score})`;
          answersList.appendChild(li);
        });
      }

      if (scoreboardList) {
        scoreboardList.innerHTML = "";
        (data.scoreboard || []).forEach((entry, index) => {
          const li = document.createElement("li");
          li.innerHTML = `<span>${index + 1}.</span><strong>${entry.player}</strong><span>${entry.score}</span>`;
          scoreboardList.appendChild(li);
        });
      }
    },
    final(data) {
      const root = container.querySelector(".final-screen");
      if (!root) {
        return;
      }

      const quizTitleEl = root.querySelector('[data-element="quiz-title"]');
      const scoreboardList = root.querySelector('[data-element="final-scoreboard"]');

      if (quizTitleEl) {
        quizTitleEl.textContent = roomConfig.quizTitle;
      }

      if (scoreboardList) {
        scoreboardList.innerHTML = "";
        (data.scoreboard || []).forEach((entry, index) => {
          const li = document.createElement("li");
          li.innerHTML = `<span class="final-screen__position">${index + 1}</span><span class="final-screen__name">${entry.player}</span><span class="final-screen__score">${entry.score}</span>`;
          scoreboardList.appendChild(li);
        });
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
            gameInProgress = true;
            safeEnsureState("question", payload || {});
            break;
          case "show_results":
            safeEnsureState("question", payload || {});
            break;
          case "show_final":
            gameInProgress = false;
            lastQuestionContext = null;
            safeEnsureState("final", payload || {});
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
