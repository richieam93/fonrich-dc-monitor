// Fonrich DC Monitor Lovelace cards - v0.7.0
(() => {
  const CARD_VERSION = '0.7.0';

  class FonrichBaseCard extends HTMLElement {
    setConfig(config) {
      this.config = config || {};
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    }

    set hass(hass) {
      this._hass = hass;
      this.render();
    }

    getCardSize() { return 8; }

    _state(id) { return id ? this._hass?.states?.[id] : undefined; }
    _num(id) {
      const value = Number.parseFloat(this._state(id)?.state);
      return Number.isFinite(value) ? value : null;
    }
    _fmt(id, digits = null) {
      const state = this._state(id);
      if (!state || ['unknown', 'unavailable', 'none', ''].includes(String(state.state).toLowerCase())) return '–';
      const raw = Number.parseFloat(state.state);
      const value = Number.isFinite(raw) && digits !== null ? raw.toFixed(digits) : state.state;
      const unit = state.attributes.unit_of_measurement || '';
      return `${value}${unit ? ` ${unit}` : ''}`;
    }

    _controllers() {
      const bySlave = new Map();
      for (const [entityId, state] of Object.entries(this._hass?.states || {})) {
        const slave = Number(state.attributes.controller_slave);
        if (!Number.isFinite(slave)) continue;
        if (!bySlave.has(slave)) {
          bySlave.set(slave, {
            slave,
            name: state.attributes.controller || `Kasten Slave ${slave}`,
            online: null,
            message: null,
            voltage: null,
            totalCurrent: null,
            totalPower: null,
            buttons: [],
            channels: new Map(),
          });
        }
        const controller = bySlave.get(slave);
        if (state.attributes.controller) controller.name = state.attributes.controller;
        const friendly = String(state.attributes.friendly_name || '').toLowerCase();
        const channel = Number(state.attributes.channel);

        if (entityId.startsWith('binary_sensor.') && friendly.includes('status online')) controller.online = entityId;
        if (entityId.startsWith('sensor.') && friendly.includes('meldungen')) controller.message = entityId;
        if (entityId.startsWith('sensor.') && !Number.isFinite(channel)) {
          if (friendly.includes('gesamtstrom')) controller.totalCurrent = entityId;
          else if (friendly.includes('gesamtleistung')) controller.totalPower = entityId;
          else if (friendly.endsWith('spannung') || friendly.includes(' kasten') && friendly.includes('spannung')) controller.voltage = entityId;
        }
        if (entityId.startsWith('button.')) controller.buttons.push(entityId);

        if (Number.isFinite(channel) && channel > 0 && entityId.startsWith('sensor.')) {
          if (!controller.channels.has(channel)) {
            controller.channels.set(channel, {
              channel,
              description: state.attributes.channel_description || '',
              current: null,
              voltage: null,
              power: null,
              maxCurrent: null,
            });
          }
          const item = controller.channels.get(channel);
          if (state.attributes.channel_description) item.description = state.attributes.channel_description;
          if (friendly.includes('max.') && friendly.includes('ampere')) item.maxCurrent = entityId;
          else if (friendly.includes('ampere')) item.current = entityId;
          else if (friendly.includes('spannung')) item.voltage = entityId;
          else if (friendly.includes('leistung')) item.power = entityId;
        }
      }
      return [...bySlave.values()].sort((a, b) => a.slave - b.slave);
    }

    _globalMessage() {
      for (const [entityId, state] of Object.entries(this._hass?.states || {})) {
        if (!entityId.startsWith('sensor.')) continue;
        const friendly = String(state.attributes.friendly_name || '').toLowerCase();
        if (friendly === 'fonrich meldungen' || friendly.includes('fonrich meldungen')) return entityId;
      }
      return null;
    }

    _press(entityId) {
      if (entityId) this._hass.callService('button', 'press', { entity_id: entityId });
    }

    _styles() {
      return `<style>
        :host{display:block}
        ha-card{overflow:hidden;border-radius:20px}
        .hero{padding:20px;background:linear-gradient(135deg,var(--primary-color),color-mix(in srgb,var(--primary-color) 55%,#111));color:var(--text-primary-color)}
        .title{font-size:22px;font-weight:750}.sub{opacity:.88;margin-top:4px;font-size:13px}
        .message{margin-top:14px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.15);font-weight:600}
        .message.ok{background:rgba(20,180,90,.20)}.message.bad{background:rgba(210,40,40,.28)}
        .content{padding:14px;display:grid;gap:14px}
        .controller{border:1px solid var(--divider-color);border-radius:18px;overflow:hidden;background:var(--card-background-color)}
        .controller-head{padding:14px 16px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px;background:var(--secondary-background-color)}
        .controller-title{font-size:19px;font-weight:700}.slave{font-size:12px;color:var(--secondary-text-color);margin-top:2px}
        .status{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}
        .status.online{background:color-mix(in srgb,var(--success-color) 18%,transparent);color:var(--success-color)}
        .status.offline{background:color-mix(in srgb,var(--error-color) 18%,transparent);color:var(--error-color)}
        .dot{width:8px;height:8px;border-radius:50%;background:currentColor}
        .summary{padding:12px 16px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
        .metric{border:1px solid var(--divider-color);border-radius:14px;padding:11px}.metric-label{font-size:12px;color:var(--secondary-text-color)}.metric-value{font-size:20px;font-weight:750;margin-top:3px}
        .controller-message{margin:0 16px 12px;padding:9px 11px;border-radius:11px;background:var(--secondary-background-color);font-size:13px}
        .controller-message.bad{border-left:4px solid var(--error-color)}
        .buttons{padding:0 16px 12px;display:flex;flex-wrap:wrap;gap:8px}
        button{border:0;border-radius:10px;padding:8px 11px;background:var(--primary-color);color:var(--text-primary-color);cursor:pointer;font-weight:600}
        .channels{padding:0 16px 16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:10px}
        .channel{border:1px solid var(--divider-color);border-radius:15px;padding:12px}
        .channel-title{font-weight:700;margin-bottom:8px}.channel-desc{font-size:12px;color:var(--secondary-text-color);margin-top:2px}
        .channel-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
        .small{background:var(--secondary-background-color);border-radius:10px;padding:8px}.small-label{font-size:11px;color:var(--secondary-text-color)}.small-value{font-size:16px;font-weight:700;margin-top:2px}
        .empty{padding:20px;color:var(--secondary-text-color)}
        @media(max-width:650px){.summary{grid-template-columns:1fr}.controller-head{display:block}.status{margin-top:8px}.channels{grid-template-columns:1fr}}
      </style>`;
    }

    _controllerHtml(controller, showButtons = true) {
      const onlineState = this._state(controller.online);
      const online = onlineState?.state === 'on';
      const messageState = this._state(controller.message)?.state || (online ? 'OK' : `${controller.name} offline`);
      const messageBad = String(messageState).toUpperCase() !== 'OK';
      const channels = [...controller.channels.values()].sort((a, b) => a.channel - b.channel);

      let html = `<section class="controller">
        <div class="controller-head">
          <div><div class="controller-title">${controller.name}</div><div class="slave">Modbus-Adresse ${controller.slave}</div></div>
          <div class="status ${online ? 'online' : 'offline'}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div>
        </div>
        <div class="summary">
          <div class="metric"><div class="metric-label">Spannung</div><div class="metric-value">${this._fmt(controller.voltage,0)}</div></div>
          <div class="metric"><div class="metric-label">Gesamtstrom</div><div class="metric-value">${this._fmt(controller.totalCurrent,2)}</div></div>
          <div class="metric"><div class="metric-label">Gesamtleistung</div><div class="metric-value">${this._fmt(controller.totalPower,0)}</div></div>
        </div>
        <div class="controller-message ${messageBad ? 'bad' : ''}"><b>Meldungen:</b> ${messageState}</div>`;

      if (showButtons && controller.buttons.length) {
        html += '<div class="buttons">';
        for (const buttonId of controller.buttons) {
          const friendly = this._state(buttonId)?.attributes?.friendly_name || buttonId;
          html += `<button data-entity="${buttonId}">${friendly.replace(`${controller.name} `, '')}</button>`;
        }
        html += '</div>';
      }

      html += '<div class="channels">';
      for (const item of channels) {
        const title = `Kanal ${String(item.channel).padStart(2, '0')}`;
        html += `<div class="channel"><div class="channel-title">${title}${item.description ? `<div class="channel-desc">${item.description}</div>` : ''}</div>
          <div class="channel-grid">
            <div class="small"><div class="small-label">Ampere</div><div class="small-value">${this._fmt(item.current,3)}</div></div>
            <div class="small"><div class="small-label">Spannung</div><div class="small-value">${this._fmt(item.voltage,0)}</div></div>
            <div class="small"><div class="small-label">Leistung</div><div class="small-value">${this._fmt(item.power,0)}</div></div>
            <div class="small"><div class="small-label">Max. Ampere heute</div><div class="small-value">${this._fmt(item.maxCurrent,3)}</div></div>
          </div></div>`;
      }
      html += '</div></section>';
      return html;
    }

    _bindButtons() {
      this.shadowRoot?.querySelectorAll('button[data-entity]').forEach((button) => {
        button.addEventListener('click', () => this._press(button.dataset.entity));
      });
    }
  }

  class FonrichKastenOverviewCard extends FonrichBaseCard {
    static getStubConfig() { return { title: 'Fonrich Kästen und Kanäle', show_buttons: true }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const controllers = this._controllers();
      const globalMessageId = this._globalMessage();
      const globalMessage = this._state(globalMessageId)?.state || 'Keine Meldungsentität gefunden';
      const ok = String(globalMessage).toUpperCase() === 'OK';
      let html = `${this._styles()}<ha-card><div class="hero"><div class="title">${this.config.title || 'Fonrich Kästen und Kanäle'}</div><div class="sub">Status, Meldungen, Gesamtwerte und alle Kanäle auf einen Blick</div><div class="message ${ok ? 'ok' : 'bad'}">${globalMessage}</div></div><div class="content">`;
      if (!controllers.length) html += '<div class="empty">Keine Fonrich-Entitäten gefunden.</div>';
      for (const controller of controllers) html += this._controllerHtml(controller, this.config.show_buttons !== false);
      html += '</div></ha-card>';
      this.shadowRoot.innerHTML = html;
      this._bindButtons();
    }
  }

  class FonrichKastenCard extends FonrichBaseCard {
    static getStubConfig() { return { title: 'Fonrich Kasten', slave: 240, show_buttons: true }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const controllers = this._controllers();
      const requested = Number(this.config.slave || 240);
      const controller = controllers.find((item) => item.slave === requested) || controllers[0];
      let html = `${this._styles()}<ha-card><div class="hero"><div class="title">${this.config.title || controller?.name || 'Fonrich Kasten'}</div><div class="sub">Einzelansicht eines Fonrich-Controllers</div></div><div class="content">`;
      html += controller ? this._controllerHtml(controller, this.config.show_buttons !== false) : '<div class="empty">Kein passender Controller gefunden.</div>';
      html += '</div></ha-card>';
      this.shadowRoot.innerHTML = html;
      this._bindButtons();
    }
  }

  class FonrichCardEditor extends HTMLElement {
    setConfig(config) { this._config = config || {}; this.render(); }
    set hass(hass) { this._hass = hass; }
    render() {
      const title = this._config.title || '';
      const slave = Number(this._config.slave || 240);
      const showButtons = this._config.show_buttons !== false;
      this.innerHTML = `<div class="card-config">
        <ha-textfield data-key="title" label="Titel" value="${title}"></ha-textfield>
        <ha-textfield data-key="slave" label="Modbus-Adresse für Einzelkarte" type="number" value="${slave}"></ha-textfield>
        <div style="display:flex;align-items:center;gap:8px;margin-top:12px"><ha-switch data-key="show_buttons" ${showButtons ? 'checked' : ''}></ha-switch><span>Buttons anzeigen</span></div>
      </div>`;
      this.querySelectorAll('ha-textfield').forEach((field) => field.addEventListener('change', (event) => {
        const key = event.currentTarget.dataset.key;
        const value = key === 'slave' ? Number(event.currentTarget.value) : event.currentTarget.value;
        this._changed({ [key]: value });
      }));
      this.querySelector('ha-switch')?.addEventListener('change', (event) => this._changed({ show_buttons: event.currentTarget.checked }));
    }
    _changed(changes) {
      this._config = { ...this._config, ...changes };
      this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this._config }, bubbles: true, composed: true }));
    }
  }

  function safeDefine(name, classFactory) {
    if (customElements.get(name)) return;
    try { customElements.define(name, classFactory()); }
    catch (error) { console.warn(`Fonrich card ${name} konnte nicht registriert werden`, error); }
  }

  safeDefine('fonrich-card-editor', () => FonrichCardEditor);
  FonrichKastenOverviewCard.getConfigElement = () => document.createElement('fonrich-card-editor');
  FonrichKastenCard.getConfigElement = () => document.createElement('fonrich-card-editor');

  safeDefine('fonrich-kasten-overview-card', () => FonrichKastenOverviewCard);
  safeDefine('fonrich-kasten-card', () => FonrichKastenCard);

  // Unique wrapper classes keep old dashboards working without reusing constructors.
  safeDefine('fonrich-modern-production-card', () => class extends FonrichKastenOverviewCard {});
  safeDefine('fonrich-production-overview-card', () => class extends FonrichKastenOverviewCard {});
  safeDefine('fonrich-overview-card', () => class extends FonrichKastenOverviewCard {});
  safeDefine('fonrich-controller-card', () => class extends FonrichKastenCard {});
  safeDefine('fonrich-strings-card', () => class extends FonrichKastenCard {});
  safeDefine('fonrich-energy-card', () => class extends FonrichKastenOverviewCard {});
  safeDefine('fonrich-alarms-card', () => class extends FonrichKastenOverviewCard {});

  window.customCards = window.customCards || [];
  const cards = [
    { type: 'fonrich-kasten-overview-card', name: 'Fonrich Kästen und Kanäle', description: 'Komplette Übersicht mit Online-Status, Meldungen, Buttons, Gesamtwerten und Kanalwerten' },
    { type: 'fonrich-kasten-card', name: 'Fonrich einzelner Kasten', description: 'Ein Kasten mit allen Kanälen und Tagesmaximum' },
  ];
  for (const card of cards) {
    if (!window.customCards.some((item) => item.type === card.type)) window.customCards.push(card);
  }
  window.dispatchEvent(new Event('fonrich-cards-loaded'));
  console.info(`Fonrich DC Monitor cards loaded v${CARD_VERSION}`);
})();
