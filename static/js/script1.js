const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

//canvas settings
ctx.fillStyle = "white";
ctx.linewidth = 1;

class Particle {
  constructor(effect) {
    this.efffect = effect;
    this.x = Math.floor(Math.random() * this.efffect.width);
    this.y = Math.floor(Math.random() * this.efffect.height);
    this.speedX;
    this.speedY;
    this.speedModifier = Math.floor(Math.random() * 4 + 1);
    this.history = [{ x: this.x, y: this.y }];
    this.maxLength = Math.floor(Math.random() * 100 + 10);
    this.angle = 0;
    this.newAngle = 0;
    this.angleCorrector = Math.random() * 0.5 + 0.01;
    this.timer = this.maxLength * 2;
    this.colors = ["#23232e", "#6649b8", "rgb(255, 0, 204)"];
    this.color = this.colors[Math.floor(Math.random() * this.colors.length)];
  }
  draw(context) {
    context.beginPath();
    context.moveTo(this.history[0].x, this.history[0].y);
    for (let i = 0; i < this.history.length; i++) {
      context.lineTo(this.history[i].x, this.history[i].y);
    }
    context.strokeStyle = this.color;
    context.stroke();
  }
  update() {
    this.timer--;
    if (this.timer >= 1) {
      let x = Math.floor(this.x / this.efffect.cellSize);
      let y = Math.floor(this.y / this.efffect.cellSize);
      let index = y * this.efffect.cols + x;

      if (this.efffect.flowField[index]) {
        this.newAngle = this.efffect.flowField[index].colorAngle;
        if (this.angle > this.newAngle) {
          this.angle -= this.angleCorrector;
        } else if (this.angle < this.newAngle) {
          this.angle += this.angleCorrector;
        } else {
          this.angle = this.newAngle;
        }
      }

      //update particle position
      this.speedX = Math.cos(this.angle);
      this.speedY = Math.sin(this.angle);
      // move particle
      this.x += this.speedX * this.speedModifier;
      this.y += this.speedY * this.speedModifier;

      //add current particle position to history
      this.history.push({ x: this.x, y: this.y });
      // if longer than maxLength, remove oldest position
      if (this.history.length > this.maxLength) {
        this.history.shift();
      }
    } else if (this.history.length > 1) {
      this.history.shift();
    } else {
      this.reset();
    }
  }
  reset() {
    let attempts = 0;
    let resetSuccess = false;

    while (attempts < 50 && !resetSuccess) {
      attempts++;
      let testIndex = Math.floor(Math.random(this.efffect.flowField.length));
      if (this.efffect.flowField[testIndex].alpha > 0) {
        this.x = this.efffect.flowField[testIndex].x;
        this.y = this.efffect.flowField[testIndex].y;
        this.history = [{ x: this.x, y: this.y }];
        this.timer = this.maxLength * 2;
        resetSuccess = true;
      }
    }
    if (!resetSuccess) {
      this.x = Math.floor(Math.random() * this.efffect.width);
      this.y = Math.floor(Math.random() * this.efffect.height);
      this.history = [{ x: this.x, y: this.y }];
      this.timer = this.maxLength * 2;
    }
  }
}

class Effect {
  constructor(canvas, ctx) {
    this.canvas = canvas;
    this.context = ctx;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.particles = [];
    this.numberOfParticles = 2000;
    this.cellSize = 5;
    this.cols;
    this.rows;
    this.flowField = [];
    this.curve = 5;
    this.zoom = 0.18;
    this.debug = true;
    this.init();

    window.addEventListener("keydown", (e) => {
      if (e.key === "d") {
        this.debug = !this.debug;
      }
    });

    window.addEventListener("resize", (e) => {
      //this.resize(e.target.innerWidth, e.target.innerHeight);
    });
  }

  drawText() {
    this.context.font = "200px Impact";
    this.context.textAlign = "center";
    this.context.textBaseline = "middle";

    const gradient1 = this.context.createLinearGradient(
      0,
      0,
      this.width,
      this.height
    );
    gradient1.addColorStop(0.2, "yellow");
    gradient1.addColorStop(0.4, "black");
    gradient1.addColorStop(0.6, "purple");
    gradient1.addColorStop(0.8, "white");

    const gradient2 = this.context.createRadialGradient(
      this.width * 0.5,
      this.height * 0.5,
      5,
      this.width * 0.5,
      this.height * 0.5,
      this.width * 0.4
    );
    gradient2.addColorStop(0.2, "rgb(0, 0, 255)");
    gradient2.addColorStop(0.4, "rgb(200, 255, 0");
    gradient2.addColorStop(0.6, "rgb(0, 0, 255)");
    gradient2.addColorStop(0.8, "rgb(0, 0, 0)");

    this.context.fillStyle = gradient1;
    this.context.fillText("Kineto", this.width * 0.5, this.height * 0.5);
  }

  init() {
    // create flow field
    this.rows = Math.floor(this.height / this.cellSize);
    this.cols = Math.floor(this.width / this.cellSize);
    this.flowField = [];

    //draw text
    this.drawText();

    // get pixel data
    const pixels = this.context.getImageData(
      0,
      0,
      this.width,
      this.height
    ).data;

    console.log(pixels);
    for (let y = 0; y < this.height; y += this.cellSize) {
      for (let x = 0; x < this.width; x += this.cellSize) {
        const index = (y * this.width + x) * 4;
        const red = pixels[index];
        const green = pixels[index + 1];
        const blue = pixels[index + 2];
        const alpha = pixels[index + 3];
        const grayScale = (red + green + blue) / 3;
        const colorAngle = ((grayScale / 255) * 6.28).toFixed(2);
        this.flowField.push({
          x: x,
          y: y,
          alpha: alpha,
          colorAngle: colorAngle,
        });
      }
    }

    // create particles
    this.particles = [];
    for (let i = 0; i < this.numberOfParticles; i++) {
      this.particles.push(new Particle(this));
    }
    this.particles.forEach((particle) => particle.reset());
  }
  drawGrid() {
    this.context.save();
    this.context.strokeStyle = "#23232e";
    this.context.lineWidth = 0.3;
    for (let c = 0; c < this.cols; c++) {
      this.context.beginPath();
      this.context.moveTo(c * this.cellSize, 0);
      this.context.lineTo(c * this.cellSize, this.height);
      this.context.stroke();
    }
    for (let r = 0; r < this.rows; r++) {
      this.context.beginPath();
      this.context.moveTo(0, r * this.cellSize);
      this.context.lineTo(this.width, r * this.cellSize);
      this.context.stroke();
    }
    this.context.restore();
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.init();
  }

  render() {
    if (this.debug) {
      this.drawGrid();
      this.drawText();
    }
    this.particles.forEach((particle) => {
      particle.draw(this.context);
      particle.update();
    });
  }
}

const effect = new Effect(canvas, ctx);
effect.render(ctx);

function animate() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  effect.render();
  requestAnimationFrame(animate);
}

animate();
