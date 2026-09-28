class ReefControlCard extends HTMLElement {
  setConfig(c) { this.c = c || {}; this.open = false; this.draw(); }
  set hass(h) { this.h = h; this.draw(); }
  getCardSize() { return 7; }

  find(names, domain = "sensor") {
    if (!this.h) return null;
    for (const n of names) {
      const x = Object.values(this.h.states).find(
        s => s.entity_id.startsWith(domain + ".") && s.entity_id.endsWith("_" + n)
      );
      if (x) return x;
    }
    return null;
  }

  ok(s) {
    if (!s) return false;
    const v = String(s.state ?? "").toLowerCase();
    return !["unknown", "unavailable", "nicht konfiguriert", "nicht verfügbar", "none", ""].includes(v);
  }

  statusClass(s) {
    if (!s) return "";
    const a = s.attributes || {};
    const status = String(a.status || "").toLowerCase();

    if (status.includes("kritisch")) return "bad";
    if (status.includes("zu niedrig") || status.includes("zu hoch") || status.includes("warn")) return "warn";
    if (status === "ok" || status === "normal") return "good";

    const n = Number(String(s.state).replace(",", "."));
    if (!Number.isFinite(n)) return "";

    const min = Number(a.minimum);
    const max = Number(a.maximum);
    const cmin = Number(a.critical_minimum);
    const cmax = Number(a.critical_maximum);

    if (Number.isFinite(cmin) && n < cmin) return "bad";
    if (Number.isFinite(cmax) && n > cmax) return "bad";
    if (Number.isFinite(min) && n < min) return "warn";
    if (Number.isFinite(max) && n > max) return "warn";

    if (Number.isFinite(min) || Number.isFinite(max)) return "good";
    return "";
  }

  statusText(s) {
    if (!s) return "";
    const status = String(s.attributes?.status || "");
    if (status && !["OK", "Normal"].includes(status)) return status;
    return status === "Normal" ? "OK" : status;
  }

  fmt(s) {
    if (!s) return "";
    let v = s.state;
    const n = Number(String(v).replace(",", "."));

    if (Number.isFinite(n)) {
      let d = /temperatur|temperature|salinitat|salinity/.test(s.entity_id) ? 1
        : /redox/.test(s.entity_id) ? 0 : 2;
      v = n.toLocaleString("de-DE", {
        minimumFractionDigits: d,
        maximumFractionDigits: d
      });
    }

    const unit = s.attributes?.unit_of_measurement;
    return v + (unit ? " " + unit : "");
  }

  toggle(s) {
    if (!s || !this.h) return;
    this.h.callService(
      "switch",
      s.state === "on" ? "turn_off" : "turn_on",
      { entity_id: s.entity_id }
    );
  }

  valObject(v) {
    if (v == null) return null;
    if (typeof v === "object") {
      if (v.value == null) return null;
      return { value: v.value, unit: v.unit || v.unit_of_measurement || "" };
    }
    return { value: v, unit: "" };
  }

  icpValue(vals, aliases) {
    for (const key of aliases) {
      if (Object.prototype.hasOwnProperty.call(vals, key)) {
        const v = this.valObject(vals[key]);
        if (v) return v;
      }
    }
    return null;
  }

  formatIcp(v) {
    if (!v) return "";
    const n = Number(String(v.value).replace(",", "."));
    const value = Number.isFinite(n)
      ? n.toLocaleString("de-DE", { maximumFractionDigits: 3 })
      : String(v.value);
    return { value, unit: v.unit || "" };
  }

  draw() {
    if (!this.h || !this.c) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    const A = this.find(["aquarium"]);
    const O = this.find(["betriebsstatus", "feeding_status"]);
    const G = this.find(["gesamtstatus", "overall_status"]);

    const T = this.find(["temperatur", "temperature_status"]);
    const S = this.find(["salinitat", "salinity_status"]);
    const P = this.find(["ph", "ph_status"]);
    const R = this.find(["redox", "redox_status"]);
    const C = this.find(["leitfahigkeit", "conductivity"]);
    const W = this.find(["wasserstand", "water_level"]);

    const V = this.find(["wasserwerte", "water_values"]);
    const I = this.find(["icp", "reef_icp"]);
    const AL = this.find(["aktive_alarme", "active_alarms"]);

    const F = this.find(["futterungsmodus", "feeding_mode"], "switch");
    const M = this.find(["wartungsmodus", "maintenance_mode"], "switch");

    const live = [
      ["Temperatur", T, "mdi:thermometer"],
      ["Salinität", S, "mdi:waves"]
    ].filter(x => this.ok(x[1]));

    const more = [
      ["pH", P, "mdi:ph"],
      ["Redox", R, "mdi:flash-outline"],
      ["Leitfähigkeit", C, "mdi:lightning-bolt-outline"],
      ["Wasserstand", W, "mdi:waves-arrow-up"]
    ].filter(x => this.ok(x[1]));

    const vals = (V && V.attributes && V.attributes.values && typeof V.attributes.values === "object")
      ? V.attributes.values : {};

    const wanted = [
      ["KH", ["kh", "alkalinity", "carbonate_hardness"]],
      ["Calcium", ["calcium", "ca"]],
      ["Magnesium", ["magnesium", "mg"]],
      ["Nitrat", ["nitrate", "nitrat", "no3"]],
      ["Phosphat", ["phosphate", "phosphat", "po4"]]
    ];

    const keys = wanted
      .map(([label, aliases]) => [label, this.icpValue(vals, aliases)])
      .filter(x => x[1] !== null);

    const rawHints = [
      ...((AL?.attributes?.alarms || []).map(x =>
        typeof x === "string" ? x : (x.message || x.reason || "Aktiver Alarm")
      )),
      ...((G?.attributes?.issues || []))
    ];

    const normalized = [];
    const seen = new Set();

    for (const item of rawHints) {
      if (!item) continue;
      let text = String(item).trim();
      const key = text
        .toLowerCase()
        .replace(/^temperature:/, "temperatur:")
        .replace(/\s+/g, " ");
      if (!seen.has(key)) {
        seen.add(key);
        normalized.push(text);
      }
    }

    const uh = normalized.slice(0, 5);

    const gs = G?.state || "OK";
    const gsLow = String(gs).toLowerCase();
    const gc = gsLow.includes("kritisch") ? "bad"
      : gsLow.includes("warn") ? "warn"
      : "good";

    const operating = O?.state || "Normalbetrieb";
    const opLow = String(operating).toLowerCase();
    const oc = opLow.includes("wart") ? "warn"
      : opLow.includes("fütter") || opLow.includes("futter") ? "feeding"
      : "good";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          overflow: hidden;
          border-radius: 22px;
        }

        .hero {
          padding: 16px 17px 14px;
          background:
            radial-gradient(circle at 88% 0%, rgba(0,188,212,.14), transparent 44%),
            radial-gradient(circle at 5% 100%, rgba(0,150,136,.08), transparent 38%);
        }

        .top {
          display: flex;
          justify-content: space-between;
          gap: 14px;
          align-items: flex-start;
        }

        .eye {
          font-size: 10px;
          letter-spacing: .16em;
          font-weight: 800;
          color: var(--secondary-text-color);
        }

        .title {
          font-size: 22px;
          line-height: 1.15;
          font-weight: 750;
          margin: 5px 0 9px;
        }

        .mode {
          display: inline-flex;
          gap: 7px;
          align-items: center;
          padding: 5px 9px;
          border-radius: 18px;
          background: rgba(127,127,127,.10);
          font-size: 12px;
        }

        .dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #66bb6a;
          box-shadow: 0 0 9px rgba(102,187,106,.75);
        }

        .mode.warn .dot {
          background: #fbc02d;
          box-shadow: 0 0 9px rgba(251,192,45,.75);
        }

        .mode.feeding .dot {
          background: #29b6f6;
          box-shadow: 0 0 9px rgba(41,182,246,.75);
        }

        .right {
          min-width: 82px;
          text-align: right;
          font-size: 10px;
          color: var(--secondary-text-color);
        }

        .right b {
          display: block;
          margin-top: 2px;
          font-size: 15px;
          color: var(--primary-text-color);
        }

        .right.good b { color: #66bb6a; }
        .right.warn b { color: #fbc02d; }
        .right.bad b  { color: #ef5350; }

        .sec {
          padding: 0 14px 14px;
        }

        .h {
          font-size: 11px;
          font-weight: 800;
          letter-spacing: .06em;
          color: var(--secondary-text-color);
          margin: 4px 2px 8px;
          text-transform: uppercase;
        }

        .grid,
        .actions,
        .mini {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }

        .live,
        .box,
        .iv {
          background: rgba(127,127,127,.075);
          border-radius: 15px;
        }

        .live {
          padding: 11px 12px 10px;
          min-height: 78px;
        }

        .lbl {
          display: flex;
          gap: 6px;
          align-items: center;
          font-size: 11px;
          color: var(--secondary-text-color);
        }

        .lbl ha-icon {
          --mdc-icon-size: 19px;
        }

        .v {
          font-size: 23px;
          line-height: 1.15;
          font-weight: 800;
          margin: 8px 0 2px;
          color: var(--primary-text-color);
        }

        .live.good .v {
          color: #66bb6a;
          text-shadow:
            0 0 7px rgba(102,187,106,.55),
            0 0 16px rgba(102,187,106,.28);
        }

        .live.warn .v {
          color: #fbc02d;
          text-shadow:
            0 0 7px rgba(251,192,45,.55),
            0 0 16px rgba(251,192,45,.25);
        }

        .live.bad .v {
          color: #ef5350;
          text-shadow:
            0 0 7px rgba(239,83,80,.65),
            0 0 17px rgba(239,83,80,.30);
        }

        .live.good .lbl ha-icon { color: #66bb6a; }
        .live.warn .lbl ha-icon { color: #fbc02d; }
        .live.bad .lbl ha-icon  { color: #ef5350; }

        .st {
          min-height: 14px;
          font-size: 10px;
          color: var(--secondary-text-color);
        }

        button {
          border: 0;
          color: var(--primary-text-color);
          font: inherit;
          cursor: pointer;
        }

        .act {
          padding: 11px 8px;
          border-radius: 14px;
          background: rgba(127,127,127,.09);
          font-size: 13px;
        }

        .act.on {
          background: rgba(0,188,212,.17);
          color: var(--primary-color);
          box-shadow: inset 0 0 0 1px rgba(0,188,212,.12);
        }

        .notes {
          padding: 9px 11px;
          border-radius: 14px;
          background: rgba(127,127,127,.065);
          font-size: 12px;
          line-height: 1.35;
        }

        .note {
          margin: 4px 0;
        }

        .yes {
          color: #66bb6a;
        }

        .icp {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 6px;
        }

        .iv {
          text-align: center;
          padding: 8px 3px 7px;
          min-width: 0;
        }

        .iv span {
          display: block;
          font-size: 9px;
          color: var(--secondary-text-color);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .iv b {
          display: inline;
          font-size: 14px;
          line-height: 1.4;
        }

        .iv small {
          margin-left: 2px;
          font-size: 8px;
          color: var(--secondary-text-color);
        }

        .icpmeta {
          display: block;
          margin: 6px 2px 0;
          font-size: 9px;
          color: var(--secondary-text-color);
        }

        .expand {
          width: 100%;
          padding: 11px;
          background: transparent;
          border-top: 1px solid rgba(127,127,127,.11);
          color: var(--secondary-text-color);
          font-size: 11px;
        }

        .details {
          display: ${this.open ? "block" : "none"};
          padding: 0 14px 14px;
        }

        .box {
          display: flex;
          gap: 8px;
          align-items: center;
          padding: 9px 10px;
        }

        .box ha-icon {
          --mdc-icon-size: 19px;
          color: var(--secondary-text-color);
        }

        .box span,
        .box b {
          display: block;
        }

        .box span {
          font-size: 9px;
          color: var(--secondary-text-color);
        }

        .box b {
          margin-top: 1px;
          font-size: 13px;
        }

        @media (max-width: 430px) {
          .icp {
            grid-template-columns: repeat(3, 1fr);
          }

          .title {
            font-size: 21px;
          }
        }
      </style>

      <ha-card>
        <div class="hero">
          <div class="top">
            <div>
              <div class="eye">REEF CONTROL</div>
              <div class="title">${this.c.title || A?.state || "Aquarium"}</div>
              <div class="mode ${oc}">
                <i class="dot"></i>
                ${operating}
              </div>
            </div>

            <div class="right ${gc}">
              Gesamtstatus
              <b>${gs}</b>
            </div>
          </div>
        </div>

        ${live.length ? `
          <div class="sec">
            <div class="h">Live-Wasserwerte</div>
            <div class="grid">
              ${live.map(x => {
                const cl = this.statusClass(x[1]);
                return `
                  <div class="live ${cl}">
                    <div class="lbl">
                      <ha-icon icon="${x[2]}"></ha-icon>
                      ${x[0]}
                    </div>
                    <div class="v">${this.fmt(x[1])}</div>
                    <div class="st">${this.statusText(x[1])}</div>
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        ` : ""}

        ${(F || M) ? `
          <div class="sec">
            <div class="h">Schnellaktionen</div>
            <div class="actions">
              ${F ? `
                <button id="f" class="act ${F.state === "on" ? "on" : ""}">
                  🐟 Fütterung
                </button>
              ` : ""}
              ${M ? `
                <button id="m" class="act ${M.state === "on" ? "on" : ""}">
                  🔧 Wartung
                </button>
              ` : ""}
            </div>
          </div>
        ` : ""}

        <div class="sec">
          <div class="h">Aktuelle Hinweise</div>
          <div class="notes">
            ${uh.length
              ? uh.map(x => `<div class="note">⚠ ${x}</div>`).join("")
              : `<div class="yes">✓ Keine aktuellen Hinweise</div>`
            }
          </div>
        </div>

        ${keys.length ? `
          <div class="sec">
            <div class="h">Letzte Wasserwerte / ICP</div>
            <div class="icp">
              ${keys.map(x => {
                const fv = this.formatIcp(x[1]);
                return `
                  <div class="iv">
                    <span>${x[0]}</span>
                    <b>${fv.value}</b><small>${fv.unit}</small>
                  </div>
                `;
              }).join("")}
            </div>

            ${I ? `
              <small class="icpmeta">
                ICP: ${I.state}
                ${I.attributes?.provider ? " · " + I.attributes.provider : ""}
                ${I.attributes?.analysis_date ? " · " + I.attributes.analysis_date : ""}
              </small>
            ` : ""}
          </div>
        ` : ""}

        ${more.length ? `
          <button id="e" class="expand">
            ${this.open ? "Weniger anzeigen ▲" : "Weitere Werte anzeigen ▼"}
          </button>

          <div class="details">
            <div class="mini">
              ${more.map(x => `
                <div class="box">
                  <ha-icon icon="${x[2]}"></ha-icon>
                  <div>
                    <span>${x[0]}</span>
                    <b>${this.fmt(x[1])}</b>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        ` : ""}
      </ha-card>
    `;

    this.shadowRoot.getElementById("f")
      ?.addEventListener("click", () => this.toggle(F));

    this.shadowRoot.getElementById("m")
      ?.addEventListener("click", () => this.toggle(M));

    this.shadowRoot.getElementById("e")
      ?.addEventListener("click", () => {
        this.open = !this.open;
        this.draw();
      });
  }
}

if (!customElements.get("reef-control-card")) {
  customElements.define("reef-control-card", ReefControlCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(x => x.type === "reef-control-card")) {
  window.customCards.push({
    type: "reef-control-card",
    name: "Reef Control Card",
    description: "Aquarium-Cockpit für Reef Control",
    preview: true
  });
}

console.info("REEF CONTROL CARD v0.1.1");
