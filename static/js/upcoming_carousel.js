(function () {
  var slideA = document.getElementById('upc-slide-a'), slideB = document.getElementById('upc-slide-b');
  var imgA = document.getElementById('upc-img-a'), imgB = document.getElementById('upc-img-b');
  var titleA = document.getElementById('upc-title-a'), titleB = document.getElementById('upc-title-b');
  var linkA = document.getElementById('upc-link-a'), linkB = document.getElementById('upc-link-b');
  var dotsEl = document.getElementById('upc-dots');
  var wrap = document.getElementById('upc-poster-wrap');
  var btnPrev = document.getElementById('upc-prev');
  var btnNext = document.getElementById('upc-next');

  var movies = [], mIdx = 0, activeSlide = 'a';
  var carouselTimer = null;

  if (!slideA) return;

  function showSlideIn(sl, img, ttl, link, m) {
    img.src = m.poster; 
    ttl.textContent = m.title;
    link.href = "#";
    link.removeAttribute("target");
    link.setAttribute("data-movie-drawer", "true");
    link.setAttribute("data-title", m.title || "");
    link.setAttribute("data-poster", m.poster || "");
    if (m.id) link.setAttribute("data-tmdb-id", m.id);
    if (m.year) link.setAttribute("data-year", m.year);
    link.onclick = function(e) {
      e.preventDefault();
      if (typeof window.openMovieDrawer === "function") {
        window.openMovieDrawer({
          title: m.title,
          tmdb_id: m.id || null,
          poster: m.poster || null,
          year: m.year || null,
          is_tv: false
        });
      }
    };
    sl.style.transition = 'none'; sl.style.opacity = '0'; sl.style.transform = 'translateY(20px)';
    sl.style.pointerEvents = 'auto';
    void sl.offsetWidth;
    sl.style.transition = 'opacity 0.8s cubic-bezier(0.4,0,0.2,1),transform 0.8s cubic-bezier(0.4,0,0.2,1)';
    sl.style.opacity = '1'; sl.style.transform = 'translateY(0)';
  }
  function hideSlideOut(sl) {
    sl.style.transition = 'opacity 0.6s ease,transform 0.6s ease';
    sl.style.opacity = '0'; sl.style.transform = 'translateY(-16px)';
    sl.style.pointerEvents = 'none';
  }
  function updateDots() {
    if (!dotsEl || !movies.length) return; dotsEl.innerHTML = '';
    movies.forEach(function (_, i) {
      var d = document.createElement('div');
      d.style.cssText = 'width:6px;height:6px;border-radius:50%;transition:background 0.4s,transform 0.4s;cursor:pointer;';
      d.style.background = (i === mIdx) ? 'rgba(181,138,138,0.85)' : 'rgba(181,138,138,0.2)';
      d.style.transform = (i === mIdx) ? 'scale(1.5)' : 'scale(1)';
      d.addEventListener('click', function() {
        if (mIdx !== i) { showMovie(movies[i], i); restartTimer(); }
      });
      dotsEl.appendChild(d);
    });
  }
  function showMovie(m, i) {
    mIdx = i; updateDots();
    if (activeSlide === 'a') { hideSlideOut(slideA); setTimeout(function () { showSlideIn(slideB, imgB, titleB, linkB, m); }, 300); activeSlide = 'b'; }
    else { hideSlideOut(slideB); setTimeout(function () { showSlideIn(slideA, imgA, titleA, linkA, m); }, 300); activeSlide = 'a'; }
  }

  function nextSlide() {
    if (!movies.length) return;
    var n = (mIdx + 1) % movies.length;
    showMovie(movies[n], n);
    restartTimer();
  }
  
  function prevSlide() {
    if (!movies.length) return;
    var n = (mIdx - 1 + movies.length) % movies.length;
    showMovie(movies[n], n);
    restartTimer();
  }

  function startTimer() {
    if (carouselTimer) clearInterval(carouselTimer);
    carouselTimer = setInterval(nextSlide, 6500); // offset slightly from the other carousel
  }

  function stopTimer() {
    if (carouselTimer) clearInterval(carouselTimer);
  }

  function restartTimer() {
    startTimer();
  }

  if (wrap) {
    wrap.addEventListener('mouseenter', stopTimer);
    wrap.addEventListener('mouseleave', startTimer);
  }
  if (btnPrev) btnPrev.addEventListener('click', prevSlide);
  if (btnNext) btnNext.addEventListener('click', nextSlide);

  fetch('/api/upcoming').then(function (r) { return r.json(); }).then(function (d) {
    if (!d.movies || !d.movies.length) return;
    movies = d.movies; updateDots();
    showSlideIn(slideA, imgA, titleA, linkA, movies[0]); activeSlide = 'a'; updateDots();
    startTimer();
  }).catch(function () { });
})();
