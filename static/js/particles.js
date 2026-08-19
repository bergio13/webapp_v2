const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

//canvas settings
ctx.fillStyle = "black";
ctx.linewidth = 1;

class Particle {
  constructor(effect) {
    this.efffect = effect;
    this.x = Math.floor(Math.random() * this.efffect.width);
    this.y = Math.floor(Math.random() * this.efffect.height);
    this.speedX = Math.random() * 5 - 2.5;
    this.speedY = Math.random() * 5 - 2.5;
  }
  draw(context) {
    context.fillRect(this.x, this.y, 5, 5);
  }
  update() {
    this.x += this.speedX;
    this.y += this.speedY;
  }
}

class Effect {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.particles = [];
    this.numberOfParticles = 100;
    this.init();
  }
  init() {
    // create particles
    for (let i = 0; i < this.numberOfParticles; i++) {
      this.particles.push(new Particle(this));
    }
  }
  render(context) {
    this.particles.forEach((particle) => {
      particle.draw(context);
      particle.update();
    });
  }
}

const effect = new Effect(canvas.width, canvas.height);

const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
let animationFrameId = null;
let isRunning = false;

function shouldAnimate() {
  return !document.hidden && !motionQuery.matches;
}

function renderStaticFrame() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  effect.render(ctx);
}

function animate() {
  if (!isRunning) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  effect.render(ctx);
  animationFrameId = requestAnimationFrame(animate);
}

function startAnimation() {
  if (!isRunning && shouldAnimate()) {
    isRunning = true;
    animationFrameId = requestAnimationFrame(animate);
  }
}

function stopAnimation() {
  isRunning = false;
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
}

function updateAnimationState() {
  if (shouldAnimate()) {
    startAnimation();
  } else {
    stopAnimation();
    if (motionQuery.matches && !document.hidden) {
      renderStaticFrame();
    }
  }
}

document.addEventListener("visibilitychange", updateAnimationState);

if (typeof motionQuery.addEventListener === "function") {
  motionQuery.addEventListener("change", updateAnimationState);
} else if (typeof motionQuery.addListener === "function") {
  motionQuery.addListener(updateAnimationState);
}

if (shouldAnimate()) {
  startAnimation();
} else if (!document.hidden) {
  renderStaticFrame();
}
