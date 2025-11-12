(function (global) {
  const medalIcons = ["🥇", "🥈", "🥉"];

  const toNumber = (value) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : 0;
  };

  const toTime = (value) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  };

  const formatPoints = (value) => {
    const score = toNumber(value);
    const abs = Math.abs(score) % 100;
    const lastDigit = abs % 10;

    if (abs > 10 && abs < 20) {
      return `${score} очков`;
    }
    if (lastDigit === 1) {
      return `${score} очко`;
    }
    if (lastDigit >= 2 && lastDigit <= 4) {
      return `${score} очка`;
    }
    return `${score} очков`;
  };

  const formatTime = (value) => {
    const time = toTime(value);
    if (time === null) {
      return "—";
    }
    const rounded = time >= 100 ? time.toFixed(0) : time.toFixed(1);
    return `${rounded} с`;
  };

  const getPositionLabel = (index) => {
    if (index < medalIcons.length) {
      return medalIcons[index];
    }
    return `${index + 1}.`;
  };

  const sortEntries = (entries) =>
    [...entries].sort((a, b) => {
      const scoreA = toNumber(a?.score);
      const scoreB = toNumber(b?.score);
      if (scoreA !== scoreB) {
        return scoreB - scoreA;
      }
      const timeA = toTime(a?.total_response_time);
      const timeB = toTime(b?.total_response_time);
      if (timeA === null && timeB === null) {
        return 0;
      }
      if (timeA === null) {
        return 1;
      }
      if (timeB === null) {
        return -1;
      }
      return timeA - timeB;
    });

  const buildItem = (entry, index) => {
    const li = document.createElement("li");
    li.className = "final-screen__row";
    if (entry?.has_fastest_record) {
      li.classList.add("is-record");
    }

    const positionEl = document.createElement("span");
    positionEl.className = "final-screen__position";
    positionEl.textContent = getPositionLabel(index);

    const nameEl = document.createElement("span");
    nameEl.className = "final-screen__name";
    nameEl.textContent = entry?.player ?? "—";

    const metaEl = document.createElement("span");
    metaEl.className = "scoreboard__meta final-screen__meta";

    const pointsEl = document.createElement("span");
    pointsEl.className = "final-screen__points";
    pointsEl.textContent = formatPoints(entry?.score);

    const separatorEl = document.createElement("span");
    separatorEl.className = "final-screen__separator";
    separatorEl.textContent = "—";

    const timeEl = document.createElement("span");
    timeEl.className = "final-screen__time";
    timeEl.textContent = `⏱ ${formatTime(entry?.total_response_time)}`;

    metaEl.append(pointsEl, separatorEl, timeEl);
    li.append(positionEl, nameEl, metaEl);

    return li;
  };

  const render = (listElement, entries) => {
    if (!listElement) {
      return;
    }
    listElement.innerHTML = "";
    if (!Array.isArray(entries) || entries.length === 0) {
      return;
    }

    const sorted = sortEntries(entries);
    sorted.forEach((entry, index) => {
      listElement.appendChild(buildItem(entry, index));
    });
  };

  global.Leaderboard = {
    render,
    _formatPoints: formatPoints,
    _formatTime: formatTime,
  };
})(window);
