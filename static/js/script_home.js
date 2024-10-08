const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// Canvas settings
ctx.fillStyle = "black";
ctx.lineWidth = 1;

class Particle {
  constructor(effect) {
    this.effect = effect;
    this.reset();
  }

  reset() {
    this.x = Math.random() * this.effect.width;
    this.y = Math.random() * this.effect.height;
    this.speedX = 0;
    this.speedY = 0;
    this.speedModifier = Math.random() * 1.5 + 0.5;
    this.history = [{ x: this.x, y: this.y }];
    this.maxLength = Math.random() * 450 + 50;
    this.angle = 0;
    this.timer = this.maxLength * 2; // Lifespan timer
    this.colors = ["ghostwhite", "azure"];
    this.color = this.colors[Math.floor(Math.random() * this.colors.length)];
  }

  draw(context) {
    context.beginPath();
    context.moveTo(this.history[0].x, this.history[0].y);
    for (let i = 1; i < this.history.length; i++) {
      context.lineTo(this.history[i].x, this.history[i].y);
    }
    context.strokeStyle = this.color;
    context.stroke();
  }

  update() {
    this.timer--;
    if (this.timer > 0) {
      let x = Math.floor(this.x / this.effect.cellSize);
      let y = Math.floor(this.y / this.effect.cellSize);
      let index = y * this.effect.cols + x;
      this.angle = this.effect.flowField[index];

      this.speedX = Math.cos(this.angle);
      this.speedY = Math.sin(this.angle);
      this.x += this.speedX * this.speedModifier;
      this.y += this.speedY * this.speedModifier;

      this.history.push({ x: this.x, y: this.y });
      if (this.history.length > this.maxLength) {
        this.history.shift(); // Keep only the max number of points
      }
    } else if (this.history.length > 1) {
      this.history.shift(); // Shrink the trail when the timer ends
    } else {
      this.reset(); // Recycle particle by resetting it
    }
  }
}

class Effect {
  constructor(canvas) {
    this.canvas = canvas;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.particles = [];
    this.numberOfParticles = 750;
    this.cellSize = 20;
    this.cols = Math.floor(this.width / this.cellSize);
    this.rows = Math.floor(this.height / this.cellSize);
    this.flowField = [];
    this.curve = 1.5;
    this.zoom = 0.15;

    window.addEventListener("resize", (e) => {
      this.resize(e.target.innerWidth, e.target.innerHeight);
    });

    this.init();
  }

  init() {
    this.createFlowField();
    this.particles = [];
    for (let i = 0; i < this.numberOfParticles; i++) {
      this.particles.push(new Particle(this));
    }
  }

  createFlowField() {
    this.cols = Math.floor(this.width / this.cellSize);
    this.rows = Math.floor(this.height / this.cellSize);
    this.flowField = [];

    for (let y = 0; y < this.rows; y++) {
      for (let x = 0; x < this.cols; x++) {
        let angle =
          (Math.cos(x * this.zoom) + Math.sin(y * this.zoom)) * this.curve;
        this.flowField.push(angle);
      }
    }
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this.width = width;
    this.height = height;
    this.createFlowField();
    this.particles.forEach((particle) => particle.reset()); // Reset all particles on resize
  }

  render(context) {
    this.particles.forEach((particle) => {
      particle.update();
      particle.draw(context);
    });
  }
}

const effect = new Effect(canvas);

let isAnimating = true; // Track animation state

// Handle visibility changes
document.addEventListener("visibilitychange", function () {
  isAnimating = !document.hidden; // Pause animation if not visible
});

function animate() {
  if (!isAnimating) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear the canvas
  effect.render(ctx); // Render the particles
  requestAnimationFrame(animate); // Loop the animation
}

animate(); // Start the animation loop
