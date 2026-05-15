(function () {
  var slideA = document.getElementById('upc-slide-a'), slideB = document.getElementById('upc-slide-b');
  var imgA = document.getElementById('upc-img-a'), imgB = document.getElementById('upc-img-b');
  var titleA = document.getElementById('upc-title-a'), titleB = document.getElementById('upc-title-b');
  var dotsEl = document.getElementById('upc-dots');
  var movies = [], mIdx = 0, activeSlide = 'a';

  if (!slideA) return;

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
      d.style.background = (i === mIdx) ? 'rgba(181,138,138,0.85)' : 'rgba(181,138,138,0.2)';
      d.style.transform = (i === mIdx) ? 'scale(1.5)' : 'scale(1)';
      dotsEl.appendChild(d);
    });
  }
  function showMovie(m, i) {
    mIdx = i; updateDots();
    if (activeSlide === 'a') { hideSlideOut(slideA); setTimeout(function () { showSlideIn(slideB, imgB, titleB, m); }, 300); activeSlide = 'b'; }
    else { hideSlideOut(slideB); setTimeout(function () { showSlideIn(slideA, imgA, titleA, m); }, 300); activeSlide = 'a'; }
  }
  fetch('/api/upcoming').then(function (r) { return r.json(); }).then(function (d) {
    if (!d.movies || !d.movies.length) return;
    movies = d.movies; updateDots();
    showSlideIn(slideA, imgA, titleA, movies[0]); activeSlide = 'a'; updateDots();
    setInterval(function () { var n = (mIdx + 1) % movies.length; showMovie(movies[n], n); }, 6500); // offset slightly from the other carousel
  }).catch(function () { });
})();
