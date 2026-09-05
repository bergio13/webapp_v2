/**
 * cosmos_worker.js — High-Performance Force-Directed Simulation in Web Worker
 * Offloads sector-cohesive cluster gravity, multi-body repulsion,
 * and cosmic void negative gravity craters from the main UI thread.
 */

self.onmessage = function (e) {
  const { type, stars, links, config } = e.data || {};

  if (type === "START_SIMULATION") {
    runForceSimulation(stars, links, config || {});
  }
};

function runForceSimulation(stars, links, config) {
  if (!stars || stars.length === 0) return;

  const maxTicks = config.maxTicks || 120;
  const kRepulse = config.kRepulse || 4500;
  const kSpring = config.kSpring || 0.055;
  const kSectorCohesion = config.kSectorCohesion || 0.012;
  const kCenter = config.kCenter || 0.0006;
  const voidCrater = config.voidCrater || 180;

  const n = stars.length;
  const idMap = new Map();
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const targetX = new Float32Array(n);
  const targetY = new Float32Array(n);
  const vx = new Float32Array(n);
  const vy = new Float32Array(n);
  const isVoid = new Uint8Array(n);
  const sectorIds = new Int16Array(n);

  // Group stars into sector indices and compute initial sector centers
  const sectorMap = new Map();
  let sectorCounter = 0;

  for (let i = 0; i < n; i++) {
    const s = stars[i];
    idMap.set(s.id, i);
    x[i] = s.x || 0;
    y[i] = s.y || 0;
    targetX[i] = s.target_x !== undefined ? s.target_x : (s.x || 0);
    targetY[i] = s.target_y !== undefined ? s.target_y : (s.y || 0);
    vx[i] = 0;
    vy[i] = 0;
    isVoid[i] = (s.is_void || s.category === "void_repulsor" || (s.is_watched && s.rating <= 2)) ? 1 : 0;

    const secKey = s.sector_code || s.sector_name || "default";
    if (!sectorMap.has(secKey)) {
      sectorMap.set(secKey, sectorCounter++);
    }
    sectorIds[i] = sectorMap.get(secKey);
  }

  const numSectors = sectorCounter;
  const secCx = new Float32Array(numSectors);
  const secCy = new Float32Array(numSectors);
  const secCount = new Int32Array(numSectors);

  // Pre-index springs
  const springList = [];
  if (links && links.length > 0) {
    for (const l of links) {
      const srcIdx = idMap.get(l.source);
      const tgtIdx = idMap.get(l.target);
      if (srcIdx !== undefined && tgtIdx !== undefined && srcIdx !== tgtIdx) {
        springList.push({
          s: srcIdx,
          t: tgtIdx,
          strength: l.strength || 0.75,
          idealDist: 60 + (1.0 - (l.strength || 0.75)) * 100
        });
      }
    }
  }

  let alpha = 1.0;
  const alphaDecay = 1.0 - Math.pow(0.001, 1.0 / maxTicks);

  let tick = 0;
  function stepBatch() {
    const batchSize = 6;
    for (let b = 0; b < batchSize && tick < maxTicks; b++, tick++) {
      alpha += (0 - alpha) * alphaDecay;

      // 1. Calculate Dynamic Sector Centroids
      secCx.fill(0);
      secCy.fill(0);
      secCount.fill(0);
      for (let i = 0; i < n; i++) {
        if (!isVoid[i]) {
          const sId = sectorIds[i];
          secCx[sId] += x[i];
          secCy[sId] += y[i];
          secCount[sId]++;
        }
      }
      for (let s = 0; s < numSectors; s++) {
        if (secCount[s] > 0) {
          secCx[s] /= secCount[s];
          secCy[s] /= secCount[s];
        }
      }

      // 2. All-pairs Multi-body Repulsion & Void Ejection
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          let dx = x[j] - x[i];
          let dy = y[j] - y[i];
          let distSq = dx * dx + dy * dy;
          if (distSq < 1) {
            dx = (Math.random() - 0.5) * 4;
            dy = (Math.random() - 0.5) * 4;
            distSq = 4;
          }

          const dist = Math.sqrt(distSq);

          // Same sector vs different sector repulsion
          const sameSector = sectorIds[i] === sectorIds[j];
          const repMultiplier = sameSector ? 0.65 : 1.8;

          if (dist < 350) {
            const repForce = ((kRepulse * repMultiplier) / (distSq + 180)) * alpha;
            const fx = (dx / dist) * repForce;
            const fy = (dy / dist) * repForce;

            vx[i] -= fx;
            vy[i] -= fy;
            vx[j] += fx;
            vy[j] += fy;
          }

          // Cosmic Void Negative Repulsion Field
          if (isVoid[i] !== isVoid[j] && dist < voidCrater) {
            const voidPush = (voidCrater - dist) * 0.65 * alpha;
            const vfx = (dx / dist) * voidPush;
            const vfy = (dy / dist) * voidPush;

            if (isVoid[i]) {
              vx[j] += vfx * 2.0;
              vy[j] += vfy * 2.0;
            } else {
              vx[i] -= vfx * 2.0;
              vy[i] -= vfy * 2.0;
            }
          }
        }
      }

      // 3. Sector Cohesion Pull (Organizes stars into beautiful distinct cluster islands)
      for (let i = 0; i < n; i++) {
        if (!isVoid[i]) {
          const sId = sectorIds[i];
          const pullX = (secCx[sId] - x[i]) * kSectorCohesion * alpha;
          const pullY = (secCy[sId] - y[i]) * kSectorCohesion * alpha;
          vx[i] += pullX;
          vy[i] += pullY;
        }
      }

      // 4. Semantic Spring Filaments (Hooke's Law)
      for (let k = 0; k < springList.length; k++) {
        const sp = springList[k];
        const s = sp.s;
        const t = sp.t;
        const dx = x[t] - x[s];
        const dy = y[t] - y[s];
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const displacement = dist - sp.idealDist;
        const force = displacement * kSpring * sp.strength * alpha;

        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        vx[s] += fx;
        vy[s] += fy;
        vx[t] -= fx;
        vy[t] -= fy;
      }

      // 5. Restoring Anchor Springs & Bounded Physics (Controlled Coupling)
      const kAnchor = config.kAnchor || 0.08;
      const maxDisplacement = config.maxDisplacement || 28.0;
      for (let i = 0; i < n; i++) {
        vx[i] += (targetX[i] - x[i]) * kAnchor * alpha;
        vy[i] += (targetY[i] - y[i]) * kAnchor * alpha;
      }

      // 6. Galactic Centering Force, Integration & Displacement Clamping
      const damping = 0.86;
      for (let i = 0; i < n; i++) {
        vx[i] -= x[i] * kCenter * alpha;
        vy[i] -= y[i] * kCenter * alpha;

        vx[i] *= damping;
        vy[i] *= damping;

        x[i] += vx[i];
        y[i] += vy[i];

        // Hard clamp displacement from anchor target to prevent semantic neighborhood drift
        const dx = x[i] - targetX[i];
        const dy = y[i] - targetY[i];
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > maxDisplacement) {
          x[i] = targetX[i] + (dx / dist) * maxDisplacement;
          y[i] = targetY[i] + (dy / dist) * maxDisplacement;
        }
      }
    }

    const updates = new Array(n);
    for (let i = 0; i < n; i++) {
      updates[i] = {
        id: stars[i].id,
        x: Math.round(x[i] * 10) / 10,
        y: Math.round(y[i] * 10) / 10
      };
    }

    self.postMessage({
      type: "TICK_UPDATE",
      tick: tick,
      maxTicks: maxTicks,
      isComplete: tick >= maxTicks,
      positions: updates
    });

    if (tick < maxTicks) {
      setTimeout(stepBatch, 16);
    }
  }

  stepBatch();
}
