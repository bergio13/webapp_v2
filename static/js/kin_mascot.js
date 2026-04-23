(function () {
  var cv  = document.getElementById('kin-canvas');
  var posterBox = document.getElementById('kin-poster-box');
  if (!cv) return;

  var ctx = cv.getContext('2d');
  var S   = 5;  // pixels per cell → sprite is 12*5=60 wide, 15*5=75 tall

  /* ── Palette ───────────────────────────────────────── */
  var C = {
    '.': null,
    'b': '#1e2a38',
    't': '#8ec8d8',
    'h': '#b8b0d8',
    'd': '#8878b8',
    'g': '#d4b870',
    'w': '#e8f4f8',
    'e': '#1e2a38',
    'p': '#f0b8b8',
  };

  /* ── Sprite frames ─────────────────────────────────── */
  var EXPR = {
    happy: [
      '....bb......',
      '...bhhb.....',
      '..bhghhb....',
      '.bdddddddb..',
      '.btttttttb..',
      'bttwttwtttb.',
      'bttettettttb',
      'bttpttptttb.',
      'btttttttttb.',
      'bttttbbtttb.',
      '.btttttttb..',
      '.btttttttttb',
      'bttttttttttb',
      'btb..btb.btb',
      '.bb...bb..bb',
    ],
    excited: [
      '....bb......',
      '...bhhb.....',
      '..bhghhb....',
      '.bdddddddb..',
      '.btttttttb..',
      'btwwttwwttb.',
      'btwwttwwttb.',
      'bttpttptttb.',
      'btttbbbttttb',
      'btttttttttb.',
      '.btttttttb..',
      '.btttttttttb',
      'bttttttttttb',
      'btb..btb.btb',
      '.bb...bb..bb',
    ],
    sleeping: [
      '....bb......',
      '...bhhb.....',
      '..bhghhb....',
      '.bdddddddb..',
      '.btttttttb..',
      'bttbtttbttb.',
      'btttttttttb.',
      'bttpttptttb.',
      'bttttttttttb',
      'bttttttttttb',
      '.btttttttb..',
      '.btttttttttb',
      'bttttttttttb',
      'btb..btb.btb',
      '.bb...bb..bb',
    ],
    wink: [
      '....bb......',
      '...bhhb.....',
      '..bhghhb....',
      '.bdddddddb..',
      '.btttttttb..',
      'bttwtbttttb.',
      'bttetttttttb',
      'bttpttptttb.',
      'btttttttttb.',
      'bttttbbtttb.',
      '.btttttttb..',
      '.btttttttttb',
      'bttttttttttb',
      'btb..btb.btb',
      '.bb...bb..bb',
    ],
    amazed: [
      '....bb......',
      '...bhhb.....',
      '..bhghhb....',
      '.bdddddddb..',
      '.btttttttb..',
      'btwwwtwwwttb',
      'btwwwtwwwttb',
      'bttpttptttb.',
      'bttttbttttb.',
      'bttttttttttb',
      '.btttttttb..',
      '.btttttttttb',
      'bttttttttttb',
      'btb..btb.btb',
      '.bb...bb..bb',
    ],
  };

  var SW = 12 * S;  // sprite pixel width  = 60
  var SH = 15 * S;  // sprite pixel height = 75
  var CW = cv.width;
  var CH = cv.height;

  /* ── Physics state ─────────────────────────────────── */
  var px  = (CW - SW) / 2;
  var py  = CH - SH;       // start on "ground"
  var vx  = (Math.random() > 0.5 ? 1 : -1) * (0.6 + Math.random() * 0.6);
  var vy  = 0;
  var GRAVITY   = 0.18;
  var BOUNCE    = 0.55;    // damping on floor bounce
  var GROUND    = CH - SH;
  var JUMP_VY   = -4.5;
  var currentExpr = 'happy';
  var isAirborne  = false;
  var nextJump    = 2000 + Math.random() * 2000;
  var elapsedMs   = 0;
  var lastTime    = performance.now();
  var blinkTimer  = 0;

  function jump(strength) {
    if (!isAirborne || strength) {
      vy = strength || JUMP_VY;
      isAirborne = true;
    }
  }

  /* ── Draw ──────────────────────────────────────────── */
  function drawSprite(rows, x, y) {
    ctx.clearRect(0, 0, CW, CH);
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r];
      for (var c = 0; c < row.length; c++) {
        var col = C[row[c]];
        if (col) {
          ctx.fillStyle = col;
          ctx.fillRect(Math.round(x + c * S), Math.round(y + r * S), S, S);
        }
      }
    }
  }

  /* ── Main loop ─────────────────────────────────────── */
  function loop(now) {
    var dt = Math.min(now - lastTime, 40);
    lastTime   = now;
    elapsedMs += dt;
    blinkTimer += dt;

    // Gravity
    vy += GRAVITY * (dt / 16);
    py += vy * (dt / 16);
    px += vx * (dt / 16);

    // Floor collision
    if (py >= GROUND) {
      py = GROUND;
      if (Math.abs(vy) > 1) {
        vy = -Math.abs(vy) * BOUNCE;
        isAirborne = true;
      } else {
        vy = 0;
        isAirborne = false;
      }
    }

    // Wall collisions
    if (px <= 0)       { px = 0;      vx = Math.abs(vx); }
    if (px >= CW - SW) { px = CW-SW;  vx = -Math.abs(vx); }

    // Auto jump
    if (elapsedMs >= nextJump && !isAirborne) {
      jump();
      nextJump = elapsedMs + 2000 + Math.random() * 3000;
      // Also nudge horizontally
      vx = (Math.random() > 0.5 ? 1 : -1) * (0.6 + Math.random() * 0.8);
    }

    // Expression logic
    var displayExpr = currentExpr;
    if (vy < -1.5)           displayExpr = 'excited';   // ascending
    else if (vy > 2)         displayExpr = 'happy';     // falling
    else if (!isAirborne)    displayExpr = currentExpr; // idle on ground

    // Blink
    var rows = EXPR[displayExpr];
    if (blinkTimer % 3500 < 120) {
      rows = rows.map(function (r) { return r.replace(/[we]/g, 't'); });
    }

    drawSprite(rows, px, py);
    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);

  /* ── Poster carousel ──────────────────────────────── */
  var movies = [];
  var mIdx   = 0;

  function ratingToExpr(rating) {
    if (rating >= 7.5) return 'amazed';
    if (rating >= 6.5) return 'excited';
    if (rating >= 5.0) return 'happy';
    if (rating >= 3.5) return 'wink';
    return 'sleeping';
  }

  function showMovie(movie) {
    if (!posterBox) return;
    currentExpr = ratingToExpr(movie.rating);

    // Big jump when a great movie appears
    if (movie.rating >= 7.0) jump(JUMP_VY * 1.3);
    else if (movie.rating >= 5.5) jump();

    posterBox.style.opacity = '0';
    var img = posterBox.querySelector('img');
    var ttl = posterBox.querySelector('.kin-movie-title');
    setTimeout(function () {
      if (img) img.src = movie.poster;
      if (ttl) ttl.textContent = movie.title;
      posterBox.style.opacity = '1';
    }, 350);
  }

  fetch('/api/now-playing')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.movies && data.movies.length) {
        movies = data.movies;
        showMovie(movies[mIdx]);
        setInterval(function () {
          mIdx = (mIdx + 1) % movies.length;
          showMovie(movies[mIdx]);
        }, 5000);
      }
    })
    .catch(function () {});
})();
