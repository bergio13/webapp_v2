(function () {
  /* ═══════════════════════════════════════
     KIN MASCOT  ·  dreamy pixel ghost
  ═══════════════════════════════════════ */
  var cv = document.getElementById('kin-canvas');
  if (!cv) return;
  var ctx = cv.getContext('2d');

  // ── Palette ──────────────────────────
  var C = {
    '.': null, 'b': '#1e2a38', 't': '#8ec8d8',
    'h': '#b8b0d8', 'd': '#8878b8', 'g': '#d4b870',
    'w': '#e8f4f8', 'e': '#1e2a38', 'p': '#f0b8b8',
  };
  var S = 4; // px per cell (smaller = cuter in compact strip)

  // ── Sprites (12 × 15) ────────────────
  var SP = {
    happy: [
      '....bb......','...bhhb.....','..bhghhb....', '.bdddddddb..',
      '.btttttttb..','bttwttwtttb.','bttettettttb','bttpttptttb.',
      'btttttttttb.','bttttbbtttb.','.btttttttb..','.btttttttttb',
      'bttttttttttb','btb..btb.btb','.bb...bb..bb',
    ],
    excited: [
      '....bb......','...bhhb.....','..bhghhb....', '.bdddddddb..',
      '.btttttttb..','btwwttwwttb.','btwwttwwttb.','bttpttptttb.',
      'btttbbbttttb','btttttttttb.','.btttttttb..','.btttttttttb',
      'bttttttttttb','btb..btb.btb','.bb...bb..bb',
    ],
    sleeping: [
      '....bb......','...bhhb.....','..bhghhb....', '.bdddddddb..',
      '.btttttttb..','bttbtttbttb.','btttttttttb.','bttpttptttb.',
      'bttttttttttb','bttttttttttb','.btttttttb..','.btttttttttb',
      'bttttttttttb','btb..btb.btb','.bb...bb..bb',
    ],
    amazed: [
      '....bb......','...bhhb.....','..bhghhb....', '.bdddddddb..',
      '.btttttttb..','btwwwtwwwttb','btwwwtwwwttb','bttpttptttb.',
      'bttttbttttb.','bttttttttttb','.btttttttb..','.btttttttttb',
      'bttttttttttb','btb..btb.btb','.bb...bb..bb',
    ],
    wink: [
      '....bb......','...bhhb.....','..bhghhb....', '.bdddddddb..',
      '.btttttttb..','bttwtbttttb.','bttetttttttb','bttpttptttb.',
      'btttttttttb.','bttttbbtttb.','.btttttttb..','.btttttttttb',
      'bttttttttttb','btb..btb.btb','.bb...bb..bb',
    ],
  };
  var SW = 12 * S, SH = 15 * S;
  var CW = cv.width, CH = cv.height;

  // ── Smooth lerp helper ────────────────
  function lerp(a, b, t) { return a + (b - a) * t; }
  function rnd(a, b)     { return a + Math.random() * (b - a); }

  // ── Kin transform state (all lerped) ──
  var px = CW / 2 - SW / 2, py = CH - SH;
  var vx = 0.3, vy = 0;

  // Current & target transforms
  var kinAlpha = 1,  tAlpha = 1;
  var kinSX = 1,     tSX = 1;     // scaleX  (Y-axis flip)
  var kinSY = 1,     tSY = 1;     // scaleY  (X-axis flip)
  var kinAngle = 0,  tAngle = 0;  // Z rotation
  var kinExpr = 'happy';

  // Physics
  var GRAVITY  = 0.06;
  var GROUND   = CH - SH;
  var BOUNCE   = 0.35;

  // ── State machine ─────────────────────
  var STATES = [
    'drift','drift','drift',   // weighted toward calm
    'nap', 'peek', 'spin_y', 'tumble',
    'vanish', 'squish', 'hover', 'cartwheel', 'belly_flop'
  ];
  var state     = 'drift';
  var elapsed   = 0;
  var stateEnd  = 6000;
  var lastTime  = performance.now();
  var blinkMs   = 0;

  // State-specific vars
  var peekDir      = 1;
  var peekPhase    = 0;    // 0=sliding in, 1=peeking, 2=sliding out
  var squishPhase  = 0;
  var hoverTargetY = 20;
  var napBreathDir = 1;

  function pickState() {
    var prev = state;
    state = STATES[Math.floor(Math.random() * STATES.length)];
    // Don't repeat vanish/nap back-to-back
    if (state === prev && (state === 'vanish' || state === 'nap')) state = 'drift';

    // Set duration
    var dur;
    switch (state) {
      case 'drift':      dur = rnd(6000, 12000); break;
      case 'nap':        dur = rnd(4000, 8000);  break;
      case 'peek':       dur = rnd(2500, 4000);  peekDir = Math.random() > 0.5 ? 1 : -1; peekPhase = 0; break;
      case 'spin_y':     dur = rnd(3000, 5000);  break;
      case 'tumble':     dur = rnd(3000, 5000);  break;
      case 'vanish':     dur = rnd(2000, 4000);  break;
      case 'squish':     dur = rnd(3000, 5000);  squishPhase = 0; break;
      case 'hover':      dur = rnd(5000, 8000);  hoverTargetY = rnd(5, CH * 0.3); break;
      case 'cartwheel':  dur = rnd(2000, 4000);  break;
      case 'belly_flop': dur = rnd(2000, 3000);  break;
      default:           dur = 6000;
    }
    stateEnd = elapsed + dur;

    // Reset targets to neutral
    tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0;
    vx = rnd(-0.3, 0.3);
  }

  // ── Main loop ─────────────────────────
  function loop(now) {
    var dt = Math.min(now - lastTime, 50);
    lastTime = now;
    elapsed += dt;
    blinkMs += dt;
    var t16 = dt / 16; // time factor

    // State transition
    if (elapsed > stateEnd) pickState();

    // Progress through current state (0→1)
    var stateProgress = 1 - Math.max(0, (stateEnd - elapsed) / (stateEnd - (stateEnd - 6000)));

    // ── Per-state behavior ──────────────
    switch (state) {

      case 'drift':
        // Gentle horizontal glide + sine bob
        px += vx * t16;
        py = GROUND + Math.sin(elapsed * 0.0012) * 6;
        tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0;
        kinExpr = 'happy';
        break;

      case 'nap':
        // Settle to ground, breathing pulse
        px += vx * 0.1 * t16;
        py = lerp(py, GROUND, 0.03);
        var breathCycle = Math.sin(elapsed * 0.002);
        tSX = 1 + breathCycle * 0.04;
        tSY = 1 - breathCycle * 0.03;
        tAlpha = 1; tAngle = 0;
        kinExpr = 'sleeping';
        break;

      case 'peek':
        // Slide in from edge, pause, slide back
        var peekTime = stateEnd - elapsed;
        var totalDur = stateEnd - (stateEnd - rnd(2500, 4000)); // approximate
        if (peekPhase === 0) {
          // Slide in
          var edgeX = peekDir > 0 ? -SW * 0.7 : CW - SW * 0.3;
          var targetX = peekDir > 0 ? SW * 0.2 : CW - SW * 1.2;
          px = lerp(px, targetX, 0.04);
          py = lerp(py, GROUND, 0.05);
          tSX = peekDir > 0 ? 1 : -1; // face the right direction
          if (Math.abs(px - targetX) < 2) peekPhase = 1;
          kinExpr = 'wink';
        } else if (peekPhase === 1) {
          // Peeking, wait
          py = GROUND + Math.sin(elapsed * 0.003) * 2;
          if (peekTime < 800) peekPhase = 2;
          kinExpr = 'wink';
        } else {
          // Slide back out
          var exitX = peekDir > 0 ? -SW : CW + SW;
          px = lerp(px, exitX, 0.05);
          kinExpr = 'happy';
        }
        tAlpha = 1; tAngle = 0; tSY = 1;
        break;

      case 'spin_y':
        // Oscillate scaleX: looks like turning around
        tSX = Math.cos(elapsed * 0.003);
        px += vx * 0.5 * t16;
        py = GROUND + Math.sin(elapsed * 0.001) * 4;
        tAlpha = 1; tSY = 1; tAngle = 0;
        kinExpr = 'happy';
        break;

      case 'tumble':
        // Slow Z rotation, no gravity, floaty
        tAngle += 0.015 * t16;
        px += vx * 0.6 * t16;
        py = lerp(py, CH * 0.3, 0.01);
        tAlpha = 1; tSX = 1; tSY = 1;
        kinExpr = 'excited';
        break;

      case 'vanish':
        // Fade out, reposition, fade in
        var half = (stateEnd - elapsed + (stateEnd - elapsed)) * 0.5; // rough midpoint
        var timeLeft = stateEnd - elapsed;
        var totalVanish = 3000; // approx
        if (timeLeft > totalVanish * 0.5) {
          tAlpha = 0;
        } else {
          // Reposition once near midpoint
          if (kinAlpha < 0.1) {
            px = rnd(SW, CW - SW * 2);
            py = rnd(GROUND * 0.3, GROUND);
          }
          tAlpha = 1;
        }
        tSX = 1; tSY = 1; tAngle = 0;
        kinExpr = 'happy';
        break;

      case 'squish':
        // Stretchy blob morph
        var sq = Math.sin(elapsed * 0.004);
        tSX = 1 + sq * 0.3;
        tSY = 1 - sq * 0.2;
        px += vx * 0.3 * t16;
        py = GROUND + Math.sin(elapsed * 0.0015) * 3;
        tAlpha = 1; tAngle = 0;
        kinExpr = 'amazed';
        break;

      case 'hover':
        // Float to target height, drift gently
        py = lerp(py, hoverTargetY, 0.015);
        px += vx * 0.4 * t16;
        tAlpha = 1; tSX = 1; tSY = 1; tAngle = 0;
        kinExpr = 'excited';
        break;

      case 'cartwheel':
        // Z rotation + X flip simultaneously
        tAngle += 0.025 * t16;
        tSX = Math.cos(elapsed * 0.005);
        px += (Math.abs(vx) + 0.5) * (vx > 0 ? 1 : -1) * t16;
        py = GROUND + Math.sin(elapsed * 0.003) * 8;
        tAlpha = 1; tSY = 1;
        kinExpr = 'excited';
        break;

      case 'belly_flop':
        // Squish Y to 0.3 then spring back
        var bfProgress = Math.min(1, (elapsed - (stateEnd - 2500)) / 2500);
        if (bfProgress < 0) bfProgress = 0;
        if (bfProgress < 0.3) {
          tSY = lerp(1, 0.3, bfProgress / 0.3);
        } else {
          // Spring back with overshoot
          var spring = (bfProgress - 0.3) / 0.7;
          tSY = 0.3 + 0.7 * (1 + Math.sin(spring * Math.PI * 3) * (1 - spring) * 0.5) * spring;
        }
        px += vx * 0.2 * t16;
        py = lerp(py, GROUND, 0.05);
        tAlpha = 1; tSX = 1; tAngle = 0;
        kinExpr = bfProgress < 0.3 ? 'amazed' : 'happy';
        break;
    }

    // ── Wall soft-bounce ──────────────
    if (px < 0)       { px = 0;      vx = Math.abs(vx); }
    if (px > CW - SW) { px = CW-SW;  vx = -Math.abs(vx); }
    if (py < 0)        py = 0;
    if (py > GROUND)   py = GROUND;

    // ── Lerp all transforms ─────────
    var lerpSpeed = 0.06;
    kinAlpha = lerp(kinAlpha, tAlpha, lerpSpeed);
    kinSX    = lerp(kinSX,    tSX,    lerpSpeed);
    kinSY    = lerp(kinSY,    tSY,    lerpSpeed);
    kinAngle = lerp(kinAngle, tAngle, lerpSpeed * 0.8);

    // ── Expression & blink ──────────
    var rows = SP[kinExpr];
    if (blinkMs % 4000 < 130) {
      rows = rows.map(function(r) { return r.replace(/[we]/g, 't'); });
    }

    // ── Draw ────────────────────────
    ctx.clearRect(0, 0, CW, CH);
    var cx = Math.round(px + SW / 2);
    var cy = Math.round(py + SH / 2);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, kinAlpha));
    ctx.translate(cx, cy);
    ctx.rotate(kinAngle);
    ctx.scale(kinSX, kinSY);
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

  /* ═══════════════════════════════════════
     POSTER CAROUSEL  ·  smooth cross-fade
  ═══════════════════════════════════════ */
  var slideA = document.getElementById('kin-slide-a');
  var slideB = document.getElementById('kin-slide-b');
  var imgA   = document.getElementById('kin-img-a');
  var imgB   = document.getElementById('kin-img-b');
  var titleA = document.getElementById('kin-title-a');
  var titleB = document.getElementById('kin-title-b');
  var dotsEl = document.getElementById('kin-dots');

  var movies = [], mIdx = 0, activeSlide = 'a';

  function showSlideIn(slide, img, title, movie) {
    img.src = movie.poster;
    title.textContent = movie.title;
    slide.style.transition = 'none';
    slide.style.opacity    = '0';
    slide.style.transform  = 'translateY(20px)';
    void slide.offsetWidth;
    slide.style.transition = 'opacity 0.8s cubic-bezier(0.4,0,0.2,1), transform 0.8s cubic-bezier(0.4,0,0.2,1)';
    slide.style.opacity    = '1';
    slide.style.transform  = 'translateY(0)';
  }

  function hideSlideOut(slide) {
    slide.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    slide.style.opacity    = '0';
    slide.style.transform  = 'translateY(-16px)';
  }

  function updateDots() {
    if (!dotsEl || !movies.length) return;
    dotsEl.innerHTML = '';
    movies.forEach(function(_, i) {
      var d = document.createElement('div');
      d.style.cssText = 'width:6px;height:6px;border-radius:50%;transition:background 0.4s,transform 0.4s;';
      d.style.background = (i === mIdx) ? 'rgba(126,181,196,0.85)' : 'rgba(126,181,196,0.2)';
      d.style.transform  = (i === mIdx) ? 'scale(1.5)' : 'scale(1)';
      dotsEl.appendChild(d);
    });
  }

  function showMovie(movie, idx) {
    mIdx = idx;
    updateDots();

    // Gentle Kin reaction based on rating
    if (movie.rating >= 7.5)      kinExpr = 'amazed';
    else if (movie.rating >= 6.5) kinExpr = 'excited';
    else if (movie.rating >= 5.0) kinExpr = 'happy';
    else if (movie.rating >= 3.5) kinExpr = 'wink';
    else                          kinExpr = 'sleeping';

    if (activeSlide === 'a') {
      hideSlideOut(slideA);
      setTimeout(function() { showSlideIn(slideB, imgB, titleB, movie); }, 300);
      activeSlide = 'b';
    } else {
      hideSlideOut(slideB);
      setTimeout(function() { showSlideIn(slideA, imgA, titleA, movie); }, 300);
      activeSlide = 'a';
    }
  }

  fetch('/api/now-playing')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.movies || !data.movies.length) return;
      movies = data.movies;
      updateDots();
      showSlideIn(slideA, imgA, titleA, movies[0]);
      activeSlide = 'a';
      updateDots();
      setInterval(function() {
        var next = (mIdx + 1) % movies.length;
        showMovie(movies[next], next);
      }, 6000);
    })
    .catch(function() {});
})();
