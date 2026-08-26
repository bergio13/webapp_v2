const canvas = document.getElementById("canvas");
if (canvas) {
  const ctx = canvas.getContext("2d");
  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  const colors = ["#3d5a6e", "#4a6d7c", "#2d4654", "#5a7d8a"];

  class Particle {
    constructor(effect) {
      this.effect = effect;
      this.reset();
    }

    reset() {
      this.x = Math.random() * this.effect.width;
      this.y = Math.random() * this.effect.height;
      this.speedModifier = Math.random() * 1.5 + 0.5;
      this.history = [{ x: this.x, y: this.y }];
      this.maxLength = Math.floor(Math.random() * 200 + 100); // 100-300 points for long sweeping flow lines
      this.timer = this.maxLength * 2;
      this.colorIndex = Math.floor(Math.random() * colors.length);
    }

    update() {
      this.timer--;
      if (this.timer > 0) {
        const xCell = Math.floor(this.x / this.effect.cellSize);
        const yCell = Math.floor(this.y / this.effect.cellSize);
        const index = yCell * this.effect.cols + xCell;

        let angle = 0;
        if (index >= 0 && index < this.effect.flowField.length) {
          angle = this.effect.flowField[index];
        }

        this.x += Math.cos(angle) * this.speedModifier;
        this.y += Math.sin(angle) * this.speedModifier;

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
  }

  class Effect {
    constructor(canvas) {
      this.canvas = canvas;
      this.width = width;
      this.height = height;
      this.numberOfParticles = 500;
      this.cellSize = 20;
      this.cols = Math.floor(this.width / this.cellSize);
      this.rows = Math.floor(this.height / this.cellSize);
      this.flowField = [];
      this.curve = 1.5;
      this.zoom = 0.15;
      this.particles = [];

      let resizeTimeout;
      window.addEventListener("resize", () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
          this.resize(window.innerWidth, window.innerHeight);
        }, 150);
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
      this.flowField = new Float32Array(this.cols * this.rows);

      for (let y = 0; y < this.rows; y++) {
        for (let x = 0; x < this.cols; x++) {
          const angle =
            (Math.cos(x * this.zoom) + Math.sin(y * this.zoom)) * this.curve;
          this.flowField[y * this.cols + x] = angle;
        }
      }
    }

    resize(w, h) {
      this.width = width = this.canvas.width = w;
      this.height = height = this.canvas.height = h;
      this.createFlowField();
      this.particles.forEach((p) => p.reset());
    }

    render(context) {
      context.clearRect(0, 0, this.width, this.height);
      context.lineWidth = 1;

      // Group paths by color: executes only 4 stroke calls per frame total
      for (let c = 0; c < colors.length; c++) {
        context.beginPath();
        context.strokeStyle = colors[c];

        for (let i = 0; i < this.particles.length; i++) {
          const p = this.particles[i];
          if (p.colorIndex === c && p.history.length > 1) {
            context.moveTo(p.history[0].x, p.history[0].y);
            for (let j = 1; j < p.history.length; j++) {
              context.lineTo(p.history[j].x, p.history[j].y);
            }
          }
          if (c === 0) {
            p.update();
          }
        }
        context.stroke();
      }
    }
  }

  const effect = new Effect(canvas);

  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let animationFrameId = null;
  let isRunning = false;
  let isIntersecting = true;

  function shouldAnimate() {
    return !document.hidden && !motionQuery.matches && isIntersecting;
  }

  function renderStaticFrame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    effect.render(ctx);
  }

  function animate() {
    if (!isRunning) return;
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
      if (motionQuery.matches && !document.hidden && isIntersecting) {
        renderStaticFrame();
      }
    }
  }

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        isIntersecting = entry.isIntersecting;
        updateAnimationState();
      });
    }, { threshold: 0.05 });
    observer.observe(canvas);
  }

  document.addEventListener("visibilitychange", updateAnimationState);

  if (typeof motionQuery.addEventListener === "function") {
    motionQuery.addEventListener("change", updateAnimationState);
  } else if (typeof motionQuery.addListener === "function") {
    motionQuery.addListener(updateAnimationState);
  }

  if (shouldAnimate()) {
    startAnimation();
  } else if (!document.hidden && isIntersecting) {
    renderStaticFrame();
  }
}
