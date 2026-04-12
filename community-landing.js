(function () {
  const nav = document.getElementById("siteNav");
  const hero = document.querySelector(".hero");
  if (!nav || !hero) return;
  function onScroll() {
    const heroBottom = hero.getBoundingClientRect().bottom;
    nav.classList.toggle("is-scrolled", heroBottom <= 60);
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
})();

(function () {
  const steps = Array.from(document.querySelectorAll("#howSteps .how-step"));
  if (!steps.length) return;

  const AUTO_FIRST = 10000;
  const AUTO_REST = 3000;
  let current = 0;
  let pinned = false;
  let timer = null;

  function activate(idx, fromUser) {
    steps.forEach((s) => s.classList.remove("is-active"));
    steps[idx].classList.add("is-active");
    current = idx;

    clearTimeout(timer);

    if (fromUser) {
      pinned = true;
      timer = setTimeout(() => {
        pinned = false;
        next();
      }, AUTO_FIRST);
    } else {
      pinned = false;
      const delay = idx === 0 ? AUTO_FIRST : AUTO_REST;
      timer = setTimeout(next, delay);
    }
  }

  function next() {
    if (pinned) return;
    activate((current + 1) % steps.length, false);
  }

  steps.forEach((s, i) => {
    s.addEventListener("click", () => activate(i, true));
  });

  activate(0, false);
})();

(function () {
  const b1 = document.getElementById("bubble1");
  const b2 = document.getElementById("bubble2");
  if (!b1 || !b2) return;

  const DIALOGUES = [
    { left: ["Поставил цель", "на эту неделю!"], right: ["Отлично, проверю", "в пятницу 👊"] },
    { left: ["Сделал 3 из 5", "задач ✓"], right: ["Уже прогресс,", "продолжай!"] },
    { left: ["Не получилось...", "расскажу"], right: ["Разберём вместе,", "не страшно"] },
    { left: ["Запустил проект!", "🚀"], right: ["Видел — огонь,", "горжусь тобой"] },
  ];
  let dialogueIdx = 0;

  function setText(bubbleEl, lines) {
    const tspans = bubbleEl.querySelectorAll("tspan");
    if (tspans[0]) tspans[0].textContent = lines[0] || "";
    if (tspans[1]) tspans[1].textContent = lines[1] || "";
  }

  function fadeTo(el, targetOpacity, duration) {
    return new Promise((resolve) => {
      const start = performance.now();
      const startOp = parseFloat(getComputedStyle(el).opacity) || 0;
      function tick(now) {
        const t = Math.min((now - start) / duration, 1);
        const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
        el.style.opacity = String(startOp + (targetOpacity - startOp) * ease);
        if (t < 1) requestAnimationFrame(tick);
        else {
          el.style.opacity = String(targetOpacity);
          resolve();
        }
      }
      requestAnimationFrame(tick);
    });
  }

  async function runLoop() {
    const dlg = DIALOGUES[dialogueIdx % DIALOGUES.length];
    dialogueIdx++;

    setText(b1, dlg.left);
    await fadeTo(b1, 1, 500);
    await new Promise((r) => setTimeout(r, 2200));
    await fadeTo(b1, 0, 400);
    await new Promise((r) => setTimeout(r, 400));

    setText(b2, dlg.right);
    await fadeTo(b2, 1, 500);
    await new Promise((r) => setTimeout(r, 2200));
    await fadeTo(b2, 0, 400);
    await new Promise((r) => setTimeout(r, 600));

    runLoop();
  }

  b1.style.opacity = "0";
  b2.style.opacity = "0";
  setTimeout(runLoop, 800);
})();

(function () {
  const nums = Array.from(document.querySelectorAll(".bstat-num[data-target]"));
  if (!nums.length) return;
  let fired = false;

  function animateNum(el) {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || "";
    const isInt = Number.isInteger(target);
    const DURATION = 1600;
    const start = performance.now();

    function tick(now) {
      const elapsed = now - start;
      const raw = Math.min(elapsed / DURATION, 1);
      const ease = raw < 1 ? 1 - Math.pow(2, -10 * raw) : 1;

      if (raw < 0.6) {
        const scramble = Math.round(Math.random() * target * 1.5);
        el.textContent = (isInt ? scramble : scramble.toFixed(1)) + suffix;
      } else {
        const value = target * ease;
        el.textContent = (isInt ? Math.round(value) : value.toFixed(1)) + suffix;
      }

      if (raw < 1) requestAnimationFrame(tick);
      else el.textContent = (isInt ? target : target.toFixed(1)) + suffix;
    }
    requestAnimationFrame(tick);
  }

  const section = nums[0].closest("section") || document.querySelector(".buddy");
  if (!section) return;

  const observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && !fired) {
        fired = true;
        nums.forEach((el, i) => setTimeout(() => animateNum(el), i * 180));
        observer.disconnect();
      }
    },
    { threshold: 0.35 }
  );

  observer.observe(section);
})();

(function () {
  const cards = Array.from(document.querySelectorAll(".tcard"));
  if (!cards.length) return;
  let current = 0;
  let hovered = null;
  let timer = null;
  const INTERVAL = 3500;
  const mqMobile = window.matchMedia("(max-width: 768px)");
  let modeAbort = null;

  function setActive(idx) {
    cards.forEach((c) => c.classList.remove("is-active"));
    if (idx !== null) cards[idx].classList.add("is-active");
    current = idx ?? current;
  }

  function cycle() {
    if (hovered !== null) return;
    current = (current + 1) % cards.length;
    setActive(current);
  }

  function onEnter(i) {
    return () => {
      hovered = i;
      if (timer) clearInterval(timer);
      timer = null;
      setActive(i);
    };
  }

  function onLeave(i) {
    return () => {
      hovered = null;
      current = i;
      timer = setInterval(cycle, INTERVAL);
    };
  }

  function onMobileClick(ev) {
    const card = ev.currentTarget;
    const idx = cards.indexOf(card);
    if (idx < 0) return;
    const wasOpen = card.classList.contains("is-mobile-expanded");
    if (wasOpen) {
      cards.forEach((c) => {
        c.classList.remove("is-mobile-expanded");
        c.classList.remove("is-active");
      });
      return;
    }
    cards.forEach((c, j) => {
      const open = j === idx;
      c.classList.toggle("is-mobile-expanded", open);
      c.classList.toggle("is-active", open);
    });
    current = idx;
  }

  function bindDesktop(signal) {
    cards.forEach((c) => c.classList.remove("is-mobile-expanded"));
    cards.forEach((card, i) => {
      card.addEventListener("mouseenter", onEnter(i), { signal });
      card.addEventListener("mouseleave", onLeave(i), { signal });
    });
    hovered = null;
    setActive(0);
    timer = setInterval(cycle, INTERVAL);
  }

  function bindMobile(signal) {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    hovered = null;
    cards.forEach((card, i) => {
      card.addEventListener("click", onMobileClick, { signal });
      card.classList.toggle("is-mobile-expanded", i === 0);
      card.classList.toggle("is-active", i === 0);
    });
    current = 0;
  }

  function applyTracksMode() {
    if (modeAbort) modeAbort.abort();
    modeAbort = new AbortController();
    const { signal } = modeAbort;
    if (mqMobile.matches) bindMobile(signal);
    else bindDesktop(signal);
  }

  applyTracksMode();
  mqMobile.addEventListener("change", applyTracksMode);
})();

(function () {
  const TEAM_GRADIENTS = [
    "linear-gradient(155deg, #2E2C2A 0%, #232120 100%)",
    "linear-gradient(155deg, #2A2C2E 0%, #1E2123 100%)",
    "linear-gradient(155deg, #2C2A2E 0%, #211E23 100%)",
    "linear-gradient(155deg, #2E2B28 0%, #232018 100%)",
    "linear-gradient(155deg, #282C2A 0%, #1C2018 100%)",
    "linear-gradient(155deg, #2A2828 0%, #1E1C1C 100%)",
    "linear-gradient(155deg, #2C2E2A 0%, #202318 100%)",
    "linear-gradient(155deg, #282A2C 0%, #181C20 100%)",
  ];
  const NAMES = [
    "Ты",
    "Максим",
    "Даша",
    "Илья",
    "Маша",
    "Артём",
    "Соня",
    "Кирилл",
    "Лера",
    "Дима",
    "Катя",
    "Женя",
    "Рома",
    "Вика",
    "Серёжа",
    "Алина",
    "Паша",
    "Настя",
    "Ваня",
    "Таня",
    "Олег",
    "Ксюша",
    "Митя",
    "Зоя",
  ];
  const grid = document.getElementById("teamGrid");
  if (!grid) return;
  for (let i = 0; i < 24; i++) {
    const cell = document.createElement("div");
    cell.className = "tcell";
    const lbl = document.createElement("div");
    lbl.className = "tcell-lbl";
    lbl.textContent = "Ваше фото может быть здесь)";
    const nm = document.createElement("div");
    nm.className = "tcell-name";
    if (i === 0 || i === 2) {
      cell.classList.add("is-photo");
      cell.setAttribute("data-photo", "true");
      if (i === 2) {
        cell.classList.add("is-dash");
        cell.style.background = "#3a3633";
        cell.style.backgroundImage = 'url("assets/dasha-portrait.png")';
        cell.style.backgroundSize = "cover";
        cell.style.backgroundPosition = "center center";
        cell.style.backgroundRepeat = "no-repeat";
        nm.textContent = "Даша";
      } else {
        cell.style.background = "linear-gradient(155deg, #edece7 0%, #dbd9cd 100%)";
        nm.textContent = NAMES[i] || "";
      }
    } else {
      cell.style.background = TEAM_GRADIENTS[i % TEAM_GRADIENTS.length];
      nm.textContent = NAMES[i] || "";
    }
    cell.appendChild(lbl);
    cell.appendChild(nm);
    grid.appendChild(cell);
  }

  const cells = Array.from(grid.querySelectorAll(".tcell"));

  function gridCols() {
    const w = window.innerWidth;
    if (w > 900) return 6;
    if (w > 768) return 3;
    return 6;
  }

  function gridDist(i, j) {
    const COLS = gridCols();
    const ri = Math.floor(i / COLS);
    const ci2 = i % COLS;
    const rj = Math.floor(j / COLS);
    const cj2 = j % COLS;
    return Math.sqrt(Math.pow(ri - rj, 2) + Math.pow(ci2 - cj2, 2));
  }

  let activeTimers = [];

  function clearTimers() {
    activeTimers.forEach((t) => clearTimeout(t));
    activeTimers = [];
  }

  function wave(centerIdx) {
    clearTimers();
    cells.forEach((cell, j) => {
      if (cell.classList.contains("is-photo")) return;
      const dist = gridDist(centerIdx, j);
      const delay = dist * 155;
      const maxDist = 2.35;
      const intensity = Math.max(0, 1 - dist / maxDist);

      const t = setTimeout(() => {
        if (intensity > 0.05) {
          const r1 = Math.round(245 - (245 - 44) * (1 - intensity));
          const g1 = Math.round(240 - (240 - 40) * (1 - intensity));
          const b1 = Math.round(232 - (232 - 36) * (1 - intensity));
          cell.style.background =
            `linear-gradient(145deg, rgb(${r1},${g1},${b1}) 0%, ` +
            `rgb(${r1 - 12},${g1 - 14},${b1 - 18}) 100%)`;
          cell.style.transition =
            `background ${2.55 + dist * 0.42}s cubic-bezier(0.33, 1, 0.68, 1)`;
        }
      }, delay);
      activeTimers.push(t);
    });
  }

  function resetAll() {
    clearTimers();
    cells.forEach((cell, j) => {
      if (!cell.classList.contains("is-photo")) {
        cell.style.transition = "background 5.2s cubic-bezier(0.33, 1, 0.68, 1)";
        cell.style.background = TEAM_GRADIENTS[j % TEAM_GRADIENTS.length];
      }
    });
  }

  if (grid) {
    grid.addEventListener("pointerleave", resetAll);
  }

  cells.forEach((cell, i) => {
    cell.addEventListener("mouseenter", () => wave(i));
  });
})();

(function () {
  const zone = document.getElementById("ballsZone");
  if (!zone) return;

  const TEX_PATHS = [
    "assets/ball-hearts.png",
    "assets/ball-orb.png",
    "assets/ball-ocean.png",
    "assets/ball-fish.png",
    "assets/ball-star.png",
    "assets/ball-galaxy.png",
    "assets/ball-moon.png",
    "assets/ball-butterflies.png",
    "assets/ball-clover.png",
    "assets/ball-flowers.png",
  ];

  const GRAVITY = 0.22;
  const BOUNCE_Y = -0.62;

  function ballPhysicsConfig() {
    const w = window.innerWidth || 800;
    if (w <= 480) {
      return { r: 30, maxBalls: 30, startCount: 6, overlapMult: 0.18 };
    }
    if (w <= 768) {
      return { r: 36, maxBalls: 38, startCount: 7, overlapMult: 0.28 };
    }
    return { r: 58, maxBalls: 60, startCount: 10, overlapMult: 1 };
  }

  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;";
  zone.style.position = "relative";
  zone.appendChild(canvas);
  const ctx = canvas.getContext("2d");

  const texImages = [];
  let cssW = 0;
  let cssH = 0;
  const balls = [];
  let footerKickArmed = true;

  function rnd(a, b) {
    return a + Math.random() * (b - a);
  }

  function loadTextures(cb) {
    let pending = TEX_PATHS.length;
    if (pending === 0) {
      cb();
      return;
    }
    TEX_PATHS.forEach((src, i) => {
      const im = new Image();
      im.onload = im.onerror = () => {
        pending--;
        if (pending === 0) cb();
      };
      im.src = src;
      texImages[i] = im;
    });
  }

  function textureForIndex(i) {
    const im = texImages[i % texImages.length];
    return im && im.complete && im.naturalWidth > 0 ? im : null;
  }

  function makeBall(x, y, vyImpulse, texIdx) {
    const r = ballPhysicsConfig().r;
    const ti =
      texIdx == null
        ? Math.floor(Math.random() * TEX_PATHS.length)
        : ((texIdx % TEX_PATHS.length) + TEX_PATHS.length) % TEX_PATHS.length;
    return {
      x: x == null ? rnd(r, cssW - r) : Math.max(r, Math.min(cssW - r, x)),
      y: y == null ? rnd(r, Math.min(cssH * 0.45, cssH - r)) : Math.max(r, Math.min(cssH - r, y)),
      vx: rnd(-0.65, 0.65),
      vy: vyImpulse == null ? rnd(-1.2, 1.2) : vyImpulse,
      r,
      texIdx: ti,
      angle: rnd(0, Math.PI * 2),
      uo: rnd(-0.35, 0.35),
      vo: rnd(-0.35, 0.35),
      phase: Math.random() * Math.PI * 2,
    };
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cssW = zone.clientWidth || zone.getBoundingClientRect().width || 400;
    cssH = zone.clientHeight || 320;
    canvas.width = Math.max(1, Math.floor(cssW * dpr));
    canvas.height = Math.max(1, Math.floor(cssH * dpr));
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const cfg = ballPhysicsConfig();
    balls.forEach((b) => {
      b.r = cfg.r;
      b.x = Math.max(b.r, Math.min(cssW - b.r, b.x));
      b.y = Math.max(b.r, Math.min(cssH - b.r, b.y));
    });
    while (balls.length > cfg.maxBalls) balls.pop();
  }

  function resolve(a, b) {
    let dx = b.x - a.x;
    let dy = b.y - a.y;
    let dist = Math.hypot(dx, dy);
    if (dist < 1e-4) {
      dx = rnd(-0.01, 0.01);
      dy = rnd(-0.01, 0.01);
      dist = Math.hypot(dx, dy) || 1e-4;
    }
    const cfg = ballPhysicsConfig();
    const crowd = balls.length / Math.max(1, cfg.maxBalls);
    const overlapAllow = crowd * crowd * 8 * cfg.overlapMult;
    const minD = a.r + b.r - overlapAllow;
    if (dist >= minD) return;
    const nx = dx / dist;
    const ny = dy / dist;
    const overlap = minD - dist;
    const s = overlap * 0.5;
    a.x -= nx * s;
    a.y -= ny * s;
    b.x += nx * s;
    b.y += ny * s;
    const rvx = b.vx - a.vx;
    const rvy = b.vy - a.vy;
    const vn = rvx * nx + rvy * ny;
    if (vn > 0) return;
    const ma = a.r * a.r;
    const mb = b.r * b.r;
    const j = -1.6 * vn / (1 / ma + 1 / mb);
    const ix = j * nx;
    const iy = j * ny;
    a.vx -= ix / ma;
    a.vy -= iy / ma;
    b.vx += ix / mb;
    b.vy += iy / mb;
  }

  let tickN = 0;
  function step() {
    tickN++;
    for (const b of balls) {
      b.vy += GRAVITY;
      b.vx += Math.sin(tickN * 0.008 + b.phase) * 0.01;
      b.x += b.vx;
      b.y += b.vy;
      if (b.x < b.r) {
        b.x = b.r;
        b.vx *= -0.7;
      } else if (b.x > cssW - b.r) {
        b.x = cssW - b.r;
        b.vx *= -0.7;
      }
      if (b.y > cssH - b.r) {
        b.y = cssH - b.r;
        b.vy *= BOUNCE_Y;
        b.vx *= 0.97;
        if (Math.abs(b.vy) < 0.8) b.vy = 0;
      }
      if (b.y < b.r) {
        b.y = b.r;
        b.vy *= -0.45;
      }
      b.vx *= 0.995;
      b.vy *= 0.999;
    }
    const _cfg = ballPhysicsConfig();
    const resolvePasses = _cfg.overlapMult < 1 ? 5 : 3;
    for (let k = 0; k < resolvePasses; k++) {
      for (let i = 0; i < balls.length; i++) {
        for (let j = i + 1; j < balls.length; j++) resolve(balls[i], balls[j]);
      }
    }
  }

  function drawBall(b) {
    const { x, y, r, uo, vo, angle } = b;
    const img = textureForIndex(b.texIdx);

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();

    if (img) {
      const iw = img.naturalWidth;
      const ih = img.naturalHeight;
      const cover = Math.max((r * 2) / iw, (r * 2) / ih) * 1.195;
      const dw = iw * cover;
      const dh = ih * cover;
      ctx.drawImage(img, -dw / 2 + uo * r * 0.5, -dh / 2 + vo * r * 0.5, dw, dh);
    } else {
      const g = ctx.createRadialGradient(-r * 0.3, -r * 0.35, r * 0.08, 0, 0, r);
      g.addColorStop(0, "#ece8e2");
      g.addColorStop(0.55, "#9a9590");
      g.addColorStop(1, "#5c5854");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);

    ctx.beginPath();
    ctx.arc(0, 0, r - 0.5, 0, Math.PI * 2);
    const edge = ctx.createLinearGradient(-r, -r, r, r);
    edge.addColorStop(0, "rgba(255,255,255,0.48)");
    edge.addColorStop(0.35, "rgba(255,255,255,0.1)");
    edge.addColorStop(0.55, "rgba(0,0,0,0.06)");
    edge.addColorStop(1, "rgba(0,0,0,0.1)");
    ctx.strokeStyle = edge;
    ctx.lineWidth = 2;
    ctx.stroke();

    function rimArc(a0, a1, rad, lw, alpha) {
      ctx.beginPath();
      ctx.arc(0, 0, rad, a0, a1);
      ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
      ctx.lineWidth = lw;
      ctx.lineCap = "round";
      ctx.stroke();
    }
    rimArc(-Math.PI * 0.97, -Math.PI * 0.4, r - 1.05, 2.4, 0.34);
    rimArc(-Math.PI * 0.9, -Math.PI * 0.5, r - 1.35, 1.5, 0.2);
    rimArc(-Math.PI * 0.82, -Math.PI * 0.58, r - 1.85, 1.1, 0.14);
    rimArc(Math.PI * 0.06, Math.PI * 0.36, r - 1.15, 1.15, 0.1);
    rimArc(Math.PI * 1.05, Math.PI * 1.42, r - 1.2, 0.95, 0.08);

    ctx.beginPath();
    ctx.arc(0, 0, r * 0.76, -Math.PI * 0.92, -Math.PI * 0.48);
    ctx.strokeStyle = "rgba(255,255,255,0.09)";
    ctx.lineWidth = 1;
    ctx.lineCap = "round";
    ctx.stroke();

    ctx.restore();
  }

  function loop() {
    step();
    ctx.clearRect(0, 0, cssW, cssH);
    for (const b of balls) drawBall(b);
    requestAnimationFrame(loop);
  }

  function local(e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function pick(px, py) {
    for (let i = balls.length - 1; i >= 0; i--) {
      if (Math.hypot(px - balls[i].x, py - balls[i].y) <= balls[i].r) return balls[i];
    }
    return null;
  }

  function spawnBurst(px, py) {
    const room = ballPhysicsConfig().maxBalls - balls.length;
    if (room <= 0) return;
    const n = Math.min(3 + Math.floor(Math.random() * 2), room);
    for (let k = 0; k < n; k++) {
      balls.push(
        makeBall(px + rnd(-28, 28), py + rnd(-22, 22), rnd(-6.5, -4.5), balls.length + k)
      );
    }
  }

  function onDown(e) {
    const p = local(e);
    const hit = pick(p.x, p.y);
    spawnBurst(p.x, p.y);
    if (hit) {
      hit.vy -= rnd(2.2, 4.2);
      hit.vx += rnd(-1.2, 1.2);
    }
  }

  canvas.addEventListener("pointerdown", onDown);

  loadTextures(() => {
    resize();
    window.addEventListener("resize", resize);
    const startN = ballPhysicsConfig().startCount;
    for (let i = 0; i < startN; i++) balls.push(makeBall());

    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return;
        if (entry.isIntersecting && entry.intersectionRatio > 0.22) {
          if (footerKickArmed && balls.length) {
            footerKickArmed = false;
            balls.forEach((b) => {
              b.vy -= rnd(5, 9.5);
              b.vx += rnd(-3.5, 3.5);
            });
          }
        } else if (!entry.isIntersecting || entry.intersectionRatio < 0.08) {
          footerKickArmed = true;
        }
      },
      { threshold: [0, 0.08, 0.22, 0.45] }
    );
    io.observe(zone);

    requestAnimationFrame(loop);
  });
})();

(function () {
  /** Ссылка на встречу в Calendly */
  const JOIN_CALENDLY_URL = "https://calendly.com/dariapaivina/meet-with-me";
  /**
   * URL бэкенда заявок (см. api/together-join.js, server.js, TELEGRAM_SETUP.md).
   * Пустая строка: тот же домен что у страницы + /api/together-join (nginx проксирует на Node).
   * Иначе полный URL, например отдельный Vercel.
   */
  const JOIN_NOTIFY_URL = "";
  /** Тот же секрет, что TOGETHER_WEBHOOK_SECRET на сервере (опционально) */
  const JOIN_NOTIFY_SECRET = "";
  /** Опционально: дубликат на Formspree — https://formspree.io/f/xxxx */
  const JOIN_FORM_ENDPOINT = "";

  const modal = document.getElementById("joinModal");
  const form = document.getElementById("joinForm");
  const successEl = document.getElementById("joinSuccess");
  const errorEl = document.getElementById("joinFormError");
  const calEl = document.getElementById("joinCalendly");
  const canvas = document.getElementById("confettiCanvas");

  if (!modal || !form || !successEl || !errorEl) return;

  let calendlyReady = false;
  /** Дата/время созвона после подтверждения записи в виджете Calendly (postMessage). */
  let calendlyBookedSlot = "";

  function joinNotifyUrl() {
    if (JOIN_NOTIFY_URL) return JOIN_NOTIFY_URL;
    if (typeof window === "undefined") return "";
    const p = window.location.protocol;
    if (p !== "http:" && p !== "https:") return "";
    return new URL("/api/together-join", window.location.origin).href;
  }

  function formatCalendlySlotRu(iso) {
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso);
      return new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "long",
        timeStyle: "short",
        timeZone: "Europe/Moscow",
      }).format(d);
    } catch {
      return String(iso);
    }
  }

  function isCalendlyMessage(e) {
    return (
      e.origin === "https://calendly.com" &&
      e.data &&
      typeof e.data === "object" &&
      typeof e.data.event === "string" &&
      e.data.event.indexOf("calendly.") === 0
    );
  }

  window.addEventListener("message", (e) => {
    if (!isCalendlyMessage(e)) return;
    const { event: calEv, payload } = e.data;
    const start =
      (payload && payload.event && payload.event.start_time) ||
      (payload && payload.scheduled_event && payload.scheduled_event.start_time) ||
      (payload && payload.invitee && payload.invitee.start_time);
    if (start) {
      calendlyBookedSlot = formatCalendlySlotRu(start);
      return;
    }
    if (calEv === "calendly.event_scheduled") {
      calendlyBookedSlot = "запись подтверждена в Calendly (время не передано виджетом — проверьте встречу в календаре)";
    }
  });

  function closeModal() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    form.hidden = false;
    successEl.hidden = true;
    errorEl.hidden = true;
    form.reset();
    calendlyReady = false;
    calendlyBookedSlot = "";
    if (calEl) calEl.innerHTML = "";
  }

  function openModal() {
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    loadCalendlyWidget();
    requestAnimationFrame(() => document.getElementById("joinFirstName")?.focus());
  }

  function loadCalendlyWidget() {
    if (calendlyReady || !calEl || !JOIN_CALENDLY_URL) return;
    function run() {
      if (!window.Calendly) return;
      calEl.innerHTML = "";
      window.Calendly.initInlineWidget({
        url: JOIN_CALENDLY_URL,
        parentElement: calEl,
      });
      calendlyReady = true;
    }
    if (window.Calendly) run();
    else {
      const s = document.createElement("script");
      s.src = "https://assets.calendly.com/assets/external/widget.js";
      s.async = true;
      s.onload = run;
      document.body.appendChild(s);
    }
  }

  document.querySelectorAll(".js-open-join").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      openModal();
    });
  });

  modal.querySelectorAll(".js-join-close").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) closeModal();
  });

  function fireConfetti() {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = window.innerWidth;
    const H = window.innerHeight;
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const colors = ["#C9A96E", "#1a1816", "#e8e4dc", "#ffffff", "#9ec5e8", "#f0b4b4", "#d4cfa8"];
    const pieces = Array.from({ length: 160 }, () => ({
      x: Math.random() * W,
      y: -30 - Math.random() * H * 0.4,
      vx: (Math.random() - 0.5) * 7,
      vy: 2.5 + Math.random() * 5,
      r: 4 + Math.random() * 7,
      c: colors[(Math.random() * colors.length) | 0],
      rot: Math.random() * Math.PI * 2,
      vr: (Math.random() - 0.5) * 0.25,
    }));
    const tEnd = performance.now() + 3400;

    function tick(now) {
      ctx.clearRect(0, 0, W, H);
      for (const p of pieces) {
        p.vy += 0.14;
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.r / 2, -p.r / 6, p.r, p.r / 3);
        ctx.restore();
      }
      if (now < tEnd) requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, W, H);
    }
    requestAnimationFrame(tick);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    const fd = new FormData(form);
    const first = String(fd.get("firstName") || "").trim();
    const last = String(fd.get("lastName") || "").trim();
    const phone = String(fd.get("phone") || "").trim();
    let tg = String(fd.get("telegram") || "").replace(/^@+/, "").trim();

    if (!first || !last) {
      errorEl.textContent = "Заполните имя и фамилию.";
      errorEl.hidden = false;
      return;
    }
    if (!phone) {
      errorEl.textContent = "Укажите телефон.";
      errorEl.hidden = false;
      return;
    }
    if (!tg) {
      errorEl.textContent = "Укажите ник в Telegram.";
      errorEl.hidden = false;
      return;
    }
    const consent = document.getElementById("joinConsent");
    if (!consent || !consent.checked) {
      errorEl.textContent = "Нужно согласие с политикой и офертой.";
      errorEl.hidden = false;
      return;
    }

    fd.set("telegram", tg);

    if (!calendlyBookedSlot) {
      errorEl.textContent =
        "Сначала завершите запись на созвон в календаре Calendly выше (выберите время и подтвердите запись).";
      errorEl.hidden = false;
      return;
    }

    const payload = {
      firstName: first,
      lastName: last,
      phone,
      telegram: tg,
      calendlySlot: calendlyBookedSlot,
      source: "together-landing",
    };

    try {
      let sent = false;
      const notifyTarget = joinNotifyUrl();

      if (notifyTarget) {
        const headers = {
          "Content-Type": "application/json",
          Accept: "application/json",
        };
        if (JOIN_NOTIFY_SECRET) headers.Authorization = "Bearer " + JOIN_NOTIFY_SECRET;
        const res = await fetch(notifyTarget, {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        });
        const ct = (res.headers.get("content-type") || "").toLowerCase();
        if (!res.ok || !ct.includes("application/json")) throw new Error("notify");
        const json = await res.json().catch(() => null);
        if (!json || json.ok !== true) throw new Error("notify");
        sent = true;
      }

      if (JOIN_FORM_ENDPOINT) {
        const res = await fetch(JOIN_FORM_ENDPOINT, {
          method: "POST",
          body: fd,
          headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error("formspree");
        sent = true;
      }

      if (!sent) {
        if (typeof console !== "undefined" && console.warn) {
          console.warn(
            "[Together] Заявка не ушла на сервер: задайте JOIN_NOTIFY_URL или JOIN_FORM_ENDPOINT в community-landing.js (см. TELEGRAM_SETUP.md)."
          );
        }
        errorEl.textContent =
          "Заявка не отправлена: не настроен адрес сервера (JOIN_NOTIFY_URL). Обновите страницу после публикации сайта или напишите в Telegram.";
        errorEl.hidden = false;
        return;
      }

      form.hidden = true;
      successEl.hidden = false;
      fireConfetti();
    } catch {
      errorEl.textContent = "Не удалось отправить. Попробуйте позже или напишите в Telegram.";
      errorEl.hidden = false;
    }
  });
})();
