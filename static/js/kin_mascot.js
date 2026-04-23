(function () {
  var cv = document.getElementById('kin-canvas');
  if (!cv) return;
  var ctx = cv.getContext('2d');

  var C = {
    '.': null, 'b': '#1e2a38', 't': '#8ec8d8',
    'h': '#b8b0d8', 'd': '#8878b8', 'g': '#d4b870',
    'w': '#e8f4f8', 'e': '#1e2a38', 'p': '#f0b8b8',
    'f': '#6aabb8', 'k': '#c0a870', 'n': '#a09878',
  };
  var S = 4;

  // ═══════════════════════════════════
  // DESIGN A: CINE-BOT  (12 × 15)
  // ═══════════════════════════════════
  var BOT = {
    happy: [
      '.....g......',
      '.....b......',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.bwwwttwwwb.',
      '.bwewttwewb.',
      '.bttttttttb.',
      '.btttbbtttb.',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.btttpptttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bbb..bbb..',
    ],
    excited: [
      '.....g......',
      '.....b......',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.bwwwttwwwb.',
      '.bwwwttwwwb.',
      '.bttttttttb.',
      '.bttbbbbttb.',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.btttpptttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bbb..bbb..',
    ],
    sleeping: [
      '.....g......',
      '.....b......',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.bttttttttb.',
      '.bbbbtttbbbb',
      '.bttttttttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.btttpptttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bbb..bbb..',
    ],
    amazed: [
      '.....g......',
      '.....b......',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.bwwwttwwwb.',
      '.bwwwttwwwb.',
      '.bwwwttwwwb.',
      '.btttbbbtttb',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.btttpptttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bbb..bbb..',
    ],
    wink: [
      '.....g......',
      '.....b......',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.bwwwtttttb.',
      '.bwewtttbtb.',
      '.bttttttttb.',
      '.btttbbtttb.',
      '..bbbbbbbb..',
      '.bttttttttb.',
      '.btttpptttb.',
      '.bttttttttb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bbb..bbb..',
    ],
  };

  // ═══════════════════════════════════
  // DESIGN B: CINEMA OWL  (12 × 15)
  // h=lavender tufts, f=feather body, k=beak gold, n=talon
  // ═══════════════════════════════════
  var OWL = {
    happy: [
      '.hb......bh.',
      '.hbb....bbh.',
      '.bttttttttb.',
      '.bwwttttwwb.',
      '.bwewtttewb.',
      '.bttttttttb.',
      '.btttkkttttb',
      '.btttkktttb.',
      '..bffffffb..',
      '.bffffffffb.',
      '.bffffffffb.',
      '.bffffffffb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bnn..nnb..',
    ],
    excited: [
      '.hb......bh.',
      '.hbb....bbh.',
      '.bttttttttb.',
      '.bwwttttwwb.',
      '.bwwttttwwb.',
      '.bttttttttb.',
      '.btttkkttttb',
      '.bttbbbbttb.',
      '..bffffffb..',
      '.bffffffffb.',
      '.bffffffffb.',
      '.bffffffffb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bnn..nnb..',
    ],
    sleeping: [
      '.hb......bh.',
      '.hbb....bbh.',
      '.bttttttttb.',
      '.bttttttttb.',
      '.bbbttttbbb.',
      '.bttttttttb.',
      '.btttkkttttb',
      '.bttttttttb.',
      '..bffffffb..',
      '.bffffffffb.',
      '.bffffffffb.',
      '.bffffffffb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bnn..nnb..',
    ],
    amazed: [
      '.hb......bh.',
      '.hbb....bbh.',
      '.bttttttttb.',
      '.bwwttttwwb.',
      '.bwwttttwwb.',
      '.bwwttttwwb.',
      '.btttkkttttb',
      '.btttbbbtttb',
      '..bffffffb..',
      '.bffffffffb.',
      '.bffffffffb.',
      '.bffffffffb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bnn..nnb..',
    ],
    wink: [
      '.hb......bh.',
      '.hbb....bbh.',
      '.bttttttttb.',
      '.bwwtttttttb',
      '.bwetttttbtb',
      '.bttttttttb.',
      '.btttkkttttb',
      '.btttkktttb.',
      '..bffffffb..',
      '.bffffffffb.',
      '.bffffffffb.',
      '.bffffffffb.',
      '..bbbbbbbb..',
      '...bb..bb...',
      '..bnn..nnb..',
    ],
  };


  // ─── Pick design (change this to BOT or OWL) ───
  var SP = BOT;

  var SW = 12 * S, SH = 15 * S;
  var CW = cv.width, CH = cv.height;

  function lerp(a, b, t) { return a + (b - a) * t; }
  function rnd(a, b) { return a + Math.random() * (b - a); }

  var px = CW / 2 - SW / 2, py = CH - SH;
  var vx = 0.3, vy = 0;
  var kinAlpha = 1, tAlpha = 1;
  var kinSX = 1, tSX = 1;
  var kinSY = 1, tSY = 1;
  var kinAngle = 0, tAngle = 0;
  var kinExpr = 'happy';
  var GROUND = CH - SH;

  var STATES = ['drift', 'drift', 'drift', 'nap', 'peek', 'spin_y',
    'tumble', 'vanish', 'squish', 'hover', 'cartwheel', 'belly_flop'];
  var state = 'drift', elapsed = 0, stateEnd = 6000, stateStart = 0;
  var lastTime = performance.now(), blinkMs = 0;
  var peekDir = 1, peekPhase = 0, hoverTargetY = 20;

  function pickState() {
    var prev = state;
    state = STATES[Math.floor(Math.random() * STATES.length)];
    if (state === prev && (state === 'vanish' || state === 'nap')) state = 'drift';
    var dur;
    switch (state) {
      case 'drift': dur = rnd(6000, 12000); break;
      case 'nap': dur = rnd(4000, 8000); break;
      case 'peek': dur = rnd(2500, 4000); peekDir = Math.random() > 0.5 ? 1 : -1; peekPhase = 0; break;
      case 'spin_y': dur = rnd(3000, 5000); break;
      case 'tumble': dur = rnd(3000, 5000); break;
      case 'vanish': dur = rnd(2000, 4000); break;
      case 'squish': dur = rnd(3000, 5000); break;
      case 'hover': dur = rnd(5000, 8000); hoverTargetY = rnd(5, CH * 0.3); break;
      case 'cartwheel': dur = rnd(2000, 4000); break;
      case 'belly_flop': dur = rnd(2000, 3000); break;
      default: dur = 6000;
    }
    stateStart = elapsed;
    stateEnd = elapsed + dur;
    tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0;
    vx = rnd(-0.3, 0.3);
  }

  function loop(now) {
    var dt = Math.min(now - lastTime, 50);
    lastTime = now; elapsed += dt; blinkMs += dt;
    var t16 = dt / 16;
    if (elapsed > stateEnd) pickState();

    switch (state) {
      case 'drift':
        px += vx * t16;
        py = GROUND + Math.sin(elapsed * 0.0012) * 6;
        tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0; kinExpr = 'happy'; break;
      case 'nap':
        px += vx * 0.1 * t16;
        py = lerp(py, GROUND, 0.03);
        tSX = 1 + Math.sin(elapsed * 0.002) * 0.04;
        tSY = 1 - Math.sin(elapsed * 0.002) * 0.03;
        tAlpha = 1; tAngle = 0; kinExpr = 'sleeping'; break;
      case 'peek':
        var pt = stateEnd - elapsed;
        if (peekPhase === 0) {
          var tx = peekDir > 0 ? SW * 0.2 : CW - SW * 1.2;
          px = lerp(px, tx, 0.04); py = lerp(py, GROUND, 0.05);
          tSX = peekDir > 0 ? 1 : -1;
          if (Math.abs(px - tx) < 2) peekPhase = 1;
          kinExpr = 'wink';
        } else if (peekPhase === 1) {
          py = GROUND + Math.sin(elapsed * 0.003) * 2;
          if (pt < 800) peekPhase = 2; kinExpr = 'wink';
        } else {
          px = lerp(px, peekDir > 0 ? -SW : CW + SW, 0.05); kinExpr = 'happy';
        }
        tAlpha = 1; tAngle = 0; tSY = 1; break;
      case 'spin_y':
        tSX = Math.cos(elapsed * 0.003);
        px += vx * 0.5 * t16; py = GROUND + Math.sin(elapsed * 0.001) * 4;
        tAlpha = 1; tSY = 1; tAngle = 0; kinExpr = 'happy'; break;
      case 'tumble':
        tAngle += 0.015 * t16;
        px += vx * 0.6 * t16; py = lerp(py, CH * 0.3, 0.01);
        tAlpha = 1; tSX = 1; tSY = 1; kinExpr = 'excited'; break;
      case 'vanish':
        var stateDur = stateEnd - stateStart;
        var progress = stateDur > 0 ? (elapsed - stateStart) / stateDur : 1;
        if (progress < 0.5) {
          tAlpha = 1 - progress * 2;
        } else {
          if (kinAlpha < 0.1) { px = rnd(SW, CW - SW * 2); py = rnd(GROUND * 0.3, GROUND); }
          tAlpha = (progress - 0.5) * 2;
        }
        tSX = 1; tSY = 1; tAngle = 0; kinExpr = 'happy'; break;
      case 'squish':
        var sq = Math.sin(elapsed * 0.004);
        tSX = 1 + sq * 0.3; tSY = 1 - sq * 0.2;
        px += vx * 0.3 * t16; py = GROUND + Math.sin(elapsed * 0.0015) * 3;
        tAlpha = 1; tAngle = 0; kinExpr = 'amazed'; break;
      case 'hover':
        py = lerp(py, hoverTargetY, 0.015);
        px += vx * 0.4 * t16;
        tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0; kinExpr = 'excited'; break;
      case 'cartwheel':
        tAngle += 0.025 * t16;
        tSX = Math.cos(elapsed * 0.005);
        px += (Math.abs(vx) + 0.5) * (vx > 0 ? 1 : -1) * t16;
        py = GROUND + Math.sin(elapsed * 0.003) * 8;
        tAlpha = 1; tSY = 1; kinExpr = 'excited'; break;
      case 'belly_flop':
        var bf = Math.min(1, Math.max(0, 1 - (stateEnd - elapsed) / 2500));
        if (bf < 0.3) tSY = lerp(1, 0.3, bf / 0.3);
        else { var sp = (bf - 0.3) / 0.7; tSY = 0.3 + 0.7 * sp * (1 + Math.sin(sp * Math.PI * 3) * (1 - sp) * 0.5); }
        px += vx * 0.2 * t16; py = lerp(py, GROUND, 0.05);
        tAlpha = 1; tSX = 1; tAngle = 0; kinExpr = bf < 0.3 ? 'amazed' : 'happy'; break;
    }

    if (px < 0) { px = 0; vx = Math.abs(vx); }
    if (px > CW - SW) { px = CW - SW; vx = -Math.abs(vx); }
    if (py < 0) py = 0;
    if (py > GROUND) py = GROUND;

    var ls = 0.06;
    kinAlpha = lerp(kinAlpha, tAlpha, ls);
    kinSX = lerp(kinSX, tSX, ls);
    kinSY = lerp(kinSY, tSY, ls);
    kinAngle = lerp(kinAngle, tAngle, ls * 0.8);

    var rows = SP[kinExpr] || SP.happy;
    if (blinkMs % 4000 < 130) rows = rows.map(function (r) { return r.replace(/[we]/g, 't'); });

    ctx.clearRect(0, 0, CW, CH);
    var cx = Math.round(px + SW / 2), cy = Math.round(py + SH / 2);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, kinAlpha));
    ctx.translate(cx, cy); ctx.rotate(kinAngle); ctx.scale(kinSX, kinSY);
    ctx.translate(-SW / 2, -SH / 2);
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r];
      for (var c = 0; c < row.length; c++) {
        var col = C[row[c]];
        if (col) { ctx.fillStyle = col; ctx.fillRect(c * S, r * S, S, S); }
      }
    }
    ctx.restore();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  // ═══════════════════════════════════
  // POSTER CAROUSEL
  // ═══════════════════════════════════
  var slideA = document.getElementById('kin-slide-a'), slideB = document.getElementById('kin-slide-b');
  var imgA = document.getElementById('kin-img-a'), imgB = document.getElementById('kin-img-b');
  var titleA = document.getElementById('kin-title-a'), titleB = document.getElementById('kin-title-b');
  var dotsEl = document.getElementById('kin-dots');
  var movies = [], mIdx = 0, activeSlide = 'a';

  function showSlideIn(sl, img, ttl, m) {
    img.src = m.poster; ttl.textContent = m.title;
    sl.style.transition = 'none'; sl.style.opacity = '0'; sl.style.transform = 'translateY(20px)';
    void sl.offsetWidth;
    sl.style.transition = 'opacity 0.8s cubic-bezier(0.4,0,0.2,1),transform 0.8s cubic-bezier(0.4,0,0.2,1)';
    sl.style.opacity = '1'; sl.style.transform = 'translateY(0)';
  }
  function hideSlideOut(sl) {
    sl.style.transition = 'opacity 0.6s ease,transform 0.6s ease';
    sl.style.opacity = '0'; sl.style.transform = 'translateY(-16px)';
  }
  function updateDots() {
    if (!dotsEl || !movies.length) return; dotsEl.innerHTML = '';
    movies.forEach(function (_, i) {
      var d = document.createElement('div');
      d.style.cssText = 'width:6px;height:6px;border-radius:50%;transition:background 0.4s,transform 0.4s;';
      d.style.background = (i === mIdx) ? 'rgba(126,181,196,0.85)' : 'rgba(126,181,196,0.2)';
      d.style.transform = (i === mIdx) ? 'scale(1.5)' : 'scale(1)';
      dotsEl.appendChild(d);
    });
  }
  function showMovie(m, i) {
    mIdx = i; updateDots();
    if (m.rating >= 7.5) kinExpr = 'amazed';
    else if (m.rating >= 6.5) kinExpr = 'excited';
    else if (m.rating >= 5.0) kinExpr = 'happy';
    else if (m.rating >= 3.5) kinExpr = 'wink';
    else kinExpr = 'sleeping';
    if (activeSlide === 'a') { hideSlideOut(slideA); setTimeout(function () { showSlideIn(slideB, imgB, titleB, m); }, 300); activeSlide = 'b'; }
    else { hideSlideOut(slideB); setTimeout(function () { showSlideIn(slideA, imgA, titleA, m); }, 300); activeSlide = 'a'; }
  }
  fetch('/api/now-playing').then(function (r) { return r.json(); }).then(function (d) {
    if (!d.movies || !d.movies.length) return;
    movies = d.movies; updateDots();
    showSlideIn(slideA, imgA, titleA, movies[0]); activeSlide = 'a'; updateDots();
    setInterval(function () { var n = (mIdx + 1) % movies.length; showMovie(movies[n], n); }, 6000);
  }).catch(function () { });
})();
