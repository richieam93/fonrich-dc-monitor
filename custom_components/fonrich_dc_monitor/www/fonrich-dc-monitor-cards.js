class FonrichBaseCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this.attachShadow({mode: 'open'});
  }
  getCardSize() { return 4; }
  _state(entity) { return entity ? this._hass.states[entity] : undefined; }
  _fmt(entity, fallback='-') {
    const s = this._state(entity);
    if (!s) return fallback;
    const unit = s.attributes.unit_of_measurement || '';
    return `${s.state}${unit ? ' ' + unit : ''}`;
  }
  _findEntity(domain, controller, needle) {
    controller = (controller || '').toLowerCase();
    needle = (needle || '').toLowerCase();
    const entries = Object.entries(this._hass.states);
    for (const [id, state] of entries) {
      if (!id.startsWith(domain + '.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (friendly.includes(controller) && friendly.includes(needle)) return id;
    }
    return undefined;
  }
  _row(label, value, cls='') { return `<div class="row ${cls}"><span>${label}</span><b>${value}</b></div>`; }
  _detectChannelCount(controller) {
    let max = 0;
    const ctrl = (controller || '').toLowerCase();
    for (const [id, state] of Object.entries(this._hass.states)) {
      if (!id.startsWith('sensor.')) continue;
      const friendly = (state.attributes.friendly_name || '').toLowerCase();
      if (!friendly.includes(ctrl)) continue;
      const match = friendly.match(/kanal\s+(\d+)\s+strom/);
      if (match) max = Math.max(max, Number(match[1]));
    }
    return max || 8;
  }
  _channelLabel(entity, fallback) {
    const s = this._state(entity);
    const desc = s?.attributes?.channel_description;
    return desc && !String(desc).toLowerCase().startsWith('kanal ') ? desc : fallback;
  }
  _styles() { return `<style>
    ha-card{padding:16px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.box{border:1px solid var(--divider-color);border-radius:12px;padding:12px}.row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--divider-color)}.row:last-child{border-bottom:0}.bad b,.bad{color:var(--error-color)}.ok b{color:var(--success-color)}.muted{color:var(--secondary-text-color)}.channels{display:grid;grid-template-columns:repeat(2,1fr);gap:4px 12px}.title{font-size:18px;font-weight:600;margin-bottom:12px}.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--secondary-background-color);margin-right:4px;margin-bottom:4px} button{background:var(--primary-color);color:var(--text-primary-color);border:0;border-radius:8px;padding:8px 10px;cursor:pointer;margin-right:6px;margin-top:6px}</style>`; }
}

class FonrichOverviewCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich DC Übersicht', controllers: ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3']}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const controllers = this.config.controllers || ['V1 / Kasten 1','V2 / Kasten 2','V3 / Kasten 3'];
    let html = `${this._styles()}<ha-card><div class="title">${this.config.title || 'Fonrich DC Übersicht'}</div><div class="grid">`;
    for (const c of controllers) {
      const voltage=this._findEntity('sensor',c,'spannung');
      const current=this._findEntity('sensor',c,'total strom');
      const trip=this._findEntity('sensor',c,'trip status 1');
      const alarm=this._findEntity('sensor',c,'alarm status 1');
      const arc=this._findEntity('sensor',c,'lichtbogen alarm maske');
      const tripVal=this._state(trip)?.state; const alarmVal=this._state(alarm)?.state; const arcVal=this._state(arc)?.state;
      const bad=(tripVal && tripVal !== '0') || (alarmVal && alarmVal !== '0') || (arcVal && arcVal !== '0');
      html += `<div class="box"><h3>${c}</h3>`;
      html += this._row('Spannung',this._fmt(voltage));
      html += this._row('Total Strom',this._fmt(current));
      html += this._row('Trip',this._fmt(trip), bad?'bad':'ok');
      html += this._row('Alarm',this._fmt(alarm), bad?'bad':'ok');
      html += this._row('Lichtbogen-Maske',this._fmt(arc), bad?'bad':'ok');
      html += `</div>`;
    }
    html += `</div></ha-card>`;
    this.shadowRoot.innerHTML=html;
  }
}

class FonrichControllerCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich Controller', controller: 'V1 / Kasten 1', show_buttons: true}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const c=this.config.controller || 'V1 / Kasten 1';
    let html=`${this._styles()}<ha-card><div class="title">${this.config.title || c}</div>`;
    html += this._row('Spannung', this._fmt(this._findEntity('sensor',c,'spannung')));
    html += this._row('Total Strom', this._fmt(this._findEntity('sensor',c,'total strom')));
    html += this._row('Online Hall Kanäle', this._fmt(this._findEntity('sensor',c,'online hall')));
    html += this._row('Trip Status 1', this._fmt(this._findEntity('sensor',c,'trip status 1')));
    html += this._row('Alarm Status 1', this._fmt(this._findEntity('sensor',c,'alarm status 1')));
    html += `<h4>Kanäle</h4><div class="channels">`;
    const channelCount = Number(this.config.channel_count || this._detectChannelCount(c));
    for(let i=1;i<=channelCount;i++) {
      const entity = this._findEntity('sensor',c,`kanal ${i} strom`);
      html += this._row(this._channelLabel(entity, 'Kanal '+i), this._fmt(entity));
    }
    html += `</div>`;
    if (this.config.show_buttons !== false) {
      html += `<div><button data-service="clear_alarm_trip">Alarm/Trip löschen</button><button data-service="clear_arc_history">Historie löschen</button><button data-service="arc_selftest">Selbsttest</button></div>`;
    }
    html += `</ha-card>`;
    this.shadowRoot.innerHTML=html;
    this.shadowRoot.querySelectorAll('button').forEach(btn => btn.addEventListener('click', ev => {
      this._hass.callService('fonrich_dc_monitor', ev.currentTarget.dataset.service, {controller: c});
    }));
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
    if (!active.length) html += `<div class="ok">Keine aktiven Binary-Alarm-Sensoren gefunden.</div>`;
    else html += active.map(a=>`<div class="pill bad">${a}</div>`).join('');
    html += `</ha-card>`;
    this.shadowRoot.innerHTML=html;
  }
}


class FonrichStringsCard extends FonrichBaseCard {
  static getStubConfig() { return {title: 'Fonrich String-Ströme', controller: 'V1 / Kasten 1', max_current: 15, channel_count: 8}; }
  set hass(hass) { this._hass = hass; this.render(); }
  render() {
    if (!this.shadowRoot || !this._hass) return;
    const c=this.config.controller || 'V1 / Kasten 1';
    const max=parseFloat(this.config.max_current || 15) || 15;
    let html=`${this._styles()}<style>.barwrap{height:12px;border-radius:999px;background:var(--secondary-background-color);overflow:hidden;margin-top:3px}.bar{height:12px;background:var(--primary-color);border-radius:999px}.stringrow{display:grid;grid-template-columns:70px 80px 1fr;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--divider-color)}.stringrow:last-child{border-bottom:0}.alarmtext{color:var(--error-color);font-weight:600}</style><ha-card><div class="title">${this.config.title || 'Fonrich String-Ströme'} - ${c}</div>`;
    const channelCount = Number(this.config.channel_count || this._detectChannelCount(c));
    html += `<div class="muted">Anzeige der konfigurierten Kanäle mit Beschreibung. max_current und channel_count können im Visual Editor angepasst werden.</div>`;
    html += `<div>`;
    for(let i=1;i<=channelCount;i++) {
      const currentEntity=this._findEntity('sensor',c,`kanal ${i} strom`);
      const alarmEntity=this._findEntity('binary_sensor',c,`kanal ${i} lichtbogen alarm`);
      const state=this._state(currentEntity);
      const raw=parseFloat(state?.state || 0);
      const width=Math.max(0, Math.min(100, (raw/max)*100));
      const alarm=this._state(alarmEntity)?.state === 'on';
      const label = this._channelLabel(currentEntity, `Kanal ${i}`);
      html += `<div class="stringrow ${alarm?'bad':''}"><div>${label}</div><b>${this._fmt(currentEntity)}</b><div><div class="barwrap"><div class="bar" style="width:${width}%"></div></div>${alarm?'<div class="alarmtext">Lichtbogen Alarm</div>':''}</div></div>`;
    }
    html += `</div></ha-card>`;
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
    this.innerHTML = `<div class="card-config">
      <ha-textfield data-key="title" label="Titel" value="${title}"></ha-textfield>
      <ha-textfield data-key="controller" label="Controller-Name für Einzelkarten" value="${controller}"></ha-textfield>
      <ha-textfield data-key="controllers" label="Controller-Liste für Übersicht/Alarme, Komma getrennt" value="${controllers}"></ha-textfield>
      <ha-textfield data-key="max_current" label="Max Strom für Balkenkarte (A)" type="number" value="${maxCurrent}"></ha-textfield>
      <ha-textfield data-key="channel_count" label="Anzahl Kanäle anzeigen" type="number" value="${channelCount}"></ha-textfield>
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
  }
  _changed(changes){ this._config={...this._config,...changes}; this.dispatchEvent(new CustomEvent('config-changed',{detail:{config:this._config},bubbles:true,composed:true})); }
}
customElements.define('fonrich-universal-card-editor', FonrichUniversalCardEditor);

FonrichControllerCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichOverviewCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichAlarmsCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');
FonrichStringsCard.getConfigElement = () => document.createElement('fonrich-universal-card-editor');

customElements.define('fonrich-overview-card', FonrichOverviewCard);
customElements.define('fonrich-controller-card', FonrichControllerCard);
customElements.define('fonrich-alarms-card', FonrichAlarmsCard);
customElements.define('fonrich-strings-card', FonrichStringsCard);
window.customCards = window.customCards || [];
window.customCards.push({type:'fonrich-overview-card', name:'Fonrich DC Übersicht', description:'Übersicht über alle Fonrich Controller'});
window.customCards.push({type:'fonrich-controller-card', name:'Fonrich Controller', description:'Detailkarte für einen Fonrich Controller'});
window.customCards.push({type:'fonrich-alarms-card', name:'Fonrich Alarme', description:'Aktive Fonrich Alarm-/Problem-Sensoren'});
window.customCards.push({type:'fonrich-strings-card', name:'Fonrich String-Ströme', description:'Kanalströme mit Kanalbeschreibung als Balkenanzeige'});
