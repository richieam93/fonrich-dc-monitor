class FonrichBaseCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    if (!this.shadowRoot) this.attachShadow({mode: 'open'});
  }
  getCardSize() { return 4; }
  _state(entity) { return entity ? this._hass?.states?.[entity] : undefined; }
  _num(entity) { const v = parseFloat(this._state(entity)?.state); return Number.isFinite(v) ? v : 0; }
  _fmt(entity, fallback='-') {
    const s = this._state(entity);
    if (!s) return fallback;
    const unit = s.attributes.unit_of_measurement || '';
    return `${s.state}${unit ? ' ' + unit : ''}`;
  }
  _containsAll(text, query) {
    text = String(text || '').toLowerCase();
    return String(query || '').toLowerCase().split(/\s+/).filter(Boolean).every(part => text.includes(part));
  }
  _findEntity(domain, controller, needle) {
    const ctrl = String(controller || '').toLowerCase();
    const entries = Object.entries(this._hass.states);
    for (const [id, state] of entries) {
      if (!id.startsWith(domain + '.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (ctrl && !friendly.includes(ctrl)) continue;
      if (this._containsAll(friendly, needle)) return id;
    }
    return undefined;
  }
  _findChannelEntity(controller, channel, metric) {
    const ctrl = String(controller || '').toLowerCase();
    const metricLower = String(metric || '').toLowerCase();
    for (const [id, state] of Object.entries(this._hass.states)) {
      if (!id.startsWith('sensor.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (ctrl && !friendly.includes(ctrl)) continue;
      if (Number(state.attributes.channel) !== Number(channel)) continue;
      if (!friendly.includes(metricLower)) continue;
      return id;
    }
    // Fallback for entity ids generated from unique ids.
    const chNo = Number(channel);
    const key = metricLower.includes('leistung') || metricLower.includes('watt') ? `ch${chNo}_power` : metricLower.includes('energie') ? `ch${chNo}_energy` : `ch${chNo}_current`;
    for (const [id, state] of Object.entries(this._hass.states)) {
      if (!id.startsWith('sensor.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (ctrl && !friendly.includes(ctrl)) continue;
      if (id.toLowerCase().includes(key)) return id;
    }
    return undefined;
  }
  _row(label, value, cls='') { return `<div class="row ${cls}"><span>${label}</span><b>${value}</b></div>`; }
  _detectChannelCount(controller) {
    let max = 0;
    const ctrl = String(controller || '').toLowerCase();
    for (const [id, state] of Object.entries(this._hass.states)) {
      if (!id.startsWith('sensor.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (ctrl && !friendly.includes(ctrl)) continue;
      const attr = Number(state.attributes.channel);
      if (Number.isFinite(attr) && attr > 0) max = Math.max(max, attr);
      const match = friendly.match(/kanal\s+0*(\d+)/);
      if (match && friendly.includes('strom')) max = Math.max(max, Number(match[1]));
    }
    return max || 8;
  }
  _channelLabel(entity, fallback) {
    const s = this._state(entity);
    const desc = s?.attributes?.channel_description;
    return desc && !String(desc).toLowerCase().startsWith('kanal ') ? String(desc) : fallback;
  }
  _styles() { return `<style>
    ha-card{padding:16px}.title{font-size:18px;font-weight:600;margin-bottom:12px}.subtitle{font-weight:600;margin-top:12px;margin-bottom:6px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.box{border:1px solid var(--divider-color);border-radius:12px;padding:12px}.row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--divider-color)}.row:last-child{border-bottom:0}.bad b,.bad{color:var(--error-color)}.ok b{color:var(--success-color)}.muted{color:var(--secondary-text-color);font-size:12px}.channels{display:grid;grid-template-columns:repeat(2,1fr);gap:4px 12px}.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--secondary-background-color);margin-right:4px;margin-bottom:4px}button{background:var(--primary-color);color:var(--text-primary-color);border:0;border-radius:8px;padding:8px 10px;cursor:pointer;margin-right:6px;margin-top:6px}.barwrap{height:12px;border-radius:999px;background:var(--secondary-background-color);overflow:hidden;margin-top:3px}.bar{height:12px;background:var(--primary-color);border-radius:999px}.stringrow{display:grid;grid-template-columns:minmax(120px,1.5fr) 80px 90px 1fr;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--divider-color)}.stringrow:last-child{border-bottom:0}@media(max-width:700px){.stringrow{grid-template-columns:1fr 80px 90px}.stringrow .barcol{grid-column:1 / -1}.channels{grid-template-columns:1fr}}</style>`; }
}

class FonrichProductionOverviewCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich Produktion', controllers: ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3']}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const controllers = this.config.controllers || ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3'];
    let html = `${this._styles()}<ha-card><div class="title">${this.config.title || 'Fonrich Produktion'}</div><div class="grid">`;
    for (const c of controllers) {
      const voltage = this._findEntity('sensor', c, 'spannung');
      const current = this._findEntity('sensor', c, 'total strom');
      const power = this._findEntity('sensor', c, 'total leistung');
      html += `<div class="box"><h3>${c}</h3>`;
      html += this._row('Volt', this._fmt(voltage));
      html += this._row('Total Ampere', this._fmt(current));
      html += this._row('Total Watt', this._fmt(power));
      html += `</div>`;
    }
    html += `</div></ha-card>`;
    this.shadowRoot.innerHTML = html;
  }
}

class FonrichControllerCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich Controller', controller: 'V1 / Kasten 1', show_buttons: false}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const c=this.config.controller || 'V1 / Kasten 1';
    let html=`${this._styles()}<ha-card><div class="title">${this.config.title || c}</div>`;
    html += this._row('Volt', this._fmt(this._findEntity('sensor',c,'spannung')));
    html += this._row('Total Ampere', this._fmt(this._findEntity('sensor',c,'total strom')));
    html += this._row('Total Watt', this._fmt(this._findEntity('sensor',c,'total leistung')));
    html += `<div class="subtitle">Strings</div><div class="channels">`;
    const channelCount = Number(this.config.channel_count || this._detectChannelCount(c));
    for(let i=1;i<=channelCount;i++) {
      const current = this._findChannelEntity(c, i, 'strom');
      const power = this._findChannelEntity(c, i, 'leistung');
      const label = this._channelLabel(current || power, `Kanal ${String(i).padStart(2,'0')}`);
      html += `<div class="box"><b>${label}</b>${this._row('A', this._fmt(current))}${this._row('W', this._fmt(power))}</div>`;
    }
    html += `</div>`;
    if (this.config.show_buttons === true) {
      html += `<div><button data-service="clear_alarm_trip">Alarm/Trip löschen</button><button data-service="clear_arc_history">Historie löschen</button><button data-service="arc_selftest">Selbsttest</button></div>`;
    }
    html += `</ha-card>`;
    this.shadowRoot.innerHTML=html;
    this.shadowRoot.querySelectorAll('button').forEach(btn => btn.addEventListener('click', ev => {
      this._hass.callService('fonrich_dc_monitor', ev.currentTarget.dataset.service, {controller: c});
    }));
  }
}

class FonrichStringsCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich String-Leistung', controller: 'V1 / Kasten 1', max_current: 15, channel_count: 8}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const c=this.config.controller || 'V1 / Kasten 1';
    const max=parseFloat(this.config.max_current || 15) || 15;
    const voltage=this._findEntity('sensor',c,'spannung');
    let html=`${this._styles()}<ha-card><div class="title">${this.config.title || 'Fonrich String-Leistung'} - ${c}</div>`;
    html += `<div class="muted">Zeigt pro String die wichtigen Produktionswerte: Ampere und Watt. Controller-Spannung: <b>${this._fmt(voltage)}</b></div>`;
    const channelCount = Number(this.config.channel_count || this._detectChannelCount(c));
    html += `<div>`;
    for(let i=1;i<=channelCount;i++) {
      const currentEntity=this._findChannelEntity(c,i,'strom');
      const powerEntity=this._findChannelEntity(c,i,'leistung');
      const raw=this._num(currentEntity);
      const width=Math.max(0, Math.min(100, (raw/max)*100));
      const label=this._channelLabel(currentEntity || powerEntity, `Kanal ${String(i).padStart(2,'0')}`);
      html += `<div class="stringrow"><div><b>${label}</b></div><div>${this._fmt(currentEntity)}</div><div>${this._fmt(powerEntity)}</div><div class="barcol"><div class="barwrap"><div class="bar" style="width:${width}%"></div></div></div></div>`;
    }
    html += `</div></ha-card>`;
    this.shadowRoot.innerHTML=html;
  }
}

class FonrichEnergyCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich Energie', controller: 'V1 / Kasten 1', channel_count: 8}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const c=this.config.controller || 'V1 / Kasten 1';
    const channelCount = Number(this.config.channel_count || this._detectChannelCount(c));
    let html=`${this._styles()}<ha-card><div class="title">${this.config.title || 'Fonrich Energie'} - ${c}</div>`;
    html += `<div class="muted">Nur sichtbar, wenn Energieregister in den Optionen aktiviert sind.</div>`;
    for(let i=1;i<=channelCount;i++) {
      const hi=this._findChannelEntity(c,i,'energie high');
      const lo=this._findChannelEntity(c,i,'energie low');
      const current=this._findChannelEntity(c,i,'strom');
      const label=this._channelLabel(current || hi || lo, `Kanal ${String(i).padStart(2,'0')}`);
      html += this._row(label, `${this._fmt(hi)} / ${this._fmt(lo)}`);
    }
    html += `</ha-card>`;
    this.shadowRoot.innerHTML=html;
  }
}

class FonrichAlarmsCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich aktive Alarme', controllers: ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3']}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const controllers=(this.config.controllers || ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3']).map(x=>x.toLowerCase());
    const active=[];
    for (const [id, s] of Object.entries(this._hass.states)) {
      if (!id.startsWith('binary_sensor.')) continue;
      if (s.state !== 'on') continue;
      const f=(s.attributes.friendly_name || '').toLowerCase();
      if (!controllers.some(c => f.includes(c))) continue;
      active.push(s.attributes.friendly_name || id);
    }
    let html=`${this._styles()}<ha-card><div class="title">${this.config.title || 'Fonrich aktive Alarme'}</div>`;
    if (!active.length) html += `<div class="ok">Keine aktiven Fonrich-Alarm-Binary-Sensoren gefunden.</div><div class="muted">Im Produktionsprofil werden Alarm-Binary-Sensoren standardmässig nicht erstellt.</div>`;
    else html += active.map(a=>`<div class="pill bad">${a}</div>`).join('');
    html += `</ha-card>`;
    this.shadowRoot.innerHTML=html;
  }
}

class FonrichUniversalCardEditor extends HTMLElement {
  setConfig(config) { this._config = config || {}; this.render(); }
  set hass(hass) { this._hass = hass; }
  render() {
    const title=this._config.title || '';
    const controller=this._config.controller || 'V1 / Kasten 1';
    const controllers=(this._config.controllers || ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3']).join(',');
    const maxCurrent=this._config.max_current || 15;
    const channelCount=this._config.channel_count || 8;
    const showButtons=this._config.show_buttons === true;
    this.innerHTML = `<div class="card-config">
      <ha-textfield data-key="title" label="Titel" value="${title}"></ha-textfield>
      <ha-textfield data-key="controller" label="Controller-Name für Einzelkarten" value="${controller}"></ha-textfield>
      <ha-textfield data-key="controllers" label="Controller-Liste für Übersicht/Alarme, Komma getrennt" value="${controllers}"></ha-textfield>
      <ha-textfield data-key="max_current" label="Max Strom für Balkenkarte (A)" type="number" value="${maxCurrent}"></ha-textfield>
      <ha-textfield data-key="channel_count" label="Anzahl Kanäle anzeigen" type="number" value="${channelCount}"></ha-textfield>
      <ha-switch data-key="show_buttons" ${showButtons ? 'checked' : ''}></ha-switch> Buttons anzeigen
    </div>`;
    this.querySelectorAll('ha-textfield').forEach(field => {
      field.addEventListener('change', e => {
        const key=e.currentTarget.dataset.key;
        let value=e.currentTarget.value;
        if (key === 'controllers') value = String(value).split(',').map(x=>x.trim()).filter(Boolean);
        if (key === 'max_current') value = Number(value);
        if (key === 'channel_count') value = Number(value);
        this._changed({[key]: value});
      });
    });
    const sw=this.querySelector('ha-switch');
    if (sw) sw.addEventListener('change', e => this._changed({show_buttons: e.currentTarget.checked}));
  }
  _changed(changes){ this._config={...this._config,...changes}; this.dispatchEvent(new CustomEvent('config-changed',{detail:{config:this._config},bubbles:true,composed:true})); }
}
customElements.define('fonrich-universal-card-editor', FonrichUniversalCardEditor);

FonrichProductionOverviewCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichControllerCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichStringsCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichEnergyCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichAlarmsCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');

customElements.define('fonrich-production-overview-card', FonrichProductionOverviewCard);
customElements.define('fonrich-overview-card', FonrichProductionOverviewCard);
customElements.define('fonrich-controller-card', FonrichControllerCard);
customElements.define('fonrich-strings-card', FonrichStringsCard);
customElements.define('fonrich-energy-card', FonrichEnergyCard);
customElements.define('fonrich-alarms-card', FonrichAlarmsCard);
window.customCards = window.customCards || [];
window.customCards.push({type:'fonrich-production-overview-card', name:'Fonrich Produktion', description:'Produktionsübersicht mit Volt, Ampere und Watt'});
window.customCards.push({type:'fonrich-overview-card', name:'Fonrich DC Übersicht', description:'Kompatibilitätskarte: Produktionsübersicht mit Volt, Ampere und Watt'});
window.customCards.push({type:'fonrich-controller-card', name:'Fonrich Controller Produktion', description:'Controllerdetails mit String Ampere und Watt'});
window.customCards.push({type:'fonrich-strings-card', name:'Fonrich String-Leistung', description:'String Ampere und Watt mit Balkenanzeige'});
window.customCards.push({type:'fonrich-energy-card', name:'Fonrich Energie', description:'Energie je String, wenn Energieregister aktiv sind'});
window.customCards.push({type:'fonrich-alarms-card', name:'Fonrich Alarme', description:'Optionale Alarmkarte, wenn Alarm-Binary-Sensoren aktiv sind'});
