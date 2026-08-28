/**
 * whats_new.js — Cross-Browser "What's New" PWA & Mobile App Announcement Controller
 */

(function () {
  "use strict";

  const WHATS_NEW_KEY = "kineto_whats_new_version";
  const CURRENT_WHATS_NEW_VERSION = "v2.4-pwa";

  function detectPlatform() {
    const ua = navigator.userAgent || "";
    const isIOS =
      /iPad|iPhone|iPod/.test(ua) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const isSafari =
      /Safari/.test(ua) && !/Chrome|CriOS|Chromium|Edg|OPR|SamsungBrowser/.test(ua);
    const isMacSafari = isSafari && /Macintosh|Mac OS X/.test(ua) && !isIOS;
    const isFirefox = /Firefox|FxiOS/.test(ua);
    const isStandalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      navigator.standalone === true;

    return {
      isIOS,
      isSafari,
      isMacSafari,
      isFirefox,
      isStandalone,
    };
  }

  window.openWhatsNew = function () {
    const overlay = document.getElementById("whats-new-overlay");
    if (!overlay) return;

    const { isIOS, isMacSafari, isFirefox, isStandalone } = detectPlatform();

    const iosGuide = document.getElementById("ios-guide");
    const macSafariGuide = document.getElementById("mac-safari-guide");
    const firefoxGuide = document.getElementById("firefox-guide");
    const pwaActionBox = document.getElementById("pwa-action-box");
    const genericGuide = document.getElementById("generic-guide");

    // Hide all guide blocks first
    if (iosGuide) iosGuide.style.display = "none";
    if (macSafariGuide) macSafariGuide.style.display = "none";
    if (firefoxGuide) firefoxGuide.style.display = "none";
    if (pwaActionBox) pwaActionBox.style.display = "none";
    if (genericGuide) genericGuide.style.display = "none";

    if (isIOS) {
      if (iosGuide) iosGuide.style.display = "flex";
    } else if (isMacSafari) {
      if (macSafariGuide) macSafariGuide.style.display = "flex";
    } else if (isFirefox) {
      if (firefoxGuide) firefoxGuide.style.display = "flex";
    } else {
      // Chromium or other browsers
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
    const { isStandalone } = detectPlatform();

    // If already installed and running as standalone app, don't popup
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

    // Hook install button to native install prompt if available, otherwise show fallback
    const installBtn = document.getElementById("whats-new-install-btn");
    if (installBtn) {
      installBtn.addEventListener("click", async function () {
        if (window.deferredInstallPrompt) {
          window.deferredInstallPrompt.prompt();
          await window.deferredInstallPrompt.userChoice;
          window.deferredInstallPrompt = null;
          window.closeWhatsNew();
        } else {
          // If native prompt is not available, show generic menu guide
          const pwaActionBox = document.getElementById("pwa-action-box");
          const genericGuide = document.getElementById("generic-guide");
          if (pwaActionBox) pwaActionBox.style.display = "none";
          if (genericGuide) genericGuide.style.display = "flex";
        }
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
