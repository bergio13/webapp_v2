const canvas = document.getElementById("canvas");
const ctx = canvas ? canvas.getContext("2d") : null;

if (canvas && ctx) {
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
      this.maxLength = Math.floor(Math.random() * 80 + 10);
      this.angle = 0;
      this.timer = this.maxLength * 2;
      /*this.colors = [
      "rgb(138, 43, 226)",
      "#6649b8",
      "rgb(255, 0, 204)",
      "indigo",
      "rgb(153,50,204)",
      "#7d05f5",
    ];*/
      this.colors = [
        "#4FD1C5",
        "#4FD1C5",
        "#63B3ED",
        "#63B3ED",
        "#7F9CF5",
        "#7F9CF5",
        "#A3BFFA",
        "#319795",
        "#319795",
        "#4FD1C5",
      ];
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
      this.numberOfParticles = 1500;
      this.cellSize = 6;
      this.cols;
      this.rows;
      this.flowField = [];
      this.curve = 3;
      this.zoom = 0.175;
      this.debug = true;
      this.init();

      window.addEventListener("keydown", (e) => {
        if (e.key === "d") {
          this.debug = !this.debug;
        }
      });

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
    drawGrid(context) {
      context.save();
      context.strokeStyle = "#23232e";
      context.lineWidth = 0.3;
      for (let c = 0; c < this.cols; c++) {
        context.beginPath();
        context.moveTo(c * this.cellSize, 0);
        context.lineTo(c * this.cellSize, this.height);
        context.stroke();
      }
      for (let r = 0; r < this.rows; r++) {
        context.beginPath();
        context.moveTo(0, r * this.cellSize);
        context.lineTo(this.width, r * this.cellSize);
        context.stroke();
      }
      context.restore();
    }

    resize(width, height) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.width = this.canvas.width;
      this.height = this.canvas.height;
      this.init();
    }

    render(context) {
      if (this.debug) this.drawGrid(context);
      this.particles.forEach((particle) => {
        particle.draw(context);
        particle.update();
      });
    }
  }

  const effect = new Effect(canvas);

  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let animationFrameId = null;
  let isRunning = false;
  let lastTime = 0;
  const fps = 60;
  const nextFrame = 1000 / fps;
  let timer = 0;

  function shouldAnimate() {
    return !document.hidden && !motionQuery.matches;
  }

  function renderStaticFrame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    effect.render(ctx);
  }

  function animate(timeStamp) {
    if (!isRunning) return;
    const deltaTime = timeStamp - lastTime;
    lastTime = timeStamp;

    if (timer > nextFrame) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      effect.render(ctx);
      timer = 0;
    } else {
      timer += deltaTime;
    }
    animationFrameId = requestAnimationFrame(animate);
  }

  function startAnimation() {
    if (!isRunning && shouldAnimate()) {
      isRunning = true;
      lastTime = performance.now();
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

  const prefersReducedMotion = motionQuery.matches;
  const isFinePointer = window.matchMedia("(pointer: fine)").matches;

  if (!prefersReducedMotion && isFinePointer) {
    document.addEventListener("mousemove", (e) => {
      const gate = document.getElementById("parallax-target");
      const canvasElement = document.querySelector(".canvas_landing");
      if (!gate || !canvasElement) return;

      const xAxis = (window.innerWidth / 2 - e.pageX) / 80;
      const yAxis = (window.innerHeight / 2 - e.pageY) / 80;

      // Gate moves toward the cursor while the canvas shifts opposite for depth.
      gate.style.transform = `translate(${-xAxis}px, ${-yAxis}px)`;
      canvasElement.style.transform = `translate(${xAxis * 1.5}px, ${yAxis * 1.5}px)`;
    });

    document.addEventListener("mouseleave", () => {
      const gate = document.getElementById("parallax-target");
      const canvasElement = document.querySelector(".canvas_landing");
      if (gate) gate.style.transform = "translate(0px, 0px)";
      if (canvasElement) canvasElement.style.transform = "translate(0px, 0px)";
    });
  }
}
