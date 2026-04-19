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
  renderChart("#bar-chart", {
    series: [
      {
        name: "Genres",
        data: top6Values,
      },
    ],
    chart: {
      height: 350,
      type: "bar",
    },
    plotOptions: {
      bar: {
        borderRadius: 10,
        dataLabels: {
          position: "top",
        },
      },
    },
    colors: ["#7217D6"],
    dataLabels: {
      enabled: true,
      offsetY: -20,
      style: {
        fontSize: "12px",
        colors: ["#fff"],
      },
    },
    xaxis: {
      categories: top6Keys,
      position: "top",
      labels: {
        style: {
          colors: "#fff",
        },
      },
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
      tooltip: {
        enabled: true,
      },
    },
    yaxis: {
      axisBorder: {
        show: false,
      },
      axisTicks: {
        show: false,
      },
      labels: {
        show: false,
      },
    },
    title: {
      text: "Your 6 Most Watched Genres",
      floating: true,
      offsetY: 330,
      align: "center",
      style: {
        color: "#fff",
      },
    },
  });
}

function renderMonthlyMoviesLine(monthValues) {
  renderChart("#line-chart", {
    series: [
      {
        name: "Monthly Watched Movies",
        data: monthValues,
      },
    ],
    chart: {
      height: 350,
      type: "line",
      dropShadow: {
        enabled: true,
        color: "#000",
        top: 18,
        left: 7,
        blur: 10,
        opacity: 0.2,
      },
      toolbar: {
        show: false,
      },
    },
    colors: ["#C47B16"],
    dataLabels: {
      enabled: true,
    },
    stroke: {
      curve: "smooth",
    },
    markers: {
      size: 1,
    },
    xaxis: {
      categories: MONTH_LABELS,
      title: {
        text: "Month",
        style: {
          color: "#9aa0ac",
        },
      },
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    yaxis: {
      title: {
        text: "Number of Movies",
        style: {
          color: "#9aa0ac",
        },
      },
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
      min: 0,
      max: Math.max(...monthValues, 0) + 5,
    },
    legend: {
      position: "top",
      horizontalAlign: "right",
      floating: true,
      offsetY: -25,
      offsetX: -5,
      labels: {
        useSeriesColors: true,
      },
    },
  });
}

function renderGenresRadar(top10Keys, top10Values) {
  renderChart("#radar-chart", {
    series: [
      {
        name: "Genres",
        data: top10Values,
      },
    ],
    chart: {
      height: 350,
      type: "radar",
    },
    colors: ["#FF5733"],
    xaxis: {
      categories: top10Keys,
    },
    yaxis: {
      tickAmount: 5,
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
      height: 320,
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
    colors: ["#7c3aed", "#14b8a6"],
    xaxis: {
      categories: MONTH_LABELS,
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    legend: {
      labels: {
        colors: "#9aa0ac",
      },
    },
    tooltip: {
      theme: "dark",
    },
  });
}

function renderDiversityChart(stats) {
  renderChart("#diversity-chart", {
    series: [
      {
        name: "Count",
        data: [stats.uniqueDirectors, stats.uniqueGenres],
      },
    ],
    chart: {
      type: "bar",
      height: 320,
      toolbar: {
        show: false,
      },
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 6,
      },
    },
    dataLabels: {
      enabled: true,
      style: {
        colors: ["#ffffff"],
      },
    },
    colors: ["#38bdf8"],
    xaxis: {
      categories: ["Unique Directors", "Unique Genres"],
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    tooltip: {
      theme: "dark",
    },
  });
}

function renderHabitCountsChart(stats) {
  renderChart("#habit-counts-chart", {
    series: [
      {
        name: "Count",
        data: [stats.rewatchCount, stats.cinemaCount],
      },
    ],
    chart: {
      type: "bar",
      height: 320,
      toolbar: {
        show: false,
      },
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 6,
      },
    },
    dataLabels: {
      enabled: true,
      style: {
        colors: ["#ffffff"],
      },
    },
    colors: ["#f59e0b"],
    xaxis: {
      categories: ["Rewatch Count", "Cinema Visits"],
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    tooltip: {
      theme: "dark",
    },
  });
}

function renderLastThreeYearsMonthlyChart(yearlySeries) {
  const maxValue = Math.max(
    0,
    ...yearlySeries.flatMap((series) => series.data),
  );
  renderChart("#yearly-monthly-line-chart", {
    series: yearlySeries,
    chart: {
      height: 320,
      type: "line",
      toolbar: {
        show: false,
      },
    },
    stroke: {
      curve: "smooth",
      width: 3,
    },
    markers: {
      size: 3,
    },
    colors: ["#38bdf8", "#f59e0b", "#22c55e"],
    xaxis: {
      categories: MONTH_LABELS,
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
    },
    yaxis: {
      min: 0,
      max: maxValue + 2,
      labels: {
        style: {
          colors: "#9aa0ac",
        },
      },
      title: {
        text: "Watched titles",
        style: {
          color: "#9aa0ac",
        },
      },
    },
    legend: {
      labels: {
        colors: "#9aa0ac",
      },
    },
    tooltip: {
      theme: "dark",
    },
  });
}

async function main() {
  const username = document.getElementById("username")?.textContent?.trim();
  const endpoint = username ? `/data/${username}` : "/data";
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

  renderTopGenresBar(top6Keys, top6Values);
  renderMonthlyMoviesLine(monthCounts);
  renderGenresRadar(top10Keys, top10Values);

  const advancedStats = extractAdvancedStats(jsondata);
  renderTvVsMoviesChart(advancedStats);
  renderDiversityChart(advancedStats);
  renderHabitCountsChart(advancedStats);
  renderLastThreeYearsMonthlyChart(buildLastThreeYearsSeries(jsondata));
}

main();
