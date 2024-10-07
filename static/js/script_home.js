const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

//canvas settings
ctx.fillStyle = "black";
ctx.linewidth = 10;

class Particle {
  constructor(effect) {
    this.efffect = effect;
    this.x = Math.floor(Math.random() * this.efffect.width);
    this.y = Math.floor(Math.random() * this.efffect.height);
    this.speedX;
    this.speedY;
    this.speedModifier = Math.floor(Math.random() * 1.5 + 0.5);
    this.history = [{ x: this.x, y: this.y }];
    this.maxLength = Math.floor(Math.random() * 500 + 50);
    this.angle = 0;
    this.timer = this.maxLength * 2;
    this.colors = ["ghostwhite", "azure"];
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
      this.angle = this.efffect.flowField[index];

      this.speedX = Math.cos(this.angle);
      this.speedY = Math.sin(this.angle);
      this.x += this.speedX * this.speedModifier;
      this.y += this.speedY * this.speedModifier;

      this.history.push({ x: this.x, y: this.y });
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
    this.x = Math.floor(Math.random() * this.efffect.width);
    this.y = Math.floor(Math.random() * this.efffect.height);
    this.history = [{ x: this.x, y: this.y }];
    this.timer = this.maxLength * 2;
  }
}

class Effect {
  constructor(canvas) {
    this.canvas = canvas;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.particles = [];
    this.numberOfParticles = 800;
    this.cellSize = 20;
    this.cols;
    this.rows;
    this.flowField = [];
    this.curve = 1.5;
    this.zoom = 0.15;
    this.debug = true;
    this.init();

    window.addEventListener("resize", (e) => {
      this.resize(e.target.innerWidth, e.target.innerHeight);
    });
  }

  init() {
    // create flow field
    this.rows = Math.floor(this.height / this.cellSize);
    this.cols = Math.floor(this.width / this.cellSize);
    this.flowField = [];

    for (let y = 0; y < this.rows; y++) {
      for (let x = 0; x < this.cols; x++) {
        let angle =
          (Math.cos(x * this.zoom) + Math.sin(y * this.zoom)) * this.curve;
        this.flowField.push(angle);
      }
    }
    // create particles
    this.particles = [];
    for (let i = 0; i < this.numberOfParticles; i++) {
      this.particles.push(new Particle(this));
    }
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.init();
  }

  render(context) {
    this.particles.forEach((particle) => {
      // Check if the particle's head is in the visible area
      const isHeadVisible =
        particle.x >= 0 &&
        particle.x <= this.width &&
        particle.y >= 0 &&
        particle.y <= this.height;

      // Check if any part of the particle's trail is visible
      const isTrailVisible = particle.history.some(
        (pos) =>
          pos.x >= 0 &&
          pos.x <= this.width &&
          pos.y >= 0 &&
          pos.y <= this.height
      );

      // Only draw if either the head or trail is visible
      if (isHeadVisible || isTrailVisible) {
        particle.draw(context);
        particle.update();
      }
    });
  }
}

const effect = new Effect(canvas);

let isAnimating = true; // Variable to track animation state

// Event listener to handle visibility changes
document.addEventListener("visibilitychange", function () {
  isAnimating = !document.hidden; // Set isAnimating based on document visibility
});

function animate() {
  if (!isAnimating) return; // Skip animation if not visible
  ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear the canvas
  effect.render(ctx); // Render the animation
  requestAnimationFrame(animate); // Request the next frame
}

// Start the animation loop
animate();
