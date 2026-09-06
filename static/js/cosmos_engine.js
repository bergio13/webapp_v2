/**
 * cosmos_engine.js — 60 FPS Interactive Cinephile Cosmos Engine (v2.1)
 * 
 * Renders the high-dimensional movie galaxy on HTML5 Canvas with smooth inertia pan,
 * cursor-centric zoom, sector nebulae, constellation filaments, glowing star cores,
 * interactive glass HUD, Wormhole trajectory bridge, Cosmic Probe sonar, and MovieDrawer matrix.
 */

(function () {
  "use strict";

  // State
  let canvas, ctx;
  let width = 0, height = 0;
  let dpr = 1;
  let animationFrameId = null;

  let galaxyData = { stars: [], links: [], sectors: [], stats: {} };
  let filteredStars = [];
  let filteredLinks = [];

  // Camera & Physics
  const camera = {
    x: 0,
    y: 0,
    targetX: 0,
    targetY: 0,
    zoom: 0.72,
    targetZoom: 0.72,
    minZoom: 0.20,
    maxZoom: 6.0,
    vx: 0,
    vy: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    lastMouseX: 0,
    lastMouseY: 0,
    hasMovedSignificantly: false
  };

  // Interaction Modes: 'explore', 'probe'
  let currentMode = "explore";
  let probeActive = null;
  let probeAnimTime = 0;

  // View Modes: 'split' (default), 'feed', 'manifold'
  let currentViewMode = "split";
  let currentMobileView = "feed"; // 'feed', 'manifold'
  let tasteFeedScrollEl = null;

  // Hover & Selection
  let hoveredStar = null;
  let selectedStar = null;
  let selectedResonantNeighbors = [];
  let hoveredEdge = null;
  let searchTargetStar = null;
  let searchCrosshairTime = 0;
  let activeSpiderfy = null;
  const currentMousePos = { x: -1000, y: -1000, wx: 0, wy: 0 };
  const activeFrameLabelBoxes = [];

  // Super-Dense Clumps Dynamic Semantic Zoom State
  let superDenseClumps = [];
  const starToClumpMap = new Map();
  let hoveredClump = null;

  // Filter State
  const filters = {
    mediaType: "all",      // 'all', 'movie', 'tv'
    category: "all",       // 'all', 'watched', 'uncharted', 'watchlist'
    searchQuery: ""
  };

  // DOM Elements
  let hudEl, hudBackdrop, hudPoster, hudTitle, hudMeta, hudDirector, hudYear, hudMatch, hudCategory, hudGenres, hudActionBtn, hudReason;
  let hudExploratoryTag, hudLowEvidenceTag;
  let hudAffinityReason, hudFrontierBadge, hudCraftMeta, hudCraftDopRow, hudCraftDop, hudCraftComposerRow, hudCraftComposer, hudCraftWriterRow, hudCraftWriter;
  let wayfindersContainer, feedWayfindersContainer, probeDrawer, probeList;
  let statsWatchedEl, statsUnchartedEl, statsWatchlistEl, statsTotalEl;
  let searchInput, searchResultsEl, modeBanner, bannerText;
  let mobileTopBar, mobileActiveRealmBtn, mobileRealmDot, mobileRealmName;
  let mobileSearchBtn, mobileSearchOverlay, mobileSearchInput, mobileSearchClearBtn, mobileSearchResults;
  let mobileFiltersBtn, mobileFilterSheet, mobileFilterSheetClose;
  let mobileOverviewBtn, mobileCenterBtn, mobileSamplerBtn;
  let hudDragHandle, hudWatchlistBtn, hudFormatTag;
  let clusterDropdownBtn, clusterDropdownMenu, mobileClusterDropdownMenu, clusterActiveDot, clusterActiveLabel;
  let feedToggleClustersBtn, feedToggleClustersLabel;
  const expandedClusterIds = new Set();
  let hasUserInteractedClusters = false;

  function getCsrfToken() {
    const el = document.getElementById("csrf_token");
    return el ? el.value : "";
  }

  // Short Core Cluster Titles for instant legibility on Canvas
  const CORE_CLUSTER_TITLES = {
    "CLUST-ANIM": "ANIMATION & MYTH",
    "CLUST-NOIR": "NOIR & CRIME",
    "CLUST-HUMAN": "ARTHOUSE & DRAMA",
    "CLUST-COSMOS": "SPECULATIVE SCI-FI",
    "CLUST-INDIE": "SATIRE & INDIE",
    "CLUST-KINETIC": "ACTION & SURVIVAL"
  };

  function getShortClusterLabel(sec) {
    if (!sec) return "";
    if (sec.code && CORE_CLUSTER_TITLES[sec.code]) {
      return CORE_CLUSTER_TITLES[sec.code];
    }
    if (sec.id === "sec_misc" || sec.code === "FRONTIER") {
      return "TASTE FRONTIER";
    }
    let name = (sec.name || "").trim();
    name = name.replace(/^THE\s+/i, "");
    name = name.replace(/\s+(CLUSTER|FRONTIER|COMMONS|LABYRINTH|CORE|COSMOS)$/i, "");
    if (name.length < 3) {
      name = (sec.name || "").trim().replace(/^THE\s+/i, "");
    }
    if (name.length > 24) {
      const parts = name.split(/[,&•/]/);
      if (parts.length > 1 && parts[0].trim().length >= 4) {
        name = parts[0].trim();
      } else {
        name = name.substring(0, 22).trim() + "…";
      }
    }
    return name.toUpperCase();
  }

  function formatClusterTitle(sec) {
    if (!sec) return "Taste Frontier";
    if (sec.id === "sec_misc" || sec.code === "FRONTIER") {
      return "Taste Frontier";
    }
    let name = (sec.name || "").trim();
    name = name.replace(/^THE\s+/i, "");
    name = name.replace(/\s+(CLUSTER|FRONTIER|COMMONS|LABYRINTH|CORE|COSMOS)$/i, "");
    if (!name || name.length < 2) {
      name = (sec.name || "Cluster").trim().replace(/^THE\s+/i, "");
    }
    return name
      .toLowerCase()
      .split(" ")
      .map((word, idx) => {
        if (["&", "and", "of", "in", "the", "a", "for", "to", "with"].includes(word) && idx !== 0) {
          return word;
        }
        if (word.includes("-")) {
          return word
            .split("-")
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join("-");
        }
        return word.charAt(0).toUpperCase() + word.slice(1);
      })
      .join(" ");
  }

  // Helper: Draw Node Shape (Movie = Circle, TV Show = Diamond)
  function drawNodeShape(ctx, x, y, r, isTv) {
    ctx.beginPath();
    if (!isTv) {
      ctx.arc(x, y, Math.max(2.5, r), 0, Math.PI * 2);
    } else {
      const d = Math.max(3.2, r * 1.32);
      ctx.moveTo(x, y - d);
      ctx.lineTo(x + d, y);
      ctx.lineTo(x, y + d);
      ctx.lineTo(x - d, y);
      ctx.closePath();
    }
  }

  // ---------------------------------------------------------------------------
  // Craft Relationship Visual Signatures & Formatting
  // ---------------------------------------------------------------------------
  function getLinkVisualProps(link) {
    if (!link) return { color: "#38bdf8", dash: [4, 4], width: 1.5, label: "Link" };
    if (link.link_type === "director") {
      return {
        color: "#e0a96d", // Sovereign Warm Gold
        dash: [],         // Solid unbroken auteur spine
        width: 2.2,
        label: "Director"
      };
    }
    if (link.link_type === "franchise") {
      return {
        color: "#f97316", // Neon Amber-Orange
        dash: [10, 3],    // Long track structural saga bond
        width: 2.4,
        label: "Franchise"
      };
    }
    if (link.link_type === "cinematography") {
      return {
        color: "#0ea5e9", // Cyber Electric Blue (Cinematography / Lens Perspective)
        dash: [6, 4],     // Optical ray framing
        width: 1.8,
        label: "Cinematographer"
      };
    }
    if (link.link_type === "composer") {
      return {
        color: "#a855f7", // Harmonic Violet
        dash: [2, 3],     // Staccato acoustic pulse
        width: 1.8,
        label: "Composer"
      };
    }
    return {
      color: "#cbd5e1", // Cosmic Starlight Silver (Thematic Affinity)
      dash: [2, 4],     // Constellation micro-dots
      width: 1.1,
      label: "Connection"
    };
  }

  function formatEdgeTooltip(link) {
    if (!link) return "";
    const reason = link.reason || "";
    if (link.link_type === "director") {
      const name = reason.replace(/^Directorial Lineage:\s*/i, "").trim();
      return name ? `${name} (Director)` : "Director Connection";
    }
    if (link.link_type === "cinematography") {
      const name = reason.replace(/^Cinematography:\s*/i, "").trim();
      return name ? `${name} (Cinematographer)` : "Cinematography Connection";
    }
    if (link.link_type === "composer") {
      const name = reason.replace(/^Original Score:\s*/i, "").trim();
      return name ? `${name} (Composer)` : "Original Score Connection";
    }
    if (link.link_type === "franchise") {
      const name = reason.replace(/^(?:Franchise|TV Series) Canon:\s*/i, "").trim();
      return name ? `${name} (Franchise)` : "Franchise Connection";
    }
    if (link.resonance) {
      return `${link.resonance}% Resonance (Thematic Affinity)`;
    }
    return reason || "Connected Link";
  }

  function getDistToQuadraticCurve(px, py, p1, mid, p2) {
    const minX = Math.min(p1.x, mid.x, p2.x) - 14;
    const maxX = Math.max(p1.x, mid.x, p2.x) + 14;
    const minY = Math.min(p1.y, mid.y, p2.y) - 14;
    const maxY = Math.max(p1.y, mid.y, p2.y) + 14;
    if (px < minX || px > maxX || py < minY || py > maxY) return Infinity;

    let minD = Infinity;
    for (let i = 1; i <= 11; i++) {
      const t = i / 12;
      const it = 1 - t;
      const qx = it * it * p1.x + 2 * it * t * mid.x + t * t * p2.x;
      const qy = it * it * p1.y + 2 * it * t * mid.y + t * t * p2.y;
      const d = Math.hypot(px - qx, py - qy);
      if (d < minD) minD = d;
    }
    return minD;
  }

  function getDistToSegment(px, py, p1, p2) {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const lenSq = dx * dx + dy * dy;
    if (lenSq === 0) return Math.hypot(px - p1.x, py - p1.y);
    const t = Math.max(0, Math.min(1, ((px - p1.x) * dx + (py - p1.y) * dy) / lenSq));
    const projX = p1.x + t * dx;
    const projY = p1.y + t * dy;
    return Math.hypot(px - projX, py - projY);
  }

  function renderEdgeTooltip() {
    if (!hoveredEdge || !hoveredEdge.text) return;
    const { text, color, x, y } = hoveredEdge;

    ctx.save();
    ctx.font = "600 11px 'Rajdhani', sans-serif";
    const tw = ctx.measureText(text).width;
    const boxW = tw + 22;
    const boxH = 22;

    let bx = x - boxW / 2;
    let by = y - boxH - 12;

    if (bx < 10) bx = 10;
    if (bx + boxW > width - 10) bx = width - boxW - 10;
    if (by < 10) by = y + 16;

    // Outer subtle glow in edge color
    ctx.shadowColor = color;
    ctx.shadowBlur = 10;

    // Glass pill background
    drawGlassPill(ctx, bx, by, boxW, boxH, 4, "rgba(6, 10, 20, 0.95)", hexToRgba(color, 0.70));
    ctx.shadowBlur = 0;

    // Accent left indicator dot
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(bx + 8, by + boxH / 2, 2.5, 0, Math.PI * 2);
    ctx.fill();

    // Text
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = "600 11px 'Rajdhani', sans-serif";
    ctx.fillText(text, bx + 15, by + boxH / 2);

    ctx.restore();
  }

  // Safe RGB Color Parser for Canvas gradients (prevents addColorStop exceptions on 8-char hex)
  function hexToRgba(hex, alpha = 1) {
    if (!hex) return `rgba(126, 181, 196, ${alpha})`;
    let c = String(hex).replace("#", "").trim();
    if (c.length === 3) {
      c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    } else if (c.length === 8) {
      c = c.substring(0, 6);
    }
    const num = parseInt(c, 16);
    if (isNaN(num) || c.length < 6) return `rgba(126, 181, 196, ${alpha})`;
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  // 5-Point Sentiment Scale & Cyber-Terminal SVG Icons (Sync with _sentiment_badge.html)
  function getSentimentBadgeHtml(rating, compact = true, showLabel = true) {
    let lvl = parseInt(rating, 10) || 3;
    if (lvl > 5) lvl = Math.ceil(lvl / 2);
    if (lvl < 1) lvl = 1;
    if (lvl > 5) lvl = 5;

    const labels = {
      1: "Trash",
      2: "Skippable",
      3: "Mid",
      4: "Great",
      5: "Masterpiece"
    };

    const svgIcons = {
      1: '<svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      2: '<svg viewBox="0 0 24 24"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>',
      3: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
      4: '<svg viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>',
      5: '<svg viewBox="0 0 24 24"><path d="M2 4l3 12h14l3-12-6 7-4-5-4 5-6-7z"/></svg>'
    };

    const label = labels[lvl] || "Watched";
    const icon = svgIcons[lvl] || svgIcons[3];

    return `<span class="sentiment-badge sentiment-level-${lvl} ${compact ? 'compact' : ''}" title="${lvl} - ${label}">${icon}${showLabel ? `<span>${label}</span>` : ''}</span>`;
  }

  // ---------------------------------------------------------------------------
  // Canvas Sentiment Rating Vectors (Precision 24x24 Cyber-Terminal Glyphs)
  // ---------------------------------------------------------------------------
  const SENTIMENT_COLORS = {
    1: "#b58a8a",
    2: "#c89674",
    3: "#9eb0ba",
    4: "#7dbfa3",
    5: "#c4a96d"
  };

  let sentimentCanvasPaths = null;
  function getSentimentCanvasPaths() {
    if (sentimentCanvasPaths) return sentimentCanvasPaths;
    if (typeof Path2D === 'undefined') return null;
    try {
      sentimentCanvasPaths = {
        1: [
          new Path2D("M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"),
          new Path2D("M12 9v4"),
          new Path2D("M12 17h0.01")
        ],
        2: [
          new Path2D("M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3")
        ],
        3: [
          new Path2D("M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"),
          new Path2D("M8 12h8")
        ],
        4: [
          new Path2D("M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3")
        ],
        5: [
          new Path2D("M2 4l3 12h14l3-12-6 7-4-5-4 5-6-7z")
        ]
      };
    } catch (e) {
      console.warn("[COSMOS JS] Failed to compile Path2D sentiment icons:", e);
    }
    return sentimentCanvasPaths;
  }

  function drawSentimentCanvasIcon(ctx, x, y, size, lvl) {
    const color = SENTIMENT_COLORS[lvl] || SENTIMENT_COLORS[3];
    const paths = getSentimentCanvasPaths();

    ctx.save();
    ctx.translate(x, y);
    const scale = size / 24;
    ctx.scale(scale, scale);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.0;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    if (paths && paths[lvl]) {
      const pList = paths[lvl];
      if (lvl === 5) {
        ctx.fillStyle = "rgba(196, 169, 109, 0.22)";
        ctx.fill(pList[0]);
      }
      for (let i = 0; i < pList.length; i++) {
        ctx.stroke(pList[i]);
      }
    } else {
      // Procedural Canvas 2D fallback
      ctx.beginPath();
      if (lvl === 1) {
        ctx.moveTo(12, 4); ctx.lineTo(2, 21); ctx.lineTo(22, 21); ctx.closePath();
        ctx.moveTo(12, 9); ctx.lineTo(12, 13);
        ctx.moveTo(12, 17); ctx.lineTo(12.01, 17);
      } else if (lvl === 2) {
        ctx.moveTo(10, 15); ctx.lineTo(10, 19); ctx.lineTo(13, 22); ctx.lineTo(17, 13);
        ctx.lineTo(17, 2); ctx.lineTo(5.7, 2); ctx.lineTo(4.3, 11); ctx.closePath();
      } else if (lvl === 3) {
        ctx.arc(12, 12, 9, 0, Math.PI * 2);
        ctx.moveTo(8, 12); ctx.lineTo(16, 12);
      } else if (lvl === 4) {
        ctx.moveTo(14, 9); ctx.lineTo(14, 5); ctx.lineTo(11, 2); ctx.lineTo(7, 11);
        ctx.lineTo(7, 22); ctx.lineTo(18.3, 22); ctx.lineTo(19.7, 13); ctx.closePath();
      } else {
        ctx.moveTo(2, 4); ctx.lineTo(5, 16); ctx.lineTo(19, 16); ctx.lineTo(22, 4);
        ctx.lineTo(16, 11); ctx.lineTo(12, 6); ctx.lineTo(8, 11); ctx.closePath();
        ctx.fillStyle = "rgba(196, 169, 109, 0.22)";
        ctx.fill();
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  // Coordinate transforms
  function worldToScreen(wx, wy) {
    return {
      x: (wx - camera.x) * camera.zoom + width / 2,
      y: (wy - camera.y) * camera.zoom + height / 2
    };
  }

  function screenToWorld(sx, sy) {
    return {
      x: (sx - width / 2) / camera.zoom + camera.x,
      y: (sy - height / 2) / camera.zoom + camera.y
    };
  }

  // Lifecycle & Init
  function init() {
    console.log("[COSMOS JS] Initializing Cinephile Taste Atlas Engine...");
    canvas = document.getElementById("cosmos-canvas");
    if (!canvas) {
      console.error("[COSMOS JS] CRITICAL: #cosmos-canvas element not found in DOM!");
      return;
    }

    ctx = canvas.getContext("2d");
    dpr = Math.min(window.devicePixelRatio || 1, 2);

    initDOM();
    handleResize();

    console.log("[COSMOS JS] Canvas size:", width, "x", height, "DPR:", dpr);

    window.addEventListener("resize", handleResize);
    setupEvents();

    // Start 60 FPS ambient cosmos render loop immediately
    if (!animationFrameId) {
      console.log("[COSMOS JS] Starting requestAnimationFrame renderLoop");
      animationFrameId = requestAnimationFrame(renderLoop);
    }

    // 1. Instant Hydration from Bootstrap Script Tag (0 Milliseconds)
    const bootstrapEl = document.getElementById("cosmos-bootstrap-data");
    let hasBootstrapData = false;
    if (bootstrapEl && bootstrapEl.textContent.trim()) {
      try {
        const initialData = JSON.parse(bootstrapEl.textContent);
        if (initialData && initialData.stars && initialData.stars.length > 0) {
          console.log("[COSMOS JS] Instant bootstrap hydration:", initialData.stars.length, "stars,", initialData.sectors ? initialData.sectors.length : 0, "sectors");
          galaxyData = initialData;
          updateStats(initialData.stats);
          renderSectorWayfinders(initialData.sectors);
          updateClusterDropdownMenu(initialData.sectors);
          applyFilters();
          showLoader(false);
          hasBootstrapData = true;

          // Level 1 Overview starts centered at (0, 0)
          camera.x = 0;
          camera.y = 0;
          camera.targetX = 0;
          camera.targetY = 0;
          camera.zoom = 0.72;
          camera.targetZoom = 0.72;
        }
      } catch (err) {
        console.warn("[COSMOS JS] Error parsing bootstrap data:", err);
      }
    }

    // 2. Fetch Latest/Fresh Data from API in background
    loadGalaxyData(false, !hasBootstrapData);
  }

  function initDOM() {
    hudEl = document.getElementById("cosmos-star-hud");
    hudBackdrop = document.getElementById("hud-backdrop");
    hudPoster = document.getElementById("hud-poster");
    hudTitle = document.getElementById("hud-title");
    hudMeta = document.getElementById("hud-meta");
    hudDirector = document.getElementById("hud-director");
    hudYear = document.getElementById("hud-year");
    hudMatch = document.getElementById("hud-score") || document.getElementById("hud-match");
    hudCategory = document.getElementById("hud-tag") || document.getElementById("hud-category");
    hudFrontierBadge = document.getElementById("hud-frontier-badge");
    hudGenres = document.getElementById("hud-genres");
    hudActionBtn = document.getElementById("hud-action-btn");
    hudReason = document.getElementById("hud-reason");

    hudAffinityReason = document.getElementById("hud-affinity-reason");
    hudCraftMeta = document.getElementById("hud-craft-meta");
    hudCraftDopRow = document.getElementById("hud-craft-dop-row");
    hudCraftDop = document.getElementById("hud-craft-dop");
    hudCraftComposerRow = document.getElementById("hud-craft-composer-row");
    hudCraftComposer = document.getElementById("hud-craft-composer");
    hudCraftWriterRow = document.getElementById("hud-craft-writer-row");
    hudCraftWriter = document.getElementById("hud-craft-writer");

    hudDragHandle = document.getElementById("hud-drag-handle");
    hudWatchlistBtn = document.getElementById("hud-watchlist-btn");
    hudFormatTag = document.getElementById("hud-format-tag");

    hudExploratoryTag = document.getElementById("hud-exploratory-tag");
    hudLowEvidenceTag = document.getElementById("hud-low-evidence-tag");

    tasteFeedScrollEl = document.getElementById("taste-feed-scroll");

    wayfindersContainer = document.getElementById("sector-wayfinders");
    feedWayfindersContainer = document.getElementById("feed-sector-wayfinders");
    probeDrawer = document.getElementById("probe-drawer");
    probeList = document.getElementById("probe-list");
    modeBanner = document.getElementById("cosmos-mode-banner");
    bannerText = document.getElementById("cosmos-mode-banner-text");

    statsWatchedEl = document.getElementById("stat-watched-feed");
    statsUnchartedEl = document.getElementById("stat-uncharted-feed");
    statsWatchlistEl = document.getElementById("stat-watchlist-feed");
    statsTotalEl = document.getElementById("stat-total-feed");

    searchInput = document.getElementById("cosmos-search-input");
    searchResultsEl = document.getElementById("cosmos-search-results");

    mobileTopBar = document.getElementById("cosmos-mobile-map-topbar");
    mobileActiveRealmBtn = document.getElementById("mobile-active-realm-btn");
    mobileRealmDot = document.getElementById("mobile-realm-dot");
    mobileRealmName = document.getElementById("mobile-realm-name");
    mobileSearchBtn = document.getElementById("mobile-map-search-btn");
    mobileSearchOverlay = document.getElementById("mobile-map-search-overlay");
    mobileSearchInput = document.getElementById("mobile-map-search-input");
    mobileSearchClearBtn = document.getElementById("mobile-search-clear-btn");
    mobileSearchResults = document.getElementById("mobile-map-search-results");
    mobileFiltersBtn = document.getElementById("mobile-map-filters-btn");
    mobileFilterSheet = document.getElementById("mobile-filter-sheet");
    mobileFilterSheetClose = document.getElementById("mobile-filter-sheet-close");
    mobileOverviewBtn = document.getElementById("mobile-map-overview-btn");
    mobileCenterBtn = document.getElementById("mobile-map-center-btn");
    mobileSamplerBtn = document.getElementById("mobile-map-sampler-btn");

    clusterDropdownBtn = document.getElementById("cluster-dropdown-btn");
    clusterDropdownMenu = document.getElementById("cluster-dropdown-menu");
    mobileClusterDropdownMenu = document.getElementById("mobile-cluster-dropdown-menu");
    clusterActiveDot = document.getElementById("cluster-active-dot");
    clusterActiveLabel = document.getElementById("cluster-active-label");

    feedToggleClustersBtn = document.getElementById("feed-toggle-clusters-btn");
    feedToggleClustersLabel = document.getElementById("feed-toggle-clusters-label");
  }

  function handleResize() {
    if (!canvas) return;
    const container = document.getElementById("taste-manifold-pane") || canvas.parentElement;
    let w = container ? container.clientWidth : 0;
    let h = container ? container.clientHeight : 0;

    if (!w || w <= 0) {
      const rect = canvas.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
    }

    if (!w || w <= 0) {
      w = currentViewMode === "manifold" ? window.innerWidth : (window.innerWidth * 0.48);
      h = window.innerHeight - 58;
    }

    width = Math.max(200, w);
    height = Math.max(200, h);

    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }

  function loadGalaxyData(forceRefresh = false, showLoadingScreen = true) {
    const url = `/api/cosmos/galaxy${forceRefresh ? "?refresh=1" : ""}`;
    console.log("[COSMOS JS] Requesting galaxy data from:", url);
    if (showLoadingScreen) {
      showLoader(true);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    fetch(url, { signal: controller.signal })
      .then((res) => {
        console.log("[COSMOS JS] Fetch response received with status:", res.status);
        return res.json();
      })
      .then((data) => {
        clearTimeout(timeoutId);
        showLoader(false);
        if (!data.success) {
          console.error("[COSMOS JS] Server reported failure loading galaxy:", data.error);
          return;
        }

        console.log("[COSMOS JS] Successfully parsed galaxy payload:", data.stars ? data.stars.length : 0, "stars,", data.sectors ? data.sectors.length : 0, "sectors");

        galaxyData = data;
        if (galaxyData.stars) {
          for (let i = 0; i < galaxyData.stars.length; i++) {
            galaxyData.stars[i].targetX = galaxyData.stars[i].x;
            galaxyData.stars[i].targetY = galaxyData.stars[i].y;
          }
        }
        updateStats(data.stats);
        renderSectorWayfinders(data.sectors);
        updateClusterDropdownMenu(data.sectors);
        applyFilters();

        // If no sector is active, stay centered on galaxy overview
        if (!activeSectorId) {
          camera.targetX = 0;
          camera.targetY = 0;
        }
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        showLoader(false);
        console.warn("[COSMOS JS] Galaxy load error/fallback:", err);
      });
  }

  function runForceDirectedSimulation() {
    if (!galaxyData.stars || galaxyData.stars.length === 0) return;
    const stars = galaxyData.stars;
    const links = galaxyData.links || [];
    const sectors = galaxyData.sectors || [];

    const starMap = new Map(stars.map((s) => [s.id, s]));
    const sectorMap = new Map(sectors.map((sec) => [sec.id, sec]));

    // Initialize velocities
    for (let i = 0; i < stars.length; i++) {
      stars[i].vx = 0;
      stars[i].vy = 0;
    }

    // Fast 85-iteration Spring-Charge convergence loop
    const iterations = 85;
    for (let iter = 0; iter < iterations; iter++) {
      const alpha = Math.pow(1 - iter / iterations, 1.4); // Cooling factor

      // 1. Spring forces along edges
      for (let i = 0; i < links.length; i++) {
        const link = links[i];
        const s1 = starMap.get(link.source);
        const s2 = starMap.get(link.target);
        if (!s1 || !s2) continue;

        const dx = s2.x - s1.x;
        const dy = s2.y - s1.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;

        let restLength = 95;
        let springK = 0.050;
        if (link.link_type === "franchise") {
          restLength = 32; // Franchise items stay tightly coupled
          springK = 0.14;
        } else if (link.link_type === "director") {
          restLength = 55;
          springK = 0.085;
        } else if (link.link_type === "cinematography" || link.link_type === "composer") {
          restLength = 72;
          springK = 0.065;
        }

        const force = (dist - restLength) * springK * alpha * (link.strength || 1.0);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        s1.vx += fx;
        s1.vy += fy;
        s2.vx -= fx;
        s2.vy -= fy;
      }

      // 2. Pairwise Electrostatic Repulsion (sampled for performance)
      const numStars = stars.length;
      for (let i = 0; i < numStars; i++) {
        const s1 = stars[i];
        for (let step = 1; step <= 25; step++) {
          const j = (i + step) % numStars;
          const s2 = stars[j];
          const dx = s1.x - s2.x;
          const dy = s1.y - s2.y;
          const distSq = dx * dx + dy * dy + 1.0;
          if (distSq < 18000) { // Within 134px
            const dist = Math.sqrt(distSq);
            const repForce = (190.0 / (distSq + 15.0)) * alpha;
            s1.vx += (dx / dist) * repForce;
            s1.vy += (dy / dist) * repForce;
            s2.vx -= (dx / dist) * repForce;
            s2.vy -= (dy / dist) * repForce;
          }
        }
      }

      // 3. Realm Centroid Gravity Pull (keeps macro realms in place)
      for (let i = 0; i < numStars; i++) {
        const s = stars[i];
        const sec = sectorMap.get(s.sector_id);
        if (sec && typeof sec.cx === "number") {
          const cdx = sec.cx - s.x;
          const cdy = sec.cy - s.y;
          s.vx += cdx * 0.010 * alpha;
          s.vy += cdy * 0.010 * alpha;
        }
        // Center gravity towards origin
        s.vx -= s.x * 0.002 * alpha;
        s.vy -= s.y * 0.002 * alpha;

        // Apply velocity with damping
        s.vx *= 0.80;
        s.vy *= 0.80;
        s.x += s.vx;
        s.y += s.vy;
        s.targetX = s.x;
        s.targetY = s.y;
      }
    }
  }

  function showLoader(show) {
    const loader = document.getElementById("cosmos-loading-overlay");
    if (loader) {
      if (show) {
        loader.classList.remove("hidden");
        loader.style.display = "flex";
        loader.style.opacity = "1";
        loader.style.pointerEvents = "all";
      } else {
        loader.classList.add("hidden");
        loader.style.opacity = "0";
        loader.style.pointerEvents = "none";
        setTimeout(() => {
          if (loader.classList.contains("hidden")) {
            loader.style.display = "none";
          }
        }, 300);
      }
    }
  }

  function updateStats(stats) {
    if (!stats) return;
    if (statsWatchedEl) statsWatchedEl.textContent = stats.watched_stars || 0;
    if (statsUnchartedEl) statsUnchartedEl.textContent = stats.uncharted_beacons || 0;
    if (statsWatchlistEl) statsWatchlistEl.textContent = stats.watchlist_stars || 0;
    if (statsTotalEl) statsTotalEl.textContent = stats.total_celestial_bodies || 0;
  }

  let activeSectorId = null; // null = Level 1 (Overview), "sector_0" = Level 2 (Deep-dive)
  let hoveredSector = null; // Sector hovered in Level 1 overview

  function setViewMode(mode) {
    currentViewMode = mode;
    const vp = document.getElementById("cosmos-viewport");
    if (vp) {
      vp.classList.remove("view-mode-split", "view-mode-feed", "view-mode-manifold");
      vp.classList.add(`view-mode-${mode}`);
    }
    document.querySelectorAll(".view-mode-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === mode);
    });
    handleResize();
    requestAnimationFrame(() => {
      handleResize();
    });
    setTimeout(() => {
      handleResize();
    }, 60);
    setTimeout(() => {
      handleResize();
    }, 200);
  }

  function setMobileView(view) {
    currentMobileView = view;
    const vp = document.getElementById("cosmos-viewport");
    if (vp) {
      vp.classList.remove("mobile-view-feed", "mobile-view-manifold");
      vp.classList.add(`mobile-view-${view}`);
    }
    document.querySelectorAll(".mobile-nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mobileView === view);
    });

    if (view === "manifold") {
      handleResize();
      requestAnimationFrame(() => {
        handleResize();
      });
      setTimeout(() => {
        handleResize();
      }, 60);
      setTimeout(() => {
        handleResize();
      }, 200);
    } else {
      unpinHUD();
    }
  }

  function centerActiveRealm() {
    if (selectedStar) {
      flyToCoordinates(selectedStar.x, selectedStar.y, 1.45);
      return;
    }
    if (activeSectorId && galaxyData.sectors) {
      const sec = galaxyData.sectors.find((s) => s.id === activeSectorId);
      if (sec && typeof sec.cx === "number" && typeof sec.cy === "number") {
        flyToCoordinates(sec.cx, sec.cy, 1.35);
        return;
      }
    }
    flyToCoordinates(0, 0, 0.85);
  }

  function selectSector(sectorId) {
    if (activeSpiderfy) {
      collapseSpiderfy(true);
    }
    activeSectorId = sectorId;
    hoveredSector = null;
    selectedStar = null;
    hideHUD();

    if (sectorId) {
      const sec = galaxyData.sectors ? galaxyData.sectors.find((s) => s.id === sectorId) : null;
      if (sec) {
        flyToCoordinates(sec.cx, sec.cy, 1.38);
        if (mobileRealmName && mobileRealmDot) {
          mobileRealmName.textContent = `⬡ ${getShortClusterLabel(sec) || sec.name}`;
          mobileRealmDot.style.background = sec.color || "#0ea5e9";
        }
        if (clusterActiveLabel && clusterActiveDot) {
          clusterActiveLabel.textContent = getShortClusterLabel(sec) || sec.name;
          clusterActiveDot.style.background = sec.color || "#0ea5e9";
        }
      }
      const groupEl = document.getElementById(`domain-group-${sectorId}`);
      if (groupEl) {
        groupEl.classList.remove("collapsed");
        const h = groupEl.querySelector(".domain-group-header");
        if (h) h.setAttribute("aria-expanded", "true");
        expandedClusterIds.add(sectorId);
        updateToggleAllClustersButton();
        if (tasteFeedScrollEl) {
          groupEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    } else {
      flyToCoordinates(0, 0, 0.75);
      if (mobileRealmName && mobileRealmDot) {
        mobileRealmName.textContent = "⬡ ALL CLUSTERS";
        mobileRealmDot.style.background = "#bae6fd";
      }
      if (clusterActiveLabel && clusterActiveDot) {
        clusterActiveLabel.textContent = "All Clusters";
        clusterActiveDot.style.background = "#bae6fd";
      }
      if (tasteFeedScrollEl) {
        tasteFeedScrollEl.scrollTo({ top: 0, behavior: "smooth" });
      }
    }

    if (clusterDropdownMenu) {
      clusterDropdownMenu.querySelectorAll(".cluster-dropdown-item").forEach((it) => {
        const itSec = it.dataset.sector;
        it.classList.toggle("active", (!sectorId && itSec === "all") || (sectorId === itSec));
      });
    }
    if (mobileClusterDropdownMenu) {
      mobileClusterDropdownMenu.querySelectorAll(".cluster-dropdown-item").forEach((it) => {
        const itSec = it.dataset.sector;
        it.classList.toggle("active", (!sectorId && itSec === "all") || (sectorId === itSec));
      });
    }

    applyFilters();
    renderSectorWayfinders(galaxyData.sectors);
    updateStats(galaxyData.stats);
  }

  function resetToOverview() {
    unpinHUD();
    closeProbe();
    selectSector(null);
  }

  function renderSectorWayfinders(sectors) {
    const containers = [wayfindersContainer, feedWayfindersContainer].filter(Boolean);
    if (containers.length === 0 || !sectors) return;

    containers.forEach((container) => {
      container.innerHTML = "";

      // Breadcrumb / Reset button if a sector is active
      if (activeSectorId) {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "sector-wayfinder-btn wayfinder-back-btn";
        resetBtn.title = "Return to Galaxy Overview (Esc)";
        resetBtn.innerHTML = `<i class="fa-solid fa-arrow-left"></i> <span class="sec-name">ALL CLUSTERS</span>`;
        resetBtn.addEventListener("click", () => {
          resetToOverview();
        });
        container.appendChild(resetBtn);

        const activeSec = sectors.find((s) => s.id === activeSectorId);
        if (activeSec) {
          const parentBtn = document.createElement("button");
          parentBtn.type = "button";
          parentBtn.className = "sector-wayfinder-btn active";
          parentBtn.style.borderColor = activeSec.color;
          parentBtn.innerHTML = `<span class="sec-dot" style="background: ${activeSec.color};"></span> <span class="sec-code">${activeSec.code}</span> <span class="sec-name">${activeSec.name} (${activeSec.count})</span>`;
          parentBtn.addEventListener("click", () => {
            flyToCoordinates(activeSec.cx, activeSec.cy, 1.15);
          });
          container.appendChild(parentBtn);
        }
        return;
      }

      // Default Macro Sectors list (Level 1)
      const allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "sector-wayfinder-btn active";
      allBtn.innerHTML = `<span class="sec-dot" style="background: #bae6fd;"></span> <span class="sec-name">ALL CLUSTERS</span>`;
      allBtn.addEventListener("click", () => {
        selectSector(null);
      });
      container.appendChild(allBtn);

      sectors.forEach((sec) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "sector-wayfinder-btn";
        btn.title = sec.subtitle ? `${sec.name} — ${sec.subtitle}` : sec.name;
        btn.innerHTML = `<span class="sec-dot" style="background: ${sec.color};"></span> <span class="sec-code">${sec.code}</span> <span class="sec-name">${getShortClusterLabel(sec) || sec.name} (${sec.count})</span>`;
        btn.addEventListener("click", () => {
          selectSector(sec.id);
        });
        container.appendChild(btn);
      });
    });
  }

  function highlightSector(secId) {
    selectSector(secId);
  }

  function flyToCoordinates(x, y, targetZoom = 1.3) {
    if (isNaN(x) || isNaN(y)) return;
    camera.targetX = Math.max(-1400, Math.min(1400, x));
    camera.targetY = Math.max(-1400, Math.min(1400, y));
    camera.targetZoom = Math.max(camera.minZoom, Math.min(camera.maxZoom, targetZoom));
  }

  function focusStarOnMap(starId) {
    if (!galaxyData.stars) return;
    const star = galaxyData.stars.find((s) => s.id === starId);
    if (!star) return;

    if (window.innerWidth <= 991) {
      setMobileView("manifold");
    } else if (currentViewMode === "feed") {
      setViewMode("split");
    }

    selectedStar = star;
    star._selectAnimStart = performance.now();
    selectedResonantNeighbors = computeLocalResonantNeighbors(star, 3);
    hoveredStar = star;
    showHUD(star, true);
    searchTargetStar = star;
    searchCrosshairTime = performance.now();
    flyToCoordinates(star.x, star.y, 1.45);
  }

  function scrollFeedToCard(starId) {
    if (!tasteFeedScrollEl) return;
    const card = document.getElementById(`card-${starId}`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      document.querySelectorAll(".taste-card.pulse-highlight").forEach((c) => c.classList.remove("pulse-highlight"));
      card.classList.add("pulse-highlight");
      setTimeout(() => {
        card.classList.remove("pulse-highlight");
      }, 2500);
    }
  }

  function toggleWatchlist(event, starId) {
    if (event) event.stopPropagation();
    const star = galaxyData.stars ? galaxyData.stars.find((s) => s.id === starId) : null;
    if (!star) return;

    const btn = event ? event.currentTarget : null;
    const csrfToken = getCsrfToken();

    fetch("/api/watchlist/add_ajax", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      },
      body: JSON.stringify({
        title: star.title,
        year: star.year,
        director: star.director,
        media_type: (star.tv_show === 1 || star.media_type === "tv") ? "tv" : "movie"
      })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          console.warn("[COSMOS JS] Watchlist AJAX returned error:", data.error);
        } else {
          star.is_watchlist = true;
          if (btn) {
            btn.classList.add("in-watchlist");
            btn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Watchlisted</span>`;
          }
          if (galaxyData.stats) {
            galaxyData.stats.watchlist_stars = (galaxyData.stats.watchlist_stars || 0) + 1;
            updateStats(galaxyData.stats);
          }
        }
      })
      .catch((err) => {
        console.warn("[COSMOS JS] Watchlist add error:", err);
      });
  }

  function renderTasteFeed() {
    if (!tasteFeedScrollEl) return;

    const starsToRender = filteredStars || [];
    if (starsToRender.length === 0) {
      tasteFeedScrollEl.innerHTML = `
        <div class="feed-empty-state">
          <i class="fa-solid fa-layer-group" style="font-size: 2rem; color: var(--atlas-cyan);"></i>
          <span>No cinematic nodes match current filter criteria.</span>
        </div>
      `;
      return;
    }

    // Group filtered stars by sector
    const sectorMap = new Map();
    const sectors = galaxyData.sectors || [];
    sectors.forEach((sec) => {
      sectorMap.set(sec.id, { sector: sec, stars: [] });
    });

    const fallbackSector = { id: "sec_misc", name: "TASTE FRONTIER", code: "FRONTIER", color: "#0ea5e9", description: "Diverse cinematic cross-pollination." };
    sectorMap.set("sec_misc", { sector: fallbackSector, stars: [] });

    starsToRender.forEach((star) => {
      const secId = star.sector_id && sectorMap.has(star.sector_id) ? star.sector_id : "sec_misc";
      sectorMap.get(secId).stars.push(star);
    });

    let html = "";
    sectorMap.forEach((entry, secId) => {
      if (entry.stars.length === 0) return;
      const sec = entry.sector;
      const stars = entry.stars;
      const isCollapsed = !expandedClusterIds.has(sec.id);
      const clusterDisplayName = formatClusterTitle(sec);
      const secColor = sec.color || '#0ea5e9';
      const secColorRgba = hexToRgba(secColor, 0.18);
      const secBorderRgba = hexToRgba(secColor, 0.38);

      html += `
        <div class="domain-group ${isCollapsed ? 'collapsed' : ''}" id="domain-group-${sec.id}" data-sector-id="${sec.id}">
          <div class="domain-group-header" role="button" tabindex="0" aria-expanded="${!isCollapsed}" data-sector-id="${sec.id}"
               style="--cluster-color: ${secColor}; border-left-color: ${secColor} !important; border-color: ${secBorderRgba} !important; background: linear-gradient(90deg, ${secColorRgba} 0%, rgba(13, 20, 34, 0.94) 48%, rgba(8, 12, 22, 0.98) 100%) !important;"
               title="Click to toggle ${clusterDisplayName} works">
            <div class="domain-header-left">
              <span class="domain-color-pip" style="background: ${secColor}; box-shadow: 0 0 8px ${secColor};"></span>
              <h3 class="domain-title">${clusterDisplayName}</h3>
            </div>
            <div class="domain-header-right">
              <span class="domain-count-inline" style="color: ${secColor};">${stars.length} titles</span>
              <span class="domain-toggle-icon" aria-hidden="true" style="color: ${secColor};"><i class="fa-solid fa-chevron-right"></i></span>
            </div>
          </div>
          <div class="domain-cards-list">
      `;

      stars.forEach((star) => {
        const isTv = star.tv_show === 1 || star.tv_show === "1" || star.tv_show === true || star.media_type === "tv";
        const isWatched = !!star.is_watched;
        const isWatchlist = !!star.is_watchlist;
        const craft = star.craft || {};

        let statusBadge = "";
        if (isWatched) {
          statusBadge = getSentimentBadgeHtml(star.rating, true, true);
        } else {
          let extraBadges = "";
          if (star.is_exploratory) {
            extraBadges = `<span class="card-status-pill status-exploratory" title="Cross-Modal Discovery: High intrigue across modalities">✦ Exploratory</span> `;
          } else if (star.low_evidence) {
            extraBadges = `<span class="card-status-pill status-sparse" title="Sparse Evidence: Limited metadata or graph lineage">⚠ Sparse</span> `;
          }
          const matchVal = star.match_score || star.match_pct || 90;
          const probTip = star.calibrated_prob !== undefined ? ` title="Calibrated P(Enjoy): ${Math.round(star.calibrated_prob * 100)}%"` : "";
          statusBadge = `<div class="card-status-cluster">${extraBadges}<span class="card-status-pill status-match"${probTip}><i class="fa-solid fa-star"></i> ${matchVal}% Match</span></div>`;
        }

        let craftChips = "";
        if (craft.cinematographer) {
          craftChips += `<span class="craft-chip"><i class="fa-solid fa-video"></i> ${craft.cinematographer} (DoP)</span>`;
        }
        if (craft.composer) {
          craftChips += `<span class="craft-chip"><i class="fa-solid fa-music"></i> ${craft.composer} (Score)</span>`;
        }
        if (craft.screenwriter) {
          craftChips += `<span class="craft-chip"><i class="fa-solid fa-pen-fancy"></i> ${craft.screenwriter} (Writer)</span>`;
        }

        let rtStr = "";
        if (star.formatted_runtime) {
          rtStr = star.formatted_runtime;
        } else if (star.runtime) {
          const num = parseInt(star.runtime, 10);
          if (!isNaN(num) && num > 0) {
            const h = Math.floor(num / 60);
            const m = num % 60;
            rtStr = h > 0 && m > 0 ? `${h}h ${m}m` : (h > 0 ? `${h}h` : `${m}m`);
          }
        }
        const dirStr = star.director ? `Dir. ${star.director}` : "";
        const metaParts = [
          `<span class="card-format-badge">${isTv ? 'SERIES' : 'FILM'}</span>`,
          star.year || null,
          rtStr || null,
          dirStr || null
        ].filter(Boolean);

        const fallbackPoster = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='150' fill='%23080e18'><rect width='100' height='150' fill='%23080e18'/><path d='M35 55 h30 v40 h-30 z' fill='none' stroke='%2338bdf8' stroke-width='2' stroke-linejoin='round'/><circle cx='50' cy='75' r='8' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><text x='50%' y='83%' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='8' font-weight='bold' letter-spacing='1'>KINETO</text></svg>";
        const posterUrl = (star.poster && star.poster.startsWith("http")) ? star.poster : fallbackPoster;

        html += `
          <article class="taste-card" id="card-${star.id}" data-star-id="${star.id}">
            <div class="card-poster-wrap">
              <img src="${posterUrl}" alt="${star.title}" class="card-poster" loading="lazy" onerror="this.src='${fallbackPoster}'" />
            </div>
            <div class="card-body">
              <div class="card-header-row">
                <div class="card-title-group">
                  <h4 class="card-title" title="${star.title}">${star.title}</h4>
                  <div class="card-meta">${metaParts.join(" • ")}</div>
                </div>
                ${statusBadge}
              </div>
              
              ${(!isWatched && star.affinity_reason) ? `<p class="card-affinity-reason">💡 ${star.affinity_reason}</p>` : ''}

              ${craftChips ? `<div class="card-craft-chips">${craftChips}</div>` : ''}

              <div class="card-actions-row">
                ${!isWatched ? `
                <button type="button" class="card-btn btn-watchlist ${isWatchlist ? 'in-watchlist' : ''}" data-star-id="${star.id}" onclick="window.CosmosEngine && window.CosmosEngine.toggleWatchlist(event, '${star.id}')">
                  <i class="fa-solid ${isWatchlist ? 'fa-check' : 'fa-plus'}"></i> <span>${isWatchlist ? 'Watchlisted' : 'Watchlist'}</span>
                </button>` : ''}
                <button type="button" class="card-btn btn-details" onclick="window.CosmosEngine && window.CosmosEngine.openMediaDetailsById('${star.id}')">
                  <i class="fa-solid fa-circle-info"></i> Details
                </button>
                <button type="button" class="card-btn btn-focus-map" onclick="window.CosmosEngine && window.CosmosEngine.focusStarOnMap('${star.id}')">
                  <i class="fa-solid fa-crosshairs"></i> <span class="btn-text-full">Focus on Map</span><span class="btn-text-short">Map</span>
                </button>
              </div>
            </div>
          </article>
        `;
      });

      html += `
          </div>
        </div>
      `;
    });

    tasteFeedScrollEl.innerHTML = html;

    // Attach card hover sync events
    tasteFeedScrollEl.querySelectorAll(".taste-card").forEach((card) => {
      const starId = card.dataset.starId;
      card.addEventListener("mouseenter", () => {
        if (selectedStar) return;
        const star = galaxyData.stars ? galaxyData.stars.find((s) => s.id === starId) : null;
        if (star) {
          hoveredStar = star;
        }
      });
      card.addEventListener("mouseleave", () => {
        if (!selectedStar) {
          hoveredStar = null;
        }
      });
      card.addEventListener("click", () => {
        const star = galaxyData.stars ? galaxyData.stars.find((s) => s.id === starId) : null;
        if (star) {
          handleStarClick(star);
        }
      });
    });
  }

  function applyFilters() {
    if (!galaxyData.stars) return;

    // Filter stars based on active sector (if any) and active filter criteria
    filteredStars = galaxyData.stars.filter((star) => {
      // If a specific sector is selected, restrict to that sector; otherwise show across whole cosmos
      if (activeSectorId && star.sector_id !== activeSectorId) return false;

      // Media Type
      const isTv = star.tv_show === 1 || star.tv_show === "1" || star.tv_show === true || star.media_type === "tv";
      if (filters.mediaType === "movie" && isTv) return false;
      if (filters.mediaType === "tv" && !isTv) return false;

      // Category
      if (filters.category === "watched" && !star.is_watched) return false;
      if (filters.category === "uncharted" && star.is_watched) return false;
      if (filters.category === "watchlist" && !star.is_watchlist) return false;

      // Search Query
      if (filters.searchQuery) {
        const q = filters.searchQuery.toLowerCase();
        const matches =
          (star.title && star.title.toLowerCase().includes(q)) ||
          (star.director && star.director.toLowerCase().includes(q)) ||
          (star.genre && star.genre.toLowerCase().includes(q));
        if (!matches) return false;
      }

      return true;
    });

    const activeStarIds = new Set(filteredStars.map((s) => s.id));
    filteredLinks = (galaxyData.links || []).filter(
      (l) => activeStarIds.has(l.source) && activeStarIds.has(l.target)
    );

    updateSuperDenseClumps();

    if (activeSpiderfy) {
      collapseSpiderfy(true);
    }

    renderTasteFeed();
    updateDiscoveryTray();
  }

  function updateDiscoveryTray() {
    const tray = document.getElementById("discovery-tray-list");
    if (!tray || !galaxyData.stars) return;

    if (filters.category === "watched") {
      const pool = (filteredStars && filteredStars.length > 0) ? filteredStars : galaxyData.stars;
      const watchedItems = pool
        .filter((s) => s.is_watched)
        .sort((a, b) => (b.rating || 0) - (a.rating || 0))
        .slice(0, 12);

      tray.innerHTML = "";
      if (watchedItems.length === 0) {
        tray.innerHTML = '<div class="tray-empty">No watched titles found matching current filters.</div>';
        return;
      }

      watchedItems.forEach((star) => {
        const card = createMiniStarCard(star);
        tray.appendChild(card);
      });
      return;
    }

    const pool = (filteredStars && filteredStars.length > 0) ? filteredStars : galaxyData.stars;
    const beacons = pool
      .filter((s) => !s.is_watched)
      .sort((a, b) => (b.match_score || b.match_pct || 0) - (a.match_score || a.match_pct || 0))
      .slice(0, 12);

    tray.innerHTML = "";
    if (beacons.length === 0) {
      tray.innerHTML = '<div class="tray-empty">No uncharted beacons found in current sector filter.</div>';
      return;
    }

    beacons.forEach((star) => {
      const card = createMiniStarCard(star);
      tray.appendChild(card);
    });
  }

  function selectStarById(starId) {
    if (!galaxyData.stars) return;
    const star = galaxyData.stars.find((s) => s.id === starId);
    if (!star) return;
    if (activeSpiderfy && !activeSpiderfy.items.some((it) => it.star.id === starId)) {
      collapseSpiderfy(true);
    }
    selectedStar = star;
    star._selectAnimStart = performance.now();
    selectedResonantNeighbors = computeLocalResonantNeighbors(star, 3);
    showHUD(star, true);
    flyToCoordinates(star.x, star.y, Math.max(camera.zoom, 1.4));
    scrollFeedToCard(star.id);
  }

  // Setup Event Listeners
  function setupEvents() {
    // Prevent clicks/drags on UI overlay components from bleeding into canvas
    document.querySelectorAll(".cosmos-control-dock, .cosmos-top-deck, .cosmos-bottom-shelf, .cosmos-side-drawer, .cosmos-star-hud, .cosmos-mobile-map-topbar, .mobile-map-search-overlay, .mobile-filter-sheet, .cosmos-mobile-map-actions, .cosmos-mobile-bar")
      .forEach((el) => {
        el.addEventListener("mousedown", (e) => e.stopPropagation());
        el.addEventListener("click", (e) => e.stopPropagation());
        el.addEventListener("touchstart", (e) => e.stopPropagation(), { passive: true });
      });

    // Canvas Drag & Pan (Mouse)
    canvas.addEventListener("mousedown", (e) => {
      camera.isDragging = true;
      camera.hasMovedSignificantly = false;
      camera.dragStartX = e.clientX;
      camera.dragStartY = e.clientY;
      camera.lastMouseX = e.clientX;
      camera.lastMouseY = e.clientY;
      camera.vx = 0;
      camera.vy = 0;
    });

    window.addEventListener("mousemove", (e) => {
      if (camera.isDragging) {
        const dx = e.clientX - camera.lastMouseX;
        const dy = e.clientY - camera.lastMouseY;
        const totalDist = Math.hypot(e.clientX - camera.dragStartX, e.clientY - camera.dragStartY);
        if (totalDist > 6) {
          camera.hasMovedSignificantly = true;
        }
        camera.targetX -= dx / camera.zoom;
        camera.targetY -= dy / camera.zoom;
        camera.lastMouseX = e.clientX;
        camera.lastMouseY = e.clientY;
      } else {
        checkHover(e.clientX, e.clientY);
      }
    });

    canvas.addEventListener("click", (e) => {
      if (camera.hasMovedSignificantly) {
        camera.hasMovedSignificantly = false;
        return;
      }
      handleCanvasClick(e.clientX, e.clientY);
    });

    window.addEventListener("mouseup", () => {
      camera.isDragging = false;
    });

    // High-Fidelity Touch Gestures (Mobile / Tablets)
    let touchStartDist = 0;
    let touchStartX = 0, touchStartY = 0;
    let pinchInitialZoom = 0.72;
    let panVx = 0, panVy = 0;
    let lastTouchMoveTime = 0;

    canvas.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        camera.isDragging = true;
        camera.hasMovedSignificantly = false;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        camera.lastMouseX = touchStartX;
        camera.lastMouseY = touchStartY;
        panVx = 0;
        panVy = 0;
        lastTouchMoveTime = performance.now();
      } else if (e.touches.length === 2) {
        camera.isDragging = false;
        touchStartDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        pinchInitialZoom = camera.zoom;
      }
    }, { passive: true });

    canvas.addEventListener("touchmove", (e) => {
      if (e.touches.length === 1 && camera.isDragging) {
        const now = performance.now();
        const dt = Math.max(1, now - lastTouchMoveTime);
        lastTouchMoveTime = now;

        const dx = e.touches[0].clientX - camera.lastMouseX;
        const dy = e.touches[0].clientY - camera.lastMouseY;
        if (Math.hypot(e.touches[0].clientX - touchStartX, e.touches[0].clientY - touchStartY) > 8) {
          camera.hasMovedSignificantly = true;
        }

        panVx = (dx / dt) * 16;
        panVy = (dy / dt) * 16;

        camera.targetX -= dx / camera.zoom;
        camera.targetY -= dy / camera.zoom;
        camera.lastMouseX = e.touches[0].clientX;
        camera.lastMouseY = e.touches[0].clientY;
      } else if (e.touches.length === 2 && touchStartDist > 0) {
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        const factor = dist / touchStartDist;

        // Smooth two-finger pinch-to-zoom with rubber-band boundaries
        const minPinch = camera.minZoom;
        const maxPinch = camera.maxZoom;
        let nextZoom = pinchInitialZoom * factor;
        if (nextZoom < minPinch) {
          nextZoom = minPinch - (minPinch - nextZoom) * 0.25;
        } else if (nextZoom > maxPinch) {
          nextZoom = maxPinch + (nextZoom - maxPinch) * 0.25;
        }

        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const worldBefore = screenToWorld(midX, midY);

        camera.targetZoom = Math.max(camera.minZoom, Math.min(camera.maxZoom, nextZoom));
        camera.zoom = camera.targetZoom;

        camera.targetX = worldBefore.x - (midX - width / 2) / camera.targetZoom;
        camera.targetY = worldBefore.y - (midY - height / 2) / camera.targetZoom;
      }
    }, { passive: true });

    canvas.addEventListener("touchend", (e) => {
      if (camera.isDragging) {
        if (!camera.hasMovedSignificantly && e.changedTouches && e.changedTouches.length > 0) {
          handleCanvasClick(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
        } else if (camera.hasMovedSignificantly) {
          // Smooth single-finger momentum panning glide
          camera.targetX -= (panVx * 2.8) / camera.zoom;
          camera.targetY -= (panVy * 2.8) / camera.zoom;
        }
      }
      camera.isDragging = false;
      panVx = 0;
      panVy = 0;
    }, { passive: true });

    // Smooth Cursor-Centric Zoom (Mouse Wheel)
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const worldBefore = screenToWorld(mouseX, mouseY);

      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newZoom = Math.max(camera.minZoom, Math.min(camera.maxZoom, camera.targetZoom * zoomFactor));
      camera.targetZoom = newZoom;

      // Adjust target position so mouse point remains stationary
      camera.targetX = worldBefore.x - (mouseX - width / 2) / newZoom;
      camera.targetY = worldBefore.y - (mouseY - height / 2) / newZoom;
    }, { passive: false });

    // View Mode Switcher (Split / Feed / Map on Desktop)
    document.querySelectorAll(".view-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        setViewMode(view);
      });
    });

    // Mobile Bottom Navigation Bar (Feed / Map)
    document.querySelectorAll(".mobile-nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.mobileView;
        setMobileView(view);
      });
    });

    // Mode Selector Buttons
    document.querySelectorAll(".cosmos-mode-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const mode = btn.dataset.mode;
        if (mode === "probe" && currentMode === "probe") {
          setMode("explore");
        } else {
          setMode(mode);
        }
      });
    });

    // Filter Buttons (Feed and Mobile Sheet)
    document.querySelectorAll(".filter-pill[data-filter]").forEach((pill) => {
      pill.addEventListener("click", () => {
        const type = pill.dataset.filterType;
        const val = pill.dataset.filter;

        document.querySelectorAll(`.filter-pill[data-filter-type="${type}"]`).forEach((p) => {
          p.classList.toggle("active", p.dataset.filter === val);
        });

        filters[type] = val;
        applyFilters();
      });
    });

    // iOS Bottom Sheet Drag Handle Toggle
    if (hudDragHandle) {
      hudDragHandle.addEventListener("click", (e) => {
        e.stopPropagation();
        if (hudEl) hudEl.classList.toggle("sheet-expanded");
      });
    }

    // Swipe down to dismiss Bottom Sheet on Mobile
    if (hudEl) {
      let sheetTouchStartY = 0;
      let sheetTouchDeltaY = 0;
      hudEl.addEventListener("touchstart", (e) => {
        if (e.touches.length === 1) {
          sheetTouchStartY = e.touches[0].clientY;
          sheetTouchDeltaY = 0;
        }
      }, { passive: true });

      hudEl.addEventListener("touchmove", (e) => {
        if (e.touches.length === 1) {
          sheetTouchDeltaY = e.touches[0].clientY - sheetTouchStartY;
        }
      }, { passive: true });

      hudEl.addEventListener("touchend", () => {
        if (sheetTouchDeltaY > 60) {
          if (hudEl.classList.contains("sheet-expanded")) {
            hudEl.classList.remove("sheet-expanded");
          } else {
            unpinHUD();
          }
        }
      }, { passive: true });
    }

    // Close HUD Button
    const hudCloseBtn = document.getElementById("hud-close-btn");
    if (hudCloseBtn) {
      hudCloseBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        unpinHUD();
      });
    }

    // Refresh Button
    const refreshBtn = document.getElementById("refresh-galaxy-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        loadGalaxyData(true);
      });
    }

    // Reset View Button
    const resetViewBtn = document.getElementById("reset-view-btn");
    if (resetViewBtn) {
      resetViewBtn.addEventListener("click", () => {
        resetToOverview();
      });
    }

    // Mobile Top Bar & Action Controls (Reliable Click + Touchend)
    if (mobileOverviewBtn) {
      const handleOverview = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        resetToOverview();
        closeProbe();
      };
      mobileOverviewBtn.addEventListener("click", handleOverview);
      mobileOverviewBtn.addEventListener("touchend", handleOverview);
    }

    if (mobileCenterBtn) {
      const handleCenter = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        centerActiveRealm();
      };
      mobileCenterBtn.addEventListener("click", handleCenter);
      mobileCenterBtn.addEventListener("touchend", handleCenter);
    }

    if (mobileSamplerBtn) {
      const handleSampler = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        const nextMode = currentMode === "probe" ? "explore" : "probe";
        setMode(nextMode);
      };
      mobileSamplerBtn.addEventListener("click", handleSampler);
      mobileSamplerBtn.addEventListener("touchend", handleSampler);
    }

    if (mobileActiveRealmBtn) {
      const handleActiveRealm = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (mobileClusterDropdownMenu) {
          const isOpen = mobileClusterDropdownMenu.style.display === "flex";
          mobileClusterDropdownMenu.style.display = isOpen ? "none" : "flex";
          mobileActiveRealmBtn.classList.toggle("open", !isOpen);
          mobileActiveRealmBtn.setAttribute("aria-expanded", String(!isOpen));
        }
      };
      mobileActiveRealmBtn.addEventListener("click", handleActiveRealm);
    }

    if (mobileClusterDropdownMenu) {
      mobileClusterDropdownMenu.addEventListener("click", (e) => {
        e.stopPropagation();
        const item = e.target.closest(".cluster-dropdown-item");
        if (!item) return;
        const secId = item.dataset.sector;
        selectSector(secId === "all" ? null : secId);
        mobileClusterDropdownMenu.style.display = "none";
        if (mobileActiveRealmBtn) {
          mobileActiveRealmBtn.classList.remove("open");
          mobileActiveRealmBtn.setAttribute("aria-expanded", "false");
        }
      });
    }

    // Neighborhood Sampler Probe Drawer Close Listeners
    const probeDrawerClose = document.getElementById("probe-drawer-close");
    if (probeDrawerClose) {
      probeDrawerClose.addEventListener("click", (e) => {
        e.stopPropagation();
        closeProbe();
      });
    }

    const bannerCloseBtn = document.getElementById("banner-close-btn");
    if (bannerCloseBtn) {
      bannerCloseBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeProbe();
      });
    }

    const probeDragHandle = document.getElementById("probe-drag-handle");
    if (probeDragHandle) {
      probeDragHandle.addEventListener("click", (e) => {
        e.stopPropagation();
        if (probeDrawer) probeDrawer.classList.toggle("sheet-expanded");
      });
    }

    // Mobile Map Search Button & Overlay
    if (mobileSearchBtn && mobileSearchOverlay) {
      mobileSearchBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = mobileSearchOverlay.style.display !== "none";
        mobileSearchOverlay.style.display = isOpen ? "none" : "flex";
        if (!isOpen && mobileSearchInput) {
          mobileSearchInput.focus();
        }
      });
    }

    if (mobileSearchClearBtn && mobileSearchInput) {
      mobileSearchClearBtn.addEventListener("click", () => {
        mobileSearchInput.value = "";
        renderMobileSearchResults("");
      });
    }

    if (mobileSearchInput) {
      mobileSearchInput.addEventListener("input", (e) => {
        const val = e.target.value.trim();
        renderMobileSearchResults(val);
      });
    }

    // Mobile Filters Sheet Button & Close
    if (mobileFiltersBtn && mobileFilterSheet) {
      mobileFiltersBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = mobileFilterSheet.style.display !== "none";
        mobileFilterSheet.style.display = isOpen ? "none" : "flex";
      });
    }

    if (mobileFilterSheetClose && mobileFilterSheet) {
      mobileFilterSheetClose.addEventListener("click", () => {
        mobileFilterSheet.style.display = "none";
      });
    }

    // Canvas Double-Click to return to Overview
    canvas.addEventListener("dblclick", () => {
      if (activeSectorId) {
        resetToOverview();
      }
    });

    // Escape Key to close HUD or return to Overview
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (mobileSearchOverlay && mobileSearchOverlay.style.display !== "none") {
          mobileSearchOverlay.style.display = "none";
        } else if (mobileFilterSheet && mobileFilterSheet.style.display !== "none") {
          mobileFilterSheet.style.display = "none";
        } else if (currentMode === "probe") {
          closeProbe();
        } else if (selectedStar) {
          unpinHUD();
        } else if (activeSectorId) {
          resetToOverview();
        }
      }
    });

    // Search Input (Desktop)
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        const val = e.target.value.trim();
        filters.searchQuery = val;
        applyFilters();
        renderSearchResults(val);
      });

      searchInput.addEventListener("focus", () => {
        if (searchInput.value.trim()) {
          searchResultsEl.style.display = "block";
        }
      });
    }

    document.addEventListener("click", (e) => {
      if (searchResultsEl && !searchResultsEl.contains(e.target) && e.target !== searchInput) {
        searchResultsEl.style.display = "none";
      }
      if (mobileSearchOverlay && !mobileSearchOverlay.contains(e.target) && e.target !== mobileSearchBtn) {
        mobileSearchOverlay.style.display = "none";
      }
    });

    // Feed Cluster Accordion & Toggle Listeners
    if (tasteFeedScrollEl) {
      tasteFeedScrollEl.addEventListener("click", (e) => {
        const header = e.target.closest(".domain-group-header");
        if (!header) return;
        const group = header.closest(".domain-group");
        if (!group) return;
        hasUserInteractedClusters = true;
        const isCollapsed = group.classList.toggle("collapsed");
        header.setAttribute("aria-expanded", String(!isCollapsed));
        const secId = group.dataset.sectorId;
        if (secId) {
          if (isCollapsed) {
            expandedClusterIds.delete(secId);
          } else {
            expandedClusterIds.add(secId);
          }
        }
        updateToggleAllClustersButton();
      });

      tasteFeedScrollEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          const header = e.target.closest(".domain-group-header");
          if (header) {
            e.preventDefault();
            header.click();
          }
        }
      });
    }

    if (feedToggleClustersBtn) {
      feedToggleClustersBtn.addEventListener("click", () => {
        if (!tasteFeedScrollEl) return;
        const groups = tasteFeedScrollEl.querySelectorAll(".domain-group");
        if (groups.length === 0) return;
        hasUserInteractedClusters = true;
        const allCollapsed = Array.from(groups).every((g) => g.classList.contains("collapsed"));
        if (allCollapsed) {
          groups.forEach((g) => {
            g.classList.remove("collapsed");
            const h = g.querySelector(".domain-group-header");
            if (h) h.setAttribute("aria-expanded", "true");
            const secId = g.dataset.sectorId;
            if (secId) expandedClusterIds.add(secId);
          });
        } else {
          groups.forEach((g) => {
            g.classList.add("collapsed");
            const h = g.querySelector(".domain-group-header");
            if (h) h.setAttribute("aria-expanded", "false");
            const secId = g.dataset.sectorId;
            if (secId) expandedClusterIds.delete(secId);
          });
        }
        updateToggleAllClustersButton();
      });
    }

    setupClusterDropdown();
  }

  function updateToggleAllClustersButton() {
    if (!feedToggleClustersLabel || !tasteFeedScrollEl) return;
    const groups = tasteFeedScrollEl.querySelectorAll(".domain-group");
    if (groups.length === 0) return;
    const allCollapsed = Array.from(groups).every((g) => g.classList.contains("collapsed"));
    feedToggleClustersLabel.textContent = allCollapsed ? "Expand All" : "Collapse All";
  }

  function setupClusterDropdown() {
    if (!clusterDropdownBtn || !clusterDropdownMenu) return;

    clusterDropdownBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = clusterDropdownMenu.style.display !== "none";
      clusterDropdownMenu.style.display = isOpen ? "none" : "flex";
      clusterDropdownBtn.classList.toggle("open", !isOpen);
    });

    clusterDropdownMenu.addEventListener("click", (e) => {
      e.stopPropagation();
      const item = e.target.closest(".cluster-dropdown-item");
      if (!item) return;
      const secId = item.dataset.sector;
      selectSector(secId === "all" ? null : secId);
      clusterDropdownMenu.style.display = "none";
      clusterDropdownBtn.classList.remove("open");
    });

    document.addEventListener("click", (e) => {
      if (clusterDropdownMenu && !clusterDropdownMenu.contains(e.target) && e.target !== clusterDropdownBtn) {
        clusterDropdownMenu.style.display = "none";
        if (clusterDropdownBtn) clusterDropdownBtn.classList.remove("open");
      }
      if (mobileClusterDropdownMenu && !mobileClusterDropdownMenu.contains(e.target) && (!mobileActiveRealmBtn || !mobileActiveRealmBtn.contains(e.target))) {
        mobileClusterDropdownMenu.style.display = "none";
        if (mobileActiveRealmBtn) {
          mobileActiveRealmBtn.classList.remove("open");
          mobileActiveRealmBtn.setAttribute("aria-expanded", "false");
        }
      }
    });
  }

  function updateClusterDropdownMenu(sectors) {
    if (!sectors) return;
    let html = `
      <div class="cluster-dropdown-item ${!activeSectorId ? 'active' : ''}" data-sector="all">
        <span class="cluster-dot" style="background: #bae6fd;"></span>
        <span class="cluster-name">All Clusters</span>
      </div>
    `;
    sectors.forEach((sec) => {
      html += `
        <div class="cluster-dropdown-item ${activeSectorId === sec.id ? 'active' : ''}" data-sector="${sec.id}" title="${sec.subtitle || sec.name}">
          <span class="cluster-dot" style="background: ${sec.color || '#0ea5e9'};"></span>
          <span class="cluster-code">${sec.code || ''}</span>
          <span class="cluster-name">${getShortClusterLabel(sec) || sec.name}</span>
        </div>
      `;
    });
    if (clusterDropdownMenu) clusterDropdownMenu.innerHTML = html;
    if (mobileClusterDropdownMenu) mobileClusterDropdownMenu.innerHTML = html;
  }

  function renderSearchResults(query) {
    if (!searchResultsEl) return;
    if (!query) {
      searchResultsEl.style.display = "none";
      searchResultsEl.innerHTML = "";
      return;
    }

    const q = query.toLowerCase();
    const matches = (galaxyData.stars || [])
      .filter((s) => (s.title && s.title.toLowerCase().includes(q)) || (s.director && s.director.toLowerCase().includes(q)))
      .slice(0, 8);

    if (matches.length === 0) {
      searchResultsEl.innerHTML = `<div class="search-result-empty"><i class="fa-solid fa-circle-question"></i> No matches found.</div>`;
      searchResultsEl.style.display = "block";
      return;
    }

    searchResultsEl.innerHTML = matches
      .map(
        (s) => `
        <div class="search-result-item" onclick="window.CosmosEngine && window.CosmosEngine.focusStarById('${s.id}')">
          <img src="${s.poster || 'https://placehold.co/40x60/0f172a/7eb5c4?text=Poster'}" alt="${s.title}" class="search-res-poster" onerror="this.src='https://placehold.co/40x60/0f172a/7eb5c4?text=Poster';"/>
          <div class="search-res-info">
            <div class="search-res-title">${s.title} <span class="search-res-year">(${s.year || '—'})</span></div>
            <div class="search-res-meta">
              <span class="search-res-director">${s.director || '—'}</span>
              ${s.is_watched 
                ? getSentimentBadgeHtml(s.rating, true, true) 
                : (s.match_score || s.match_pct ? `<span class="search-res-status match">${s.match_score || s.match_pct} Match Score</span>` : '')
              }
            </div>
          </div>
        </div>
      `
      )
      .join("");

    searchResultsEl.style.display = "block";
  }

  function renderMobileSearchResults(query) {
    if (!mobileSearchResults) return;
    if (!query) {
      mobileSearchResults.style.display = "none";
      mobileSearchResults.innerHTML = "";
      return;
    }

    const q = query.toLowerCase();
    const matches = (galaxyData.stars || [])
      .filter((s) => (s.title && s.title.toLowerCase().includes(q)) || (s.director && s.director.toLowerCase().includes(q)))
      .slice(0, 6);

    if (matches.length === 0) {
      mobileSearchResults.innerHTML = `<div style="padding: 10px; font-size: 0.85rem; color: var(--atlas-text-muted);">No matches found.</div>`;
      mobileSearchResults.style.display = "block";
      return;
    }

    mobileSearchResults.innerHTML = matches.map((s) => `
      <div class="search-result-item" onclick="window.CosmosEngine && window.CosmosEngine.focusStarById('${s.id}'); if (document.getElementById('mobile-map-search-overlay')) document.getElementById('mobile-map-search-overlay').style.display='none';">
        <img src="${s.poster || 'https://placehold.co/36x54/0f172a/7eb5c4?text=Poster'}" alt="${s.title}" style="width: 32px; height: 48px; object-fit: cover; border-radius: 4px;" onerror="this.src='https://placehold.co/36x54/0f172a/7eb5c4?text=Poster';"/>
        <div style="flex: 1; min-width: 0;">
          <div style="font-weight: 700; font-size: 0.90rem; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${s.title}</div>
          <div style="font-size: 0.76rem; color: var(--atlas-text-muted); display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
            <span>${s.director || '—'} • ${s.year || '—'}</span>
            ${s.is_watched ? getSentimentBadgeHtml(s.rating, true, true) : (s.match_score || s.match_pct ? `<span style="color: var(--atlas-gold); font-weight: 700;">• ${s.match_score || s.match_pct} Match</span>` : '')}
          </div>
        </div>
      </div>
    `).join("");
    mobileSearchResults.style.display = "block";
  }

  function focusStarById(starId) {
    if (!galaxyData.stars) return;
    const star = galaxyData.stars.find((s) => s.id === starId);
    if (!star) return;

    if (searchResultsEl) searchResultsEl.style.display = "none";
    if (searchInput) searchInput.value = "";
    if (mobileSearchOverlay) mobileSearchOverlay.style.display = "none";
    if (mobileSearchInput) mobileSearchInput.value = "";
    filters.searchQuery = "";
    applyFilters();

    searchTargetStar = star;
    searchCrosshairTime = performance.now();

    selectStarById(starId);
  }

  // ---------------------------------------------------------------------------
  // Dynamic Semantic Zoom: Super-Dense Clumps Detection & Progressive Unfolding
  // ---------------------------------------------------------------------------
  function updateSuperDenseClumps() {
    superDenseClumps = [];
    starToClumpMap.clear();

    if (!filteredStars || filteredStars.length === 0) return;

    const visited = new Set();
    const denseDist = 25.0; // Latent world units threshold for co-located dense points

    for (let i = 0; i < filteredStars.length; i++) {
      const seedStar = filteredStars[i];
      if (visited.has(seedStar.id)) continue;

      const clumpStars = [seedStar];
      visited.add(seedStar.id);

      const queue = [seedStar];
      while (queue.length > 0) {
        const curr = queue.shift();
        for (let j = 0; j < filteredStars.length; j++) {
          const cand = filteredStars[j];
          if (visited.has(cand.id)) continue;

          // Group co-located stars within same sector or immediate latent proximity
          if (cand.sector_id && curr.sector_id && cand.sector_id !== curr.sector_id) continue;

          const dx = curr.x - cand.x;
          const dy = curr.y - cand.y;
          if (Math.abs(dx) > denseDist || Math.abs(dy) > denseDist) continue;
          const wDist = Math.hypot(dx, dy);

          if (wDist <= denseDist) {
            visited.add(cand.id);
            clumpStars.push(cand);
            queue.push(cand);
          }
        }
      }

      if (clumpStars.length >= 2) {
        let sumX = 0, sumY = 0;
        let hasWatched = false;
        const starIds = new Set();

        for (const s of clumpStars) {
          sumX += s.x;
          sumY += s.y;
          if (s.is_watched) hasWatched = true;
          starIds.add(s.id);
        }

        const cx = sumX / clumpStars.length;
        const cy = sumY / clumpStars.length;

        let clumpColor = "#0ea5e9";
        if (galaxyData.sectors) {
          const sec = galaxyData.sectors.find((sc) => sc.id === clumpStars[0].sector_id);
          if (sec && sec.color) clumpColor = sec.color;
        }
        if (clumpColor === "#0ea5e9" && (clumpStars[0].cluster_color || clumpStars[0].sector_color)) {
          clumpColor = clumpStars[0].cluster_color || clumpStars[0].sector_color;
        }

        const clumpObj = {
          id: `dense_clump_${superDenseClumps.length}`,
          stars: clumpStars,
          starIds,
          cx,
          cy,
          color: clumpColor,
          count: clumpStars.length,
          hasWatched,
          _badgeScreen: null
        };

        superDenseClumps.push(clumpObj);
        for (const s of clumpStars) {
          starToClumpMap.set(s.id, clumpObj);
        }
      }
    }
  }

  function getSemanticZoomSplitProgress(clump) {
    if (!clump) return 1.0;
    // If active spiderfy is active for this clump, consider it 100% split open
    if (activeSpiderfy && clump.stars.some((s) => activeSpiderfy.items.some((it) => it.star.id === s.id))) {
      return 1.0;
    }

    const zMin = 0.88;
    const zMax = 1.32;
    const z = camera.zoom;

    if (z <= zMin) return 0.0;
    if (z >= zMax) return 1.0;

    const t = (z - zMin) / (zMax - zMin);
    // Smooth cubic Hermite ease: 3t^2 - 2t^3
    return t * t * (3 - 2 * t);
  }

  // ---------------------------------------------------------------------------
  // Interactive Spiderfying / Radial Fan-Out for Co-Located Vector Clumps
  // ---------------------------------------------------------------------------
  function findStarClump(seedStar, screenX, screenY) {
    if (!seedStar || !filteredStars || filteredStars.length === 0) return [];
    const seedSp = worldToScreen(seedStar.x, seedStar.y);

    const clump = [seedStar];
    for (let i = 0; i < filteredStars.length; i++) {
      const star = filteredStars[i];
      if (star.id === seedStar.id) continue;
      const wDist = Math.hypot(star.x - seedStar.x, star.y - seedStar.y);
      const sp = worldToScreen(star.x, star.y);
      const sDist = Math.hypot(sp.x - seedSp.x, sp.y - seedSp.y);

      if ((wDist <= 16 && sDist <= 32) || sDist <= 22) {
        clump.push(star);
      }
    }

    // Transitive clustering (group contiguous overlapping neighbors, up to 20 max)
    let expanded = true;
    while (expanded && clump.length < 20) {
      expanded = false;
      for (let i = 0; i < filteredStars.length; i++) {
        const star = filteredStars[i];
        if (clump.some((c) => c.id === star.id)) continue;
        const sp = worldToScreen(star.x, star.y);
        const isClose = clump.some((c) => {
          const cSp = worldToScreen(c.x, c.y);
          const wD = Math.hypot(star.x - c.x, star.y - c.y);
          const sD = Math.hypot(sp.x - cSp.x, sp.y - cSp.y);
          return (wD <= 16 && sD <= 32) || sD <= 22;
        });
        if (isClose) {
          clump.push(star);
          expanded = true;
        }
      }
    }

    return clump;
  }

  function spiderfyClump(clump) {
    if (!clump || clump.length < 2) return;

    // Centroid of the clump in world space
    let sumX = 0, sumY = 0;
    for (const star of clump) {
      sumX += star.x;
      sumY += star.y;
    }
    const cx = sumX / clump.length;
    const cy = sumY / clump.length;

    const N = clump.length;
    const items = [];

    if (N <= 8) {
      // 1. Clean Equidistant Radial Ring
      const ringRadius = Math.max(44, 32 + N * 4.5);
      const startAngle = -Math.PI / 2; // start at top (12 o'clock)
      for (let i = 0; i < N; i++) {
        const angle = startAngle + (i * 2 * Math.PI) / N;
        items.push({
          star: clump[i],
          screenDx: ringRadius * Math.cos(angle),
          screenDy: ringRadius * Math.sin(angle),
          angle
        });
      }
    } else {
      // 2. Sunflower Spiral (Phyllotaxis / Fermat Spiral)
      const goldenAngle = 2.399963229728653; // ~137.5 degrees
      for (let i = 0; i < N; i++) {
        const r = 34 + 14 * Math.sqrt(i);
        const angle = i * goldenAngle - Math.PI / 2;
        items.push({
          star: clump[i],
          screenDx: r * Math.cos(angle),
          screenDy: r * Math.sin(angle),
          angle
        });
      }
    }

    activeSpiderfy = {
      centroid: { x: cx, y: cy },
      items,
      startTime: performance.now(),
      duration: 320,
      state: "expanding"
    };
  }

  function collapseSpiderfy(instant = false) {
    if (!activeSpiderfy) return;
    if (instant) {
      activeSpiderfy = null;
      return;
    }
    if (activeSpiderfy.state !== "collapsing") {
      activeSpiderfy.state = "collapsing";
      activeSpiderfy.collapseStartTime = performance.now();
    }
  }

  function getSpiderfyProgress() {
    if (!activeSpiderfy) return 0;
    const now = performance.now();
    if (activeSpiderfy.state === "expanding") {
      const elapsed = now - activeSpiderfy.startTime;
      const t = Math.min(1.0, elapsed / activeSpiderfy.duration);
      const p = 1.0 - Math.pow(1.0 - t, 3);
      if (t >= 1.0) {
        activeSpiderfy.state = "open";
        return 1.0;
      }
      return p;
    } else if (activeSpiderfy.state === "open") {
      return 1.0;
    } else if (activeSpiderfy.state === "collapsing") {
      const elapsed = now - activeSpiderfy.collapseStartTime;
      const t = Math.min(1.0, elapsed / 220);
      const p = Math.max(0, 1.0 - Math.pow(t, 2));
      if (t >= 1.0) {
        activeSpiderfy = null;
        return 0;
      }
      return p;
    }
    return 0;
  }

  function getStarScreenPos(star) {
    const sp = worldToScreen(star.x, star.y);
    if (activeSpiderfy) {
      const item = activeSpiderfy.items.find((it) => it.star.id === star.id);
      if (item) {
        const p = getSpiderfyProgress();
        const spCentroid = worldToScreen(activeSpiderfy.centroid.x, activeSpiderfy.centroid.y);
        const targetX = spCentroid.x + item.screenDx;
        const targetY = spCentroid.y + item.screenDy;
        sp.x = sp.x * (1 - p) + targetX * p;
        sp.y = sp.y * (1 - p) + targetY * p;
        return sp;
      }
    }

    // Dynamic Semantic Zoom: Smoothly interpolate from centroid to actual location as user zooms in
    const clump = starToClumpMap.get(star.id);
    if (clump) {
      const splitProgress = getSemanticZoomSplitProgress(clump);
      if (splitProgress < 1.0) {
        const spCentroid = worldToScreen(clump.cx, clump.cy);
        sp.x = spCentroid.x * (1 - splitProgress) + sp.x * splitProgress;
        sp.y = spCentroid.y * (1 - splitProgress) + sp.y * splitProgress;
      }
    }

    return sp;
  }

  function getActiveNeighborSet(activeStar = (selectedStar || hoveredStar)) {
    const neighborSet = new Set();
    if (!activeStar) return neighborSet;
    neighborSet.add(activeStar.id);
    for (const link of (filteredLinks || [])) {
      if (link.source === activeStar.id) neighborSet.add(link.target);
      else if (link.target === activeStar.id) neighborSet.add(link.source);
    }
    if (selectedStar && activeStar.id === selectedStar.id && selectedResonantNeighbors) {
      for (const res of selectedResonantNeighbors) {
        neighborSet.add(res.star.id);
      }
    }
    return neighborSet;
  }

  function renderSpiderfySpokes(timestamp) {
    if (!activeSpiderfy) return;
    const p = getSpiderfyProgress();
    if (p <= 0.01) return;

    const spCentroid = worldToScreen(activeSpiderfy.centroid.x, activeSpiderfy.centroid.y);
    const activeStar = selectedStar || hoveredStar;
    const neighborSet = activeStar ? getActiveNeighborSet(activeStar) : null;

    ctx.save();

    // 1. Centroid Origin Hub Anchor (luminous origin marker)
    const hubAlpha = selectedStar ? 0.35 : 0.85;
    ctx.save();
    ctx.fillStyle = `rgba(56, 189, 248, ${hubAlpha * p})`;
    ctx.shadowColor = "#38bdf8";
    ctx.shadowBlur = selectedStar ? 4 : 8;
    ctx.beginPath();
    ctx.arc(spCentroid.x, spCentroid.y, 3.0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.strokeStyle = `rgba(56, 189, 248, ${(selectedStar ? 0.18 : 0.40) * p})`;
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    ctx.arc(spCentroid.x, spCentroid.y, 6.0, 0, Math.PI * 2);
    ctx.stroke();

    // 2. Faint, elegant spokes connecting each fanned-out node back to centroid
    for (const item of activeSpiderfy.items) {
      const starPos = getStarScreenPos(item.star);
      const isDirect = activeStar && activeStar.id === item.star.id;
      const isNeighbor = neighborSet && !isDirect && neighborSet.has(item.star.id);
      const isRelevant = !selectedStar || isDirect || isNeighbor;

      const alpha1 = (isRelevant ? (selectedStar ? 0.70 : 0.60) : 0.12) * p;
      const alpha2 = (isRelevant ? (selectedStar ? 0.35 : 0.28) : 0.06) * p;

      ctx.save();
      const spokeGrad = ctx.createLinearGradient(spCentroid.x, spCentroid.y, starPos.x, starPos.y);
      spokeGrad.addColorStop(0, `rgba(56, 189, 248, ${alpha1})`);
      spokeGrad.addColorStop(1, `rgba(186, 230, 253, ${alpha2})`);

      ctx.strokeStyle = spokeGrad;
      ctx.lineWidth = isRelevant ? (isDirect ? 1.4 : 1.1) : 0.8;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(spCentroid.x, spCentroid.y);
      ctx.lineTo(starPos.x, starPos.y);
      ctx.stroke();
      ctx.restore();
    }

    ctx.restore();
  }

  function getClumpBadgeAt(screenX, screenY) {
    if (!superDenseClumps || superDenseClumps.length === 0) return null;
    for (let i = 0; i < superDenseClumps.length; i++) {
      const clump = superDenseClumps[i];
      const b = clump._badgeScreen;
      if (b && b.alpha > 0.12) {
        const d = Math.hypot(screenX - b.x, screenY - b.y);
        if (d <= b.r + 7) {
          return clump;
        }
      }
    }
    return null;
  }

  function getStarAt(screenX, screenY) {
    if (!filteredStars || filteredStars.length === 0) return null;

    // 0. Check placed label callout boxes
    if (activeFrameLabelBoxes && activeFrameLabelBoxes.length > 0) {
      for (let i = 0; i < activeFrameLabelBoxes.length; i++) {
        const box = activeFrameLabelBoxes[i];
        if (screenX >= box.x && screenX <= box.x + box.w && screenY >= box.y && screenY <= box.y + box.h) {
          if (box.star) return box.star;
        }
      }
    }

    // 1. If spiderfy is active, prioritize checking fanned-out stars first!
    if (activeSpiderfy) {
      const p = getSpiderfyProgress();
      if (p > 0.05) {
        for (const item of activeSpiderfy.items) {
          const sp = getStarScreenPos(item.star);
          const dist = Math.hypot(sp.x - screenX, sp.y - screenY);
          if (dist <= 26) {
            return item.star;
          }
        }
      }
    }

    let closest = null;
    let minScreenDistSq = 1296; // 36px * 36px expanded touch hit radius for effortless mobile selection

    for (let i = 0; i < filteredStars.length; i++) {
      const star = filteredStars[i];
      // If star belongs to a super-dense clump that is currently collapsed at overview,
      // and not currently selected, let the clump badge handle the interaction
      const clump = starToClumpMap.get(star.id);
      if (clump && (!selectedStar || selectedStar.id !== star.id)) {
        const splitP = getSemanticZoomSplitProgress(clump);
        if (splitP <= 0.08) continue;
      }

      const sp = getStarScreenPos(star);
      const dx = sp.x - screenX;
      if (Math.abs(dx) > 36) continue;
      const dy = sp.y - screenY;
      if (Math.abs(dy) > 36) continue;
      const distSq = dx * dx + dy * dy;
      if (distSq < minScreenDistSq) {
        minScreenDistSq = distSq;
        closest = star;
      }
    }
    return closest;
  }

  function getSectorAt(screenX, screenY) {
    if (!galaxyData.sectors) return null;
    const worldPos = screenToWorld(screenX, screenY);
    for (let i = 0; i < galaxyData.sectors.length; i++) {
      const sec = galaxyData.sectors[i];
      const cx = typeof sec.cx === "number" ? sec.cx : 0;
      const cy = typeof sec.cy === "number" ? sec.cy : 0;
      const hitRadius = (sec.radius || 180) * 1.15;
      const dx = worldPos.x - cx;
      if (Math.abs(dx) > hitRadius) continue;
      const dy = worldPos.y - cy;
      if (Math.abs(dy) > hitRadius) continue;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        return sec;
      }
    }
    return null;
  }

  function handleCanvasClick(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;

    if (sx < 0 || sx > width || sy < 0 || sy > height) return;

    // Dismiss any mobile overlays/sheets if open
    if (mobileSearchOverlay && mobileSearchOverlay.style.display !== "none") {
      mobileSearchOverlay.style.display = "none";
    }
    if (mobileFilterSheet && mobileFilterSheet.style.display !== "none") {
      mobileFilterSheet.style.display = "none";
    }

    if (currentMode === "probe") {
      const worldPos = screenToWorld(sx, sy);
      dropProbe(worldPos.x, worldPos.y);
      return;
    }

    // 1. Check if clicking the canvas floating "← Return to Overview" button
    if (galaxyData._overviewBtn) {
      const b = galaxyData._overviewBtn;
      if (sx >= b.x && sx <= b.x + b.w && sy >= b.y && sy <= b.y + b.h) {
        resetToOverview();
        return;
      }
    }

    // 2. Check if clicking any Sector Header Badge directly
    if (galaxyData.sectors) {
      for (const sec of galaxyData.sectors) {
        const b = sec._badgeScreen;
        if (b && (b.alpha === undefined || b.alpha > 0.08)) {
          if (sx >= b.x - 8 && sx <= b.x + b.w + 8 && sy >= b.y - 8 && sy <= b.y + b.h + 8) {
            if (activeSectorId === sec.id) {
              resetToOverview();
            } else {
              selectSector(sec.id);
            }
            return;
          }
        }
      }
    }

    // 2.5 Check if clicking any Super-Dense Clump Micro-Badge (+3, +4, etc.)
    const clickedClump = getClumpBadgeAt(sx, sy);
    if (clickedClump) {
      if (activeSpiderfy) {
        collapseSpiderfy(true);
      }
      if (camera.zoom < 1.25) {
        flyToCoordinates(clickedClump.cx, clickedClump.cy, 1.45);
      } else {
        spiderfyClump(clickedClump.stars);
      }
      return;
    }

    // 3. Check if clicking a star node or clump
    const clickedStar = getStarAt(sx, sy);
    if (clickedStar) {
      // If clicking one of the fanned-out stars in an active spiderfy:
      if (activeSpiderfy && activeSpiderfy.items.some((it) => it.star.id === clickedStar.id)) {
        handleStarClick(clickedStar);
        return;
      }

      // Check if clicked star is part of an overlapping clump of >= 2 stars
      const clump = findStarClump(clickedStar, sx, sy);
      if (clump.length >= 2) {
        if (activeSpiderfy) {
          collapseSpiderfy(true);
        }
        if (selectedStar && !clump.some((s) => s.id === selectedStar.id)) {
          unpinHUD();
        }
        spiderfyClump(clump);
        return;
      }

      // Single star: collapse existing spiderfy if any and select star
      if (activeSpiderfy) {
        collapseSpiderfy();
      }
      handleStarClick(clickedStar);
      return;
    }

    // 4. If in overview mode, check if clicking a sector territory
    if (!activeSectorId) {
      const clickedSec = getSectorAt(sx, sy);
      if (clickedSec) {
        if (activeSpiderfy) collapseSpiderfy();
        selectSector(clickedSec.id);
        return;
      }
    }

    // 5. Clicked empty space: collapse spiderfy and unpin HUD
    if (activeSpiderfy) {
      collapseSpiderfy();
    }
    if (probeDrawer && probeDrawer.classList.contains("open")) {
      closeProbe();
      return;
    }
    if (selectedStar) {
      unpinHUD();
    } else if (activeSectorId) {
      resetToOverview();
    }
  }

  function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll(".cosmos-mode-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === mode);
    });
    if (mobileSamplerBtn) {
      mobileSamplerBtn.classList.toggle("active", mode === "probe");
    }

    if (mode === "probe") {
      selectedStar = null;
      unpinHUD();
      if (probeDrawer) {
        probeDrawer.classList.add("open");
        if (probeList && !probeActive) {
          probeList.innerHTML = `<div class="tray-empty"><i class="fa-solid fa-satellite-dish" style="margin-right: 6px; color: var(--atlas-cyan);"></i> Click any coordinate on the manifold to sample the 6 nearest films.</div>`;
        }
      }
      if (modeBanner && bannerText) {
        bannerText.textContent = "SAMPLER ACTIVE: TAP CANVAS TO PROBE";
        modeBanner.style.display = "flex";
      }
      canvas.style.cursor = "crosshair";
    } else {
      closeProbe();
      canvas.style.cursor = "grab";
    }
  }

  function computeLocalResonantNeighbors(star, maxCount = 3) {
    if (!star || !filteredStars || filteredStars.length === 0) return [];
    const results = [];
    const starCraft = star.craft || {};
    const sDir = (star.director || starCraft.director || "").trim().toLowerCase();
    const sDop = (starCraft.cinematographer || "").trim().toLowerCase();
    const sComp = (starCraft.composer || "").trim().toLowerCase();

    for (const cand of filteredStars) {
      if (cand.id === star.id) continue;

      const sameSector = cand.sector_id && star.sector_id && cand.sector_id === star.sector_id;
      const dist = Math.hypot(cand.x - star.x, cand.y - star.y);
      if (dist > 380 && !sameSector) continue;

      // 1. Proximity score in constellation space
      const proxScore = Math.max(0, 1.0 - dist / 320.0);

      // 2. Craft / Auteur overlap score
      const cCraft = cand.craft || {};
      let craftPoints = 0;
      const sharedRoles = [];
      const cDir = (cand.director || cCraft.director || "").trim().toLowerCase();
      if (sDir && cDir && sDir !== "unknown" && sDir === cDir) {
        craftPoints += 0.55;
        sharedRoles.push("Director");
      }
      const cDop = (cCraft.cinematographer || "").trim().toLowerCase();
      if (sDop && cDop && sDop !== "unknown" && sDop === cDop) {
        craftPoints += 0.35;
        sharedRoles.push("Cinematographer");
      }
      const cComp = (cCraft.composer || "").trim().toLowerCase();
      if (sComp && cComp && sComp !== "unknown" && sComp === cComp) {
        craftPoints += 0.25;
        sharedRoles.push("Composer");
      }
      const craftScore = Math.min(1.0, craftPoints);
      const sharedReason = sharedRoles.length > 0 ? `Shared ${sharedRoles.join(" & ")}` : "Thematic & Visual Affinity";

      // 3. User affinity score
      const affScore = cand.affinity_score !== undefined ? cand.affinity_score : ((cand.match_score || cand.match_pct || 75) / 100.0);

      // Local resonance blend: 40% User Affinity + 35% Spatial Proximity + 25% Craft Overlap
      const resonance = Math.round((0.40 * affScore + 0.35 * proxScore + 0.25 * craftScore) * 100);

      results.push({
        star: cand,
        resonance: Math.min(99, Math.max(50, resonance)),
        craftReason: sharedReason,
        dist: dist
      });
    }

    results.sort((a, b) => b.resonance - a.resonance || a.dist - b.dist);
    return results.slice(0, maxCount);
  }

  function handleStarClick(star) {
    // Explore mode: Lock / Pin the star details HUD, compute local resonance, and center camera
    selectedStar = star;
    star._selectAnimStart = performance.now();
    selectedResonantNeighbors = computeLocalResonantNeighbors(star, 3);
    hoveredStar = null;
    showHUD(star, true);
    flyToCoordinates(star.x, star.y, Math.max(camera.zoom, 1.45));
    scrollFeedToCard(star.id);
  }

  function checkHover(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;

    currentMousePos.x = sx;
    currentMousePos.y = sy;
    const wp = screenToWorld(sx, sy);
    currentMousePos.wx = wp.x;
    currentMousePos.wy = wp.y;

    if (currentMode === "probe") {
      canvas.style.cursor = "crosshair";
      return;
    }

    if (sx < 0 || sx > width || sy < 0 || sy > height) {
      hoveredEdge = null;
      if (!selectedStar) {
        hideHUD();
        hoveredStar = null;
        hoveredSector = null;
      }
      return;
    }

    // -------------------------------------------------------------------------
    // Edge & Related Node Interaction (Hover over connection lines or related nodes)
    // -------------------------------------------------------------------------
    const activeStar = selectedStar || hoveredStar;
    let foundEdge = null;

    if (activeStar) {
      const star = getStarAt(sx, sy);

      // 1. Hovering a related node connected to activeStar
      if (star && star.id !== activeStar.id) {
        const matchingLinks = (filteredLinks || []).filter(l => 
          (l.source === activeStar.id && l.target === star.id) ||
          (l.target === activeStar.id && l.source === star.id)
        );

        if (matchingLinks.length > 0) {
          const texts = matchingLinks.map(l => formatEdgeTooltip(l));
          const primaryProps = getLinkVisualProps(matchingLinks[0]);
          foundEdge = {
            link: matchingLinks[0],
            text: texts.join(" • "),
            color: primaryProps.color,
            x: sx,
            y: sy
          };
        } else if (selectedStar && activeStar.id === selectedStar.id && selectedResonantNeighbors) {
          const res = selectedResonantNeighbors.find(r => r.star.id === star.id);
          if (res) {
            foundEdge = {
              res,
              starId: star.id,
              text: `${res.resonance}% Resonance (Thematic Affinity)`,
              color: "#cbd5e1",
              x: sx,
              y: sy
            };
          }
        }
      }

      // 2. Hovering an individual connection line
      if (!foundEdge) {
        const starMap = new Map((filteredStars || []).map((s) => [s.id, s]));
        const connectedLinks = (filteredLinks || []).filter(l =>
          l.source === activeStar.id || l.target === activeStar.id
        );

        for (const link of connectedLinks) {
          const s1 = starMap.get(link.source);
          const s2 = starMap.get(link.target);
          if (!s1 || !s2) continue;
          const p1 = worldToScreen(s1.x, s1.y);
          const p2 = worldToScreen(s2.x, s2.y);
          const mid = {
            x: (p1.x + p2.x) / 2 + (p1.y - p2.y) * 0.08,
            y: (p1.y + p2.y) / 2 + (p2.x - p1.x) * 0.08
          };
          const dist = getDistToQuadraticCurve(sx, sy, p1, mid, p2);
          if (dist < 10) {
            const props = getLinkVisualProps(link);
            foundEdge = {
              link,
              text: formatEdgeTooltip(link),
              color: props.color,
              x: sx,
              y: sy
            };
            break;
          }
        }

        if (!foundEdge && selectedStar && activeStar.id === selectedStar.id && selectedResonantNeighbors && selectedResonantNeighbors.length > 0) {
          const p1 = worldToScreen(selectedStar.x, selectedStar.y);
          for (const res of selectedResonantNeighbors) {
            const p2 = worldToScreen(res.star.x, res.star.y);
            const dist = getDistToSegment(sx, sy, p1, p2);
            if (dist < 9) {
              foundEdge = {
                res,
                starId: res.star.id,
                text: `${res.resonance}% Resonance (Thematic Affinity)`,
                color: "#cbd5e1",
                x: sx,
                y: sy
              };
              break;
            }
          }
        }
      }
    }

    hoveredEdge = foundEdge;

    // If mouse is inside HUD element, keep HUD as is
    if (hudEl && hudEl.matches(":hover")) {
      return;
    }

    // If a star is locked / selected, keep the selection spotlight fixed until clicked elsewhere!
    if (selectedStar) {
      hoveredStar = null;
      const star = getStarAt(sx, sy);
      const clumpBadge = getClumpBadgeAt(sx, sy);
      hoveredClump = clumpBadge;
      canvas.style.cursor = (star || foundEdge || clumpBadge) ? "pointer" : (camera.isDragging ? "grabbing" : "grab");
      return;
    }

    // 0.5 Check if hovering a Super-Dense Clump Micro-Badge at overview
    const clumpBadge = getClumpBadgeAt(sx, sy);
    if (clumpBadge) {
      hoveredClump = clumpBadge;
      hoveredStar = null;
      hoveredSector = null;
      hideHUD();
      canvas.style.cursor = "pointer";
      return;
    }
    hoveredClump = null;

    // 1. Check if hovering a node across the manifold (unselected exploration)
    const star = getStarAt(sx, sy);
    if (star) {
      if (hoveredStar !== star) {
        hoveredStar = star;
        hoveredSector = null;
        showHUD(hoveredStar, false);
      }
      canvas.style.cursor = "pointer";
      return;
    }

    // 2. If not hovering a star, check if hovering a Realm Hub (in overview mode)
    hideHUD();
    hoveredStar = null;

    if (!activeSectorId) {
      const sec = getSectorAt(sx, sy);
      if (sec !== hoveredSector) {
        hoveredSector = sec;
      }
      canvas.style.cursor = hoveredSector ? "pointer" : (camera.isDragging ? "grabbing" : "grab");
    } else {
      hoveredSector = null;
      canvas.style.cursor = currentMode === "probe" ? "crosshair" : (camera.isDragging ? "grabbing" : "grab");
    }
  }

  function showHUD(star, isPinned = false) {
    if (hudBackdrop) {
      if (star.poster && star.poster.startsWith("http")) {
        hudBackdrop.style.backgroundImage = `url("${star.poster}")`;
        hudBackdrop.style.opacity = "0.22";
      } else {
        hudBackdrop.style.backgroundImage = "none";
        hudBackdrop.style.opacity = "0";
      }
    }

    if (hudPoster) {
      const fallbackSvg = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='150' fill='%23080e18'><rect width='100' height='150' fill='%23080e18'/><path d='M35 55 h30 v40 h-30 z' fill='none' stroke='%2338bdf8' stroke-width='2' stroke-linejoin='round'/><circle cx='50' cy='75' r='8' fill='none' stroke='%2338bdf8' stroke-width='1.5'/><text x='50%' y='83%' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='8' font-weight='bold' letter-spacing='1'>KINETO</text></svg>";
      hudPoster.onerror = () => { hudPoster.src = fallbackSvg; };
      hudPoster.src = (star.poster && star.poster.startsWith("http")) ? star.poster : fallbackSvg;
    }
    if (hudTitle) hudTitle.textContent = star.title;

    // Streamlined header line: 1997 • 2h 14m • Dir. Hayao Miyazaki (13px muted gray)
    if (hudMeta) {
      let rtStr = "";
      if (star.formatted_runtime) {
        rtStr = star.formatted_runtime;
      } else if (star.runtime) {
        const num = parseInt(star.runtime, 10);
        if (!isNaN(num) && num > 0) {
          const h = Math.floor(num / 60);
          const m = num % 60;
          rtStr = h > 0 && m > 0 ? `${h}h ${m}m` : (h > 0 ? `${h}h` : `${m}m`);
        }
      let creditStr = "";
      const sCreator = (star.creator || "").trim();
      const sDirector = (star.director || "").trim();
      if (star.tv_show) {
        if (sCreator && sDirector && sCreator.toLowerCase() !== sDirector.toLowerCase()) {
          creditStr = `Created by ${sCreator} • Dir. ${sDirector}`;
        } else if (sCreator) {
          creditStr = `Created by ${sCreator}`;
        } else if (sDirector) {
          creditStr = `Dir. ${sDirector}`;
        }
      } else {
        creditStr = sDirector ? `Dir. ${sDirector}` : "";
      }
      const metaParts = [star.year, rtStr, creditStr].filter(Boolean);
      hudMeta.textContent = metaParts.length > 0 ? metaParts.join(" • ") : "—";
    }

    // Simplified readable score pill: ★ 57% Match (no raw db formulas)
    if (hudMatch) {
      if (star.is_watched) {
        hudMatch.textContent = "";
        hudMatch.style.display = "none";
      } else {
        const scoreVal = star.match_score || star.match_pct || 90;
        hudMatch.innerHTML = `<i class="fa-solid fa-star"></i> <span>${scoreVal}% Match</span>`;
        hudMatch.title = star.calibrated_prob !== undefined ? `Calibrated probability: ${(star.calibrated_prob * 100).toFixed(1)}%` : "Match Score";
        hudMatch.style.display = "inline-flex";
      }
    }

    // Drop redundant RECOMMENDATION badge when score pill is present
    if (hudCategory) {
      if (star.is_watched) {
        hudCategory.innerHTML = getSentimentBadgeHtml(star.rating, true, true);
        hudCategory.className = "hud-tag-sentiment-wrap";
        hudCategory.style.display = "inline-flex";
      } else if (star.is_watchlist) {
        hudCategory.textContent = "WATCHLIST";
        hudCategory.className = "hud-tag hud-tag-watchlist";
        hudCategory.style.display = "inline-flex";
      } else {
        hudCategory.textContent = "";
        hudCategory.style.display = "none";
      }
    }

    if (hudExploratoryTag) {
      if (!star.is_watched && star.is_exploratory) {
        hudExploratoryTag.style.display = "inline-block";
      } else {
        hudExploratoryTag.style.display = "none";
      }
    }

    if (hudLowEvidenceTag) {
      if (!star.is_watched && star.low_evidence) {
        hudLowEvidenceTag.style.display = "inline-block";
      } else {
        hudLowEvidenceTag.style.display = "none";
      }
    }

    if (hudFrontierBadge) {
      hudFrontierBadge.style.display = "none";
      hudFrontierBadge.textContent = "";
    }

    // Consolidate genre pills: deduplicate cluster genre & format subtle bullets
    if (hudGenres) {
      const realmCodeOrShort = star.sector_code || (star.sector_name && star.sector_name.length > 20 ? star.sector_name.substring(0, 18) + '…' : star.sector_name);
      const realmTag = realmCodeOrShort ? `<span class="hud-genre-tag hud-realm-tag" style="border-color: ${star.sector_color || '#0ea5e9'}; color: ${star.sector_color || '#38bdf8'}; font-weight: 700;">⬡ ${realmCodeOrShort}</span>` : "";

      const sectorLower = (star.sector_name || "").toLowerCase();
      const allGenres = (star.genre || "")
        .split(",")
        .map((g) => g.trim())
        .filter(Boolean);

      const filteredGenres = allGenres.filter((g) => !sectorLower.includes(g.toLowerCase())).slice(0, 3);
      const displayGenres = filteredGenres.length > 0 ? filteredGenres : allGenres.slice(0, 2);

      const bulletsHtml = displayGenres.length > 0
        ? `<span class="hud-genre-bullets">${displayGenres.join(" • ")}</span>`
        : "";

      hudGenres.innerHTML = realmTag + (bulletsHtml ? ` ${bulletsHtml}` : "");
    }

    // Recommendation rationale removed for now
    if (hudReason) {
      hudReason.innerHTML = "";
      hudReason.style.display = "none";
    }

    // Craft Credits in clean 3-item horizontal row (DoP, Score, Writer)
    const craft = star.craft || {};
    let hasCraft = false;

    if (hudCraftDop && hudCraftDopRow) {
      if (craft.cinematographer) {
        hudCraftDop.textContent = craft.cinematographer;
        hudCraftDopRow.style.display = "flex";
        hasCraft = true;
      } else {
        hudCraftDopRow.style.display = "none";
      }
    }

    if (hudCraftComposer && hudCraftComposerRow) {
      if (craft.composer) {
        hudCraftComposer.textContent = craft.composer;
        hudCraftComposerRow.style.display = "flex";
        hasCraft = true;
      } else {
        hudCraftComposerRow.style.display = "none";
      }
    }

    if (hudCraftWriter && hudCraftWriterRow) {
      if (craft.screenwriter) {
        hudCraftWriter.textContent = craft.screenwriter;
        hudCraftWriterRow.style.display = "flex";
        hasCraft = true;
      } else {
        hudCraftWriterRow.style.display = "none";
      }
    }

    if (hudCraftMeta) {
      hudCraftMeta.style.display = hasCraft ? "grid" : "none";
    }

    // Drop FILM tag (poster and subtitle imply it), show SERIES only for TV
    const isTv = star.tv_show === 1 || star.tv_show === "1" || star.tv_show === true || star.media_type === "tv";
    if (hudFormatTag) {
      if (isTv) {
        hudFormatTag.textContent = "SERIES";
        hudFormatTag.style.display = "inline-flex";
      } else {
        hudFormatTag.style.display = "none";
      }
    }

    if (hudWatchlistBtn) {
      if (star.is_watched) {
        // Already watched — no point adding to watchlist
        hudWatchlistBtn.style.display = "none";
      } else {
        hudWatchlistBtn.style.display = "";
        hudWatchlistBtn.classList.toggle("in-watchlist", !!star.is_watchlist);
        hudWatchlistBtn.innerHTML = `<i class="fa-solid ${star.is_watchlist ? 'fa-check' : 'fa-plus'}"></i> <span>${star.is_watchlist ? 'Watchlisted' : 'Watchlist'}</span>`;
        hudWatchlistBtn.onclick = (e) => {
          e.stopPropagation();
          toggleWatchlist(e, star.id);
          hudWatchlistBtn.classList.add("in-watchlist");
          hudWatchlistBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Watchlisted</span>`;
        };
      }
    }

    if (hudActionBtn) {
      hudActionBtn.onclick = (e) => {
        e.stopPropagation();
        openMediaDetails(star);
      };
    }

    if (hudPoster) {
      hudPoster.style.cursor = "pointer";
      hudPoster.onclick = (e) => {
        e.stopPropagation();
        openMediaDetails(star);
      };
    }

    if (hudEl) {
      hudEl.classList.remove("sheet-expanded");
      hudEl.style.display = "flex";
      hudEl.classList.toggle("pinned", isPinned);
      hudEl.classList.add("visible");
    }

    const vp = document.getElementById("cosmos-viewport");
    if (vp) vp.classList.add("has-active-hud");
    if (isPinned && probeDrawer) closeProbe();
  }

  function openMediaDetails(star) {
    if (!star) return;
    const media = {
      title: star.title,
      year: star.year,
      director: star.director,
      creator: star.creator,
      poster: star.poster,
      is_tv: star.tv_show === 1
    };
    if (typeof window.openMovieDrawer === "function") {
      window.openMovieDrawer(media);
    } else if (window.MovieDrawer && typeof window.MovieDrawer.open === "function") {
      window.MovieDrawer.open(media);
    } else {
      console.warn("[COSMOS JS] openMovieDrawer is not available on window.");
    }
  }

  function hideHUD() {
    if (!hudEl) return;
    if (selectedStar) return; // Keep pinned HUD fixed!
    hudEl.classList.remove("visible", "pinned");
    const vp = document.getElementById("cosmos-viewport");
    if (vp && (!probeDrawer || !probeDrawer.classList.contains("open"))) {
      vp.classList.remove("has-active-hud");
    }
  }

  function unpinHUD() {
    selectedStar = null;
    selectedResonantNeighbors = [];
    hoveredStar = null;
    hoveredEdge = null;
    collapseSpiderfy();
    const vp = document.getElementById("cosmos-viewport");
    if (vp && (!probeDrawer || !probeDrawer.classList.contains("open"))) {
      vp.classList.remove("has-active-hud");
    }
    if (hudEl) {
      hudEl.classList.remove("visible", "pinned", "sheet-expanded");
      setTimeout(() => {
        if (!selectedStar && !hudEl.classList.contains("visible")) {
          hudEl.style.display = "none";
        }
      }, 350);
    }
  }

  function dropProbe(x, y) {
    if (isNaN(x) || isNaN(y)) return;
    probeActive = { x, y };
    probeAnimTime = performance.now();

    // Dismiss open HUD and overlays
    unpinHUD();
    if (mobileSearchOverlay) mobileSearchOverlay.style.display = "none";
    if (mobileFilterSheet) mobileFilterSheet.style.display = "none";

    const vp = document.getElementById("cosmos-viewport");
    if (vp) vp.classList.add("has-active-hud");

    if (probeDrawer) probeDrawer.classList.add("open");
    if (probeList) {
      probeList.innerHTML = `<div class="tray-empty"><i class="fa-solid fa-satellite-dish fa-spin"></i> Sampling manifold neighborhood...</div>`;
    }

    // Immediate Client-Side Calculation Fallback
    const localStars = galaxyData.stars || [];
    const unwatched = localStars.filter((s) => !s.is_watched);
    const pool = unwatched.length > 0 ? unwatched : localStars;
    const localRanked = [...pool].sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y)).slice(0, 6);

    const csrfToken = getCsrfToken();

    fetch("/api/cosmos/probe", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      },
      body: JSON.stringify({ x, y, limit: 6, csrf_token: csrfToken })
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Status ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (data.success && data.recommendations && data.recommendations.length > 0) {
          renderProbeResults(data.recommendations);
        } else {
          renderProbeResults(localRanked);
        }
      })
      .catch((err) => {
        console.warn("Probe API request fallback to local vector calculation:", err);
        renderProbeResults(localRanked);
      });
  }

  function renderProbeResults(recs) {
    if (!probeList) return;
    probeList.innerHTML = "";

    if (!recs || recs.length === 0) {
      probeList.innerHTML = `<div class="tray-empty">No manifold nodes detected in this coordinate region.</div>`;
      return;
    }

    recs.forEach((star) => {
      const card = createMiniStarCard(star);
      probeList.appendChild(card);
    });
  }

  function createMiniStarCard(star) {
    const card = document.createElement("div");
    card.className = "mini-star-card";
    const posterUrl = star.poster || "https://placehold.co/100x150/0f172a/7eb5c4?text=Cinema";
    card.innerHTML = `
      <img src="${posterUrl}" alt="${star.title}" class="mini-card-poster" loading="lazy" onerror="this.src='https://placehold.co/100x150/0f172a/7eb5c4?text=Cinema';"/>
      <div class="mini-card-body">
        <div class="mini-card-title">${star.title}</div>
        <div class="mini-card-meta">${star.year || '—'} • ${star.director || '—'}</div>
        ${star.is_watched ? `<div class="mini-card-match">${getSentimentBadgeHtml(star.rating, true, true)}</div>` : `<div class="mini-card-match"><i class="fa-solid fa-crosshairs"></i> ${star.match_score || star.match_pct || 90} Match Score</div>`}
      </div>
    `;
    card.addEventListener("click", () => {
      closeProbe();
      focusStarOnMap(star.id);
    });
    return card;
  }

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]') || document.querySelector('input[name="csrf_token"]') || document.getElementById("csrf_token");
    if (meta) {
      return meta.getAttribute("content") || meta.value || "";
    }
    return "";
  }

  // ---------------------------------------------------------------------------
  // Canvas Rendering Pipeline (60 FPS Mathematical Topological Manifold)
  // ---------------------------------------------------------------------------
  function renderLoop(timestamp) {
    try {
      // 1. Smooth Camera Physics Lerp with safety checks
      camera.x += (camera.targetX - camera.x) * 0.12;
      camera.y += (camera.targetY - camera.y) * 0.12;
      camera.zoom += (camera.targetZoom - camera.zoom) * 0.14;

      if (isNaN(camera.x) || isNaN(camera.y) || isNaN(camera.zoom)) {
        camera.x = 0; camera.y = 0; camera.targetX = 0; camera.targetY = 0;
        camera.zoom = 0.88; camera.targetZoom = 0.88;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      activeFrameLabelBoxes.length = 0;

      // 1. Mathematical Matte Slate Background & Cartesian Latent Grid
      renderManifoldBackground(timestamp);

      // 2. Topological Density Fields, Isoclines & Perimeter Realm Headers
      renderRealmTerritories(timestamp);

      // 3. Hierarchical Craft Filaments (Whisper-Quiet Default + Radiant Geodesic Spotlight)
      renderCraftFilaments(timestamp);

      // 4. Latent Sampler Radar Pulse (if probe mode active)
      if (probeActive) {
        renderSamplerPulse(timestamp);
      }

      // 4.5 Interactive Spiderfy Connecting Spokes & Origin Centroid Hub
      if (activeSpiderfy) {
        renderSpiderfySpokes(timestamp);
      }

      // 5. Mathematical Data Nodes & Anchor Landmark Keystones
      renderNodes(timestamp);

      // 5.5 Dynamic Semantic Zoom: Super-Dense Clump Micro-Badges (+3, +4)
      renderSuperDenseClumpBadges(timestamp);
      renderClumpHoverTooltip();

      // 6. Focus Crosshair Reticle if search target active
      if (searchTargetStar && timestamp - searchCrosshairTime < 4000) {
        renderTargetCrosshair(searchTargetStar, timestamp - searchCrosshairTime);
      }

      // 7. Interactive Edge & Relationship Tooltip (Hover / Interaction)
      renderEdgeTooltip();
    } catch (err) {
      console.error("Manifold render loop error:", err);
    }

    animationFrameId = requestAnimationFrame(renderLoop);
  }

  function hexToRgba(hex, alpha = 1.0) {
    if (!hex || typeof hex !== "string") {
      return `rgba(126, 181, 196, ${alpha})`;
    }
    if (hex.startsWith("rgba(") || hex.startsWith("rgb(")) {
      return hex;
    }
    let c = hex.replace("#", "").trim();
    if (c.length === 3) {
      c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    }
    if (c.length !== 6) {
      return `rgba(126, 181, 196, ${alpha})`;
    }
    const num = parseInt(c, 16);
    if (isNaN(num)) {
      return `rgba(126, 181, 196, ${alpha})`;
    }
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function drawGlassPill(ctx, x, y, w, h, r, bgRgba, borderRgba) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
    if (bgRgba) {
      ctx.fillStyle = bgRgba;
      ctx.fill();
    }
    if (borderRgba) {
      ctx.strokeStyle = borderRgba;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    ctx.restore();
  }

  // Helper: Smooth Closed Polygon (Catmull-Rom / Quadratic Bezier Spline)
  function drawSmoothClosedPolygon(ctx, pts) {
    if (!pts || pts.length < 3) return;
    const screenPts = pts.map((p) => worldToScreen(p[0], p[1]));
    const len = screenPts.length;
    const startMidX = (screenPts[0].x + screenPts[len - 1].x) / 2;
    const startMidY = (screenPts[0].y + screenPts[len - 1].y) / 2;
    ctx.beginPath();
    ctx.moveTo(startMidX, startMidY);
    for (let i = 0; i < len; i++) {
      const curr = screenPts[i];
      const next = screenPts[(i + 1) % len];
      const midX = (curr.x + next.x) / 2;
      const midY = (curr.y + next.y) / 2;
      ctx.quadraticCurveTo(curr.x, curr.y, midX, midY);
    }
    ctx.closePath();
  }

  // ---------------------------------------------------------------------------
  // 1. Mathematical Cartesian Latent Vector Manifold Grid
  // ---------------------------------------------------------------------------
  function renderManifoldBackground(timestamp) {
    // Deep matte obsidian slate background
    const grad = ctx.createRadialGradient(width / 2, height / 2, 60, width / 2, height / 2, Math.max(width, height) * 0.90);
    grad.addColorStop(0, "#080c16");
    grad.addColorStop(1, "#04060c");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    ctx.save();

    // 1. Fine Mathematical Subdivisions (40px spacing)
    const fineSpacing = 40 * camera.zoom;
    const fineOffsetX = (width / 2 - camera.x * camera.zoom) % fineSpacing;
    const fineOffsetY = (height / 2 - camera.y * camera.zoom) % fineSpacing;

    if (camera.zoom > 0.65) {
      ctx.strokeStyle = "rgba(126, 181, 196, 0.012)";
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      for (let x = fineOffsetX; x < width; x += fineSpacing) {
        ctx.moveTo(x, 0); ctx.lineTo(x, height);
      }
      for (let y = fineOffsetY; y < height; y += fineSpacing) {
        ctx.moveTo(0, y); ctx.lineTo(width, y);
      }
      ctx.stroke();
    }

    // 2. Primary Coordinate Grid (160px spacing - dimmed by 45%)
    const gridSpacing = 160 * camera.zoom;
    const offsetX = (width / 2 - camera.x * camera.zoom) % gridSpacing;
    const offsetY = (height / 2 - camera.y * camera.zoom) % gridSpacing;

    ctx.strokeStyle = "rgba(126, 181, 196, 0.024)";
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    for (let x = offsetX; x < width; x += gridSpacing) {
      ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    for (let y = offsetY; y < height; y += gridSpacing) {
      ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    ctx.stroke();

    // 3. Subtle Coordinate Intersection Crosshairs & Numeric Hashes (dimmed by 60%)
    ctx.strokeStyle = "rgba(14, 165, 233, 0.055)";
    ctx.lineWidth = 0.8;
    const tick = 3.5;
    for (let x = offsetX; x < width; x += gridSpacing) {
      for (let y = offsetY; y < height; y += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(x - tick, y); ctx.lineTo(x + tick, y);
        ctx.moveTo(x, y - tick); ctx.lineTo(x, y + tick);
        ctx.stroke();
      }
    }

    // 5. Canvas HUD Telemetry Badge (Top-Right)
    const hudW = 260;
    const hudH = 22;
    const hudX = width - hudW - 14;
    const hudY = 14;
    drawGlassPill(ctx, hudX, hudY, hudW, hudH, 4, "rgba(8, 12, 22, 0.85)", "rgba(14, 165, 233, 0.20)");

    ctx.font = "600 9px 'JetBrains Mono', monospace";
    ctx.fillStyle = "rgba(126, 181, 196, 0.75)";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const coordStr = `LAT: ${(camera.x * 0.01).toFixed(2)} | LON: ${(camera.y * 0.01).toFixed(2)} | ZOOM: ${camera.zoom.toFixed(2)}x`;
    ctx.fillText(coordStr, hudX + hudW / 2, hudY + hudH / 2);

    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // 2. Topological Density Fields & Perimeter Realm Headers
  // ---------------------------------------------------------------------------
  function renderRealmTerritories(timestamp) {
    if (!galaxyData.sectors || galaxyData.sectors.length === 0) return;
    ctx.save();

    // Dim all cluster contours, volumetric auras, and apex badges to 10%–15% (12%) when a movie is selected
    const clusterDimFactor = selectedStar ? 0.12 : 1.0;
    ctx.globalAlpha = clusterDimFactor;

    const stars = galaxyData.stars || [];

    for (const sec of galaxyData.sectors) {
      const secColor = sec.color || "#0ea5e9";
      const isHovered = hoveredSector && hoveredSector.id === sec.id;
      const isActive = activeSectorId === sec.id;

      // Filter member stars for this sector
      const memberStars = [];
      let sumX = 0, sumY = 0;
      for (let i = 0; i < stars.length; i++) {
        if (stars[i].sector_id === sec.id) {
          memberStars.push(stars[i]);
          sumX += stars[i].x;
          sumY += stars[i].y;
        }
      }

      if (memberStars.length === 0 && typeof sec.cx !== "number") continue;

      const cx = memberStars.length > 0 ? (sumX / memberStars.length) : (sec.cx || 0);
      const cy = memberStars.length > 0 ? (sumY / memberStars.length) : (sec.cy || 0);
      const sp = worldToScreen(cx, cy);

      // Find radius encompassing stars
      let maxDist = 75;
      for (let i = 0; i < memberStars.length; i++) {
        const d = Math.hypot(memberStars[i].x - cx, memberStars[i].y - cy);
        if (d > maxDist) maxDist = d;
      }
      const radius = Math.max(80, (maxDist + 35) * camera.zoom);

      // 1. Soft Low-Opacity Volumetric Radial Field / Blurred Hull Presence (5-8% alpha)
      const auraGrad = ctx.createRadialGradient(sp.x, sp.y, radius * 0.10, sp.x, sp.y, radius * 1.25);
      const auraAlpha = isHovered || isActive ? 0.14 : 0.065;
      auraGrad.addColorStop(0, hexToRgba(secColor, auraAlpha));
      auraGrad.addColorStop(0.55, hexToRgba(secColor, auraAlpha * 0.45));
      auraGrad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = auraGrad;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, radius * 1.25, 0, Math.PI * 2);
      ctx.fill();

      // 2. Multi-Level Organic Density Contours (Isoclines) with solid, cohesive boundaries
      const validContours = (sec.density_contours || []).filter((c) => c.polygon && c.polygon.length >= 3);
      if (validContours.length > 0) {
        for (const cnt of validContours) {
          const lvl = cnt.level || 0.5;
          const isOuter = lvl <= 0.35;
          const isCore = lvl >= 0.75;

          const polyAlpha = (isHovered || isActive)
            ? (isCore ? 0.22 : (isOuter ? 0.08 : 0.14))
            : (isCore ? 0.12 : (isOuter ? 0.055 : 0.08));

          ctx.fillStyle = hexToRgba(secColor, polyAlpha);
          ctx.strokeStyle = hexToRgba(secColor, isCore ? 0.55 : (isOuter ? 0.32 : 0.38));
          ctx.lineWidth = isCore ? 1.4 : (isOuter ? 1.2 : 1.0);

          drawSmoothClosedPolygon(ctx, cnt.polygon);
          ctx.fill();
          ctx.stroke();
        }
      } else {
        // Fallback: Clear Spatial Boundary Ring (Solid, not lost against grid)
        ctx.strokeStyle = hexToRgba(secColor, isHovered || isActive ? 0.45 : 0.24);
        ctx.lineWidth = isHovered || isActive ? 1.4 : 1.1;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, radius * 0.98, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 3. Collision-Free Outward Perimeter Apex Realm Header Badge
      // Position badge on the outward vector from manifold origin (0,0) beyond the cluster boundary
      const normDist = Math.hypot(cx, cy) || 1.0;
      const uX = cx / normDist;
      const uY = cy / normDist;
      const badgeWorldX = cx + uX * (maxDist + 42);
      const badgeWorldY = cy + uY * (maxDist + 42);
      const spBadge = worldToScreen(badgeWorldX, badgeWorldY);

      // Smoothly fade out realm header badge when zoomed in deep (> 1.35x)
      const badgeAlpha = Math.max(0, Math.min(1.0, 1.0 - (camera.zoom - 1.25) / 0.35));
      if (badgeAlpha > 0.05) {
        ctx.save();
        ctx.globalAlpha = badgeAlpha * (isHovered ? 1.0 : 0.85) * clusterDimFactor;

        const titleText = getShortClusterLabel(sec);
        const fontSize = Math.max(10, Math.min(13, Math.round(11 * Math.min(1.1, camera.zoom))));
        ctx.font = `700 ${fontSize}px 'Rajdhani', sans-serif`;
        const titleWidth = ctx.measureText(titleText).width;
        const pillW = titleWidth + 18;
        const pillH = fontSize + 10;

        sec._badgeScreen = {
          x: spBadge.x - pillW / 2,
          y: spBadge.y - pillH / 2,
          w: pillW,
          h: pillH,
          alpha: badgeAlpha
        };

        drawGlassPill(
          ctx,
          spBadge.x - pillW / 2,
          spBadge.y - pillH / 2,
          pillW,
          pillH,
          4,
          hexToRgba("#070b14", isHovered || isActive ? 0.96 : 0.88),
          hexToRgba(secColor, isHovered || isActive ? 0.95 : 0.45)
        );

        ctx.fillStyle = isHovered || isActive ? "#ffffff" : hexToRgba(secColor, 0.95);
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(titleText, spBadge.x, spBadge.y);
        ctx.restore();
      } else {
        sec._badgeScreen = null;
      }
    }

    // Legacy canvas return breadcrumb suppressed to prevent overlapping with floating toolbar
    galaxyData._overviewBtn = null;

    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // 3. Hierarchical Craft Filaments (Whisper-Quiet Default + Radiant Spotlight)
  // ---------------------------------------------------------------------------
  function renderCraftFilaments(timestamp) {
    if (!filteredLinks || filteredLinks.length === 0) return;
    ctx.save();

    const starMap = new Map((filteredStars || []).map((s) => [s.id, s]));
    const activeStar = selectedStar || hoveredStar;

    for (const link of filteredLinks) {
      const s1 = starMap.get(link.source);
      const s2 = starMap.get(link.target);
      if (!s1 || !s2) continue;

      const p1 = getStarScreenPos(s1);
      const p2 = getStarScreenPos(s2);

      // Frustum culling
      if ((p1.x < 0 && p2.x < 0) || (p1.x > width && p2.x > width) ||
        (p1.y < 0 && p2.y < 0) || (p1.y > height && p2.y > height)) {
        continue;
      }

      const isConnectedToActive = activeStar && (activeStar.id === s1.id || activeStar.id === s2.id);

      // Curvature Control Point (Quadratic Spline)
      const midX = (p1.x + p2.x) / 2 + (p1.y - p2.y) * 0.08;
      const midY = (p1.y + p2.y) / 2 + (p2.x - p1.x) * 0.08;

      if (activeStar) {
        // Spotlight Mode: Only illuminate connected craft filaments (visually encoded, bare lines)
        if (isConnectedToActive) {
          const props = getLinkVisualProps(link);
          const isHovered = hoveredEdge && hoveredEdge.link === link;

          ctx.save();
          ctx.strokeStyle = isHovered ? "#ffffff" : props.color;
          ctx.lineWidth = isHovered ? (props.width + 1.2) : props.width;
          if (isHovered) {
            ctx.shadowColor = props.color;
            ctx.shadowBlur = 12;
          }
          ctx.setLineDash(props.dash);
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.quadraticCurveTo(midX, midY, p2.x, p2.y);
          ctx.stroke();
          ctx.restore();
        }
      } else {
        // Default Overview Mode: Subdued ambient craft filaments (ultra-quiet whisper)
        const isStructural = link.link_type === "franchise" || link.link_type === "director";
        if (!isStructural) continue;

        const baseAlpha = link.link_type === "franchise" ? 0.035 : 0.018;
        ctx.strokeStyle = link.link_type === "franchise" ? `rgba(249, 115, 22, ${baseAlpha})` : `rgba(224, 169, 109, ${baseAlpha})`;
        ctx.lineWidth = link.link_type === "franchise" ? 0.85 : 0.55;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.quadraticCurveTo(midX, midY, p2.x, p2.y);
        ctx.stroke();
      }
    }

    // Anchor-Conditioned Local Neighborhood Resonance Filaments (bare dotted arcs, details on hover)
    if (selectedStar && selectedResonantNeighbors && selectedResonantNeighbors.length > 0) {
      const p1 = getStarScreenPos(selectedStar);
      for (const res of selectedResonantNeighbors) {
        const p2 = getStarScreenPos(res.star);
        if ((p1.x < -100 && p2.x < -100) || (p1.x > width + 100 && p2.x > width + 100) ||
            (p1.y < -100 && p2.y < -100) || (p1.y > height + 100 && p2.y > height + 100)) {
          continue;
        }

        const isHovered = hoveredEdge && (hoveredEdge.res === res || hoveredEdge.starId === res.star.id);

        ctx.save();
        ctx.strokeStyle = isHovered ? "#ffffff" : "rgba(203, 213, 225, 0.50)";
        ctx.lineWidth = isHovered ? 2.0 : 1.0;
        if (isHovered) {
          ctx.shadowColor = "#cbd5e1";
          ctx.shadowBlur = 10;
        }
        ctx.setLineDash([2, 4]);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
        ctx.restore();
      }
    }
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // 4. Latent Coordinate Sampler Radar Pulse
  // ---------------------------------------------------------------------------
  function renderSamplerPulse(timestamp) {
    if (!probeActive || currentMode !== "probe") {
      probeActive = null;
      return;
    }
    const sp = worldToScreen(probeActive.x, probeActive.y);
    if (sp.x < -300 || sp.x > width + 300 || sp.y < -300 || sp.y > height + 300) return;

    const elapsed = Math.max(0, (timestamp - probeAnimTime) * 0.001);

    ctx.save();
    const ringFade = Math.max(0, 1 - (elapsed - 4.0) / 1.5);
    if (ringFade > 0) {
      for (let i = 0; i < 3; i++) {
        const phase = (elapsed + i * 0.6) % 2.0;
        const radius = Math.max(0.5, phase * 130 * camera.zoom);
        const alpha = Math.max(0, Math.min(0.8, (1 - phase / 2.0) * 0.7 * ringFade));

        ctx.strokeStyle = `rgba(168, 85, 247, ${alpha})`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, radius, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    ctx.fillStyle = "#a855f7";
    ctx.beginPath();
    ctx.arc(sp.x, sp.y, 3.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "rgba(168, 85, 247, 0.65)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sp.x - 14, sp.y); ctx.lineTo(sp.x + 14, sp.y);
    ctx.moveTo(sp.x, sp.y - 14); ctx.lineTo(sp.x, sp.y + 14);
    ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // 5. Mathematical Data Nodes & Progressive Semantic LOD (Anti-Trypophobia)
  // ---------------------------------------------------------------------------
  function renderNodes(timestamp) {
    if (!filteredStars || filteredStars.length === 0) return;
    ctx.save();

    const activeStar = selectedStar || hoveredStar;

    // Build fast neighbor set
    const neighborSet = getActiveNeighborSet(activeStar);

    const sectorMap = new Map((galaxyData.sectors || []).map((s) => [s.id, s]));
    const nodeScreenData = [];

    // --- PASS 1: Render All Data Nodes (Cluster Color, Movie Circle vs TV Rounded Square, Watched Glow vs Unwatched 20% Translucent) ---
    for (const star of filteredStars) {
      const sp = getStarScreenPos(star);
      if (sp.x < -80 || sp.x > width + 80 || sp.y < -80 || sp.y > height + 80) continue;

      const isDirect = activeStar && activeStar.id === star.id;
      const isNeighbor = activeStar && !isDirect && neighborSet.has(star.id);
      const isSpiderfied = activeSpiderfy && activeSpiderfy.items.some((it) => it.star.id === star.id);
      const isTv = star.tv_show === 1 || star.tv_show === "1" || star.tv_show === true || star.media_type === "tv";
      const isWatched = !!star.is_watched;
      const isAnchor = !!star.is_anchor;
      const isWatchlist = star.is_watchlist && !isWatched;
      const isVoid = !!star.is_void || star.category === "void_repulsor" || (isWatched && star.rating <= 2);
      const deg = star.degree || 1;

      // Spotlight Dimming Factor: when movie selected, dim background dots to 10%–15% (0.12)
      let nodeAlpha = 1.0;
      if (selectedStar) {
        if (isDirect) {
          nodeAlpha = 1.0;
        } else if (isNeighbor) {
          nodeAlpha = 1.0;
        } else if (isSpiderfied) {
          // Spiderfied star not connected to selected movie: dim so selected star & true neighbors stand out
          nodeAlpha = 0.20;
        } else {
          nodeAlpha = 0.12;
        }
      } else if (hoveredStar) {
        if (isDirect) {
          nodeAlpha = 1.0;
        } else if (isNeighbor) {
          nodeAlpha = 0.95;
        } else if (isSpiderfied) {
          nodeAlpha = 0.65;
        } else {
          nodeAlpha = 0.25;
        }
      } else if (isSpiderfied) {
        nodeAlpha = 1.0; // In free overview mode, spiderfied stars remain 100% visible
      }

      // Dynamic Semantic Zooming: scale individual node alpha with splitProgress, collapse into badge at overview
      const clump = starToClumpMap.get(star.id);
      const splitProgress = clump ? getSemanticZoomSplitProgress(clump) : 1.0;

      if (splitProgress <= 0.01 && !isDirect && !isSpiderfied) {
        continue;
      }
      if (splitProgress < 1.0 && !isDirect && !isSpiderfied) {
        nodeAlpha *= splitProgress;
      }
      ctx.globalAlpha = nodeAlpha;

      // Base color inherited from cluster / sector region
      const sec = sectorMap.get(star.sector_id);
      const clusterColor = (sec && sec.color) ? sec.color : (star.cluster_color || star.sector_color || "#0ea5e9");
      const coreColor = isVoid ? "#94a3b8" : clusterColor;

      let radius = isWatched
        ? ((isAnchor ? 5.2 : 4.0) + Math.min(2.0, deg * 0.25) * Math.min(1.3, Math.max(0.7, camera.zoom)))
        : (isAnchor ? 4.8 : (3.6 + Math.min(1.4, deg * 0.15)));

      if (isDirect) radius *= 1.35;
      radius = Math.max(3.0, radius);

      // 1. Top 5 Anchor Landmark Keystones: Sleek 4-Axis Reticle Crosshair
      if (isAnchor && nodeAlpha > 0.3) {
        const arm = radius + 4.2;
        ctx.strokeStyle = hexToRgba(clusterColor, 0.70);
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        ctx.moveTo(sp.x - arm, sp.y); ctx.lineTo(sp.x + arm, sp.y);
        ctx.moveTo(sp.x, sp.y - arm); ctx.lineTo(sp.x, sp.y + arm);
        ctx.stroke();
      }

      // 2. Node Core Rendering
      // - Movie vs TV Show: Circle vs Diamond
      // - Watched vs Unwatched: Solid bright fill with soft glow vs Hollow delicate outline
      // - Low-Rated / Void: Extinguished ashen slate core with diagonal slash strike-through (never red)
      if (isVoid) {
        drawNodeShape(ctx, sp.x, sp.y, radius, isTv);
        ctx.fillStyle = "#0c1017";
        ctx.fill();

        ctx.strokeStyle = isDirect ? "#ffffff" : (isNeighbor ? "rgba(203, 213, 225, 0.95)" : "rgba(148, 163, 184, 0.70)");
        ctx.lineWidth = isDirect ? 1.3 : 0.85;
        ctx.setLineDash([2, 2]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Distinct diagonal slash strike-through across the center
        const d = radius * 0.65;
        ctx.beginPath();
        ctx.moveTo(sp.x - d, sp.y - d);
        ctx.lineTo(sp.x + d, sp.y + d);
        ctx.strokeStyle = isDirect ? "#ffffff" : (isNeighbor ? "rgba(203, 213, 225, 0.95)" : "rgba(148, 163, 184, 0.80)");
        ctx.lineWidth = 1.0;
        ctx.stroke();
      } else if (isWatched) {
        // Watched: Solid, bright, filled shape with a soft glow in cluster base color
        ctx.save();
        drawNodeShape(ctx, sp.x, sp.y, radius, isTv);
        ctx.fillStyle = clusterColor;
        ctx.shadowColor = clusterColor;
        ctx.shadowBlur = isDirect ? 14 : (isNeighbor ? 10 : 6);
        ctx.fill();
        ctx.restore();

        if (isDirect || isNeighbor) {
          drawNodeShape(ctx, sp.x, sp.y, radius, isTv);
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = isDirect ? 1.4 : 1.0;
          ctx.stroke();
        } else if (isWatchlist) {
          drawNodeShape(ctx, sp.x, sp.y, radius + 1.5, isTv);
          ctx.strokeStyle = "#10b981";
          ctx.lineWidth = 0.9;
          ctx.stroke();
        }
      } else {
        // Unwatched: Refined, lightweight wireframe with semi-transparent interior (delicate stroke, no heavy borders)
        drawNodeShape(ctx, sp.x, sp.y, radius, isTv);
        ctx.fillStyle = hexToRgba(clusterColor, 0.20);
        ctx.fill();

        ctx.strokeStyle = hexToRgba(clusterColor, isDirect ? 0.95 : (isNeighbor ? 0.85 : 0.50));
        ctx.lineWidth = isDirect ? 1.3 : (isNeighbor ? 1.0 : 0.75);
        ctx.stroke();

        if (isDirect || isNeighbor) {
          drawNodeShape(ctx, sp.x, sp.y, radius + 1.4, isTv);
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 0.9;
          ctx.stroke();
        } else if (isWatchlist) {
          drawNodeShape(ctx, sp.x, sp.y, radius + 1.5, isTv);
          ctx.strokeStyle = "#10b981";
          ctx.lineWidth = 0.9;
          ctx.stroke();
        }
      }

      // 3. Direct Selection: Crisp Neon Halo & Animated Locked-On Pulse Ring
      if (isDirect) {
        const now = timestamp || performance.now();
        if (!star._selectAnimStart) {
          star._selectAnimStart = now;
        }
        const animElapsed = Math.max(0, (now - star._selectAnimStart) * 0.001);

        ctx.save();

        // A. Primary Crisp Neon Halo
        const haloR = radius + 4.5;

        // Outer glowing cyan aura
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 2.0;
        ctx.shadowColor = "#38bdf8";
        ctx.shadowBlur = 14;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, haloR, 0, Math.PI * 2);
        ctx.stroke();

        // Crisp inner core ring
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.1;
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, haloR, 0, Math.PI * 2);
        ctx.stroke();

        // B. Intentional "Lock-On" Ease-In Convergence Ring (First 0.5s after selection)
        if (animElapsed < 0.5) {
          const tNorm = animElapsed / 0.5;
          const easeOutCubic = 1 - Math.pow(1 - tNorm, 3);
          const lockR = haloR + (1 - easeOutCubic) * 18;
          const lockAlpha = (1 - easeOutCubic) * 0.85;

          ctx.strokeStyle = `rgba(255, 255, 255, ${lockAlpha})`;
          ctx.lineWidth = 1.5;
          ctx.shadowColor = "#38bdf8";
          ctx.shadowBlur = 12;
          ctx.beginPath();
          ctx.arc(sp.x, sp.y, lockR, 0, Math.PI * 2);
          ctx.stroke();
        }

        // C. Continuous Luminous Pulse Waves (Smooth ease-out harmonic rings)
        for (let p = 0; p < 2; p++) {
          const pulsePhase = ((now * 0.0012) + p * 0.5) % 1.0;
          const ease = Math.sin(pulsePhase * Math.PI * 0.5);
          const pulseR = haloR + ease * 13;
          const pulseAlpha = Math.max(0, (1.0 - pulsePhase) * 0.70);

          ctx.strokeStyle = `rgba(56, 189, 248, ${pulseAlpha})`;
          ctx.lineWidth = 1.3 * (1.0 - pulsePhase * 0.4);
          ctx.shadowColor = "rgba(56, 189, 248, 0.9)";
          ctx.shadowBlur = 10 * (1.0 - pulsePhase);
          ctx.beginPath();
          ctx.arc(sp.x, sp.y, pulseR, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.restore();
      }

      nodeScreenData.push({
        star,
        sp,
        radius,
        coreColor,
        isDirect,
        isNeighbor,
        isSpiderfied,
        isWatched,
        isAnchor,
        nodeAlpha,
        deg,
        priority: isDirect ? 100 : (isNeighbor ? 95 : (selectedStar ? 10 : (isSpiderfied ? 98 : (isAnchor ? 85 : (isWatched && (star.rating >= 4.5 || deg >= 3) ? 75 : (isWatched ? 60 : (star.match_score || star.match_pct || 40)))))))
      });
    }

    // --- PASS 2: Force-Directed Collision-Free Semantic Labels ---
    try {
      nodeScreenData.sort((a, b) => b.priority - a.priority);

      const screenPoints = nodeScreenData.map((d) => ({
        id: d.star.id,
        x: d.sp.x,
        y: d.sp.y,
        r: d.radius + 3
      }));

      const candidateLabels = [];

      for (const item of nodeScreenData) {
        const { star, sp, radius, coreColor, isDirect, isNeighbor, isSpiderfied, isWatched, isAnchor, nodeAlpha, deg } = item;
        if (nodeAlpha < 0.3) continue;

        // When a movie is selected, only show labels for the selected movie and its true connected subgraph
        if (selectedStar && !isDirect && !isNeighbor) {
          continue;
        }

        const isTop5Anchor = isAnchor;
        const isHighRatedWatched = isWatched && ((star.rating && star.rating >= 4.5) || deg >= 3);
        const isStandardWatched = isWatched && star.rating && star.rating >= 4.0;

        const shouldShowLabel = (isSpiderfied && !selectedStar) ||
          isDirect ||
          isNeighbor ||
          (isTop5Anchor && camera.zoom >= 0.40) ||
          (isHighRatedWatched && camera.zoom >= 0.95) ||
          (isStandardWatched && camera.zoom >= 1.35) ||
          (camera.zoom >= 1.75);

        // Dynamic Semantic Zoom: hide individual labels if clump is mostly collapsed at overview
        const clump = starToClumpMap.get(star.id);
        const splitProgress = clump ? getSemanticZoomSplitProgress(clump) : 1.0;
        if (splitProgress < 0.65 && !isDirect && !isSpiderfied) {
          continue;
        }

        if (!shouldShowLabel) continue;

        let text = star.title || "";
        if (isNeighbor && selectedStar && selectedResonantNeighbors) {
          const res = selectedResonantNeighbors.find(r => r.star.id === star.id);
          if (res && res.resonance) {
            text = `${star.title} · ${res.resonance}`;
          } else if (star.match_pct || star.match_score) {
            text = `${star.title} · ${star.match_pct || star.match_score}`;
          }
        }
        if (!isDirect && !isSpiderfied && text.length > 28) {
          text = text.substring(0, 26).trim() + "…";
        }

        let sentimentLvl = null;
        if (isWatched && star.rating) {
          let lvl = parseInt(star.rating, 10) || 3;
          if (lvl > 5) lvl = Math.ceil(lvl / 2);
          if (lvl < 1) lvl = 1;
          if (lvl > 5) lvl = 5;
          sentimentLvl = lvl;
        }

        const isProminent = isDirect || isNeighbor || (!selectedStar && isSpiderfied) || isTop5Anchor;
        const fontSize = Math.max(9, Math.min(13, Math.round(10.5 * Math.min(1.15, camera.zoom))));
        ctx.font = `${isProminent ? '600' : '500'} ${fontSize}px 'Rajdhani', sans-serif`;
        const textWidth = ctx.measureText(text).width;

        const iconSize = sentimentLvl ? Math.max(9, Math.min(13, Math.round(10 * Math.min(1.15, camera.zoom)))) : 0;
        const iconGap = sentimentLvl ? 5 : 0;
        const contentW = textWidth + (sentimentLvl ? (iconGap + iconSize) : 0);

        const boxW = contentW + 8;
        const boxH = Math.max(15, fontSize + 4);

        candidateLabels.push({
          star,
          sp,
          radius,
          isDirect,
          isNeighbor,
          isSpiderfied,
          isWatched,
          isProminent,
          text,
          sentimentLvl,
          fontSize,
          textWidth,
          iconSize,
          iconGap,
          boxW,
          boxH,
          priority: item.priority
        });
      }

      if (candidateLabels.length > 40) {
        candidateLabels.length = 40;
      }

      // Clear frame label boxes for accurate hit-testing
      activeFrameLabelBoxes.length = 0;

      const placedLabels = [];

      if (selectedStar) {
        // --- SELECTION FOCUS MODE: Focused Label + Angled Leader Line Callouts in Quadrant Space ---
        const centerSp = getStarScreenPos(selectedStar);

        // 1. Focused Node Label (Primary, 100% full opacity, anchored directly adjacent)
        const focusedCand = candidateLabels.find((c) => c.isDirect);
        if (focusedCand) {
          let anchorX = focusedCand.sp.x + focusedCand.radius + 10;
          let anchorY = focusedCand.sp.y - focusedCand.boxH / 2;
          if (anchorX + focusedCand.boxW > width - 12) {
            anchorX = focusedCand.sp.x - focusedCand.radius - 10 - focusedCand.boxW;
          }
          placedLabels.push({
            ...focusedCand,
            x: anchorX,
            y: anchorY,
            origX: anchorX,
            origY: anchorY,
            isFocused: true,
            isLeaderCallout: false,
            opacity: 1.0
          });
        }

        // 2. Connected Neighbors: Angled Leader Lines (Pin Markers) pushed into empty quadrant space
        const neighborCands = candidateLabels.filter((c) => !c.isDirect && c.isNeighbor);
        const neighborCount = neighborCands.length;

        for (let i = 0; i < neighborCount; i++) {
          const cand = neighborCands[i];
          const { sp, radius, boxW, boxH, star } = cand;

          // Compute outward angle from focused cluster center to this neighbor
          const dxCenter = sp.x - centerSp.x;
          const dyCenter = sp.y - centerSp.y;
          const distCenter = Math.hypot(dxCenter, dyCenter);

          let angle;
          if (distCenter < 8) {
            // Symmetrically fan callouts across available quadrants if physically co-located
            angle = -Math.PI * 0.70 + (i * Math.PI * 2) / Math.max(1, neighborCount);
          } else {
            angle = Math.atan2(dyCenter, dxCenter);
          }

          const normX = Math.cos(angle);
          const normY = Math.sin(angle);
          const isRight = normX >= 0;

          // Stagger leader distances to prevent callouts in the same quadrant from overlapping
          const stagger = (i % 3) * 24;
          const radialDist = 48 + stagger;

          // Angled elbow position pushed out into empty quadrant space
          let elbowX = sp.x + (isRight ? Math.max(34, Math.abs(normX) * radialDist) : -Math.max(34, Math.abs(normX) * radialDist));
          let elbowY = sp.y + normY * (radialDist * 0.70);

          const shelfLen = 14;
          let shelfX = isRight ? elbowX + shelfLen : elbowX - shelfLen;

          let labelX = isRight ? shelfX + 4 : shelfX - boxW - 4;
          let labelY = elbowY - boxH / 2;

          // Screen boundary margins
          const margin = 12;
          if (labelX < margin) {
            labelX = margin;
            shelfX = labelX + boxW + 4;
            elbowX = shelfX + shelfLen;
          } else if (labelX + boxW > width - margin) {
            labelX = width - margin - boxW;
            shelfX = labelX - 4;
            elbowX = shelfX - shelfLen;
          }

          if (labelY < margin) {
            labelY = margin;
            elbowY = labelY + boxH / 2;
          } else if (labelY + boxH > height - margin) {
            labelY = height - margin - boxH;
            elbowY = labelY + boxH / 2;
          }

          // Resolve vertical overlap between neighboring callouts on the same side
          for (const prev of placedLabels) {
            if (prev.isLeaderCallout && prev.isRightSide === isRight) {
              const overlapY = (prev.y + prev.boxH + 5) - labelY;
              if (overlapY > 0 && (labelY + boxH + 5) > prev.y) {
                labelY += overlapY + 4;
                elbowY = labelY + boxH / 2;
              }
            }
          }

          // Movies that have connections with the selected one are clearly visible at 100% opacity with angled leader lines!
          placedLabels.push({
            ...cand,
            x: labelX,
            y: labelY,
            origX: labelX,
            origY: labelY,
            isFocused: false,
            isLeaderCallout: true,
            isRightSide: isRight,
            pin: { x: sp.x, y: sp.y, r: radius },
            elbow: { x: elbowX, y: elbowY },
            shelf: { x: shelfX, y: elbowY },
            opacity: 1.0,
            isHovered: false
          });
        }
      } else {
        // --- OVERVIEW / FREE BROWSING MODE (No node selected) ---
        for (const cand of candidateLabels) {
          const { sp, radius, boxW, boxH, isDirect, isNeighbor, isSpiderfied, star } = cand;

          if (isSpiderfied) {
            let anchorX = sp.x + radius + 8;
            let anchorY = sp.y - boxH / 2;
            if (anchorX + boxW > width - 10) {
              anchorX = sp.x - radius - 8 - boxW;
            }
            placedLabels.push({
              ...cand,
              x: anchorX,
              y: anchorY,
              origX: anchorX,
              origY: anchorY,
              isAnchoredRight: true,
              opacity: 1.0,
              isFocused: false,
              isLeaderCallout: false
            });
            continue;
          }

          const candidatePositions = [
            { x: sp.x + radius + 8, y: sp.y - boxH / 2, bias: 0 },
            { x: sp.x + radius + 5, y: sp.y - boxH - 2, bias: 6 },
            { x: sp.x + radius + 5, y: sp.y + 4, bias: 6 },
            { x: sp.x - radius - boxW - 8, y: sp.y - boxH / 2, bias: 15 },
            { x: sp.x - radius - boxW - 5, y: sp.y - boxH - 2, bias: 20 },
            { x: sp.x - radius - boxW - 5, y: sp.y + 4, bias: 20 },
            { x: sp.x - boxW / 2, y: sp.y - radius - boxH - 4, bias: 30 },
            { x: sp.x - boxW / 2, y: sp.y + radius + 4, bias: 30 }
          ];

          let bestPos = candidatePositions[0];
          let lowestCost = Infinity;

          for (const pos of candidatePositions) {
            let cost = pos.bias;
            for (let i = 0; i < screenPoints.length; i++) {
              const pt = screenPoints[i];
              if (pt.id === star.id) continue;
              const nearestX = Math.max(pos.x, Math.min(pt.x, pos.x + boxW));
              const nearestY = Math.max(pos.y, Math.min(pt.y, pos.y + boxH));
              const distSq = (pt.x - nearestX) ** 2 + (pt.y - nearestY) ** 2;
              if (distSq < pt.r * pt.r) cost += 4000;
            }
            for (let i = 0; i < placedLabels.length; i++) {
              const pl = placedLabels[i];
              const overlapW = Math.min(pos.x + boxW + 4, pl.x + pl.boxW + 4) - Math.max(pos.x - 4, pl.x - 4);
              const overlapH = Math.min(pos.y + boxH + 3, pl.y + pl.boxH + 3) - Math.max(pos.y - 3, pl.y - 3);
              if (overlapW > 0 && overlapH > 0) cost += 2000 + overlapW * overlapH * 2;
            }
            if (cost < lowestCost) {
              lowestCost = cost;
              bestPos = pos;
              if (cost === 0) break;
            }
          }

          if (lowestCost < 1800 || cand.isProminent) {
            placedLabels.push({
              ...cand,
              x: bestPos.x,
              y: bestPos.y,
              origX: bestPos.x,
              origY: bestPos.y,
              isAnchoredRight: false,
              opacity: 0.90,
              isFocused: false,
              isLeaderCallout: false
            });
          }
        }

        // Force-directed relaxation passes (2 iterations) for overview mode
        for (let iter = 0; iter < 2; iter++) {
          for (let i = 0; i < placedLabels.length; i++) {
            const L1 = placedLabels[i];
            for (let j = 0; j < placedLabels.length; j++) {
              if (i === j) continue;
              const L2 = placedLabels[j];
              const padX = 4, padY = 3;
              const overlapW = Math.min(L1.x + L1.boxW + padX, L2.x + L2.boxW + padX) - Math.max(L1.x - padX, L2.x - padX);
              const overlapH = Math.min(L1.y + L1.boxH + padY, L2.y + L2.boxH + padY) - Math.max(L1.y - padY, L2.y - padY);
              if (overlapW > 0 && overlapH > 0) {
                const push = (overlapH / 2) + 1;
                const dir = L1.y < L2.y ? -1 : 1;
                L1.y += dir * push * 0.7;
                if (!L2.isDirect) L2.y -= dir * push * 0.7;
              }
            }
            if (L1.isAnchoredRight) {
              L1.x = L1.origX;
            } else {
              const dx = L1.x - L1.origX;
              const dy = L1.y - L1.origY;
              const drift = Math.hypot(dx, dy);
              if (drift > 26) {
                L1.x = L1.origX + (dx / drift) * 26;
                L1.y = L1.origY + (dy / drift) * 26;
              }
            }
          }
        }
      }

      // Render placed labels with subtle dark background blur, leader lines, and high-contrast glass pills
      for (const L of placedLabels) {
        const padX = 5;
        const padY = 3;
        const pillX = L.x - padX;
        const pillY = L.y - padY;
        const pillW = L.boxW + padX * 2;
        const pillH = L.boxH + padY * 2;
        const pillR = 3.5;

        activeFrameLabelBoxes.push({ x: pillX, y: pillY, w: pillW, h: pillH, star: L.star });

        const baseAlpha = L.opacity !== undefined ? L.opacity : 1.0;

        // 1. Draw Angled Leader Line (Pin Marker & Elbow Shelf) if callout
        if (L.isLeaderCallout && L.pin && L.elbow && L.shelf) {
          ctx.save();
          ctx.globalAlpha = 1.0;

          // A. Pin Marker at star node (radiating pin ring + center dot)
          ctx.fillStyle = "#38bdf8";
          ctx.beginPath();
          ctx.arc(L.pin.x, L.pin.y, 2.2, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = "rgba(56, 189, 248, 0.70)";
          ctx.lineWidth = 1.1;
          ctx.beginPath();
          ctx.arc(L.pin.x, L.pin.y, L.pin.r + 2.5, 0, Math.PI * 2);
          ctx.stroke();

          // B. Angled Leader Line & Horizontal Shelf
          const angleToElbow = Math.atan2(L.elbow.y - L.pin.y, L.elbow.x - L.pin.x);
          const startX = L.pin.x + Math.cos(angleToElbow) * (L.pin.r + 2.5);
          const startY = L.pin.y + Math.sin(angleToElbow) * (L.pin.r + 2.5);

          ctx.strokeStyle = "rgba(56, 189, 248, 0.65)";
          ctx.lineWidth = 1.2;
          ctx.setLineDash([3, 2]);
          ctx.beginPath();
          ctx.moveTo(startX, startY);
          ctx.lineTo(L.elbow.x, L.elbow.y);
          ctx.lineTo(L.shelf.x, L.shelf.y);
          ctx.stroke();

          // C. Elbow vertex accent dot
          ctx.fillStyle = "#38bdf8";
          ctx.beginPath();
          ctx.arc(L.elbow.x, L.elbow.y, 1.8, 0, Math.PI * 2);
          ctx.fill();

          ctx.restore();
        }

        // 2. Draw Label Pill Background & Border
        ctx.save();
        ctx.globalAlpha = 1.0;

        ctx.shadowColor = "rgba(0, 0, 0, 0.95)";
        ctx.shadowBlur = L.isFocused ? 12 : 8;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 1;

        // Dark obsidian backdrop with high opacity to cleanly occlude crossing filaments
        ctx.fillStyle = L.isFocused
          ? "rgba(6, 11, 22, 0.98)"
          : (L.isLeaderCallout ? "rgba(6, 11, 22, 0.96)" : "rgba(6, 11, 22, 0.92)");

        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(pillX, pillY, pillW, pillH, pillR);
        } else {
          ctx.rect(pillX, pillY, pillW, pillH);
        }
        ctx.fill();

        // Border accent: glowing cyan for focused / callout, subtle cyan tint for others
        ctx.shadowBlur = L.isFocused ? 8 : (L.isLeaderCallout ? 5 : 0);
        ctx.shadowColor = "#38bdf8";
        ctx.strokeStyle = L.isFocused
          ? "rgba(56, 189, 248, 0.95)"
          : (L.isLeaderCallout ? "rgba(56, 189, 248, 0.50)" : "rgba(56, 189, 248, 0.30)");
        ctx.lineWidth = L.isFocused ? 1.4 : 1.0;
        ctx.stroke();

        ctx.restore();

        // 3. Label Typography
        ctx.save();
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = L.isFocused
          ? "#ffffff"
          : (L.isNeighbor ? "#e0f2fe" : "#ffffff");
        ctx.font = `${(L.isFocused || L.isLeaderCallout || L.isProminent) ? '600' : '500'} ${L.fontSize}px 'Rajdhani', sans-serif`;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(L.text, L.x + 2, L.y + L.boxH / 2);

        if (L.sentimentLvl) {
          const iconX = L.x + 2 + L.textWidth + L.iconGap;
          const iconY = L.y + (L.boxH - L.iconSize) / 2;
          drawSentimentCanvasIcon(ctx, iconX, iconY, L.iconSize, L.sentimentLvl);
        }
        ctx.restore();
      }
    } catch (labelErr) {
      console.warn("Manifold label layout warning:", labelErr);
    }

    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Dynamic Semantic Zoom: Super-Dense Clump Micro-Badges (+3, +4, etc.)
  // ---------------------------------------------------------------------------
  function renderSuperDenseClumpBadges(timestamp) {
    if (!superDenseClumps || superDenseClumps.length === 0) return;
    ctx.save();

    const clusterDimFactor = selectedStar ? 0.12 : 1.0;

    for (const clump of superDenseClumps) {
      const splitProgress = getSemanticZoomSplitProgress(clump);
      if (splitProgress >= 1.0) {
        clump._badgeScreen = null;
        continue;
      }

      const sp = worldToScreen(clump.cx, clump.cy);
      if (sp.x < -60 || sp.x > width + 60 || sp.y < -60 || sp.y > height + 60) {
        clump._badgeScreen = null;
        continue;
      }

      // Smoothly fade out as zoom approaches split threshold
      let badgeAlpha = 1.0 - splitProgress;
      if (badgeAlpha <= 0.02) {
        clump._badgeScreen = null;
        continue;
      }

      const isHovered = hoveredClump && hoveredClump.id === clump.id;
      const isSelected = selectedStar && clump.starIds.has(selectedStar.id);

      // Dim non-selected badges when another star is selected
      if (selectedStar && !isSelected) {
        badgeAlpha *= clusterDimFactor;
      }

      // Base radius ~13px to 15px, scale subtly with zoom
      const r = (isSelected ? 15.0 : (isHovered ? 14.2 : 13.0)) * Math.max(0.75, 1.0 - splitProgress * 0.25);
      clump._badgeScreen = { x: sp.x, y: sp.y, r, alpha: badgeAlpha, clump };

      ctx.save();
      ctx.globalAlpha = Math.max(0.05, Math.min(1.0, badgeAlpha));

      const clumpColor = clump.color || "#0ea5e9";

      // 1. Stacked Depth Layer: offset shadow disc behind the badge to indicate multiple works
      ctx.beginPath();
      ctx.arc(sp.x + 2.4, sp.y + 2.4, r - 0.8, 0, Math.PI * 2);
      ctx.fillStyle = hexToRgba(clumpColor, 0.20 * badgeAlpha);
      ctx.fill();
      ctx.strokeStyle = hexToRgba(clumpColor, 0.40 * badgeAlpha);
      ctx.lineWidth = 1.0;
      ctx.stroke();

      // 2. Luminous Ambient Glow
      ctx.shadowColor = isSelected ? "#38bdf8" : clumpColor;
      ctx.shadowBlur = (isHovered || isSelected) ? 14 : 8;

      // 3. Main Glassmorphic Circular Body
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, r, 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? "rgba(14, 28, 48, 0.96)" : (isHovered ? "rgba(10, 16, 28, 0.95)" : "rgba(7, 11, 20, 0.92)");
      ctx.fill();

      // Subtle inner ambient color wash
      ctx.fillStyle = hexToRgba(clumpColor, isHovered ? 0.35 : 0.22);
      ctx.fill();

      // 4. Glowing Border Rim
      ctx.strokeStyle = isSelected ? "#ffffff" : hexToRgba(clumpColor, isHovered ? 0.95 : 0.72);
      ctx.lineWidth = isSelected ? 1.8 : (isHovered ? 1.5 : 1.2);
      ctx.stroke();

      // 5. Selected Locked-On Pulse Wave (if movie inside this clump is active)
      if (isSelected) {
        const pulsePhase = ((performance.now() * 0.0015) % 1.0);
        const pulseR = r + pulsePhase * 10;
        const pulseAlpha = Math.max(0, (1.0 - pulsePhase) * 0.75 * badgeAlpha);
        ctx.strokeStyle = `rgba(56, 189, 248, ${pulseAlpha})`;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, pulseR, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 6. Numbered Micro-Badge Text: "+3", "+4"
      ctx.shadowBlur = 0;
      ctx.fillStyle = isHovered || isSelected ? "#ffffff" : hexToRgba(clumpColor, 0.98);
      const fontSize = Math.max(9, Math.min(13, Math.round(r * 0.90)));
      ctx.font = `700 ${fontSize}px 'Rajdhani', sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`+${clump.count}`, sp.x, sp.y + 0.5);

      // 7. Watched Indicator Pip (tiny luminous pip on top-right rim if clump has watched film)
      if (clump.hasWatched) {
        const pipAngle = -Math.PI / 4; // 45° top-right
        const pipDist = r + 1.2;
        const pipX = sp.x + pipDist * Math.cos(pipAngle);
        const pipY = sp.y + pipDist * Math.sin(pipAngle);
        ctx.beginPath();
        ctx.arc(pipX, pipY, 2.4, 0, Math.PI * 2);
        ctx.fillStyle = "#38bdf8";
        ctx.shadowColor = "#38bdf8";
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }

      ctx.restore();
    }

    ctx.restore();
  }

  function renderClumpHoverTooltip() {
    if (!hoveredClump || !hoveredClump._badgeScreen) return;
    const b = hoveredClump._badgeScreen;
    if (b.alpha < 0.2) return;

    ctx.save();
    ctx.globalAlpha = Math.min(1.0, b.alpha * 1.25);

    const count = hoveredClump.count;
    const titles = hoveredClump.stars.map((s) => s.title).slice(0, 3).join(", ");
    const moreStr = count > 3 ? ` (+${count - 3} more)` : "";
    const tooltipText = `⬡ ${count} FILMS: ${titles}${moreStr}`;

    ctx.font = "600 11px 'Rajdhani', sans-serif";
    const textW = ctx.measureText(tooltipText).width;
    const boxW = textW + 18;
    const boxH = 22;
    const boxX = Math.max(12, Math.min(width - boxW - 12, b.x - boxW / 2));
    const boxY = b.y - b.r - boxH - 7;

    drawGlassPill(
      ctx,
      boxX,
      boxY,
      boxW,
      boxH,
      4,
      "rgba(7, 11, 20, 0.94)",
      hexToRgba(hoveredClump.color || "#0ea5e9", 0.85)
    );

    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(tooltipText, boxX + boxW / 2, boxY + boxH / 2);

    ctx.restore();
  }

  function renderTargetCrosshair(star, elapsed) {
    const sp = worldToScreen(star.x, star.y);
    const pulsePhase = (elapsed * 0.002) % 1.0;
    const alpha = Math.max(0, 1 - elapsed / 4000);
    if (alpha <= 0) return;

    ctx.save();
    ctx.strokeStyle = `rgba(56, 189, 248, ${alpha * 0.85})`;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = "#38bdf8";
    ctx.shadowBlur = 12;

    const r = 16 + pulsePhase * 18;
    ctx.beginPath();
    ctx.arc(sp.x, sp.y, r, 0, Math.PI * 2);
    ctx.stroke();

    ctx.restore();
  }

  function closeProbe() {
    probeActive = null;
    if (probeDrawer) probeDrawer.classList.remove("open", "sheet-expanded");
    if (modeBanner) modeBanner.style.display = "none";
    if (mobileSamplerBtn) mobileSamplerBtn.classList.remove("active");
    const vp = document.getElementById("cosmos-viewport");
    if (vp && (!hudEl || !hudEl.classList.contains("visible"))) {
      vp.classList.remove("has-active-hud");
    }
    currentMode = "explore";
    document.querySelectorAll(".cosmos-mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === "explore"));
    if (canvas) canvas.style.cursor = "grab";
  }

  // Public API
  window.CosmosEngine = {
    init: init,
    flyTo: flyToCoordinates,
    selectSector: selectSector,
    selectStarById: selectStarById,
    focusStarById: focusStarById,
    focusStarOnMap: focusStarOnMap,
    scrollFeedToCard: scrollFeedToCard,
    toggleWatchlist: toggleWatchlist,
    openMediaDetails: openMediaDetails,
    openMediaDetailsById: (starId) => {
      const star = galaxyData.stars ? galaxyData.stars.find((s) => s.id === starId) : null;
      if (star) openMediaDetails(star);
    },
    unpinHUD: unpinHUD,
    setMode: setMode,
    setViewMode: setViewMode,
    setMobileView: setMobileView,
    centerActiveRealm: centerActiveRealm,
    closeProbe: closeProbe,
    clearProbe: () => {
      probeActive = null;
    },
    refresh: () => loadGalaxyData(true)
  };

  // Auto-init on DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
