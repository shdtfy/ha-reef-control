class ReefControlCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this.detailsOpen = false;
    this.renderCard();
  }

  set hass(hass) {
    this._hass = hass;
    this.renderCard();
  }

  getCardSize() { return 7; }

  norm(value) {
    return String(value ?? "")
      .toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  aquariumPrefix(aquarium) {
    if (!aquarium?.entity_id) return null;
    const objectId = aquarium.entity_id.split(".")[1] || "";
    const endings = ["_aquarium", "_reef_aquarium"];
    for (const ending of endings) {
      if (objectId.endsWith(ending)) return objectId.slice(0, -ending.length);
    }
    return objectId || null;
  }

  entityCandidates(domain, prefix) {
    if (!this._hass) return [];
    return Object.values(this._hass.states).filter(state => {
      if (!state.entity_id.startsWith(domain + ".")) return false;
      if (!prefix) return true;
      const id = state.entity_id.split(".")[1] || "";
      return id === prefix || id.startsWith(prefix + "_");
    });
  }

  find(names, domain = "sensor", prefix = null) {
    if (!this._hass) return null;
    const aliases = names.map(x => this.norm(x));
    const candidates = this.entityCandidates(domain, prefix);

    // 1. Exact object-id suffix. This remains the safest match.
    for (const alias of aliases) {
      const exact = candidates.find(state => {
        const id = this.norm(state.entity_id.split(".")[1] || "");
        return id === alias || id.endsWith("_" + alias);
      });
      if (exact) return exact;
    }

    // 2. Match the Home Assistant friendly name.
    for (const alias of aliases) {
      const byName = candidates.find(state => {
        const friendly = this.norm(state.attributes?.friendly_name);
        return friendly === alias || friendly.endsWith("_" + alias);
      });
      if (byName) return byName;
    }

    // 3. Robust fallback: token match inside the aquarium device namespace.
    for (const alias of aliases) {
      const tokens = alias.split("_").filter(Boolean);
      const fuzzy = candidates.find(state => {
        const haystack = this.norm(
          `${state.entity_id} ${state.attributes?.friendly_name || ""}`
        );
        return tokens.every(token => haystack.includes(token));
      });
      if (fuzzy) return fuzzy;
    }

    // 4. Last fallback without prefix, but only if the match is unambiguous.
    if (prefix) {
      const all = this.entityCandidates(domain, null);
      for (const alias of aliases) {
        const matches = all.filter(state => {
          const id = this.norm(state.entity_id.split(".")[1] || "");
          const friendly = this.norm(state.attributes?.friendly_name);
          return id === alias || id.endsWith("_" + alias) ||
                 friendly === alias || friendly.endsWith("_" + alias);
        });
        if (matches.length === 1) return matches[0];
      }
    }
    return null;
  }

  available(state) {
    if (!state) return false;
    const value = String(state.state ?? "").toLowerCase();
    return !["unknown", "unavailable", "nicht konfiguriert",
      "nicht verfügbar", "none", "null", ""].includes(value);
  }

  number(value) {
    if (value === null || value === undefined || value === "") return NaN;
    return Number(String(value).replace(",", "."));
  }

  statusClass(state) {
    if (!state) return "";
    const a = state.attributes || {};
    const n = this.number(state.state);
    const min = this.number(a.minimum);
    const max = this.number(a.maximum);
    const cmin = this.number(a.critical_minimum);
    const cmax = this.number(a.critical_maximum);

    if (Number.isFinite(n)) {
      if (Number.isFinite(cmin) && n < cmin) return "bad";
      if (Number.isFinite(cmax) && n > cmax) return "bad";
      if (Number.isFinite(min) && n < min) return "warn";
      if (Number.isFinite(max) && n > max) return "warn";
      if ([min, max, cmin, cmax].some(Number.isFinite)) return "good";
    }

    const status = this.norm(a.status);
    if (status.includes("kritisch")) return "bad";
    if (status.includes("zu_niedrig") || status.includes("zu_hoch") || status.includes("warn")) return "warn";
    if (["ok", "normal"].includes(status)) return "good";
    return "";
  }

  statusText(state) {
    if (!state) return "";
    const a = state.attributes || {};
    const n = this.number(state.state);
    const min = this.number(a.minimum);
    const max = this.number(a.maximum);
    const cmin = this.number(a.critical_minimum);
    const cmax = this.number(a.critical_maximum);

    if (Number.isFinite(n)) {
      if (Number.isFinite(cmin) && n < cmin) return "Kritisch niedrig";
      if (Number.isFinite(cmax) && n > cmax) return "Kritisch hoch";
      if (Number.isFinite(min) && n < min) return "Zu niedrig";
      if (Number.isFinite(max) && n > max) return "Zu hoch";
      if ([min, max, cmin, cmax].some(Number.isFinite)) return "OK";
    }
    return String(a.status || "");
  }

  format(state) {
    if (!state) return "";
    let value = state.state;
    const n = this.number(value);
    if (Number.isFinite(n)) {
      const id = this.norm(state.entity_id);
      const digits = /temperatur|temperature|salinitat|salinity/.test(id) ? 1
        : /redox/.test(id) ? 0 : 2;
      value = n.toLocaleString("de-DE", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
      });
    }

    let unit = state.attributes?.unit_of_measurement ?? state.attributes?.unit ?? "";
    if (unit && typeof unit === "object") unit = unit.name || unit.value || "";
    if (typeof unit !== "string" && typeof unit !== "number") unit = "";
    return `${value}${unit ? " " + unit : ""}`;
  }

  toggle(state) {
    if (!state || !this._hass) return;
    this._hass.callService(
      "switch",
      state.state === "on" ? "turn_off" : "turn_on",
      { entity_id: state.entity_id }
    );
  }

  valueObject(value) {
    if (value == null) return null;
    if (typeof value === "object") {
      if (value.value == null) return null;
      let unit = value.unit || value.unit_of_measurement || "";
      if (unit && typeof unit === "object") unit = unit.name || unit.value || "";
      return { value: value.value, unit: typeof unit === "string" ? unit : "" };
    }
    return { value, unit: "" };
  }

  icpValue(values, aliases) {
    for (const key of aliases) {
      if (Object.prototype.hasOwnProperty.call(values, key)) {
        const value = this.valueObject(values[key]);
        if (value) return value;
      }
    }
    return null;
  }

  formatIcp(item) {
    if (!item) return { value: "", unit: "" };
    const n = this.number(item.value);
    return {
      value: Number.isFinite(n)
        ? n.toLocaleString("de-DE", { maximumFractionDigits: 3 })
        : String(item.value),
      unit: item.unit || ""
    };
  }

  renderCard() {
    if (!this._hass || !this.config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    const configured = this.config.entity ? this._hass.states[this.config.entity] : null;
    const aquarium = configured || this.find(["aquarium", "reef_aquarium"]);
    const prefix = this.aquariumPrefix(aquarium);
    const f = (names, domain = "sensor") => this.find(names, domain, prefix);

    const operating = f(["betriebsstatus", "feeding_status"]);
    const overall = f(["gesamtstatus", "overall_status"]);

    // Include both display names and implementation/unique-id style aliases.
    const temperature = f([
      "temperatur", "temperature", "temperature_status",
      "temperatur_status", "wasser_temperatur"
    ]);
    const salinity = f([
      "salinitat", "salinity", "salinity_status",
      "salinitat_status", "salzgehalt"
    ]);
    const ph = f(["ph", "ph_status", "ph_wert"]);
    const redox = f(["redox", "redox_status", "orp", "orp_status"]);
    const conductivity = f([
      "leitfahigkeit", "leitfaehigkeit", "conductivity",
      "conductivity_status"
    ]);
    const waterLevel = f(["wasserstand", "water_level", "wasserstand_status"]);
    const waterValues = f(["wasserwerte", "water_values"]);
    const icp = f(["icp", "reef_icp"]);
    const alarms = f(["aktive_alarme", "active_alarms"]);
    const feeding = f(["futterungsmodus", "feeding_mode"], "switch");
    const maintenance = f(["wartungsmodus", "maintenance_mode"], "switch");

    const live = [
      ["Temperatur", temperature, "mdi:thermometer"],
      ["Salinität", salinity, "mdi:waves"]
    ].filter(x => this.available(x[1]));

    const more = [
      ["pH", ph, "mdi:ph"],
      ["Redox", redox, "mdi:flash-outline"],
      ["Leitfähigkeit", conductivity, "mdi:lightning-bolt-outline"],
      ["Wasserstand", waterLevel, "mdi:waves-arrow-up"]
    ].filter(x => this.available(x[1]));

    const values = (waterValues?.attributes?.values &&
      typeof waterValues.attributes.values === "object")
      ? waterValues.attributes.values : {};

    const wanted = [
      ["KH", ["kh", "alkalinity", "carbonate_hardness"]],
      ["Calcium", ["calcium", "ca"]],
      ["Magnesium", ["magnesium", "mg"]],
      ["Nitrat", ["nitrate", "nitrat", "no3"]],
      ["Phosphat", ["phosphate", "phosphat", "po4"]]
    ];

    const icpValues = wanted
      .map(([label, aliases]) => [label, this.icpValue(values, aliases)])
      .filter(x => x[1] !== null);

    const rawHints = [
      ...((alarms?.attributes?.alarms || []).map(x =>
        typeof x === "string" ? x : (x.message || x.reason || "Aktiver Alarm")
      )),
      ...((overall?.attributes?.issues || []))
    ];

    const hints = [];
    const seen = new Set();
    for (const raw of rawHints) {
      if (!raw) continue;
      let text = String(raw).trim().replace(/^temperature:/i, "Temperatur:");
      const key = this.norm(text);
      if (!seen.has(key)) {
        seen.add(key);
        hints.push(text);
      }
    }

    const overallState = overall?.state || "OK";
    const overallNorm = this.norm(overallState);
    const overallClass = overallNorm.includes("kritisch") ? "bad"
      : (overallNorm.includes("warn") || overallNorm.includes("achtung")) ? "warn"
      : "good";

    const operation = operating?.state || "Normalbetrieb";
    const operationNorm = this.norm(operation);
    const operationClass = operationNorm.includes("wart") ? "warn"
      : operationNorm.includes("futter") ? "feeding" : "good";

    const title = aquarium?.state || "Aquarium";
    const meta = icp?.attributes || {};
    const provider = meta.provider || meta.lab || meta.source || "";
    const date = meta.analysis_date || meta.date || "";
    const connected = this.available(icp);

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { overflow:hidden; border-radius:22px; }
        .hero {
          padding:14px 16px 13px;
          background:
            radial-gradient(circle at 88% 0%, rgba(0,188,212,.14), transparent 44%),
            radial-gradient(circle at 5% 100%, rgba(0,150,136,.08), transparent 38%);
        }
        .top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
        .eye { font-size:9px; letter-spacing:.16em; font-weight:800; color:var(--secondary-text-color); }
        .title { font-size:20px; line-height:1.15; font-weight:750; margin:4px 0 8px; }
        .mode {
          display:inline-flex; gap:7px; align-items:center; padding:4px 8px;
          border-radius:18px; background:rgba(127,127,127,.10); font-size:11px;
        }
        .dot { width:7px; height:7px; border-radius:50%; background:#66bb6a; box-shadow:0 0 9px rgba(102,187,106,.75); }
        .mode.warn .dot { background:#fbc02d; box-shadow:0 0 9px rgba(251,192,45,.75); }
        .mode.feeding .dot { background:#29b6f6; box-shadow:0 0 9px rgba(41,182,246,.75); }
        .right { min-width:80px; text-align:right; font-size:9px; color:var(--secondary-text-color); }
        .right b { display:block; margin-top:2px; font-size:14px; color:var(--primary-text-color); }
        .right.good b { color:#66bb6a; }
        .right.warn b { color:#fbc02d; }
        .right.bad b { color:#ef5350; }

        .sec { padding:0 13px 12px; }
        .h { font-size:10px; font-weight:800; letter-spacing:.06em; color:var(--secondary-text-color); margin:3px 2px 7px; text-transform:uppercase; }
        .grid,.actions,.mini { display:grid; grid-template-columns:1fr 1fr; gap:7px; }
        .live,.box,.iv { background:rgba(127,127,127,.075); border-radius:14px; }
        .live { padding:9px 11px 8px; min-height:68px; }
        .lbl { display:flex; gap:6px; align-items:center; font-size:10px; color:var(--secondary-text-color); }
        .lbl ha-icon { --mdc-icon-size:18px; }
        .v { font-size:21px; line-height:1.15; font-weight:800; margin:7px 0 2px; color:var(--primary-text-color); }
        .live.good .v { color:#66bb6a; text-shadow:0 0 7px rgba(102,187,106,.62),0 0 17px rgba(102,187,106,.30); }
        .live.warn .v { color:#fbc02d; text-shadow:0 0 7px rgba(251,192,45,.62),0 0 17px rgba(251,192,45,.28); }
        .live.bad .v { color:#ef5350; text-shadow:0 0 7px rgba(239,83,80,.72),0 0 18px rgba(239,83,80,.34); }
        .live.good .lbl ha-icon { color:#66bb6a; }
        .live.warn .lbl ha-icon { color:#fbc02d; }
        .live.bad .lbl ha-icon { color:#ef5350; }
        .st { min-height:12px; font-size:9px; color:var(--secondary-text-color); }

        button { border:0; color:var(--primary-text-color); font:inherit; cursor:pointer; }
        .act { padding:10px 8px; border-radius:14px; background:rgba(127,127,127,.09); font-size:12px; }
        .act.on { background:rgba(0,188,212,.17); color:var(--primary-color); box-shadow:inset 0 0 0 1px rgba(0,188,212,.12); }
        .notes { padding:8px 10px; border-radius:14px; background:rgba(127,127,127,.065); font-size:11px; line-height:1.35; }
        .note { margin:3px 0; }
        .yes { color:#66bb6a; }

        .icp { display:grid; grid-template-columns:repeat(5,1fr); gap:6px; }
        .iv { text-align:center; padding:7px 3px 6px; min-width:0; }
        .iv span { display:block; font-size:8px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .iv b { display:inline; font-size:13px; line-height:1.4; }
        .iv small { margin-left:2px; font-size:7px; color:var(--secondary-text-color); }
        .icpmeta { display:block; margin:5px 2px 0; font-size:8px; color:var(--secondary-text-color); }

        .expand { width:100%; padding:10px; background:transparent; border-top:1px solid rgba(127,127,127,.11); color:var(--secondary-text-color); font-size:10px; }
        .details { display:${this.detailsOpen ? "block" : "none"}; padding:0 13px 13px; }
        .box { padding:9px 10px; }
        .box .value { font-size:13px; font-weight:700; margin-top:3px; }
        .empty { font-size:10px; color:var(--secondary-text-color); padding:2px; }
      </style>

      <ha-card>
        <div class="hero">
          <div class="top">
            <div>
              <div class="eye">REEF CONTROL</div>
              <div class="title">${title}</div>
              <div class="mode ${operationClass}"><span class="dot"></span>${operation}</div>
            </div>
            <div class="right ${overallClass}">Gesamtstatus<b>${overallState}</b></div>
          </div>
        </div>

        ${live.length ? `
          <div class="sec">
            <div class="h">Live-Wasserwerte</div>
            <div class="grid">
              ${live.map(([label, state, icon]) => {
                const cls = this.statusClass(state);
                const status = this.statusText(state);
                return `<div class="live ${cls}">
                  <div class="lbl"><ha-icon icon="${icon}"></ha-icon>${label}</div>
                  <div class="v">${this.format(state)}</div>
                  <div class="st">${status}</div>
                </div>`;
              }).join("")}
            </div>
          </div>` : ""}

        ${(feeding || maintenance) ? `
          <div class="sec">
            <div class="h">Schnellaktionen</div>
            <div class="actions">
              ${feeding ? `<button class="act feed ${feeding.state === "on" ? "on" : ""}">🐟 Fütterung</button>` : ""}
              ${maintenance ? `<button class="act maintenance ${maintenance.state === "on" ? "on" : ""}">🔧 Wartung</button>` : ""}
            </div>
          </div>` : ""}

        <div class="sec">
          <div class="h">Aktuelle Hinweise</div>
          <div class="notes">
            ${hints.length
              ? hints.slice(0,5).map(x => `<div class="note">⚠ ${x}</div>`).join("")
              : `<div class="note yes">✓ Keine aktuellen Hinweise</div>`}
          </div>
        </div>

        ${icpValues.length ? `
          <div class="sec">
            <div class="h">Letzte Wasserwerte / ICP</div>
            <div class="icp">
              ${icpValues.map(([label, item]) => {
                const v = this.formatIcp(item);
                return `<div class="iv"><span>${label}</span><b>${v.value}</b><small>${v.unit}</small></div>`;
              }).join("")}
            </div>
            ${connected ? `<span class="icpmeta">ICP: Verbunden${provider ? " · " + provider : ""}${date ? " · " + date : ""}</span>` : ""}
          </div>` : ""}

        ${more.length ? `
          <button class="expand">${this.detailsOpen ? "Weniger anzeigen ▲" : "Weitere Werte anzeigen ▼"}</button>
          <div class="details">
            <div class="mini">
              ${more.map(([label, state, icon]) => `
                <div class="box">
                  <div class="lbl"><ha-icon icon="${icon}"></ha-icon>${label}</div>
                  <div class="value">${this.format(state)}</div>
                </div>`).join("")}
            </div>
          </div>` : ""}
      </ha-card>
    `;

    const feedButton = this.shadowRoot.querySelector(".feed");
    if (feedButton) feedButton.onclick = () => this.toggle(feeding);

    const maintenanceButton = this.shadowRoot.querySelector(".maintenance");
    if (maintenanceButton) maintenanceButton.onclick = () => this.toggle(maintenance);

    const expandButton = this.shadowRoot.querySelector(".expand");
    if (expandButton) expandButton.onclick = () => {
      this.detailsOpen = !this.detailsOpen;
      this.renderCard();
    };
  }
}

if (!customElements.get("reef-control-card")) {
  customElements.define("reef-control-card", ReefControlCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "reef-control-card")) {
  window.customCards.push({
    type: "reef-control-card",
    name: "Reef Control Card",
    description: "Kompakte Aquarium-Steuerung für Reef Control"
  });
}
