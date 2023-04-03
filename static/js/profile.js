const genres = {
  Action: 0,
  Adventure: 0,
  Animation: 0,
  Children: 0,
  Comedy: 0,
  Crime: 0,
  Documentary: 0,
  Drama: 0,
  Fantasy: 0,
  "Film-Noir": 0,
  Horror: 0,
  Musical: 0,
  Mystery: 0,
  Romance: 0,
  "Sci-Fi": 0,
  Thriller: 0,
  War: 0,
  Western: 0,
};

let jsondata;

async function getJson(url) {
  let response = await fetch(url);
  let data = await response.json();
  return data;
}

async function main() {
  jsondata = await getJson("/data");

  jsondata.forEach((item) => {
    if (genres[item.genre]) {
      genres[item.genre] += 1;
    } else {
      genres[item.genre] = genres[item.genre];
    }
  });
  console.log(jsondata);
  console.log(genres);
  const sortedDict = Object.entries(genres).sort((a, b) => a[1] - b[1]);
  const top4Values = sortedDict.slice(0, 4).map((item) => item[1]);
  console.log(top4Values);
}

main();
//LINE CHART
var lineChartOptions = {
  series: [
    {
      name: "High - 2013",
      data: [28, 29, 33, 36, 32, 32, 33],
    },
    {
      name: "Low - 2013",
      data: [12, 11, 14, 18, 17, 13, 13],
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
  colors: ["#77B6EA", "#00bfa5"],
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
    categories: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"],
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
      text: "Temperature",
      style: {
        color: "#9aa0ac",
      },
    },
    labels: {
      style: {
        colors: "#9aa0ac",
      },
    },
    min: 5,
    max: 40,
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
};

var lineChart = new ApexCharts(
  document.querySelector("#line-chart"),
  lineChartOptions
);
lineChart.render();

//BAR CHART
var barchartoptions = {
  series: [
    {
      name: "PRODUCT A",
      data: top4Values,
    },
    {
      name: "PRODUCT B",
      data: [13, 23, 20, 8, 13, 27],
    },
    {
      name: "PRODUCT C",
      data: [11, 17, 15, 15, 21, 14],
    },
    {
      name: "PRODUCT D",
      data: [21, 7, 25, 13, 22, 8],
    },
  ],
  chart: {
    type: "bar",
    height: 350,
    stacked: true,
    toolbar: {
      show: true,
    },
    zoom: {
      enabled: true,
    },
  },
  responsive: [
    {
      breakpoint: 480,
      options: {
        legend: {
          position: "bottom",
          offsetX: -10,
          offsetY: 0,
        },
      },
    },
  ],
  plotOptions: {
    bar: {
      horizontal: false,
      borderRadius: 10,
      dataLabels: {
        total: {
          enabled: true,
          style: {
            fontSize: "13px",
            fontWeight: 900,
            color: "#fff",
          },
        },
      },
    },
  },
  xaxis: {
    type: "datetime",
    categories: [
      "01/01/2011 GMT",
      "01/02/2011 GMT",
      "01/03/2011 GMT",
      "01/04/2011 GMT",
      "01/05/2011 GMT",
      "01/06/2011 GMT",
    ],
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
    position: "right",
    offsetY: 40,
    labels: {
      useSeriesColors: true,
    },
  },
  fill: {
    opacity: 1,
  },
};

var barchart = new ApexCharts(
  document.querySelector("#bar-chart"),
  barchartoptions
);
barchart.render();
