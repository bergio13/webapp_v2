/**
 * canvas_bg.js — Shared configurable canvas background
 *
 * Two modes:
 *   "flow"    – flow-field trails (like Home / Landing)
 *   "dots"    – slowly drifting glowing dots (resembles the Friends dot-pattern)
 *
 * Usage:
 *   initCanvasBg({ canvasId: "canvas", mode: "flow", ... });
 */

(function () {
  "use strict";

  /* ───────── Flow-field mode ───────── */

  class FlowParticle {
    constructor(effect) {
      this.effect = effect;
      this.reset();
    }
    reset() {
      this.x = Math.random() * this.effect.width;
      this.y = Math.random() * this.effect.height;
      this.speedX = 0;
      this.speedY = 0;
      this.speedModifier =
        Math.random() * (this.effect.speedRange[1] - this.effect.speedRange[0]) +
        this.effect.speedRange[0];
      this.history = [{ x: this.x, y: this.y }];
      this.maxLength =
        Math.random() * (this.effect.trailRange[1] - this.effect.trailRange[0]) +
        this.effect.trailRange[0];
      this.angle = 0;
      this.timer = this.maxLength * 2;
      this.color =
        this.effect.colors[
          Math.floor(Math.random() * this.effect.colors.length)
        ];
    }
    draw(ctx) {
      ctx.beginPath();
      ctx.moveTo(this.history[0].x, this.history[0].y);
      for (let i = 1; i < this.history.length; i++) {
        ctx.lineTo(this.history[i].x, this.history[i].y);
      }
      ctx.strokeStyle = this.color;
      ctx.lineWidth = this.effect.lineWidth;
      ctx.stroke();
    }
    update() {
      this.timer--;
      if (this.timer > 0) {
        let x = Math.floor(this.x / this.effect.cellSize);
        let y = Math.floor(this.y / this.effect.cellSize);
        let index = y * this.effect.cols + x;
        if (index >= 0 && index < this.effect.flowField.length) {
          this.angle = this.effect.flowField[index];
        }
        this.speedX = Math.cos(this.angle);
        this.speedY = Math.sin(this.angle);
        this.x += this.speedX * this.speedModifier;
        this.y += this.speedY * this.speedModifier;
        this.history.push({ x: this.x, y: this.y });
        if (this.history.length > this.maxLength) this.history.shift();
      } else if (this.history.length > 1) {
        this.history.shift();
      } else {
        this.reset();
      }
    }
  }

  class FlowEffect {
    constructor(canvas, opts) {
      this.canvas = canvas;
      this.width = canvas.width;
      this.height = canvas.height;
      this.colors = opts.colors;
      this.particleCount = opts.particleCount;
      this.cellSize = opts.cellSize || 20;
      this.curve = opts.curve;
      this.zoom = opts.zoom;
      this.speedRange = opts.speedRange || [0.5, 2.0];
      this.trailRange = opts.trailRange || [50, 450];
      this.lineWidth = opts.lineWidth || 1;
      this.cols = 0;
      this.rows = 0;
      this.flowField = [];
      this.particles = [];
      this.init();
    }
    init() {
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
      this.particles = [];
      for (let i = 0; i < this.particleCount; i++) {
        this.particles.push(new FlowParticle(this));
      }
    }
    resize(w, h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.width = w;
      this.height = h;
      this.init();
    }
    render(ctx) {
      this.particles.forEach((p) => {
        p.update();
        p.draw(ctx);
      });
    }
  }

  /* ───────── Dot-drift mode (Friends-style) ───────── */

  class DotParticle {
    constructor(effect) {
      this.effect = effect;
      this.reset(true);
    }
    reset(initial) {
      this.x = Math.random() * this.effect.width;
      this.y = Math.random() * this.effect.height;
      this.vx = (Math.random() - 0.5) * this.effect.driftSpeed;
      this.vy = (Math.random() - 0.5) * this.effect.driftSpeed;
      this.radius =
        Math.random() * (this.effect.sizeRange[1] - this.effect.sizeRange[0]) +
        this.effect.sizeRange[0];
      this.color =
        this.effect.colors[
          Math.floor(Math.random() * this.effect.colors.length)
        ];
      this.alpha =
        Math.random() * (this.effect.alphaRange[1] - this.effect.alphaRange[0]) +
        this.effect.alphaRange[0];
      // Subtle pulsing
      this.pulsePhase = Math.random() * Math.PI * 2;
      this.pulseSpeed = 0.008 + Math.random() * 0.012;
    }
    draw(ctx) {
      const pulse = 0.7 + 0.3 * Math.sin(this.pulsePhase);
      const a = this.alpha * pulse;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = this.color;
      ctx.globalAlpha = a;
      ctx.shadowBlur = this.effect.glowSize;
      ctx.shadowColor = this.color;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.pulsePhase += this.pulseSpeed;
      // Wrap around edges
      if (this.x < -this.radius) this.x = this.effect.width + this.radius;
      if (this.x > this.effect.width + this.radius) this.x = -this.radius;
      if (this.y < -this.radius) this.y = this.effect.height + this.radius;
      if (this.y > this.effect.height + this.radius) this.y = -this.radius;
    }
  }

  class DotEffect {
    constructor(canvas, opts) {
      this.canvas = canvas;
      this.width = canvas.width;
      this.height = canvas.height;
      this.colors = opts.colors;
      this.particleCount = opts.particleCount;
      this.driftSpeed = opts.driftSpeed || 0.3;
      this.sizeRange = opts.sizeRange || [0.6, 2.0];
      this.alphaRange = opts.alphaRange || [0.3, 0.8];
      this.glowSize = opts.glowSize || 6;
      this.particles = [];
      this.init();
    }
    init() {
      this.particles = [];
      for (let i = 0; i < this.particleCount; i++) {
        this.particles.push(new DotParticle(this));
      }
    }
    resize(w, h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.width = w;
      this.height = h;
      // Re-spread existing particles
      this.particles.forEach((p) => p.reset(false));
    }
    render(ctx) {
      this.particles.forEach((p) => {
        p.update();
        p.draw(ctx);
      });
    }
  }

  /* ───────── Public init function ───────── */

  window.initCanvasBg = function (opts) {
    const canvas = document.getElementById(opts.canvasId || "canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const mode = opts.mode || "flow";
    let effect;

    if (mode === "dots") {
      effect = new DotEffect(canvas, opts);
    } else {
      effect = new FlowEffect(canvas, opts);
    }

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
        // If reduced motion is requested and tab is visible, draw a calm static frame
        if (motionQuery.matches && !document.hidden) {
          renderStaticFrame();
        }
      }
    }

    window.addEventListener("resize", () => {
      effect.resize(window.innerWidth, window.innerHeight);
      if (!shouldAnimate() && !document.hidden) {
        renderStaticFrame();
      }
    });

    document.addEventListener("visibilitychange", updateAnimationState);

    if (typeof motionQuery.addEventListener === "function") {
      motionQuery.addEventListener("change", updateAnimationState);
    } else if (typeof motionQuery.addListener === "function") {
      motionQuery.addListener(updateAnimationState);
    }

    // Initial start or static render
    if (shouldAnimate()) {
      startAnimation();
    } else if (!document.hidden) {
      renderStaticFrame();
    }
  };
})();
