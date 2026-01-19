      const storageKey = "quailRecentInboxes";
      const currentInbox = document.body.dataset.currentInbox;
      const listEl = document.getElementById("recent-inboxes");
      const emptyEl = document.getElementById("recent-inboxes-empty");

      const readRecent = () => {
        try {
          const raw = window.sessionStorage.getItem(storageKey);
          return raw ? JSON.parse(raw) : [];
        } catch (error) {
          return [];
        }
      };

      const writeRecent = (items) => {
        try {
          window.sessionStorage.setItem(storageKey, JSON.stringify(items));
        } catch (error) {
          // Ignore storage errors.
        }
      };

      const updateRecent = () => {
        if (!listEl || !emptyEl) {
          return;
        }
        const items = readRecent();
        listEl.innerHTML = "";
        items.forEach((item) => {
          const li = document.createElement("li");
          const link = document.createElement("a");
          link.href = `/inbox?inbox=${encodeURIComponent(item)}`;
          link.textContent = item;
          li.appendChild(link);
          listEl.appendChild(li);
        });
        emptyEl.style.display = items.length ? "none" : "block";
      };

      const bumpInbox = (value) => {
        if (!value) {
          return;
        }
        const normalized = value.trim();
        if (!normalized) {
          return;
        }
        const items = readRecent().filter((item) => item !== normalized);
        items.unshift(normalized);
        writeRecent(items.slice(0, 5));
      };

      if (currentInbox) {
        bumpInbox(currentInbox);
      }
      updateRecent();

      const initTabs = () => {
        const tabsGroups = document.querySelectorAll("[data-tabs]");
        tabsGroups.forEach((tabsEl) => {
          const container = tabsEl.closest(".tabs-container");
          if (!container) {
            return;
          }
          const buttons = Array.from(tabsEl.querySelectorAll("[data-tab]"));
          const panels = Array.from(container.querySelectorAll("[data-tab-panel]"));
          if (!buttons.length || !panels.length) {
            return;
          }
          const setActive = (name) => {
            buttons.forEach((button) => {
              const isActive = button.dataset.tab === name;
              button.classList.toggle("active", isActive);
              button.setAttribute("aria-selected", isActive ? "true" : "false");
            });
            panels.forEach((panel) => {
              panel.classList.toggle("active", panel.dataset.tabPanel === name);
            });
          };
          buttons.forEach((button) => {
            button.addEventListener("click", () => setActive(button.dataset.tab));
          });
          const initial = buttons.find((button) => button.classList.contains("active")) || buttons[0];
          if (initial) {
            setActive(initial.dataset.tab);
          }
        });
      };

      initTabs();

      const applyMinimalHtmlTheme = () => {
        const iframe = document.querySelector(".message-html-frame[data-minimal=\"true\"]");
        if (!iframe) {
          return;
        }
        const applyTheme = () => {
          const doc = iframe.contentDocument;
          if (!doc) {
            return false;
          }
          const rootStyles = getComputedStyle(document.documentElement);
          const background = rootStyles.getPropertyValue("--message-rich-bg").trim() || "#ffffff";
          const text = rootStyles.getPropertyValue("--text").trim() || "#0f1b2d";
          const link = rootStyles.getPropertyValue("--primary").trim() || "#1f5eff";
          if (doc.documentElement) {
            doc.documentElement.style.backgroundColor = background;
            doc.documentElement.style.color = text;
          }
          if (doc.body) {
            doc.body.style.backgroundColor = background;
            doc.body.style.color = text;
          }
          const styleId = "quail-minimal-theme";
          let style = doc.getElementById(styleId);
          if (!style) {
            style = doc.createElement("style");
            style.id = styleId;
            if (doc.head) {
              doc.head.appendChild(style);
            } else {
              doc.documentElement.appendChild(style);
            }
          }
          style.textContent = `html,body{background:${background}!important;color:${text}!important;}body *{color:${text}!important;}a{color:${link}!important;}`;
          return true;
        };
        const tryApply = () => {
          if (applyTheme()) {
            return;
          }
          window.setTimeout(tryApply, 50);
        };
        iframe.addEventListener("load", tryApply, { once: true });
        tryApply();
      };

      applyMinimalHtmlTheme();
