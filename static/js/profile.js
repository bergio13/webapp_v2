const genres = {
  Action: 0,
  Adventure: 0,
  Animation: 0,
  Children: 0,
  Comedy: 0,
  Crime: 0,
  Documentary: 0,
  Drama: 0,
  Family: 0,
  Fantasy: 0,
  "Film-Noir": 0,
  Kids: 0,
  History: 0,
  Horror: 0,
  Musical: 0,
  Mystery: 0,
  News: 0,
  Reality: 0,
  Romance: 0,
  "Sci-Fi": 0,
  Soap: 0,
  Talk: 0,
  "TV Movie": 0,
  Thriller: 0,
  War: 0,
  Politics: 0,
  Western: 0,
};

const genreMappings = {
  "Action & Adventure": ["Action", "Adventure"],
  "Sci-Fi & Fantasy": ["Sci-Fi", "Fantasy"],
  "War & Politics": ["War", "Politics"],
};

const MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const IS_COMPACT_VIEWPORT = window.matchMedia("(max-width: 600px)").matches;

function chartHeight(desktopHeight, mobileHeight = 260) {
  return IS_COMPACT_VIEWPORT ? mobileHeight : desktopHeight;
}

let jsondata;

function toNumeric(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isTruthyFlag(value) {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value === 1;
  }
  if (typeof value === "string") {
    const lowered = value.trim().toLowerCase();
    return lowered === "1" || lowered === "true" || lowered === "yes";
  }
  return false;
}

function safeGenres(rawGenre) {
  if (!rawGenre || typeof rawGenre !== "string") {
    return [];
  }
  return rawGenre
    .split(",")
    .map((g) => g.trim())
    .filter(Boolean);
}

async function getJson(url) {
  const response = await fetch(url);
  return response.json();
}

function renderChart(selector, options) {
  const container = document.querySelector(selector);
  if (!container) {
    return;
  }
  new ApexCharts(container, options).render();
}

function extractAdvancedStats(movies) {
  const uniqueDirectors = new Set();
  const uniqueGenres = new Set();
  const tvByMonth = Array(12).fill(0);
  const movieByMonth = Array(12).fill(0);

  let rewatchCount = 0;
  let cinemaCount = 0;

  for (const movie of movies) {
    const director = (movie.director || "").toString().trim();
    if (director) {
      uniqueDirectors.add(director);
    }

    for (const genre of safeGenres(movie.genre)) {
      if (genreMappings[genre]) {
        for (const mappedGenre of genreMappings[genre]) {
          uniqueGenres.add(mappedGenre);
        }
      } else {
        uniqueGenres.add(genre);
      }
    }

    if (isTruthyFlag(movie.rewatch)) {
      rewatchCount += 1;
    }
    if (isTruthyFlag(movie.cinema)) {
      cinemaCount += 1;
    }

    const watchedDate = new Date(movie.v_date);
    if (!Number.isNaN(watchedDate.getTime())) {
      const monthIndex = watchedDate.getMonth();
      if (isTruthyFlag(movie.tv_show)) {
        tvByMonth[monthIndex] += 1;
      } else {
        movieByMonth[monthIndex] += 1;
      }
    }
  }

  return {
    uniqueDirectors: uniqueDirectors.size,
    uniqueGenres: uniqueGenres.size,
    rewatchCount,
    cinemaCount,
    tvByMonth,
    movieByMonth,
  };
}

function buildLastThreeYearsSeries(movies) {
  const currentYear = new Date().getFullYear();
  const targetYears = [currentYear - 2, currentYear - 1, currentYear];
  const countsByYear = Object.fromEntries(
    targetYears.map((year) => [year, Array(12).fill(0)]),
  );

  for (const movie of movies) {
    const watchedDate = new Date(movie.v_date);
    if (Number.isNaN(watchedDate.getTime())) {
      continue;
    }

    const year = watchedDate.getFullYear();
    const month = watchedDate.getMonth();
    if (countsByYear[year]) {
      countsByYear[year][month] += 1;
    }
  }

  return targetYears.map((year) => ({
    name: String(year),
    data: countsByYear[year],
  }));
}

function renderTopGenresBar(top6Keys, top6Values) {
  const maxVal = Math.max(...top6Values, 1);
  renderChart("#bar-chart", {
    series: [
      {
        name: "Watched Titles",
        data: top6Values,
      },
    ],
    chart: {
      height: chartHeight(240, 220),
      type: "bar",
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 6,
        barHeight: "58%",
        dataLabels: {
          position: "top",
        },
      },
    },
    colors: ["#a78bfa"],
    dataLabels: {
      enabled: true,
      textAnchor: "start",
      offsetX: 14,
      style: {
        fontSize: "11px",
        fontFamily: "monospace",
        fontWeight: 700,
        colors: ["#cbd5e1"],
      },
      formatter: (val) => `${val}`,
    },
    xaxis: {
      categories: top6Keys,
      max: Math.ceil(maxVal * 1.15) + 2,
      labels: {
        style: {
          colors: "#64748b",
          fontFamily: "monospace",
          fontSize: "10px",
        },
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
          fontWeight: 600,
        },
      },
    },
    grid: {
      borderColor: "rgba(126, 181, 196, 0.08)",
      strokeDashArray: 4,
      yaxis: {
        lines: {
          show: false,
        },
      },
      xaxis: {
        lines: {
          show: true,
        },
      },
    },
    tooltip: {
      theme: "dark",
      y: {
        formatter: (val) => `${val} films`,
      },
    },
  });
}

function renderMonthlyMoviesLine(monthValues) {
  renderChart("#line-chart", {
    series: [
      {
        name: "Monthly Watched Titles",
        data: monthValues,
      },
    ],
    chart: {
      height: chartHeight(270, 220),
      type: "area",
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    colors: ["#fcd34d"],
    fill: {
      type: "gradient",
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.35,
        opacityTo: 0.02,
        stops: [0, 95, 100],
      },
    },
    dataLabels: {
      enabled: false,
    },
    stroke: {
      curve: "smooth",
      width: 2.5,
      colors: ["#fcd34d"],
    },
    markers: {
      size: 3,
      colors: ["#fcd34d"],
      strokeColors: "#0f172a",
      strokeWidth: 2,
      hover: {
        size: 6,
      },
    },
    grid: {
      borderColor: "rgba(126, 181, 196, 0.1)",
      strokeDashArray: 4,
      xaxis: {
        lines: {
          show: false,
        },
      },
      yaxis: {
        lines: {
          show: true,
        },
      },
    },
    xaxis: {
      categories: MONTH_LABELS,
      labels: {
        rotate: IS_COMPACT_VIEWPORT ? -45 : 0,
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
    },
    yaxis: {
      tickAmount: 4,
      labels: {
        style: {
          colors: "#64748b",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
      min: 0,
    },
    tooltip: {
      theme: "dark",
      y: {
        formatter: (val) => `${val} titles`,
      },
    },
  });
}

function renderGenresRadar(top10Keys, top10Values) {
  renderChart("#radar-chart", {
    series: [
      {
        name: "Watched Titles",
        data: top10Values,
      },
    ],
    chart: {
      height: chartHeight(280, 205),
      type: "radar",
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    colors: ["#38bdf8"],
    markers: {
      size: 3,
      colors: ["#38bdf8"],
      strokeColors: "#0f172a",
      strokeWidth: 2,
    },
    fill: {
      opacity: 0.25,
    },
    stroke: {
      width: 2,
      colors: ["#38bdf8"],
    },
    xaxis: {
      categories: top10Keys,
      labels: {
        show: true,
        style: {
          colors: Array(top10Keys.length).fill("#94a3b8"),
          fontSize: IS_COMPACT_VIEWPORT ? "9px" : "11px",
          fontFamily: "monospace",
          fontWeight: 600,
        },
      },
    },
    yaxis: {
      show: false,
      labels: {
        show: false,
      },
      tickAmount: 4,
    },
    plotOptions: {
      radar: {
        size: IS_COMPACT_VIEWPORT ? 65 : 100,
        polygons: {
          strokeColors: "rgba(126, 181, 196, 0.2)",
          connectorColors: "rgba(126, 181, 196, 0.2)",
          fill: {
            colors: ["transparent", "rgba(126, 181, 196, 0.02)"],
          },
        },
      },
    },
    tooltip: {
      theme: "dark",
      y: {
        formatter: (val) => `${val} films`,
      },
    },
  });
}

function renderTvVsMoviesChart(stats) {
  renderChart("#tv-vs-movies-chart", {
    series: [
      {
        name: "Movies",
        data: stats.movieByMonth,
      },
      {
        name: "TV Shows",
        data: stats.tvByMonth,
      },
    ],
    chart: {
      type: "bar",
      height: chartHeight(270, 220),
      stacked: true,
      toolbar: {
        show: false,
      },
    },
    plotOptions: {
      bar: {
        borderRadius: 6,
      },
    },
    dataLabels: {
      enabled: false,
    },
    stroke: {
      width: 1,
      colors: ["#1d2634"],
    },
    colors: ["#b78efd", "#22d3ee"],
    xaxis: {
      categories: MONTH_LABELS,
      labels: {
        rotate: IS_COMPACT_VIEWPORT ? -45 : 0,
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#64748b",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
    },
    grid: {
      borderColor: "rgba(126, 181, 196, 0.08)",
      strokeDashArray: 4,
      yaxis: {
        lines: {
          show: true,
        },
      },
      xaxis: {
        lines: {
          show: false,
        },
      },
    },
    legend: {
      position: "top",
      horizontalAlign: "right",
      offsetY: -5,
      labels: {
        colors: "#cbd5e1",
      },
      fontFamily: "monospace",
      fontSize: "11px",
    },
    tooltip: {
      theme: "dark",
    },
  });
}

function renderDiversityChart(stats) {
  const maxVal = Math.max(stats.uniqueDirectors, stats.uniqueGenres, 1);
  renderChart("#diversity-chart", {
    series: [
      {
        name: "Count",
        data: [stats.uniqueDirectors, stats.uniqueGenres],
      },
    ],
    chart: {
      type: "bar",
      height: 125,
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 5,
        barHeight: "48%",
        distributed: true,
        dataLabels: {
          position: "top",
        },
      },
    },
    colors: ["#38bdf8", "#4ade80"],
    dataLabels: {
      enabled: true,
      textAnchor: "start",
      offsetX: 14,
      style: {
        fontSize: "11px",
        fontFamily: "monospace",
        fontWeight: 700,
        colors: ["#cbd5e1"],
      },
      formatter: (val) => `${val}`,
    },
    xaxis: {
      categories: ["Unique Directors", "Unique Genres"],
      max: Math.ceil(maxVal * 1.15) + 2,
      labels: {
        show: false,
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
          fontWeight: 600,
        },
      },
    },
    grid: {
      show: false,
    },
    legend: {
      show: false,
    },
    tooltip: {
      theme: "dark",
      y: {
        formatter: (val) => `${val} total`,
      },
    },
  });
}

function renderHabitCountsChart(stats) {
  const maxVal = Math.max(stats.cinemaCount, stats.rewatchCount, 1);
  renderChart("#habit-counts-chart", {
    series: [
      {
        name: "Count",
        data: [stats.cinemaCount, stats.rewatchCount],
      },
    ],
    chart: {
      type: "bar",
      height: 125,
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 5,
        barHeight: "48%",
        distributed: true,
        dataLabels: {
          position: "top",
        },
      },
    },
    colors: ["#fcd34d", "#a78bfa"],
    dataLabels: {
      enabled: true,
      textAnchor: "start",
      offsetX: 14,
      style: {
        fontSize: "11px",
        fontFamily: "monospace",
        fontWeight: 700,
        colors: ["#cbd5e1"],
      },
      formatter: (val) => `${val}`,
    },
    xaxis: {
      categories: ["Cinema Visits", "Rewatch Count"],
      max: Math.ceil(maxVal * 1.15) + 2,
      labels: {
        show: false,
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
          fontWeight: 600,
        },
      },
    },
    grid: {
      show: false,
    },
    legend: {
      show: false,
    },
    tooltip: {
      theme: "dark",
      y: {
        formatter: (val) => `${val} times`,
      },
    },
  });
}

function renderLastThreeYearsMonthlyChart(yearlySeries) {
  renderChart("#yearly-monthly-line-chart", {
    series: yearlySeries,
    chart: {
      height: chartHeight(270, 220),
      type: "line",
      toolbar: {
        show: false,
      },
      parentHeightOffset: 0,
    },
    stroke: {
      curve: "smooth",
      width: [3, 2.5, 2],
    },
    markers: {
      size: 3,
      strokeColors: "#0f172a",
      strokeWidth: 2,
      hover: {
        size: 6,
      },
    },
    colors: ["#38bdf8", "#fcd34d", "#a78bfa"],
    grid: {
      borderColor: "rgba(126, 181, 196, 0.1)",
      strokeDashArray: 4,
      xaxis: {
        lines: {
          show: false,
        },
      },
      yaxis: {
        lines: {
          show: true,
        },
      },
    },
    xaxis: {
      categories: MONTH_LABELS,
      labels: {
        rotate: IS_COMPACT_VIEWPORT ? -45 : 0,
        style: {
          colors: "#94a3b8",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
    },
    yaxis: {
      min: 0,
      tickAmount: 4,
      labels: {
        style: {
          colors: "#64748b",
          fontFamily: "monospace",
          fontSize: "11px",
        },
      },
    },
    legend: {
      position: "top",
      horizontalAlign: "right",
      offsetY: -5,
      labels: {
        colors: "#cbd5e1",
        useSeriesColors: false,
      },
      fontFamily: "monospace",
      fontSize: "11px",
      markers: {
        radius: 12,
      },
    },
    tooltip: {
      theme: "dark",
      shared: true,
      intersect: false,
      y: {
        formatter: (val) => `${val ?? 0} titles`,
      },
    },
  });
}

async function main() {
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  let username = "";
  if (pathParts[0] === "profile" && pathParts.length > 1) {
    username = decodeURIComponent(pathParts[1]);
  } else {
    username = document.getElementById("profile-username")?.textContent?.trim() || 
               document.getElementById("username")?.textContent?.trim() || "";
  }
  const endpoint = username ? `/data/${encodeURIComponent(username)}` : "/data";
  jsondata = await getJson(endpoint);

  const genreCounts = { ...genres };
  const monthCounts = Array(12).fill(0);

  for (const movie of jsondata) {
    for (const genre of safeGenres(movie.genre)) {
      if (genreMappings[genre]) {
        for (const mappedGenre of genreMappings[genre]) {
          if (genreCounts[mappedGenre] !== undefined) {
            genreCounts[mappedGenre] += 1;
          }
        }
      } else if (genreCounts[genre] !== undefined) {
        genreCounts[genre] += 1;
      }
    }

    const date = new Date(movie.v_date);
    if (!Number.isNaN(date.getTime())) {
      monthCounts[date.getMonth()] += 1;
    }
  }

  const top6 = Object.entries(genreCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);
  const top6Keys = top6.map(([name]) => name);
  const top6Values = top6.map(([, value]) => value);

  const top10 = Object.entries(genreCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10);
  const top10Keys = top10.map(([name]) => name);
  const top10Values = top10.map(([, value]) => value);

  let genomeChartsRendered = false;
  let habitsChartsRendered = false;

  function renderGenomeCharts() {
    if (genomeChartsRendered) {
      window.dispatchEvent(new Event("resize"));
      return;
    }
    genomeChartsRendered = true;
    requestAnimationFrame(() => {
      const advancedStats = extractAdvancedStats(jsondata);
      renderGenresRadar(top10Keys, top10Values);
      renderTopGenresBar(top6Keys, top6Values);
      renderDiversityChart(advancedStats);
      setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    });
  }

  function renderHabitsCharts() {
    if (habitsChartsRendered) {
      window.dispatchEvent(new Event("resize"));
      return;
    }
    habitsChartsRendered = true;
    requestAnimationFrame(() => {
      const advancedStats = extractAdvancedStats(jsondata);
      renderHabitCountsChart(advancedStats);
      renderTvVsMoviesChart(advancedStats);
      renderMonthlyMoviesLine(monthCounts);
      renderLastThreeYearsMonthlyChart(buildLastThreeYearsSeries(jsondata));
      setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    });
  }

  // ───────── Tab Switcher Logic ─────────
  const tabBtns = document.querySelectorAll(".profile-tab-btn-min, .profile-tab-btn");
  const tabPanes = document.querySelectorAll(".profile-tab-pane");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");

      tabBtns.forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-selected", "false");
        const openBr = b.querySelector(".tab-open");
        const closeBr = b.querySelector(".tab-close");
        if (openBr) openBr.textContent = "[";
        if (closeBr) closeBr.textContent = "]";
      });
      tabPanes.forEach((p) => {
        p.classList.remove("is-active");
        p.style.display = "none";
      });

      btn.classList.add("is-active");
      btn.setAttribute("aria-selected", "true");
      const activeOpen = btn.querySelector(".tab-open");
      const activeClose = btn.querySelector(".tab-close");
      if (activeOpen) activeOpen.textContent = ">";
      if (activeClose) activeClose.textContent = "<";

      const targetPane = document.getElementById(targetTabId);
      if (targetPane) {
        targetPane.classList.add("is-active");
        targetPane.style.display = "block";

        // Lazy-render chart groups on demand for active tab
        if (targetTabId === "tab-genome") {
          renderGenomeCharts();
        } else if (targetTabId === "tab-habits") {
          renderHabitsCharts();
        }
        window.dispatchEvent(new Event("resize"));
      }
    });
  });

  // ───────── Share / Copy Link Logic ─────────
  function setupCopyButton(btnId) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        const originalText = btn.textContent;
        btn.textContent = "[ ✓ LINK COPIED! ]";
        btn.classList.add("btn-active");
        setTimeout(() => {
          btn.textContent = originalText;
          btn.classList.remove("btn-active");
        }, 2200);
      } catch (err) {
        alert("Profile link copied: " + window.location.href);
      }
    });
  }

  setupCopyButton("btn-share-profile");
  setupCopyButton("btn-copy-profile-link");

  // Check if initially active tab requires charts
  const initialActiveTab = document.querySelector(".profile-tab-pane.is-active");
  if (initialActiveTab) {
    if (initialActiveTab.id === "tab-genome") renderGenomeCharts();
    else if (initialActiveTab.id === "tab-habits") renderHabitsCharts();
  }
}

main();
