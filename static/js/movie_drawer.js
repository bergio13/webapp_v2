/**
 * movie_drawer.js — In-App Movie Detail Matrix Drawer Controller
 *
 * Provides instant slide-in details with TMDB trailer embeds, JustWatch
 * streaming providers, cast info, and quick library actions.
 */

(function () {
  "use strict";

  const drawerCache = new Map();
  let currentActiveMedia = null;
  let currentCountry = "IT";

  // Try to detect country from browser locale or fallback to IT
  try {
    const userLocale = navigator.language || navigator.userLanguage || "it-IT";
    const parts = userLocale.split("-");
    if (parts.length > 1 && parts[1].length === 2) {
      currentCountry = parts[1].toUpperCase();
    }
  } catch (e) {
    currentCountry = "IT";
  }

  // DOM Elements cache
  let backdropEl, panelEl, skeletonEl, bodyEl, closeBtnEl, countrySelectEl;
  let titleEl, origTitleRowEl, origTitleEl, directorEl, yearBadgeEl, runtimeBadgeEl, ratingBadgeEl, typeBadgeEl, genresListEl;
  let backdropImgEl, posterImgEl, taglineEl, overviewEl;
  let trailerSectionEl, trailerFrameWrapperEl;
  let providersSectionEl, flatrateBlockEl, flatrateListEl, rentBlockEl, rentListEl, buyBlockEl, buyListEl, freeBlockEl, freeListEl, noProvidersEl, justwatchLinkEl;
  let castSectionEl, castListEl;
  let actionLogEl, actionWatchlistEl, actionTmdbEl;

  function initElements() {
    backdropEl = document.getElementById("movie-drawer-backdrop");
    panelEl = document.getElementById("movie-drawer-panel");
    skeletonEl = document.getElementById("drawer-skeleton-loader");
    bodyEl = document.getElementById("drawer-body");
    closeBtnEl = document.getElementById("drawer-close-btn");
    countrySelectEl = document.getElementById("drawer-country-select");

    titleEl = document.getElementById("drawer-title");
    origTitleRowEl = document.getElementById("drawer-orig-title-row");
    origTitleEl = document.getElementById("drawer-orig-title");
    directorEl = document.getElementById("drawer-director");
    yearBadgeEl = document.getElementById("drawer-year-badge");
    runtimeBadgeEl = document.getElementById("drawer-runtime-badge");
    ratingBadgeEl = document.getElementById("drawer-rating-badge");
    typeBadgeEl = document.getElementById("drawer-media-type-badge");
    genresListEl = document.getElementById("drawer-genres-list");

    backdropImgEl = document.getElementById("drawer-backdrop");
    posterImgEl = document.getElementById("drawer-poster-img");
    taglineEl = document.getElementById("drawer-tagline");
    overviewEl = document.getElementById("drawer-overview");

    trailerSectionEl = document.getElementById("drawer-trailer-section");
    trailerFrameWrapperEl = document.getElementById("drawer-trailer-frame-wrapper");

    providersSectionEl = document.getElementById("drawer-providers-section");
    flatrateBlockEl = document.getElementById("drawer-flatrate-block");
    flatrateListEl = document.getElementById("drawer-flatrate-list");
    rentBlockEl = document.getElementById("drawer-rent-block");
    rentListEl = document.getElementById("drawer-rent-list");
    buyBlockEl = document.getElementById("drawer-buy-block");
    buyListEl = document.getElementById("drawer-buy-list");
    freeBlockEl = document.getElementById("drawer-free-block");
    freeListEl = document.getElementById("drawer-free-list");
    noProvidersEl = document.getElementById("drawer-no-providers");
    justwatchLinkEl = document.getElementById("drawer-justwatch-link");

    castSectionEl = document.getElementById("drawer-cast-section");
    castListEl = document.getElementById("drawer-cast-list");

    actionLogEl = document.getElementById("drawer-action-log");
    actionWatchlistEl = document.getElementById("drawer-action-watchlist");
    actionTmdbEl = document.getElementById("drawer-action-tmdb");

    if (closeBtnEl) {
      closeBtnEl.addEventListener("click", window.closeMovieDrawer);
    }
    if (backdropEl) {
      backdropEl.addEventListener("click", window.closeMovieDrawer);
    }
    if (countrySelectEl) {
      // Set initial selector value
      const hasOption = Array.from(countrySelectEl.options).some(opt => opt.value === currentCountry);
      if (hasOption) {
        countrySelectEl.value = currentCountry;
      } else {
        countrySelectEl.value = "IT";
        currentCountry = "IT";
      }

      countrySelectEl.addEventListener("change", (e) => {
        currentCountry = e.target.value;
        if (currentActiveMedia) {
          fetchDetails(currentActiveMedia, currentCountry, false);
        }
      });
    }

    if (actionWatchlistEl) {
      actionWatchlistEl.addEventListener("click", handleWatchlistToggle);
    }

    // Keyboard ESC listener
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && panelEl && panelEl.classList.contains("is-open")) {
        window.closeMovieDrawer();
      }
    });
  }

  function handleWatchlistToggle() {
    if (!currentActiveMedia || !actionWatchlistEl) return;
    const title = currentActiveMedia.title;
    const year = currentActiveMedia.year || "";
    const poster = currentActiveMedia.poster || "";
    const director = currentActiveMedia.director || "";

    actionWatchlistEl.disabled = true;
    actionWatchlistEl.textContent = "[ SAVING... ]";

    fetch("/add_to_watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        title: title,
        p_year: year,
        director: director,
        poster: poster
      })
    })
      .then(res => {
        if (res.ok) {
          actionWatchlistEl.textContent = "[ ✓ IN WATCHLIST ]";
          actionWatchlistEl.classList.add("btn-active");
        } else {
          actionWatchlistEl.textContent = "[ + WATCHLIST ]";
        }
      })
      .catch(() => {
        actionWatchlistEl.textContent = "[ + WATCHLIST ]";
      })
      .finally(() => {
        actionWatchlistEl.disabled = false;
      });
  }

  function renderProviderBadges(container, items) {
    if (!container) return;
    container.innerHTML = "";
    if (!items || items.length === 0) return;

    items.forEach(item => {
      const badge = document.createElement("div");
      badge.className = "provider-item-badge";
      badge.title = item.name || "Provider";

      if (item.logo) {
        const img = document.createElement("img");
        img.src = item.logo;
        img.alt = item.name;
        img.className = "provider-logo-img";
        img.loading = "lazy";
        badge.appendChild(img);
      }

      const nameSpan = document.createElement("span");
      nameSpan.className = "provider-name-text";
      nameSpan.textContent = item.name;
      badge.appendChild(nameSpan);

      container.appendChild(badge);
    });
  }

  function renderMediaDetails(data) {
    if (!bodyEl || !skeletonEl) return;

    skeletonEl.style.display = "none";
    bodyEl.style.display = "block";

    // Title & Meta
    titleEl.textContent = data.title || "Unknown Title";
    if (data.original_title && data.original_title !== data.title) {
      origTitleEl.textContent = data.original_title;
      origTitleRowEl.style.display = "flex";
    } else {
      origTitleRowEl.style.display = "none";
    }

    directorEl.textContent = data.director || "Unknown";
    yearBadgeEl.textContent = data.year || "—";
    typeBadgeEl.textContent = data.media_type === "tv" ? "TV SHOW" : "MOVIE";

    if (data.formatted_runtime) {
      runtimeBadgeEl.textContent = data.formatted_runtime;
      runtimeBadgeEl.style.display = "inline-block";
    } else {
      runtimeBadgeEl.style.display = "none";
    }

    if (data.vote_average) {
      ratingBadgeEl.textContent = `★ ${data.vote_average}`;
      ratingBadgeEl.style.display = "inline-block";
    } else {
      ratingBadgeEl.style.display = "none";
    }

    // Genres
    genresListEl.innerHTML = "";
    if (data.genres && data.genres.length > 0) {
      data.genres.forEach(g => {
        const chip = document.createElement("span");
        chip.className = "drawer-genre-chip";
        chip.textContent = g;
        genresListEl.appendChild(chip);
      });
      genresListEl.style.display = "flex";
    } else {
      genresListEl.style.display = "none";
    }

    // Images
    if (data.backdrop) {
      backdropImgEl.style.backgroundImage = `url('${data.backdrop}')`;
    } else if (data.poster) {
      backdropImgEl.style.backgroundImage = `url('${data.poster}')`;
    } else {
      backdropImgEl.style.backgroundImage = "none";
    }

    if (data.poster) {
      posterImgEl.src = data.poster;
      posterImgEl.style.display = "block";
    } else {
      posterImgEl.src = "https://placehold.co/500x750/0f172a/7eb5c4?text=No+Poster";
    }

    // Tagline & Overview
    if (data.tagline && data.tagline.trim()) {
      taglineEl.textContent = `“${data.tagline}”`;
      taglineEl.style.display = "block";
    } else {
      taglineEl.style.display = "none";
    }

    overviewEl.textContent = data.overview || "No plot summary available.";

    // Trailer
    if (data.trailer && data.trailer.embed_url) {
      const embedUrl = data.trailer.embed_url.replace(/autoplay=1/g, "autoplay=0");
      trailerSectionEl.style.display = "block";
      trailerFrameWrapperEl.innerHTML = `
        <iframe
          src="${embedUrl}"
          title="${data.title} Trailer"
          frameborder="0"
          allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen
          loading="lazy"
          class="drawer-trailer-iframe"
        ></iframe>
      `;
    } else {
      trailerSectionEl.style.display = "none";
      trailerFrameWrapperEl.innerHTML = "";
    }

    // Streaming Providers
    const wp = data.watch_providers || {};
    let hasAnyProvider = false;

    if (wp.flatrate && wp.flatrate.length > 0) {
      flatrateBlockEl.style.display = "block";
      renderProviderBadges(flatrateListEl, wp.flatrate);
      hasAnyProvider = true;
    } else {
      flatrateBlockEl.style.display = "none";
    }

    if (wp.rent && wp.rent.length > 0) {
      rentBlockEl.style.display = "block";
      renderProviderBadges(rentListEl, wp.rent);
      hasAnyProvider = true;
    } else {
      rentBlockEl.style.display = "none";
    }

    if (wp.buy && wp.buy.length > 0) {
      buyBlockEl.style.display = "block";
      renderProviderBadges(buyListEl, wp.buy);
      hasAnyProvider = true;
    } else {
      buyBlockEl.style.display = "none";
    }

    if (wp.free && wp.free.length > 0) {
      freeBlockEl.style.display = "block";
      renderProviderBadges(freeListEl, wp.free);
      hasAnyProvider = true;
    } else {
      freeBlockEl.style.display = "none";
    }

    noProvidersEl.style.display = hasAnyProvider ? "none" : "block";
    if (wp.link) {
      justwatchLinkEl.href = wp.link;
    }

    // Top Cast
    if (data.cast && data.cast.length > 0) {
      castSectionEl.style.display = "block";
      castListEl.innerHTML = "";
      data.cast.forEach(actor => {
        const card = document.createElement("div");
        card.className = "drawer-cast-card";

        const img = document.createElement("img");
        img.className = "drawer-cast-photo";
        img.src = actor.profile || "https://placehold.co/185x185/0f172a/7eb5c4?text=" + encodeURIComponent(actor.name ? actor.name[0] : "?");
        img.alt = actor.name;
        img.loading = "lazy";
        card.appendChild(img);

        const name = document.createElement("div");
        name.className = "drawer-cast-name";
        name.textContent = actor.name;
        card.appendChild(name);

        const role = document.createElement("div");
        role.className = "drawer-cast-role";
        role.textContent = actor.character;
        card.appendChild(role);

        castListEl.appendChild(card);
      });
    } else {
      castSectionEl.style.display = "none";
    }

    // Action Footer
    if (actionLogEl) {
      const isTv = data.media_type === "tv" ? "1" : "0";
      actionLogEl.href = `/add_movie?title=${encodeURIComponent(data.title)}&year=${encodeURIComponent(data.year || "")}&director=${encodeURIComponent(data.director || "")}&tv=${isTv}`;
      if (data.user_status && data.user_status.is_watched) {
        actionLogEl.textContent = "[ ✓ LOGGED (ADD AGAIN) ]";
      } else {
        actionLogEl.textContent = "[ + ADD TO WATCHED ]";
      }
    }

    if (actionTmdbEl && data.tmdb_url) {
      actionTmdbEl.href = data.tmdb_url;
    }
  }

  function fetchDetails(media, country, showSkeleton = true) {
    const cacheKey = `${media.tmdb_id || media.title}_${media.year || ''}_${media.season || ''}_${media.is_tv ? '1' : '0'}_${country}`;

    if (drawerCache.has(cacheKey)) {
      const cached = drawerCache.get(cacheKey);
      renderMediaDetails(cached);
      return;
    }

    if (showSkeleton) {
      skeletonEl.style.display = "block";
      bodyEl.style.display = "none";
      if (trailerFrameWrapperEl) trailerFrameWrapperEl.innerHTML = "";
    }

    const params = new URLSearchParams({
      country: country
    });
    if (media.tmdb_id) params.append("tmdb_id", media.tmdb_id);
    if (media.title) params.append("title", media.title);
    if (media.year) params.append("year", media.year);
    if (media.season) params.append("season", media.season);
    if (media.is_tv !== undefined) params.append("is_tv", media.is_tv ? "1" : "0");

    fetch(`/api/media_details?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          drawerCache.set(cacheKey, data);
          renderMediaDetails(data);
        } else {
          showErrorState(data.error || "Could not retrieve media details.");
        }
      })
      .catch(err => {
        showErrorState("Network connection error. Please try again.");
      });
  }

  function showErrorState(msg) {
    if (!skeletonEl || !bodyEl) return;
    skeletonEl.style.display = "none";
    bodyEl.style.display = "block";
    overviewEl.innerHTML = `<span style="color: var(--color-danger, #ff6b6b)">[ERROR] ${msg}</span>`;
    trailerSectionEl.style.display = "none";
    castSectionEl.style.display = "none";
    flatrateBlockEl.style.display = "none";
    rentBlockEl.style.display = "none";
    buyBlockEl.style.display = "none";
    freeBlockEl.style.display = "none";
    noProvidersEl.style.display = "block";
  }

  // ───────── Public API ─────────

  window.openMovieDrawer = function (media) {
    if (!panelEl) initElements();
    if (!panelEl || !backdropEl) return;

    currentActiveMedia = media;

    // Reset watchlist button state
    if (actionWatchlistEl) {
      actionWatchlistEl.textContent = "[ + WATCHLIST ]";
      actionWatchlistEl.classList.remove("btn-active");
    }

    // Open panel
    backdropEl.classList.add("is-open");
    panelEl.classList.add("is-open");
    panelEl.setAttribute("aria-hidden", "false");
    document.body.classList.add("movie-drawer-open");

    // Fetch and render
    fetchDetails(media, currentCountry, true);
  };

  window.closeMovieDrawer = function () {
    if (!panelEl || !backdropEl) return;

    backdropEl.classList.remove("is-open");
    panelEl.classList.remove("is-open");
    panelEl.setAttribute("aria-hidden", "true");
    document.body.classList.remove("movie-drawer-open");

    // Stop trailer video audio immediately when closed
    if (trailerFrameWrapperEl) {
      trailerFrameWrapperEl.innerHTML = "";
    }
  };

  window.MovieDrawer = {
    open: window.openMovieDrawer,
    close: window.closeMovieDrawer
  };

  // ───────── Global Event Interceptor ─────────

  function setupDrawerEvents() {
    initElements();

    // Delegate clicks on any movie title or poster link
    document.addEventListener("click", (e) => {
      // Check if clicked element or its parent is a movie trigger
      const trigger = e.target.closest("[data-movie-drawer], a[href*='/tmdb_redirect'], .trigger-movie-drawer");
      if (!trigger) return;

      // Allow holding Ctrl/Cmd or middle-click to open TMDB directly in new tab
      if (e.ctrlKey || e.metaKey || e.button === 1) return;

      e.preventDefault();

      let title = trigger.getAttribute("data-title");
      let year = trigger.getAttribute("data-year");
      let is_tv = trigger.getAttribute("data-tv");
      let season = trigger.getAttribute("data-season");
      let tmdb_id = trigger.getAttribute("data-tmdb-id");
      let poster = trigger.getAttribute("data-poster");
      let director = trigger.getAttribute("data-director");

      // If clicked from a /tmdb_redirect link, extract search query params
      if (!title && trigger.tagName === "A" && trigger.getAttribute("href") && trigger.getAttribute("href").includes("/tmdb_redirect")) {
        try {
          const url = new URL(trigger.href, window.location.origin);
          title = url.searchParams.get("title");
          is_tv = url.searchParams.get("tv") === "1";
        } catch (err) {
          title = trigger.textContent.trim();
        }
      }

      if (!title && trigger.closest(".movie-card, .card-grid, tr")) {
        const card = trigger.closest(".movie-card, .card-grid, tr");
        title = card.getAttribute("data-title") || (card.querySelector(".card-title, .movie-title") ? card.querySelector(".card-title, .movie-title").textContent.trim() : "");
      }
      if (!season && trigger.closest(".movie-card, .card-grid, tr")) {
        const card = trigger.closest(".movie-card, .card-grid, tr");
        season = card.getAttribute("data-season");
      }

      if (title || tmdb_id) {
        window.openMovieDrawer({
          title: title ? title.trim() : "",
          year: year ? year.trim() : null,
          is_tv: is_tv === "1" || is_tv === "true" || is_tv === true,
          season: season ? season.trim() : null,
          tmdb_id: tmdb_id || null,
          poster: poster || null,
          director: director || null
        });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupDrawerEvents);
  } else {
    setupDrawerEvents();
  }
})();
