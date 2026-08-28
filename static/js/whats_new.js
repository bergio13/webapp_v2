/**
 * whats_new.js — "What's New" PWA & Mobile App Announcement Controller
 */

(function () {
  "use strict";

  const WHATS_NEW_KEY = "kineto_whats_new_version";
  const CURRENT_WHATS_NEW_VERSION = "v2.4-pwa";

  window.openWhatsNew = function () {
    const overlay = document.getElementById("whats-new-overlay");
    if (!overlay) return;

    // Detect iOS Safari (not in standalone mode)
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;

    const iosGuide = document.getElementById("ios-guide");
    const pwaActionBox = document.getElementById("pwa-action-box");

    if (isIOS && !isStandalone) {
      if (iosGuide) iosGuide.style.display = "flex";
      if (pwaActionBox) pwaActionBox.style.display = "none";
    } else {
      if (iosGuide) iosGuide.style.display = "none";
      if (pwaActionBox) pwaActionBox.style.display = "block";
    }

    overlay.style.display = "flex";
  };

  window.closeWhatsNew = function () {
    const overlay = document.getElementById("whats-new-overlay");
    if (overlay) {
      overlay.style.display = "none";
    }
    try {
      localStorage.setItem(WHATS_NEW_KEY, CURRENT_WHATS_NEW_VERSION);
    } catch (e) {
      // Ignore storage errors in private browsing
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    // Check if running in standalone mode already
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
    if (isStandalone) {
      return;
    }

    // Check if user has seen this release announcement
    try {
      const seenVersion = localStorage.getItem(WHATS_NEW_KEY);
      if (seenVersion !== CURRENT_WHATS_NEW_VERSION) {
        // Show after slight delay so page transitions settle first
        setTimeout(window.openWhatsNew, 1200);
      }
    } catch (e) {
      // Ignore storage error
    }

    // Hook install button to native install prompt if available
    const installBtn = document.getElementById("whats-new-install-btn");
    if (installBtn) {
      installBtn.addEventListener("click", async function () {
        if (window.deferredInstallPrompt) {
          window.deferredInstallPrompt.prompt();
          await window.deferredInstallPrompt.userChoice;
          window.deferredInstallPrompt = null;
        }
        window.closeWhatsNew();
      });
    }

    // Close on background backdrop click
    const overlay = document.getElementById("whats-new-overlay");
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) {
          window.closeWhatsNew();
        }
      });
    }

    // Close on Escape key
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        const ov = document.getElementById("whats-new-overlay");
        if (ov && ov.style.display !== "none") {
          window.closeWhatsNew();
        }
      }
    });
  });
})();
