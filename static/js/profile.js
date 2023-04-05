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

  for (var i = 0; i < jsondata.length; ++i) {
    genres[jsondata[i].genre] += 1;
  }

  console.log(jsondata);
  console.log(genres);
  const top6 = Object.entries(genres)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);
  const top6Keys = top6.map(([n]) => n);
  const top6Values = top6.map(([, v]) => v);
  console.log(top6Keys);
  console.log(top6Values);

  //BAR CHART
  var barChartOptions = {
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
          position: "top", // top, center, bottom
        },
        colors: {
          ranges: [
            {
              from: 0,
              to: 5,
              color: "#00bfa5",
            },
            {
              from: 5,
              to: 10,
              color: "rgb(255, 0, 0)",
            },
            {
              from: 10,
              to: 20,
              color: "rgb(0, 255,0)",
            },
            {
              from: 20,
              to: 40,
              color: "rgb(0, 0, 255)",
            },
          ],
          backgroundBarColors: [],
          backgroundBarOpacity: 1,
          backgroundBarRadius: 0,
        },
      },
    },
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
      crosshairs: {
        fill: {
          type: "gradient",
          gradient: {
            colorFrom: "indigo",
            colorTo: "yellow",
            stops: [0, 100],
            opacityFrom: 0.2,
            opacityTo: 0.4,
          },
        },
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
  };

  var barChart = new ApexCharts(
    document.querySelector("#bar-chart"),
    barChartOptions
  );
  barChart.render();
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
/*var barchartoptions = {
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
barchart.render(); */
