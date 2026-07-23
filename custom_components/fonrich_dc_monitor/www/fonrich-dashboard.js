// Fonrich DC Monitor dashboard cards - integration v1.0.0
(() => {
  const VERSION = '1.0.0';
  const DOCS_URL = 'https://github.com/richieam93/fonrich-dc-monitor';
  const LOAD_KEY = `fonrich-dashboard-${VERSION}`;

  if (!(window.__fonrichDashboardLoads instanceof Set)) {
    window.__fonrichDashboardLoads = new Set();
  }
  if (window.__fonrichDashboardLoads.has(LOAD_KEY)) return;
  window.__fonrichDashboardLoads.add(LOAD_KEY);

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  const normalize = (value) => String(value ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

  const parseVIndex = (...values) => {
    for (const value of values) {
      const text = String(value ?? '');
      const patterns = [
        /(?:kasten[\s_/-]*v|\bv)[\s_/-]*0*(\d+)\b/i,
        /kasten[\s_/-]*0*(\d+)\b/i,
      ];
      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) return Number(match[1]);
      }
    }
    return null;
  };

  const isUnavailableState = (state) => {
    if (!state) return true;
    return ['unknown', 'unavailable', 'none', ''].includes(String(state.state).toLowerCase());
  };

  const ACTION_ORDER = [
    'clear_alarm_trip_status',
    'clear_arc_history',
    'arc_selftest',
    'arm_remote_trip_test',
    'remote_trip_test',
    'lightning_message_test',
    'clear_test_messages',
  ];

  const inferActionKey = (entityId, state) => {
    const attrs = state?.attributes || {};
    if (attrs.action_key) return String(attrs.action_key);
    const text = normalize(`${entityId} ${attrs.friendly_name || ''}`);
    if (text.includes('alarm und trip zurucksetzen') || text.includes('alarm trip reset')) return 'clear_alarm_trip_status';
    if (text.includes('lichtbogen historie loschen')) return 'clear_arc_history';
    if (text.includes('lichtbogen selbsttest')) return 'arc_selftest';
    if (text.includes('hauptschalter test freigeben')) return 'arm_remote_trip_test';
    if (text.includes('hauptschalter schutz auslosen')) return 'remote_trip_test';
    if (text.includes('blitzschutz meldetest')) return 'lightning_message_test';
    if (text.includes('testmeldungen zurucksetzen')) return 'clear_test_messages';
    return '';
  };

  const inferRole = (entityId, state) => {
    const attrs = state?.attributes || {};
    if (attrs.fonrich_role) return String(attrs.fonrich_role);

    const domain = entityId.split('.')[0];
    const id = entityId.split('.')[1] || '';
    const text = normalize(`${id} ${attrs.friendly_name || ''}`);

    if (id === 'fonrich_gateway_status' || text === 'fonrich gateway status') return 'gateway_status';
    if (id === 'fonrich_meldungen' || id === 'fonrich_alarmmeldung' || text === 'fonrich meldungen') return 'gateway_messages';
    if (domain === 'binary_sensor' && text.includes('status online')) return 'controller_online';
    if (domain === 'sensor' && (text.endsWith(' meldungen') || text.endsWith(' alarmmeldung'))) return 'controller_messages';
    if (domain === 'sensor' && text.includes('schutz teststatus')) return 'safety_test_status';
    if (domain === 'sensor' && text.includes('gesamtleistung')) return 'controller_total_power';
    if (domain === 'sensor' && text.includes('gesamtstrom')) return 'controller_total_current';

    const channelMatch = `${id} ${attrs.friendly_name || ''}`.match(/kanal[\s_/-]*0*(\d+)[\s_/-]*(ampere|strom|spannung|leistung|max(?:\.|imum)?[\s_/-]*ampere[\s_/-]*heute)/i);
    if (channelMatch) {
      const metric = normalize(channelMatch[2]);
      if (metric.includes('spannung')) return 'channel_voltage';
      if (metric.includes('leistung')) return 'channel_power';
      if (metric.includes('max') && metric.includes('ampere')) return 'channel_daily_max_current';
      return 'channel_current';
    }

    if (domain === 'sensor' && text.endsWith(' spannung')) return 'controller_voltage';
    if (domain === 'button') {
      const action = inferActionKey(entityId, state);
      return ['arm_remote_trip_test', 'remote_trip_test', 'lightning_message_test', 'clear_test_messages'].includes(action)
        ? 'safety_test_button'
        : 'command_button';
    }
    if (domain === 'binary_sensor' && /\bdi\s*\d+/.test(text)) return 'digital_input';
    return '';
  };

  const looksLikeFonrich = (entityId, state) => {
    const attrs = state?.attributes || {};
    if (attrs.fonrich_integration === true) return true;
    if (Number.isFinite(Number(attrs.controller_slave))) return true;
    if (/^(sensor|binary_sensor|button)\.kasten_v\d+_/i.test(entityId)) return true;
    if (/^sensor\.fonrich_(gateway_status|meldungen|alarmmeldung)$/i.test(entityId)) return true;
    const friendly = String(attrs.friendly_name || '');
    return /kasten\s+v\d+/i.test(friendly) && ['sensor', 'binary_sensor', 'button'].includes(entityId.split('.')[0]);
  };

  const controllerInfo = (entityId, state) => {
    const attrs = state?.attributes || {};
    const friendly = attrs.friendly_name || '';
    const vIndex = parseVIndex(attrs.controller, attrs.controller_id, entityId, friendly);
    const slaveValue = Number(attrs.controller_slave);
    const slave = Number.isFinite(slaveValue) ? slaveValue : null;
    const name = String(attrs.controller || (vIndex ? `Kasten V${vIndex}` : (slave !== null ? `Kasten Slave ${slave}` : 'Fonrich Kasten')));
    const id = String(attrs.controller_id || (vIndex ? `kasten_v${vIndex}` : (slave !== null ? `slave_${slave}` : normalize(name).replaceAll(' ', '_'))));
    return { id, name, vIndex, slave };
  };

  const channelNumber = (entityId, state) => {
    const attrs = state?.attributes || {};
    const direct = Number(attrs.channel);
    if (Number.isFinite(direct) && direct > 0) return direct;
    const match = `${entityId} ${attrs.friendly_name || ''}`.match(/kanal[\s_/-]*0*(\d+)/i);
    return match ? Number(match[1]) : null;
  };

  const inputNumber = (entityId, state) => {
    const attrs = state?.attributes || {};
    const direct = Number(attrs.di_index);
    if (Number.isFinite(direct) && direct > 0) return direct;
    const match = `${entityId} ${attrs.friendly_name || ''}`.match(/\bdi[\s_/-]*0*(\d+)/i);
    return match ? Number(match[1]) : null;
  };

  const assignPreferred = (target, key, entityId, priority) => {
    if (!entityId) return;
    target._priority ||= {};
    if (!target[key] || priority >= Number(target._priority[key] || 0)) {
      target[key] = entityId;
      target._priority[key] = priority;
    }
  };

  const buildFonrichModel = (hass) => {
    const controllers = new Map();
    let gatewayStatus = null;
    let gatewayMessages = null;

    for (const [entityId, state] of Object.entries(hass?.states || {})) {
      if (!looksLikeFonrich(entityId, state)) continue;
      const attrs = state.attributes || {};
      const priority = attrs.fonrich_integration === true && attrs.fonrich_role ? 3 : 1;
      const role = inferRole(entityId, state);

      if (role === 'gateway_status') {
        gatewayStatus = entityId;
        continue;
      }
      if (role === 'gateway_messages') {
        gatewayMessages = entityId;
        continue;
      }
      if (!role) continue;

      const info = controllerInfo(entityId, state);
      if (!info.id) continue;
      if (!controllers.has(info.id)) {
        controllers.set(info.id, {
          id: info.id,
          slave: info.slave,
          vIndex: info.vIndex,
          name: info.name,
          online: null,
          messages: null,
          safetyStatus: null,
          voltage: null,
          totalCurrent: null,
          totalPower: null,
          buttons: [],
          inputs: [],
          channels: new Map(),
          _priority: {},
        });
      }

      const controller = controllers.get(info.id);
      if (attrs.controller) controller.name = String(attrs.controller);
      if (info.vIndex !== null) controller.vIndex = info.vIndex;
      if (info.slave !== null) controller.slave = info.slave;

      if (role === 'controller_online') assignPreferred(controller, 'online', entityId, priority);
      else if (role === 'controller_messages') assignPreferred(controller, 'messages', entityId, priority);
      else if (role === 'safety_test_status') assignPreferred(controller, 'safetyStatus', entityId, priority);
      else if (role === 'controller_voltage') assignPreferred(controller, 'voltage', entityId, priority);
      else if (role === 'controller_total_current') assignPreferred(controller, 'totalCurrent', entityId, priority);
      else if (role === 'controller_total_power') assignPreferred(controller, 'totalPower', entityId, priority);
      else if (role === 'command_button' || role === 'safety_test_button') {
        if (!controller.buttons.includes(entityId)) controller.buttons.push(entityId);
      } else if (role === 'digital_input') {
        const index = inputNumber(entityId, state);
        if (index !== null && !controller.inputs.some((item) => item.index === index)) {
          controller.inputs.push({
            entity: entityId,
            index,
            description: attrs.di_description || `DI${index}`,
          });
        }
      } else if (role.startsWith('channel_')) {
        const channel = channelNumber(entityId, state);
        if (!Number.isFinite(channel) || channel < 1) continue;
        if (!controller.channels.has(channel)) {
          controller.channels.set(channel, {
            channel,
            description: attrs.channel_description || `Kanal ${channel}`,
            current: null,
            voltage: null,
            power: null,
            maxCurrent: null,
            _priority: {},
          });
        }
        const item = controller.channels.get(channel);
        if (attrs.channel_description) item.description = String(attrs.channel_description);
        if (role === 'channel_current') assignPreferred(item, 'current', entityId, priority);
        else if (role === 'channel_voltage') assignPreferred(item, 'voltage', entityId, priority);
        else if (role === 'channel_power') assignPreferred(item, 'power', entityId, priority);
        else if (role === 'channel_daily_max_current') assignPreferred(item, 'maxCurrent', entityId, priority);
      }
    }

    for (const controller of controllers.values()) {
      controller.buttons.sort((a, b) => {
        const aa = inferActionKey(a, hass?.states?.[a]);
        const bb = inferActionKey(b, hass?.states?.[b]);
        const ia = ACTION_ORDER.includes(aa) ? ACTION_ORDER.indexOf(aa) : 999;
        const ib = ACTION_ORDER.includes(bb) ? ACTION_ORDER.indexOf(bb) : 999;
        return ia - ib;
      });
      controller.inputs.sort((a, b) => a.index - b.index);
      delete controller._priority;
      for (const channel of controller.channels.values()) delete channel._priority;
    }

    const result = [...controllers.values()].sort((a, b) => {
      const av = a.vIndex ?? 999;
      const bv = b.vIndex ?? 999;
      if (av !== bv) return av - bv;
      return (a.slave ?? 9999) - (b.slave ?? 9999);
    });

    return { gatewayStatus, gatewayMessages, controllers: result };
  };

  class FonrichDashboardBase extends HTMLElement {
    setConfig(config) {
      this.config = {
        columns: 3,
        show_buttons: true,
        show_channels: true,
        show_inputs: true,
        show_panels: true,
        show_inactive: true,
        hide_zero: false,
        sort_by: 'channel',
        sort_desc: false,
        metric: 'power',
        zero_threshold: 0.01,
        max_current: 15,
        channel_count: 0,
        ...config,
      };
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      this.render();
    }

    set hass(hass) {
      this._hass = hass;
      this.render();
    }

    getCardSize() { return 6; }
    getGridOptions() {
      return { columns: { min: 3, max: 12, default: 12 }, rows: { min: 2, max: 12, default: 6 } };
    }

    _state(entityId) { return entityId ? this._hass?.states?.[entityId] : undefined; }
    _available(entityId) { return !isUnavailableState(this._state(entityId)); }
    _number(entityId) {
      const value = Number.parseFloat(this._state(entityId)?.state);
      return Number.isFinite(value) ? value : null;
    }
    _format(entityId, digits = null, fallback = '–') {
      const state = this._state(entityId);
      if (isUnavailableState(state)) return fallback;
      const numeric = Number.parseFloat(state.state);
      const value = digits !== null && Number.isFinite(numeric) ? numeric.toFixed(digits) : state.state;
      const unit = state.attributes?.unit_of_measurement || '';
      return `${value}${unit ? ` ${unit}` : ''}`;
    }
    _formatExternal(entityId, digits = 0) {
      if (!entityId) return '–';
      return this._format(entityId, digits);
    }
    _date(value) {
      if (!value) return '–';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat(this._hass?.locale?.language || 'de-CH', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
      }).format(date);
    }
    _moreInfo(entityId) {
      if (!entityId) return;
      this.dispatchEvent(new CustomEvent('hass-more-info', {
        detail: { entityId }, bubbles: true, composed: true,
      }));
    }
    _notify(message) {
      this.dispatchEvent(new CustomEvent('hass-notification', {
        detail: { message }, bubbles: true, composed: true,
      }));
    }

    async _press(entityId) {
      const state = this._state(entityId);
      if (!state || String(state.state).toLowerCase() === 'unavailable') return;
      const label = state.attributes?.friendly_name || entityId;
      const action = inferActionKey(entityId, state);

      if (action === 'remote_trip_test') {
        const entered = window.prompt(
          `${label}\n\nACHTUNG: Dieser Befehl kann den real angeschlossenen Hauptschalter / Shunt-Auslöser betätigen.\n` +
          `Die kurze Freigabe muss vorher aktiv sein.\n\nZum Ausführen exakt AUSLOESEN eingeben:`
        );
        if (entered !== 'AUSLOESEN') return;
      } else if (action === 'arm_remote_trip_test') {
        if (!window.confirm(`${label}\n\nDie reale Hauptschalter-Auslösung wird für kurze Zeit freigegeben. Fortfahren?`)) return;
      } else if (action === 'lightning_message_test') {
        if (!window.confirm(
          `${label}\n\nDies erzeugt ausschliesslich eine Home-Assistant-Testmeldung. ` +
          `Die Blitzschutz-Hardware wird NICHT elektrisch ausgelöst. Fortfahren?`
        )) return;
      } else if (!window.confirm(`${label} wirklich ausführen?`)) {
        return;
      }

      try {
        await this._hass.callService('button', 'press', { entity_id: entityId });
      } catch (error) {
        this._notify(error?.message || String(error));
      }
    }

    _model() { return buildFonrichModel(this._hass); }

    _controllerOnline(controller) {
      const onlineState = this._state(controller.online);
      if (onlineState?.state === 'on') return true;
      if (onlineState?.state === 'off') return false;
      return [controller.voltage, controller.totalCurrent, controller.totalPower]
        .some((entityId) => this._available(entityId));
    }

    _selected(model) {
      const requested = Array.isArray(this.config?.controllers)
        ? this.config.controllers.map((value) => String(value)).filter(Boolean)
        : [];
      if (requested.length) {
        const result = [];
        for (const label of requested) {
          const vIndex = parseVIndex(label);
          const normalized = normalize(label);
          const match = model.controllers.find((controller) => {
            if (vIndex !== null && controller.vIndex === vIndex) return true;
            const name = normalize(controller.name);
            return name === normalized || name.includes(normalized) || normalized.includes(name);
          });
          if (match && !result.includes(match)) result.push(match);
        }
        if (result.length) return result;
      }

      const slave = Number(this.config?.slave || 0);
      return slave > 0 ? model.controllers.filter((controller) => controller.slave === slave) : model.controllers;
    }

    _channels(controller, forceAll = false) {
      const hideZero = !forceAll && (this.config?.hide_zero === true || this.config?.show_inactive === false);
      const threshold = Number(this.config?.zero_threshold ?? 0.01);
      const limit = Number(this.config?.channel_count || 0);
      const values = [...controller.channels.values()].filter((item) => {
        if (limit > 0 && item.channel > limit) return false;
        if (!hideZero) return true;
        return Math.abs(this._number(item.current) || 0) >= threshold || Math.abs(this._number(item.power) || 0) >= 1;
      });
      const sortBy = this.config?.sort_by || 'channel';
      const direction = this.config?.sort_desc === true ? -1 : 1;
      const value = (item) => {
        if (sortBy === 'current') return this._number(item.current) || 0;
        if (sortBy === 'power') return this._number(item.power) || 0;
        if (sortBy === 'max_current') return this._number(item.maxCurrent) || 0;
        return item.channel;
      };
      return values.sort((a, b) => (value(a) - value(b)) * direction);
    }

    _active(channel) {
      const threshold = Number(this.config?.zero_threshold ?? 0.01);
      return Math.abs(this._number(channel.current) || 0) >= threshold || Math.abs(this._number(channel.power) || 0) >= 1;
    }

    _messageText(entityId) {
      const state = this._state(entityId);
      return state?.state || 'Keine Meldungs-Entity gefunden';
    }

    _styles() {
      const columns = Math.max(1, Math.min(6, Number(this.config?.columns || 3)));
      return `<style>
        :host{display:block;--fr-gap:12px;--fr-radius:18px}
        ha-card{overflow:hidden;border-radius:22px;background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow)}
        .header{padding:18px 20px 14px;background:linear-gradient(135deg,color-mix(in srgb,var(--primary-color) 24%,transparent),transparent)}
        .title{font-size:20px;font-weight:750;letter-spacing:-.01em}.subtitle{font-size:13px;color:var(--secondary-text-color);margin-top:4px;line-height:1.4}
        .content{padding:16px 18px 20px}.grid{display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:var(--fr-gap)}
        .box{border:1px solid var(--divider-color);border-radius:var(--fr-radius);padding:14px;background:color-mix(in srgb,var(--card-background-color) 94%,var(--primary-color) 6%)}
        .box.offline{opacity:.7;border-style:dashed}.row{display:flex;align-items:center;justify-content:space-between;gap:10px}.name{font-weight:750}.muted{color:var(--secondary-text-color);font-size:12px;line-height:1.35}
        .status{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;white-space:nowrap}.dot{width:9px;height:9px;border-radius:50%;background:var(--error-color)}.status.online .dot{background:var(--success-color)}
        .metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}.metric{padding:9px;border-radius:12px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent);min-width:0}.metric b{display:block;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.metric span{font-size:11px;color:var(--secondary-text-color)}
        .hero-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.hero{padding:14px;border-radius:16px;background:color-mix(in srgb,var(--primary-color) 10%,var(--card-background-color));border:1px solid color-mix(in srgb,var(--primary-color) 18%,transparent)}.hero b{font-size:22px;display:block}.hero span{font-size:12px;color:var(--secondary-text-color)}
        .message{margin-top:12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warning-color) 14%,transparent);white-space:normal;overflow-wrap:anywhere;line-height:1.4}.message.ok{background:color-mix(in srgb,var(--success-color) 13%,transparent)}
        .warning{margin:12px 0;padding:11px 13px;border-radius:12px;border:1px solid color-mix(in srgb,var(--error-color) 55%,transparent);background:color-mix(in srgb,var(--error-color) 11%,transparent);font-size:12px;line-height:1.45}
        .safety{margin-top:12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warning-color) 10%,transparent)}
        .inputs{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.input{padding:7px 9px;border-radius:999px;background:color-mix(in srgb,var(--primary-text-color) 6%,transparent);font-size:12px;cursor:pointer}.input.on{background:color-mix(in srgb,var(--warning-color) 18%,transparent);font-weight:700}
        .buttons{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.btn{border:0;border-radius:12px;padding:9px 11px;cursor:pointer;background:color-mix(in srgb,var(--primary-color) 14%,var(--card-background-color));color:var(--primary-text-color);font:inherit;font-size:12px}.btn:hover{filter:brightness(1.06)}.btn:disabled{cursor:not-allowed;opacity:.45}.btn.danger{background:color-mix(in srgb,var(--error-color) 18%,var(--card-background-color));font-weight:700}.btn.test{border:1px dashed var(--warning-color)}
        table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--divider-color);font-size:13px}th{color:var(--secondary-text-color);font-weight:600}.click{cursor:pointer}.num{text-align:right;font-variant-numeric:tabular-nums}
        .bar-row{display:grid;grid-template-columns:minmax(120px,1.3fr) 3fr minmax(70px,.7fr);gap:10px;align-items:center;margin:10px 0}.track{height:12px;border-radius:999px;background:color-mix(in srgb,var(--primary-text-color) 9%,transparent);overflow:hidden}.fill{height:100%;border-radius:999px;background:var(--primary-color)}
        .diag{display:grid;gap:8px;margin-top:10px}.diagline{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.pill{padding:9px;border-radius:12px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent)}
        .controller{margin-top:14px}.controller:first-child{margin-top:0}.controller-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}.controller-title{font-size:17px;font-weight:750}
        .channel-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-top:12px}.channel{position:relative;padding:12px;border-radius:15px;border:1px solid var(--divider-color);background:color-mix(in srgb,var(--card-background-color) 96%,var(--primary-color) 4%);overflow:hidden}.channel.active{border-color:color-mix(in srgb,var(--success-color) 45%,var(--divider-color));background:color-mix(in srgb,var(--success-color) 8%,var(--card-background-color))}.channel-alarm{border-color:color-mix(in srgb,var(--error-color) 55%,var(--divider-color))}
        .panel-icon{width:58px;height:34px;border-radius:6px;transform:skewX(-8deg);background:linear-gradient(90deg,transparent 31%,rgba(255,255,255,.35) 32%,transparent 34%,transparent 65%,rgba(255,255,255,.35) 66%,transparent 68%),linear-gradient(0deg,transparent 46%,rgba(255,255,255,.35) 47%,transparent 51%),linear-gradient(145deg,#0c3c71,#1976b8);box-shadow:0 5px 10px rgba(0,0,0,.18);border:2px solid color-mix(in srgb,var(--primary-text-color) 35%,transparent)}
        .panel-icon.off{filter:grayscale(1);opacity:.42}.channel-top{display:flex;align-items:center;justify-content:space-between;gap:8px}.channel-no{font-size:12px;font-weight:750}.channel-desc{font-size:11px;color:var(--secondary-text-color);min-height:16px;margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.channel-values{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:9px}.channel-value{font-size:12px}.channel-value b{display:block;font-size:14px}.amp-track{height:6px;border-radius:999px;background:color-mix(in srgb,var(--primary-text-color) 9%,transparent);overflow:hidden;margin-top:8px}.amp-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--success-color),var(--warning-color))}
        .flow{display:grid;grid-template-columns:minmax(130px,1fr) 48px minmax(150px,1.2fr) 48px minmax(150px,1fr);align-items:center;gap:10px;margin-bottom:16px}.flow-node{padding:16px;border-radius:18px;border:1px solid var(--divider-color);text-align:center;background:color-mix(in srgb,var(--card-background-color) 94%,var(--primary-color) 6%)}.flow-node b{font-size:21px;display:block}.flow-icon{font-size:28px;margin-bottom:6px}.flow-arrow{position:relative;height:4px;border-radius:999px;background:color-mix(in srgb,var(--primary-color) 55%,transparent)}.flow-arrow:after{content:'';position:absolute;right:-1px;top:50%;width:10px;height:10px;border-top:3px solid var(--primary-color);border-right:3px solid var(--primary-color);transform:translateY(-50%) rotate(45deg)}.flow-arrow.active{animation:pulse 1.6s ease-in-out infinite}.flow-extra{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:12px}.flow-small{padding:12px;border-radius:15px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent);text-align:center}.flow-small b{display:block;font-size:17px}
        .empty{padding:22px;text-align:center;color:var(--secondary-text-color)}.debug{margin-top:10px;font-size:11px;color:var(--secondary-text-color)}
        @keyframes pulse{0%,100%{opacity:.45}50%{opacity:1}}
        @media(max-width:900px){.hero-metrics{grid-template-columns:1fr 1fr}.flow{grid-template-columns:1fr}.flow-arrow{width:4px;height:28px;justify-self:center}.flow-arrow:after{right:50%;top:auto;bottom:-1px;transform:translateX(50%) rotate(135deg)}}
        @media(max-width:760px){.grid{grid-template-columns:1fr}.metrics{grid-template-columns:1fr 1fr}.diagline{grid-template-columns:1fr}.bar-row{grid-template-columns:1fr}.track{height:10px}table{display:block;overflow-x:auto}.hero-metrics{grid-template-columns:1fr 1fr}}
      </style>`;
    }

    _header(title, subtitle) {
      return `<div class="header"><div class="title">${esc(title)}</div><div class="subtitle">${esc(subtitle)}</div></div>`;
    }
    _message(entityId) {
      const text = this._messageText(entityId);
      return `<div class="message ${text === 'OK' ? 'ok' : ''} ${entityId ? 'click' : ''}" ${entityId ? `data-info="${esc(entityId)}"` : ''}>${esc(text)}</div>`;
    }
    _safety(controller) {
      if (!controller.safetyStatus) return '';
      const state = this._state(controller.safetyStatus);
      const text = state?.state || 'Unbekannt';
      const armedUntil = state?.attributes?.remote_trip_armed_until;
      const detail = armedUntil ? ` bis ${this._date(armedUntil)}` : '';
      return `<div class="safety click" data-info="${esc(controller.safetyStatus)}"><b>Schutz-Teststatus:</b> ${esc(text)}${esc(detail)}</div>`;
    }
    _inputs(controller) {
      if (this.config.show_inputs === false || !controller.inputs.length) return '';
      return `<div class="inputs">${controller.inputs.map((input) => {
        const state = this._state(input.entity);
        const on = state?.state === 'on';
        return `<span class="input ${on ? 'on' : ''}" data-info="${esc(input.entity)}">DI${input.index} ${esc(input.description)}: ${on ? 'Ein' : state?.state === 'off' ? 'Aus' : '–'}</span>`;
      }).join('')}</div>`;
    }
    _buttons(controller, safetyOnly = false) {
      const buttons = controller.buttons.filter((id) => {
        const role = inferRole(id, this._state(id));
        return !safetyOnly || role === 'safety_test_button';
      });
      if (!buttons.length) return '';
      return `<div class="buttons">${buttons.map((id) => {
        const state = this._state(id);
        const action = inferActionKey(id, state);
        const css = action === 'remote_trip_test' ? 'danger' : (['lightning_message_test', 'clear_test_messages'].includes(action) ? 'test' : '');
        const disabled = !this._available(id);
        return `<button class="btn ${css}" data-press="${esc(id)}" ${disabled ? 'disabled' : ''}>${esc(state?.attributes?.friendly_name || id)}</button>`;
      }).join('')}</div>`;
    }
    _channelTile(controller, channel, showPanel = true) {
      const active = this._active(channel);
      const current = Math.max(0, this._number(channel.current) || 0);
      const maxCurrent = Math.max(0.1, Number(this.config.max_current || 15));
      const width = Math.min(100, current / maxCurrent * 100);
      return `<div class="channel ${active ? 'active' : ''}">
        <div class="channel-top">
          ${showPanel ? `<div class="panel-icon ${active ? '' : 'off'}"></div>` : ''}
          <div class="channel-no">CH ${String(channel.channel).padStart(2, '0')}</div>
        </div>
        <div class="channel-desc">${esc(channel.description || `Kanal ${channel.channel}`)}</div>
        <div class="channel-values">
          <div class="channel-value click" data-info="${esc(channel.power || '')}"><b>${esc(this._format(channel.power, 0, '0 W'))}</b><span class="muted">Leistung</span></div>
          <div class="channel-value click" data-info="${esc(channel.current || '')}"><b>${esc(this._format(channel.current, 3, '0.000 A'))}</b><span class="muted">Ampere</span></div>
          <div class="channel-value click" data-info="${esc(channel.voltage || '')}"><b>${esc(this._format(channel.voltage, 0))}</b><span class="muted">Spannung</span></div>
          <div class="channel-value click" data-info="${esc(channel.maxCurrent || '')}"><b>${esc(this._format(channel.maxCurrent, 3))}</b><span class="muted">Max. heute</span></div>
        </div>
        <div class="amp-track"><div class="amp-fill" style="width:${width.toFixed(1)}%"></div></div>
      </div>`;
    }
    _bind() {
      this.shadowRoot?.querySelectorAll('[data-info]').forEach((element) => {
        element.addEventListener('click', () => this._moreInfo(element.dataset.info));
      });
      this.shadowRoot?.querySelectorAll('[data-press]').forEach((element) => {
        element.addEventListener('click', () => this._press(element.dataset.press));
      });
    }
  }

  class FonrichOverviewCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: 'Fonrich Gesamtübersicht', columns: 3 }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controllers = this._selected(model);
      const blocks = controllers.map((controller) => {
        const online = this._controllerOnline(controller);
        const activeChannels = this._channels(controller, true).filter((channel) => this._active(channel)).length;
        return `<div class="box ${online ? '' : 'offline'}">
          <div class="row"><div><div class="name">${esc(controller.name)}</div><div class="muted">${controller.slave !== null ? `Modbus ${controller.slave} · ` : ''}${activeChannels} aktive Kanäle</div></div><div class="status ${online ? 'online' : ''}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div></div>
          <div class="metrics"><div class="metric click" data-info="${esc(controller.voltage || '')}"><b>${esc(this._format(controller.voltage, 0))}</b><span>Spannung</span></div><div class="metric click" data-info="${esc(controller.totalCurrent || '')}"><b>${esc(this._format(controller.totalCurrent, 2))}</b><span>Gesamtstrom</span></div><div class="metric click" data-info="${esc(controller.totalPower || '')}"><b>${esc(this._format(controller.totalPower, 0))}</b><span>Gesamtleistung</span></div></div>
          ${this._message(controller.messages)}${this._safety(controller)}${this._inputs(controller)}${this.config.show_buttons === false ? '' : this._buttons(controller)}
        </div>`;
      }).join('');
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Gesamtübersicht', 'Status, Gesamtwerte, Meldungen und Bedienung aller Kästen')}<div class="content">${model.gatewayMessages ? this._message(model.gatewayMessages) : ''}<div style="height:12px"></div><div class="grid">${blocks || '<div class="empty">Keine Fonrich-Entities gefunden. Nach dem Update Home Assistant und Browser vollständig neu laden.</div>'}</div></div></ha-card>`;
      this._bind();
    }
  }

  class FonrichControllerCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: '', slave: 240, columns: 1, show_buttons: true, show_channels: true }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controller = this._selected(model)[0];
      if (!controller) {
        this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Kasten', 'Keine passende Kasten-Entity gefunden')}<div class="empty">Prüfe die Modbus-Adresse oder entferne die Kasten-Auswahl.</div></ha-card>`;
        return;
      }
      const online = this._controllerOnline(controller);
      const rows = this._channels(controller).map((channel) => `<tr>
        <td>${String(channel.channel).padStart(2, '0')}</td><td>${esc(channel.description || '–')}</td>
        <td class="num click" data-info="${esc(channel.current || '')}">${esc(this._format(channel.current, 3))}</td>
        <td class="num click" data-info="${esc(channel.voltage || '')}">${esc(this._format(channel.voltage, 0))}</td>
        <td class="num click" data-info="${esc(channel.power || '')}">${esc(this._format(channel.power, 0))}</td>
        <td class="num click" data-info="${esc(channel.maxCurrent || '')}">${esc(this._format(channel.maxCurrent, 3))}</td>
      </tr>`).join('');
      const table = this.config.show_channels === false ? '' : `<div style="overflow:auto;margin-top:14px"><table><thead><tr><th>Kanal</th><th>Beschreibung</th><th class="num">Ampere</th><th class="num">Volt</th><th class="num">Watt</th><th class="num">Max. A heute</th></tr></thead><tbody>${rows || '<tr><td colspan="6">Keine Kanäle gefunden.</td></tr>'}</tbody></table></div>`;
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || controller.name, `${controller.slave !== null ? `Modbus ${controller.slave} · ` : ''}${online ? 'Online' : 'Offline'}`)}<div class="content">
        <div class="metrics"><div class="metric click" data-info="${esc(controller.voltage || '')}"><b>${esc(this._format(controller.voltage, 0))}</b><span>Spannung</span></div><div class="metric click" data-info="${esc(controller.totalCurrent || '')}"><b>${esc(this._format(controller.totalCurrent, 2))}</b><span>Gesamtstrom</span></div><div class="metric click" data-info="${esc(controller.totalPower || '')}"><b>${esc(this._format(controller.totalPower, 0))}</b><span>Gesamtleistung</span></div></div>
        ${this._message(controller.messages)}${this._safety(controller)}${this._inputs(controller)}${this.config.show_buttons === false ? '' : this._buttons(controller)}${table}
      </div></ha-card>`;
      this._bind();
    }
  }

  class FonrichAlarmTestCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: 'Fonrich Schutz, Alarm und Tests', slave: 0, columns: 2, show_inputs: true }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controllers = this._selected(model);
      const blocks = controllers.map((controller) => {
        const online = this._controllerOnline(controller);
        return `<div class="box ${online ? '' : 'offline'}"><div class="row"><div class="name">${esc(controller.name)}</div><div class="status ${online ? 'online' : ''}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div></div>${this._message(controller.messages)}${this._safety(controller)}${this._inputs(controller)}${this._buttons(controller)}</div>`;
      }).join('');
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Schutz, Alarm und Tests', 'Echte Alarmmeldungen, Reset, Selbsttest und abgesicherter Hauptschalter-Test')}<div class="content">
        <div class="warning"><b>Sicherheit:</b> „Hauptschalter-Schutz auslösen (Test)“ kann eine reale Schutzauslösung bewirken. „Blitzschutz-Meldetest“ simuliert nur die Meldung in Home Assistant und löst keine Blitzschutz-Hardware aus.</div>
        ${model.gatewayMessages ? this._message(model.gatewayMessages) : ''}<div style="height:12px"></div><div class="grid">${blocks || '<div class="empty">Keine Kästen gefunden.</div>'}</div>
      </div></ha-card>`;
      this._bind();
    }
  }

  class FonrichChannelsCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: 'Fonrich Kanaltabelle', slave: 0, hide_zero: false, sort_by: 'channel' }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const controllers = this._selected(this._model());
      let rows = '';
      for (const controller of controllers) {
        for (const channel of this._channels(controller)) {
          rows += `<tr><td>${esc(controller.name)}</td><td>${String(channel.channel).padStart(2, '0')}</td><td>${esc(channel.description || '–')}</td><td class="num click" data-info="${esc(channel.current || '')}">${esc(this._format(channel.current, 3))}</td><td class="num click" data-info="${esc(channel.voltage || '')}">${esc(this._format(channel.voltage, 0))}</td><td class="num click" data-info="${esc(channel.power || '')}">${esc(this._format(channel.power, 0))}</td><td class="num click" data-info="${esc(channel.maxCurrent || '')}">${esc(this._format(channel.maxCurrent, 3))}</td></tr>`;
        }
      }
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Kanaltabelle', 'Alle Kanäle als stabile, sortierbare Tabelle')}<div class="content"><div style="overflow:auto"><table><thead><tr><th>Kasten</th><th>Kanal</th><th>Beschreibung</th><th class="num">Ampere</th><th class="num">Volt</th><th class="num">Watt</th><th class="num">Max. A heute</th></tr></thead><tbody>${rows || '<tr><td colspan="7">Keine Kanäle gefunden.</td></tr>'}</tbody></table></div></div></ha-card>`;
      this._bind();
    }
  }

  class FonrichBarsCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: 'Fonrich Kanalvergleich', slave: 0, metric: 'power', hide_zero: true }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const controllers = this._selected(this._model());
      const metric = this.config.metric || 'power';
      const items = [];
      for (const controller of controllers) {
        for (const channel of this._channels(controller)) {
          const entity = metric === 'current' ? channel.current : metric === 'max_current' ? channel.maxCurrent : channel.power;
          items.push({ controller, channel, entity, value: Math.max(0, this._number(entity) || 0) });
        }
      }
      const maximum = Math.max(1, ...items.map((item) => item.value));
      const rows = items.map((item) => `<div class="bar-row click" data-info="${esc(item.entity || '')}"><div><div class="name">${esc(item.controller.name)} · Kanal ${String(item.channel.channel).padStart(2, '0')}</div><div class="muted">${esc(item.channel.description || '')}</div></div><div class="track"><div class="fill" style="width:${Math.min(100, (item.value / maximum) * 100).toFixed(1)}%"></div></div><div class="num">${esc(this._format(item.entity, metric === 'power' ? 0 : 3))}</div></div>`).join('');
      const metricName = metric === 'current' ? 'aktuelle Ampere' : metric === 'max_current' ? 'maximale Ampere heute' : 'Leistung in Watt';
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Kanalvergleich', metricName)}<div class="content">${rows || '<div class="empty">Keine Werte gefunden.</div>'}</div></ha-card>`;
      this._bind();
    }
  }

  class FonrichDiagnosticsCard extends FonrichDashboardBase {
    static getStubConfig() { return { title: 'Fonrich Busdiagnose', slave: 0, columns: 2 }; }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const controllers = this._selected(this._model());
      const blocks = controllers.map((controller) => {
        const state = this._state(controller.online);
        const attrs = state?.attributes || {};
        const online = this._controllerOnline(controller);
        const categoryErrors = Object.entries(attrs.category_errors || {}).map(([key, value]) => `${key}: ${value}`).join(' · ');
        return `<div class="box ${online ? '' : 'offline'}"><div class="row"><div class="name">${esc(controller.name)}</div><div class="status ${online ? 'online' : ''}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div></div><div class="diag"><div class="diagline"><div class="pill"><div class="muted">Letzter Erfolg</div>${esc(this._date(attrs.last_success))}</div><div class="pill"><div class="muted">Letzter Versuch</div>${esc(this._date(attrs.last_attempt))}</div></div><div class="diagline"><div class="pill"><div class="muted">Fehler in Folge</div>${Number(attrs.consecutive_errors || 0)}</div><div class="pill"><div class="muted">Polls Erfolg / Fehler</div>${Number(attrs.successful_polls || 0)} / ${Number(attrs.failed_polls || 0)}</div></div><div class="muted">${esc(attrs.last_error || categoryErrors || 'Keine Kommunikationsfehler')}</div></div></div>`;
      }).join('');
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Busdiagnose', 'Kommunikation, Zeitstempel und Fehler je Kasten')}<div class="content"><div class="grid">${blocks || '<div class="empty">Keine Diagnoseinformationen gefunden.</div>'}</div></div></ha-card>`;
      this._bind();
    }
  }

  class FonrichModernProductionCard extends FonrichDashboardBase {
    static getStubConfig() {
      return {
        title: 'Fonrich Modern',
        controllers: ['V1 / Kasten 1', 'V2 / Kasten 2', 'V3 / Kasten 3'],
        max_current: 15,
        channel_count: 8,
        show_buttons: true,
        show_inactive: true,
      };
    }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controllers = this._selected(model);
      const allChannels = controllers.flatMap((controller) => this._channels(controller, true));
      const totalPower = controllers.reduce((sum, controller) => sum + (this._number(controller.totalPower) || 0), 0);
      const totalCurrent = controllers.reduce((sum, controller) => sum + (this._number(controller.totalCurrent) || 0), 0);
      const activeCount = allChannels.filter((channel) => this._active(channel)).length;
      const onlineCount = controllers.filter((controller) => this._controllerOnline(controller)).length;
      const expectedCount = Number(this.config.channel_count || 0) > 0
        ? controllers.length * Number(this.config.channel_count)
        : allChannels.length;

      const blocks = controllers.map((controller) => {
        const online = this._controllerOnline(controller);
        const channels = this._channels(controller);
        const active = channels.filter((channel) => this._active(channel)).length;
        return `<div class="box controller ${online ? '' : 'offline'}">
          <div class="controller-head"><div><div class="controller-title">${esc(controller.name)}</div><div class="muted">${active} von ${channels.length} Strings aktiv${controller.slave !== null ? ` · Modbus ${controller.slave}` : ''}</div></div><div class="status ${online ? 'online' : ''}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div></div>
          <div class="metrics"><div class="metric click" data-info="${esc(controller.voltage || '')}"><b>${esc(this._format(controller.voltage, 0))}</b><span>Spannung</span></div><div class="metric click" data-info="${esc(controller.totalCurrent || '')}"><b>${esc(this._format(controller.totalCurrent, 2))}</b><span>Gesamtstrom</span></div><div class="metric click" data-info="${esc(controller.totalPower || '')}"><b>${esc(this._format(controller.totalPower, 0))}</b><span>Gesamtleistung</span></div></div>
          ${this._message(controller.messages)}
          <div class="channel-grid">${channels.map((channel) => this._channelTile(controller, channel, true)).join('') || '<div class="empty">Keine Kanäle gefunden.</div>'}</div>
          ${this.config.show_buttons === false ? '' : this._buttons(controller)}
        </div>`;
      }).join('');

      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Modern', 'Moderne Produktionskarte: Solarstrings, Leistung, Ampere, Spannung und Tagesmaximum')}<div class="content">
        <div class="hero-metrics"><div class="hero"><b>${Math.round(totalPower).toLocaleString('de-CH')} W</b><span>Gesamtleistung</span></div><div class="hero"><b>${totalCurrent.toFixed(2)} A</b><span>Gesamtstrom</span></div><div class="hero"><b>${activeCount}/${expectedCount}</b><span>Aktive Strings</span></div><div class="hero"><b>${onlineCount}/${controllers.length}</b><span>Kästen online</span></div></div>
        ${model.gatewayMessages ? this._message(model.gatewayMessages) : ''}
        ${blocks || '<div class="empty">Keine Fonrich-Entities erkannt. Die Karte unterstützt jetzt sowohl die neuen stabilen Metadaten als auch Entity-Namen wie sensor.kasten_v1_gesamtleistung.</div>'}
      </div></ha-card>`;
      this._bind();
    }
  }

  class FonrichSolarMonitorCard extends FonrichDashboardBase {
    static getStubConfig() {
      return {
        title: 'Fonrich Solar Monitor',
        controllers: ['V1 / Kasten 1', 'V2 / Kasten 2', 'V3 / Kasten 3'],
        channel_count: 8,
        max_current: 15,
        show_inactive: true,
        columns: 1,
      };
    }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controllers = this._selected(model);
      const channels = controllers.flatMap((controller) => this._channels(controller, true));
      const active = channels.filter((channel) => this._active(channel)).length;
      const totalPower = controllers.reduce((sum, controller) => sum + (this._number(controller.totalPower) || 0), 0);
      const maxPower = channels.reduce((max, channel) => Math.max(max, this._number(channel.power) || 0), 0);
      const maxChannel = channels.find((channel) => (this._number(channel.power) || 0) === maxPower);

      const groups = controllers.map((controller) => {
        const online = this._controllerOnline(controller);
        const selectedChannels = this._channels(controller);
        return `<div class="box controller ${online ? '' : 'offline'}">
          <div class="controller-head"><div><div class="controller-title">☀ ${esc(controller.name)}</div><div class="muted">Solarzellen / Strings · ${selectedChannels.filter((channel) => this._active(channel)).length} aktiv</div></div><div class="status ${online ? 'online' : ''}"><span class="dot"></span>${online ? 'Online' : 'Offline'}</div></div>
          <div class="channel-grid">${selectedChannels.map((channel) => this._channelTile(controller, channel, true)).join('') || '<div class="empty">Keine Solarstrings gefunden.</div>'}</div>
        </div>`;
      }).join('');

      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Solar Monitor', 'Visuelle Solarzellen-Ansicht für alle Fonrich-Strings')}<div class="content">
        <div class="hero-metrics"><div class="hero"><b>${Math.round(totalPower).toLocaleString('de-CH')} W</b><span>PV DC Gesamt</span></div><div class="hero"><b>${active}/${channels.length}</b><span>Solarstrings aktiv</span></div><div class="hero"><b>${Math.round(maxPower).toLocaleString('de-CH')} W</b><span>Stärkster String</span></div><div class="hero"><b>${maxChannel ? `CH ${String(maxChannel.channel).padStart(2, '0')}` : '–'}</b><span>Aktuell stärkster Kanal</span></div></div>
        ${model.gatewayMessages ? this._message(model.gatewayMessages) : ''}
        ${groups || '<div class="empty">Keine Fonrich-Solarstrings erkannt.</div>'}
      </div></ha-card>`;
      this._bind();
    }
  }

  class FonrichSolarFlowCard extends FonrichDashboardBase {
    static getStubConfig() {
      return {
        title: 'Fonrich Solar Energiefluss',
        controllers: ['V1 / Kasten 1', 'V2 / Kasten 2', 'V3 / Kasten 3'],
        channel_count: 8,
        show_panels: true,
        inverter_power_entity: '',
        house_power_entity: '',
        grid_power_entity: '',
        battery_power_entity: '',
        battery_soc_entity: '',
      };
    }
    render() {
      if (!this.shadowRoot || !this._hass) return;
      const model = this._model();
      const controllers = this._selected(model);
      const channels = controllers.flatMap((controller) => this._channels(controller, true));
      const active = channels.filter((channel) => this._active(channel)).length;
      const dcPower = controllers.reduce((sum, controller) => sum + (this._number(controller.totalPower) || 0), 0);
      const inverterPower = this.config.inverter_power_entity ? this._number(this.config.inverter_power_entity) : null;
      const outputPower = inverterPower ?? dcPower;
      const controllerNodes = controllers.map((controller) => `<div class="flow-small click" data-info="${esc(controller.totalPower || '')}"><b>${esc(this._format(controller.totalPower, 0, '0 W'))}</b><span class="muted">${esc(controller.name)}</span></div>`).join('');
      const externalNodes = [
        this.config.house_power_entity ? `<div class="flow-small click" data-info="${esc(this.config.house_power_entity)}"><b>${esc(this._formatExternal(this.config.house_power_entity, 0))}</b><span class="muted">Haus</span></div>` : '',
        this.config.grid_power_entity ? `<div class="flow-small click" data-info="${esc(this.config.grid_power_entity)}"><b>${esc(this._formatExternal(this.config.grid_power_entity, 0))}</b><span class="muted">Netz</span></div>` : '',
        this.config.battery_power_entity ? `<div class="flow-small click" data-info="${esc(this.config.battery_power_entity)}"><b>${esc(this._formatExternal(this.config.battery_power_entity, 0))}</b><span class="muted">Batterie Leistung</span></div>` : '',
        this.config.battery_soc_entity ? `<div class="flow-small click" data-info="${esc(this.config.battery_soc_entity)}"><b>${esc(this._formatExternal(this.config.battery_soc_entity, 1))}</b><span class="muted">Batterie SOC</span></div>` : '',
      ].filter(Boolean).join('');
      const panelPreview = this.config.show_panels === false ? '' : `<div class="channel-grid" style="margin-top:16px">${channels.map((channel) => this._channelTile(null, channel, true)).join('')}</div>`;

      this.shadowRoot.innerHTML = `${this._styles()}<ha-card>${this._header(this.config.title || 'Fonrich Solar Energiefluss', 'Solarzellen → Fonrich-Kästen → DC-Gesamt → Wechselrichter / Verbraucher')}<div class="content">
        <div class="flow">
          <div class="flow-node"><div class="flow-icon">☀️</div><b>${active}/${channels.length}</b><span class="muted">aktive Solarstrings</span></div>
          <div class="flow-arrow ${dcPower > 0 ? 'active' : ''}"></div>
          <div class="flow-node"><div class="flow-icon">▦</div><b>${Math.round(dcPower).toLocaleString('de-CH')} W</b><span class="muted">Fonrich DC Gesamt</span><div class="flow-extra">${controllerNodes}</div></div>
          <div class="flow-arrow ${outputPower > 0 ? 'active' : ''}"></div>
          <div class="flow-node ${this.config.inverter_power_entity ? 'click' : ''}" ${this.config.inverter_power_entity ? `data-info="${esc(this.config.inverter_power_entity)}"` : ''}><div class="flow-icon">⚡</div><b>${Math.round(outputPower).toLocaleString('de-CH')} W</b><span class="muted">${this.config.inverter_power_entity ? 'Wechselrichter / PV-Ausgang' : 'PV DC Ausgang'}</span></div>
        </div>
        ${externalNodes ? `<div class="flow-extra">${externalNodes}</div>` : '<div class="muted">Haus-, Netz-, Batterie- und Wechselrichter-Entities können im visuellen Editor optional ergänzt werden.</div>'}
        ${model.gatewayMessages ? this._message(model.gatewayMessages) : ''}
        ${panelPreview}
      </div></ha-card>`;
      this._bind();
    }
  }

  class FonrichDashboardEditor extends HTMLElement {
    setConfig(config) { this._config = { ...config }; this.render(); }
    set hass(hass) { this._hass = hass; this.render(); }

    _slaves() {
      return [...new Set(
        buildFonrichModel(this._hass).controllers
          .map((controller) => controller.slave)
          .filter((slave) => Number.isFinite(slave))
      )].sort((a, b) => a - b);
    }

    render() {
      if (!this._config) return;
      const config = this._config;
      const type = String(config.type || '');
      const isModern = type.includes('modern-production');
      const isSolar = type.includes('solar-monitor') || type.includes('solar-flow');
      const isFlow = type.includes('solar-flow');
      const slaves = this._slaves();
      const controllersText = Array.isArray(config.controllers) ? config.controllers.join(', ') : '';

      this.innerHTML = `<style>
        .e{display:grid;gap:12px}.r{display:grid;grid-template-columns:1fr 1fr;gap:10px}.f{display:grid;gap:5px}label{font-size:12px;color:var(--secondary-text-color)}
        input:not([type=checkbox]),select,textarea{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--divider-color);border-radius:9px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}
        textarea{min-height:70px;resize:vertical}.t{display:flex;align-items:center;gap:7px}.t input{width:auto}@media(max-width:600px){.r{grid-template-columns:1fr}}
      </style><div class="e">
        <div class="f"><label>Titel</label><input data-key="title" value="${esc(config.title || '')}"></div>
        <div class="r"><div class="f"><label>Kasten / Modbus-Adresse</label><select data-key="slave"><option value="0">Alle Kästen</option>${slaves.map((slave) => `<option value="${slave}" ${Number(config.slave || 0) === slave ? 'selected' : ''}>${slave}</option>`).join('')}</select></div><div class="f"><label>Spalten</label><input data-key="columns" type="number" min="1" max="6" value="${Number(config.columns || 3)}"></div></div>
        ${(isModern || isSolar) ? `<div class="f"><label>Kästen in gewünschter Reihenfolge (Komma getrennt)</label><textarea data-key="controllers">${esc(controllersText)}</textarea></div><div class="r"><div class="f"><label>Anzahl Kanäle je Kasten, 0 = automatisch</label><input data-key="channel_count" type="number" min="0" max="24" value="${Number(config.channel_count || 0)}"></div><div class="f"><label>Skala maximale Ampere</label><input data-key="max_current" type="number" min="1" step="1" value="${Number(config.max_current || 15)}"></div></div>` : ''}
        <div class="r"><div class="f"><label>Sortierung</label><select data-key="sort_by"><option value="channel" ${!config.sort_by || config.sort_by === 'channel' ? 'selected' : ''}>Kanal</option><option value="current" ${config.sort_by === 'current' ? 'selected' : ''}>Ampere</option><option value="power" ${config.sort_by === 'power' ? 'selected' : ''}>Watt</option><option value="max_current" ${config.sort_by === 'max_current' ? 'selected' : ''}>Max. Ampere heute</option></select></div><div class="f"><label>Balkenwert</label><select data-key="metric"><option value="power" ${!config.metric || config.metric === 'power' ? 'selected' : ''}>Watt</option><option value="current" ${config.metric === 'current' ? 'selected' : ''}>Ampere</option><option value="max_current" ${config.metric === 'max_current' ? 'selected' : ''}>Max. Ampere heute</option></select></div></div>
        <div class="r"><label class="t"><input data-key="show_buttons" type="checkbox" ${config.show_buttons !== false ? 'checked' : ''}> Buttons anzeigen</label><label class="t"><input data-key="show_channels" type="checkbox" ${config.show_channels !== false ? 'checked' : ''}> Kanäle anzeigen</label><label class="t"><input data-key="show_inputs" type="checkbox" ${config.show_inputs !== false ? 'checked' : ''}> DI-Eingänge anzeigen</label><label class="t"><input data-key="show_inactive" type="checkbox" ${config.show_inactive !== false ? 'checked' : ''}> Inaktive Strings anzeigen</label><label class="t"><input data-key="hide_zero" type="checkbox" ${config.hide_zero === true ? 'checked' : ''}> Nullkanäle ausblenden</label><label class="t"><input data-key="sort_desc" type="checkbox" ${config.sort_desc === true ? 'checked' : ''}> Absteigend</label>${isFlow ? `<label class="t"><input data-key="show_panels" type="checkbox" ${config.show_panels !== false ? 'checked' : ''}> Solarzellen anzeigen</label>` : ''}</div>
        <div class="f"><label>Nullschwelle Ampere</label><input data-key="zero_threshold" type="number" min="0" step="0.001" value="${Number(config.zero_threshold ?? 0.01)}"></div>
        ${isFlow ? `<div class="f"><label>Wechselrichter-Leistung Entity</label><input data-key="inverter_power_entity" placeholder="sensor.inverter_gesamt_pv" value="${esc(config.inverter_power_entity || '')}"></div><div class="r"><div class="f"><label>Hausleistung Entity</label><input data-key="house_power_entity" value="${esc(config.house_power_entity || '')}"></div><div class="f"><label>Netzleistung Entity</label><input data-key="grid_power_entity" value="${esc(config.grid_power_entity || '')}"></div></div><div class="r"><div class="f"><label>Batterieleistung Entity</label><input data-key="battery_power_entity" value="${esc(config.battery_power_entity || '')}"></div><div class="f"><label>Batterie SOC Entity</label><input data-key="battery_soc_entity" value="${esc(config.battery_soc_entity || '')}"></div></div>` : ''}
      </div>`;

      this.querySelectorAll('input,select,textarea').forEach((element) => element.addEventListener('change', () => {
        const key = element.dataset.key;
        let value = element.type === 'checkbox' ? element.checked : element.value;
        if (['slave', 'columns', 'zero_threshold', 'channel_count', 'max_current'].includes(key)) value = Number(value);
        if (key === 'controllers') value = String(value).split(/[,\n]+/).map((item) => item.trim()).filter(Boolean);
        this._config = { ...this._config, [key]: value };
        this.dispatchEvent(new CustomEvent('config-changed', {
          detail: { config: this._config }, bubbles: true, composed: true,
        }));
      }));
    }
  }

  const patchExistingElement = (name, existingClass, sourceClass) => {
    // A cached older Fonrich resource may have registered the same custom element
    // before this file loads. Custom elements cannot be redefined, but their
    // prototype can be upgraded safely so an open browser session also receives
    // the corrected entity discovery and rendering logic.
    const chain = [];
    let prototype = sourceClass.prototype;
    while (prototype && prototype !== HTMLElement.prototype) {
      chain.unshift(prototype);
      prototype = Object.getPrototypeOf(prototype);
    }
    for (const sourcePrototype of chain) {
      for (const key of Object.getOwnPropertyNames(sourcePrototype)) {
        if (key === 'constructor') continue;
        const descriptor = Object.getOwnPropertyDescriptor(sourcePrototype, key);
        if (!descriptor) continue;
        try {
          Object.defineProperty(existingClass.prototype, key, descriptor);
        } catch (error) {
          console.debug(`Fonrich: bestehende Methode ${name}.${key} konnte nicht aktualisiert werden`, error);
        }
      }
    }
    if (sourceClass.getConfigElement) existingClass.getConfigElement = sourceClass.getConfigElement;
    if (sourceClass.getStubConfig) existingClass.getStubConfig = sourceClass.getStubConfig;
  };

  const safeDefine = (name, baseClass) => {
    const existing = customElements.get(name);
    if (existing) {
      try {
        patchExistingElement(name, existing, baseClass);
        console.info(`Fonrich: bestehende Karte ${name} auf v${VERSION} aktualisiert`);
      } catch (error) {
        console.warn(`Fonrich: bestehende Karte ${name} konnte nicht aktualisiert werden`, error);
      }
      return;
    }
    try {
      customElements.define(name, class extends baseClass {});
    } catch (error) {
      console.warn(`Fonrich: ${name} konnte nicht registriert werden`, error);
    }
  };

  safeDefine('fonrich-dashboard-editor-v100', FonrichDashboardEditor);
  const editor = () => document.createElement('fonrich-dashboard-editor-v100');

  const definitions = [
    ['fonrich-dashboard-overview-card', FonrichOverviewCard],
    ['fonrich-dashboard-controller-card', FonrichControllerCard],
    ['fonrich-dashboard-alarm-card', FonrichAlarmTestCard],
    ['fonrich-dashboard-channels-card', FonrichChannelsCard],
    ['fonrich-dashboard-bars-card', FonrichBarsCard],
    ['fonrich-dashboard-diagnostics-card', FonrichDiagnosticsCard],
    ['fonrich-modern-production-card', FonrichModernProductionCard],
    ['fonrich-solar-monitor-card', FonrichSolarMonitorCard],
    ['fonrich-solar-flow-card', FonrichSolarFlowCard],
  ];

  const aliases = [
    ['fonrich-system-overview-card', FonrichOverviewCard],
    ['fonrich-kasten-overview-card', FonrichOverviewCard],
    ['fonrich-production-overview-card', FonrichModernProductionCard],
    ['fonrich-overview-card', FonrichOverviewCard],
    ['fonrich-controller-detail-card', FonrichControllerCard],
    ['fonrich-kasten-card', FonrichControllerCard],
    ['fonrich-controller-card', FonrichControllerCard],
    ['fonrich-channel-table-card', FonrichChannelsCard],
    ['fonrich-strings-card', FonrichSolarMonitorCard],
    ['fonrich-power-bars-card', FonrichBarsCard],
    ['fonrich-alarm-center-card', FonrichAlarmTestCard],
    ['fonrich-alarms-card', FonrichAlarmTestCard],
    ['fonrich-diagnostics-card', FonrichDiagnosticsCard],
    ['fonrich-energy-card', FonrichSolarFlowCard],
  ];

  for (const [, cardClass] of definitions) cardClass.getConfigElement = editor;
  for (const [name, cardClass] of definitions) safeDefine(name, cardClass);
  for (const [name, cardClass] of aliases) safeDefine(name, cardClass);

  const allFonrichTypes = new Set([...definitions, ...aliases].map(([name]) => name));
  window.customCards = (window.customCards || []).filter((item) => !allFonrichTypes.has(item.type));

  const suggestionFor = (cardType, hass, entityId) => {
    const state = hass?.states?.[entityId];
    if (!looksLikeFonrich(entityId, state)) return null;
    const role = inferRole(entityId, state);
    const slaveValue = Number(state?.attributes?.controller_slave);
    const slave = Number.isFinite(slaveValue) ? slaveValue : 0;
    const controllerConfig = slave > 0 ? { slave } : {};

    const roleGroups = {
      'fonrich-dashboard-overview-card': ['gateway_status', 'gateway_messages'],
      'fonrich-dashboard-controller-card': ['controller_online', 'controller_messages', 'controller_voltage', 'controller_total_current', 'controller_total_power', 'channel_current', 'channel_voltage', 'channel_power', 'channel_daily_max_current'],
      'fonrich-modern-production-card': ['controller_total_current', 'controller_total_power', 'channel_current', 'channel_voltage', 'channel_power', 'channel_daily_max_current'],
      'fonrich-solar-monitor-card': ['controller_total_current', 'controller_total_power', 'channel_current', 'channel_voltage', 'channel_power', 'channel_daily_max_current'],
      'fonrich-solar-flow-card': ['gateway_status', 'controller_total_power', 'channel_power'],
      'fonrich-dashboard-alarm-card': ['gateway_messages', 'controller_messages', 'command_button', 'safety_test_button', 'safety_test_status', 'digital_input'],
      'fonrich-dashboard-channels-card': ['channel_current', 'channel_voltage', 'channel_power', 'channel_daily_max_current'],
      'fonrich-dashboard-bars-card': ['channel_current', 'channel_power', 'channel_daily_max_current'],
      'fonrich-dashboard-diagnostics-card': ['gateway_status', 'controller_online'],
    };
    if (!(roleGroups[cardType] || []).includes(role)) return null;
    return { config: { type: `custom:${cardType}`, ...controllerConfig } };
  };

  const cards = [
    { type: 'fonrich-dashboard-overview-card', name: 'Fonrich Gesamtübersicht', description: 'Status, Gesamtwerte, Meldungen, DI-Eingänge und Bedienung' },
    { type: 'fonrich-dashboard-controller-card', name: 'Fonrich Kasten und Kanäle', description: 'Ein Kasten mit Ampere, Volt, Watt, Tagesmaximum und Buttons' },
    { type: 'fonrich-modern-production-card', name: 'Fonrich Modern Produktion', description: 'Moderne Produktionskarte mit korrekter automatischer Entity-Erkennung' },
    { type: 'fonrich-solar-monitor-card', name: 'Fonrich Solar Monitor', description: 'Solarzellen- und Stringansicht mit Leistung, Strom, Spannung und Tagesmaximum' },
    { type: 'fonrich-solar-flow-card', name: 'Fonrich Solar Energiefluss', description: 'Solar-Flowkarte von den Strings über die Kästen bis Wechselrichter, Haus, Netz und Batterie' },
    { type: 'fonrich-dashboard-alarm-card', name: 'Fonrich Schutz, Alarm und Tests', description: 'Alarmzentrale mit Reset, Selbsttest und abgesichertem Hauptschalter-Test' },
    { type: 'fonrich-dashboard-channels-card', name: 'Fonrich Kanaltabelle', description: 'Tabelle für alle Kanäle und Kästen' },
    { type: 'fonrich-dashboard-bars-card', name: 'Fonrich Kanalvergleich', description: 'Balkenvergleich für Watt, Ampere oder Tagesmaximum' },
    { type: 'fonrich-dashboard-diagnostics-card', name: 'Fonrich Busdiagnose', description: 'Abfragezeiten, Fehlerzähler und Kommunikationszustand' },
  ];

  for (const card of cards) {
    window.customCards.push({
      ...card,
      preview: true,
      documentationURL: DOCS_URL,
      getEntitySuggestion: (hass, entityId) => suggestionFor(card.type, hass, entityId),
    });
  }

  window.FonrichDashboardDebug = {
    version: VERSION,
    buildModel: buildFonrichModel,
    inferRole,
    looksLikeFonrich,
  };

  window.dispatchEvent(new Event('fonrich-dashboard-loaded'));
  console.info(`Fonrich DC Monitor dashboard cards loaded v${VERSION}`);
})();
