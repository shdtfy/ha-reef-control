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
    return String(value ?? "").toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/ß/g, "ss").replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  aquariumPrefix(aquarium) {
    if (!aquarium?.entity_id) return null;
    const id = aquarium.entity_id.split(".")[1] || "";
    for (const ending of ["_aquarium", "_reef_aquarium"]) {
      if (id.endsWith(ending)) return id.slice(0, -ending.length);
    }
    return id || null;
  }

  candidates(domain, prefix) {
    if (!this._hass) return [];
    return Object.values(this._hass.states).filter(s => {
      if (!s.entity_id.startsWith(domain + ".")) return false;
      if (!prefix) return true;
      const id = s.entity_id.split(".")[1] || "";
      return id === prefix || id.startsWith(prefix + "_");
    });
  }

  find(names, domain="sensor", prefix=null) {
    const aliases = names.map(x => this.norm(x));
    const list = this.candidates(domain, prefix);
    for (const alias of aliases) {
      const hit = list.find(s => {
        const id = this.norm(s.entity_id.split(".")[1] || "");
        return id === alias || id.endsWith("_" + alias);
      });
      if (hit) return hit;
    }
    for (const alias of aliases) {
      const hit = list.find(s => {
        const n = this.norm(s.attributes?.friendly_name);
        return n === alias || n.endsWith("_" + alias);
      });
      if (hit) return hit;
    }
    for (const alias of aliases) {
      const tokens = alias.split("_").filter(Boolean);
      const hit = list.find(s => {
        const h = this.norm(`${s.entity_id} ${s.attributes?.friendly_name || ""}`);
        return tokens.every(t => h.includes(t));
      });
      if (hit) return hit;
    }
    if (prefix) {
      const all = this.candidates(domain, null);
      for (const alias of aliases) {
        const hits = all.filter(s => {
          const id = this.norm(s.entity_id.split(".")[1] || "");
          const n = this.norm(s.attributes?.friendly_name);
          return id === alias || id.endsWith("_"+alias) || n === alias || n.endsWith("_"+alias);
        });
        if (hits.length === 1) return hits[0];
      }
    }
    return null;
  }

  available(s) {
    if (!s) return false;
    return !["unknown","unavailable","nicht konfiguriert","nicht verfügbar","none","null",""].includes(
      String(s.state ?? "").toLowerCase()
    );
  }

  number(v) {
    if (v === null || v === undefined || v === "") return NaN;
    return Number(String(v).replace(",", "."));
  }

  format(s) {
    if (!s) return "";
    let value = s.state;
    const n = this.number(value);
    if (Number.isFinite(n)) {
      const id = this.norm(s.entity_id);
      const digits = /temperatur|temperature|salinitat|salinity/.test(id) ? 1 :
                     /redox|wasserstand|water_level/.test(id) ? 0 : 2;
      value = n.toLocaleString("de-DE", {minimumFractionDigits:digits, maximumFractionDigits:digits});
    }
    let unit = s.attributes?.unit_of_measurement ?? s.attributes?.unit ?? "";
    if (unit && typeof unit === "object") unit = unit.name || unit.value || "";
    if (typeof unit !== "string" && typeof unit !== "number") unit = "";
    return `${value}${unit ? " " + unit : ""}`;
  }

  statusClass(s) {
    if (!s) return "";
    const a=s.attributes||{}, n=this.number(s.state);
    const min=this.number(a.minimum), max=this.number(a.maximum);
    const cmin=this.number(a.critical_minimum), cmax=this.number(a.critical_maximum);
    if (Number.isFinite(n)) {
      if (Number.isFinite(cmin) && n<cmin) return "bad";
      if (Number.isFinite(cmax) && n>cmax) return "bad";
      if (Number.isFinite(min) && n<min) return "warn";
      if (Number.isFinite(max) && n>max) return "warn";
      if ([min,max,cmin,cmax].some(Number.isFinite)) return "good";
    }
    const st=this.norm(a.status);
    if (st.includes("kritisch") || st.includes("zu_hoch") || st.includes("zu_niedrig")) return st.includes("kritisch") ? "bad" : "warn";
    if (["ok","normal","normalbetrieb","bereit"].includes(st)) return "good";
    return "";
  }

  statusText(s) {
    if (!s) return "";
    const a=s.attributes||{}, n=this.number(s.state);
    const min=this.number(a.minimum), max=this.number(a.maximum);
    const cmin=this.number(a.critical_minimum), cmax=this.number(a.critical_maximum);
    if (Number.isFinite(n)) {
      if (Number.isFinite(cmin)&&n<cmin) return "Kritisch niedrig";
      if (Number.isFinite(cmax)&&n>cmax) return "Kritisch hoch";
      if (Number.isFinite(min)&&n<min) return "Zu niedrig";
      if (Number.isFinite(max)&&n>max) return "Zu hoch";
      if ([min,max,cmin,cmax].some(Number.isFinite)) return "OK";
    }
    return String(a.status || "");
  }

  moreInfo(s) {
    if (!s?.entity_id) return;
    const ev = new Event("hass-more-info", {bubbles:true, composed:true});
    ev.detail = {entityId:s.entity_id};
    this.dispatchEvent(ev);
  }

  toggle(s) {
    if (!s || !this._hass) return;
    this._hass.callService(s.entity_id.split(".")[0], s.state==="on" ? "turn_off" : "turn_on", {entity_id:s.entity_id});
  }

  valueObject(v) {
    if (v == null) return null;
    if (typeof v === "object") {
      if (v.value == null) return null;
      let unit=v.unit || v.unit_of_measurement || "";
      if (unit && typeof unit==="object") unit=unit.name || unit.value || "";
      return {value:v.value, unit:typeof unit==="string" ? unit : ""};
    }
    return {value:v, unit:""};
  }

  icpValue(values, aliases) {
    for (const key of aliases) {
      if (Object.prototype.hasOwnProperty.call(values,key)) {
        const v=this.valueObject(values[key]);
        if (v) return v;
      }
    }
    return null;
  }

  formatIcp(item) {
    if (!item) return {value:"",unit:""};
    const n=this.number(item.value);
    return {
      value:Number.isFinite(n) ? n.toLocaleString("de-DE",{maximumFractionDigits:3}) : String(item.value),
      unit:item.unit || ""
    };
  }

  stateById(entityId) {
    return entityId && this._hass?.states?.[entityId] ? this._hass.states[entityId] : null;
  }

  ageText(days, date) {
    const d=Number(days);
    if (Number.isFinite(d)) {
      if (d===0) return "heute";
      if (d===1) return "vor 1 Tag";
      if (d<31) return `vor ${d} Tagen`;
      if (d<365) {
        const m=Math.floor(d/30);
        return `vor ${m} ${m===1 ? "Monat" : "Monaten"}`;
      }
      const y=Math.floor(d/365), m=Math.floor((d%365)/30);
      return `vor ${y} J.${m ? ` ${m} Mon.` : ""}`;
    }
    return date || "";
  }

  renderCard() {
    if (!this._hass || !this.config) return;
    if (!this.shadowRoot) this.attachShadow({mode:"open"});

    const configured=this.config.entity ? this._hass.states[this.config.entity] : null;
    const aquarium=configured || this.find(["aquarium","reef_aquarium"]);
    const prefix=this.aquariumPrefix(aquarium);
    const f=(names,domain="sensor")=>this.find(names,domain,prefix);

    const operating=f(["betriebsstatus","feeding_status"]);
    const overall=f(["gesamtstatus","overall_status"]);
    const temperature=f(["temperatur","temperature","temperature_status","temperatur_status","wasser_temperatur"]);
    const salinity=f(["salinitat","salinity","salinity_status","salinitat_status","salzgehalt"]);
    const ph=f(["ph","ph_status","ph_wert"]);
    const redox=f(["redox","redox_status","orp","orp_status"]);
    const conductivity=f(["leitfahigkeit","leitfaehigkeit","conductivity","conductivity_status"]);
    const waterLevel=f(["wasserstand","water_level","wasserstand_status"]);
    const waterValues=f(["wasserwerte","water_values"]);
    const icp=f(["icp","reef_icp"]);
    const alarms=f(["aktive_alarme","active_alarms"]);
    const tempControl=f(["temperaturregelung_status","temperature_control_status"]);
    const atoControl=f(["wasserstandsregelung","ato_control"],"switch");
    const feeding=f(["futterungsmodus","feeding_mode"],"switch");
    const maintenance=f(["wartungsmodus","maintenance_mode"],"switch");

    const live=[
      ["Temperatur",temperature,"mdi:thermometer"],
      ["Salinität",salinity,"mdi:waves"]
    ].filter(x=>this.available(x[1]));

    const more=[
      ["pH",ph,"mdi:ph"],
      ["Redox",redox,"mdi:flash-outline"],
      ["Leitfähigkeit",conductivity,"mdi:lightning-bolt-outline"]
    ].filter(x=>this.available(x[1]));

    const values=(waterValues?.attributes?.values && typeof waterValues.attributes.values==="object") ? waterValues.attributes.values : {};
    const wanted=[
      ["KH",["kh","alkalinity","carbonate_hardness"]],
      ["Calcium",["calcium","ca"]],
      ["Magnesium",["magnesium","mg"]],
      ["Nitrat",["nitrate","nitrat","no3"]],
      ["Phosphat",["phosphate","phosphat","po4"]]
    ];
    const icpValues=wanted.map(([l,a])=>[l,this.icpValue(values,a)]).filter(x=>x[1]!==null);

    const rawHints=[
      ...((alarms?.attributes?.alarms||[]).map(x=>typeof x==="string" ? x : (x.message||x.reason||"Aktiver Alarm"))),
      ...((overall?.attributes?.issues||[]))
    ];
    const hints=[], seen=new Set();
    for (const raw of rawHints) {
      if (!raw) continue;
      const text=String(raw).trim().replace(/^temperature:/i,"Temperatur:");
      const key=this.norm(text);
      if (!seen.has(key)) { seen.add(key); hints.push(text); }
    }

    const overallState=overall?.state || "OK";
    const on=this.norm(overallState);
    const overallClass=on.includes("kritisch") ? "bad" : (on.includes("warn")||on.includes("achtung")) ? "warn" : "good";

    // Dynamic operating mode, highest priority first.
    // Prefer the real configured actuator state instead of relying only on text status.
    let operation=operating?.state || "Normalbetrieb", operationClass="good", operationIcon="mdi:check-circle";
    const opNorm=this.norm(operation);
    const tempNorm=this.norm(tempControl?.state || tempControl?.attributes?.status || "");
    const heaterId=tempControl?.attributes?.heater_entity || null;
    const heaterEntity=this.stateById(heaterId);
    const heaterOn=heaterEntity?.state==="on" || this.norm(tempControl?.attributes?.heater_state)==="on";
    const atoStatus=this.norm(atoControl?.attributes?.status || atoControl?.attributes?.last_action || "");
    const atoId=atoControl?.attributes?.ato_entity || atoControl?.attributes?.pump_entity || atoControl?.attributes?.entity_id || null;
    const atoEntity=this.stateById(atoId);
    const atoOn=atoEntity?.state==="on";

    if (maintenance?.state==="on" || opNorm.includes("wart")) {
      operation="Wartung"; operationClass="warn"; operationIcon="mdi:tools";
    } else if (feeding?.state==="on" || opNorm.includes("futter")) {
      operation="Fütterung"; operationClass="feeding"; operationIcon="mdi:fish";
    } else if (atoOn || atoStatus.includes("nachfull") || atoStatus.includes("fullt") || opNorm.includes("nachfull")) {
      operation="Nachfüllung"; operationClass="water"; operationIcon="mdi:water-plus";
    } else if (heaterOn || tempNorm.includes("heizen") || opNorm.includes("heiz")) {
      operation="Heizbetrieb"; operationClass="heating"; operationIcon="mdi:radiator";
    } else {
      operation="Normalbetrieb"; operationClass="good"; operationIcon="mdi:check-circle";
    }

    const title=aquarium?.state || "Aquarium";
    const meta=icp?.attributes || {};
    const provider=meta.provider || meta.icp_provider || meta.lab || meta.source || "";
    const date=meta.analysis_date || meta.icp_analysis_date || meta.date || "";
    const age=meta.analysis_age_days ?? meta.icp_analysis_age_days;
    const connected=this.available(icp);

    const wlClass=this.statusClass(waterLevel);
    const wlStatus=this.statusText(waterLevel) || waterLevel?.attributes?.status || "";
    const wlHtml=this.available(waterLevel) ? `
      <div class="waterline clickable ${wlClass}" data-entity="${waterLevel.entity_id}">
        <div class="wlleft"><ha-icon icon="mdi:waves-arrow-up"></ha-icon><span>Wasserstand</span></div>
        <div class="wlright"><b>${this.format(waterLevel)}</b>${wlStatus ? `<small>${wlStatus}</small>`:""}</div>
      </div>` : "";

    this.shadowRoot.innerHTML=`
      <style>
        :host{display:block} ha-card{overflow:hidden;border-radius:22px}
        .hero{padding:14px 16px 13px;background:radial-gradient(circle at 88% 0%,rgba(0,188,212,.14),transparent 44%),radial-gradient(circle at 5% 100%,rgba(0,150,136,.08),transparent 38%)}
        .top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
        .eye{font-size:9px;letter-spacing:.16em;font-weight:800;color:var(--secondary-text-color)}
        .title{font-size:20px;line-height:1.15;font-weight:750;margin:4px 0 8px}
        .mode{display:inline-flex;gap:7px;align-items:center;padding:4px 8px;border-radius:18px;background:rgba(127,127,127,.10);font-size:11px}
        .mode ha-icon{--mdc-icon-size:14px}.mode.good ha-icon{color:#66bb6a}.mode.warn ha-icon{color:#fbc02d}.mode.feeding ha-icon{color:#29b6f6}.mode.water ha-icon{color:#29b6f6}.mode.heating ha-icon{color:#ff9800}
        .right{min-width:80px;text-align:right;font-size:9px;color:var(--secondary-text-color)}.right b{display:block;margin-top:2px;font-size:14px}.right.good b{color:#66bb6a}.right.warn b{color:#fbc02d}.right.bad b{color:#ef5350}
        .sec{padding:0 13px 12px}.h{font-size:10px;font-weight:800;letter-spacing:.06em;color:var(--secondary-text-color);margin:3px 2px 7px;text-transform:uppercase}
        .grid,.actions,.mini{display:grid;grid-template-columns:1fr 1fr;gap:7px}
        .live,.box,.iv,.waterline{background:rgba(127,127,127,.075);border-radius:14px}
        .live{padding:9px 11px 8px;min-height:68px}.lbl{display:flex;gap:6px;align-items:center;font-size:10px;color:var(--secondary-text-color)}.lbl ha-icon{--mdc-icon-size:18px}
        .v{font-size:21px;line-height:1.15;font-weight:800;margin:7px 0 2px}.st{font-size:9px;color:var(--secondary-text-color)}
        .good .v,.good .lbl ha-icon{color:#66bb6a;text-shadow:0 0 11px rgba(102,187,106,.35)}.warn .v,.warn .lbl ha-icon{color:#fbc02d;text-shadow:0 0 11px rgba(251,192,45,.35)}.bad .v,.bad .lbl ha-icon{color:#ef5350;text-shadow:0 0 11px rgba(239,83,80,.45)}
        .clickable{cursor:pointer;transition:transform .12s ease,background .12s ease}.clickable:active{transform:scale(.985);background:rgba(127,127,127,.14)}
        .waterline{margin-top:7px;padding:8px 11px;display:flex;align-items:center;justify-content:space-between}.wlleft{display:flex;align-items:center;gap:7px;font-size:11px}.wlleft ha-icon{--mdc-icon-size:18px}.wlright{text-align:right;font-size:11px}.wlright b{display:block}.wlright small{font-size:8px;color:var(--secondary-text-color)}.waterline.good .wlleft ha-icon,.waterline.good b{color:#66bb6a}.waterline.warn .wlleft ha-icon,.waterline.warn b{color:#fbc02d}.waterline.bad .wlleft ha-icon,.waterline.bad b{color:#ef5350}
        .box{padding:10px;text-align:center;font-size:12px}.box.on{background:rgba(41,182,246,.12)}
        .hints{background:rgba(127,127,127,.065);border-radius:14px;padding:9px 11px;font-size:10px}.hint+.hint{margin-top:5px}
        .icps{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.iv{padding:7px 4px;text-align:center;min-width:0}.iv .il{font-size:8px;color:var(--secondary-text-color)}.iv .in{font-size:14px;font-weight:750;margin-top:3px;white-space:nowrap}.iv .iu{font-size:7px;font-weight:400;color:var(--secondary-text-color);margin-left:2px}
        .meta{font-size:8px;color:var(--secondary-text-color);margin:7px 2px 0}.expand{text-align:center;padding:9px;border-top:1px solid rgba(127,127,127,.10);font-size:10px;cursor:pointer}
        .mini{padding:0 13px 13px}.mini .live{min-height:52px}.mini .v{font-size:14px}
        @media(max-width:360px){.title{font-size:18px}.icps{grid-template-columns:repeat(3,1fr)}}
      </style>
      <ha-card>
        <div class="hero">
          <div class="top">
            <div><div class="eye">REEF CONTROL</div><div class="title">${title}</div>
              <div class="mode ${operationClass}"><ha-icon icon="${operationIcon}"></ha-icon>${operation}</div>
            </div>
            <div class="right ${overallClass}">Gesamtstatus<b>${overallState}</b></div>
          </div>
        </div>

        ${live.length ? `<div class="sec"><div class="h">Live-Wasserwerte</div><div class="grid">
          ${live.map(([l,s,i])=>`<div class="live clickable ${this.statusClass(s)}" data-entity="${s.entity_id}">
            <div class="lbl"><ha-icon icon="${i}"></ha-icon>${l}</div><div class="v">${this.format(s)}</div><div class="st">${this.statusText(s)}</div>
          </div>`).join("")}
        </div>${wlHtml}</div>` : (wlHtml ? `<div class="sec"><div class="h">Live-Wasserwerte</div>${wlHtml}</div>`:"")}

        ${(feeding||maintenance) ? `<div class="sec"><div class="h">Schnellaktionen</div><div class="actions">
          ${feeding ? `<div class="box action ${feeding.state==="on"?"on":""}" data-action="feed">🐟 Fütterung</div>`:""}
          ${maintenance ? `<div class="box action ${maintenance.state==="on"?"on":""}" data-action="maint">🔧 Wartung</div>`:""}
        </div></div>`:""}

        ${hints.length ? `<div class="sec"><div class="h">Aktuelle Hinweise</div><div class="hints">${hints.map(x=>`<div class="hint">⚠ ${x}</div>`).join("")}</div></div>`:""}

        ${icpValues.length ? `<div class="sec"><div class="h">Letzte Wasserwerte / ICP</div><div class="icps">
          ${icpValues.map(([l,x])=>{const q=this.formatIcp(x);return `<div class="iv"><div class="il">${l}</div><div class="in">${q.value}<span class="iu">${q.unit}</span></div></div>`}).join("")}
        </div><div class="meta">ICP: ${connected ? "Verbunden":"Nicht verbunden"}${provider ? ` · ${provider}`:""}${(age!==undefined&&age!==null)||date ? ` · ${this.ageText(age,date)}`:""}</div></div>`:""}

        ${more.length ? `<div class="expand">${this.detailsOpen ? "Weniger anzeigen ▲":"Weitere Werte anzeigen ▼"}</div>
          ${this.detailsOpen ? `<div class="mini">${more.map(([l,s,i])=>`<div class="live clickable ${this.statusClass(s)}" data-entity="${s.entity_id}">
            <div class="lbl"><ha-icon icon="${i}"></ha-icon>${l}</div><div class="v">${this.format(s)}</div>
          </div>`).join("")}</div>`:""}`:""}
      </ha-card>`;

    this.shadowRoot.querySelectorAll("[data-entity]").forEach(el=>{
      el.addEventListener("click",()=>this.moreInfo(this._hass.states[el.dataset.entity]));
    });
    this.shadowRoot.querySelector('[data-action="feed"]')?.addEventListener("click",()=>this.toggle(feeding));
    this.shadowRoot.querySelector('[data-action="maint"]')?.addEventListener("click",()=>this.toggle(maintenance));
    this.shadowRoot.querySelector(".expand")?.addEventListener("click",()=>{this.detailsOpen=!this.detailsOpen;this.renderCard();});
  }
}

customElements.define("reef-control-card", ReefControlCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type:"reef-control-card",
  name:"Reef Control Card",
  description:"Kompakte Reef-Control-Aquariumkarte"
});
