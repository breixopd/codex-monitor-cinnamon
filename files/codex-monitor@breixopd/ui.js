'use strict';

const BarLevel = imports.ui.barLevel;
const Clutter = imports.gi.Clutter;
const St = imports.gi.St;

function _clear(actor) {
  for (const child of actor.get_children())
    child.destroy();
}

function _button(label, callback, styleClass = 'codex-monitor-button') {
  const button = new St.Button({
    label,
    style_class: styleClass,
    reactive: true,
    can_focus: true,
    track_hover: true,
    x_align: Clutter.ActorAlign.CENTER,
  });
  button.connect('clicked', callback);
  return button;
}

class QuotaCard {
  constructor(title, translate) {
    this._ = translate;
    this.actor = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-quota-card',
      x_expand: true,
    });
    this._title = new St.Label({ text: title, style_class: 'codex-monitor-card-kicker' });
    this._percent = new St.Label({ text: '—', style_class: 'codex-monitor-percent' });
    this._bar = new BarLevel.BarLevel({ style_class: 'codex-monitor-bar' });
    this._reset = new St.Label({
      text: this._('Waiting for Codex…'),
      style_class: 'codex-monitor-secondary',
    });
    this.actor.add_child(this._title);
    this.actor.add_child(this._percent);
    this.actor.add_child(this._bar);
    this.actor.add_child(this._reset);
  }

  update(window, model, now) {
    if (!window) {
      this._percent.set_text('—');
      this._bar.value = 0;
      this._reset.set_text(this._('Not available'));
      return;
    }
    const percentage = Math.max(0, Math.min(100, Number(window.usedPercent)));
    this._percent.set_text(`${Math.round(percentage)}% ${this._('used')}`);
    this._bar.value = percentage / 100;
    if (window.resetsAt == null) {
      this._reset.set_text(this._('Reset time unavailable'));
      return;
    }
    const countdown = model.formatDuration(Number(window.resetsAt) - now);
    const exact = new Date(Number(window.resetsAt) * 1000).toLocaleString();
    this._reset.set_text(`${this._('Resets in')} ${countdown} · ${exact}`);
  }
}

var Dashboard = class Dashboard {
  constructor(options) {
    this._ = options.translate;
    this._model = options.model;
    this._graph = options.graph;
    this._callbacks = options.callbacks;
    this._snapshot = null;
    this._remoteStatus = null;
    this._pairing = null;
    this._settings = {};

    this.actor = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-dashboard',
    });
    this._buildHeader();
    this._buildQuotaCards();
    this._buildGraph();
    this._buildResetBank();
    this._buildRemote();
    this._buildFooter();
  }

  _buildHeader() {
    const header = new St.BoxLayout({ style_class: 'codex-monitor-header' });
    const title = new St.Label({
      text: this._('Codex Monitor'),
      style_class: 'codex-monitor-title',
      x_expand: true,
    });
    this._status = new St.Label({
      text: this._('Connecting…'),
      style_class: 'codex-monitor-status',
    });
    header.add_child(title);
    header.add_child(this._status);
    this.actor.add_child(header);
  }

  _buildQuotaCards() {
    const row = new St.BoxLayout({ style_class: 'codex-monitor-card-row' });
    this._fiveHourCard = new QuotaCard(this._('5-HOUR'), this._);
    this._weeklyCard = new QuotaCard(this._('WEEKLY'), this._);
    row.add_child(this._fiveHourCard.actor);
    row.add_child(this._weeklyCard.actor);
    this.actor.add_child(row);
  }

  _buildGraph() {
    const section = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-section',
    });
    const heading = new St.BoxLayout({ style_class: 'codex-monitor-section-heading' });
    heading.add_child(new St.Label({
      text: this._('Usage trend'),
      style_class: 'codex-monitor-section-title',
      x_expand: true,
    }));
    this._modeButtons = {};
    for (const [mode, label] of [
      ['quota', this._('Quota')],
      ['activity', this._('Activity')],
      ['both', this._('Both')],
    ]) {
      const button = _button(label, () => this._callbacks.onGraphMode(mode), 'codex-monitor-tab');
      this._modeButtons[mode] = button;
      heading.add_child(button);
    }
    section.add_child(heading);
    this._graphActor = this._graph.createQuotaGraph();
    section.add_child(this._graphActor);

    const ranges = new St.BoxLayout({ style_class: 'codex-monitor-range-row' });
    this._rangeButtons = {};
    for (const [hours, label] of [[24, '24h'], [168, '7d'], [720, '30d']]) {
      const button = _button(label, () => this._callbacks.onGraphRange(hours), 'codex-monitor-range');
      this._rangeButtons[hours] = button;
      ranges.add_child(button);
    }
    section.add_child(ranges);
    this.actor.add_child(section);
  }

  _buildResetBank() {
    this._resetSection = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-section',
    });
    this._resetHeading = new St.Label({
      text: this._('Banked resets'),
      style_class: 'codex-monitor-section-title',
    });
    this._resetList = new St.BoxLayout({ vertical: true });
    this._resetSection.add_child(this._resetHeading);
    this._resetSection.add_child(this._resetList);
    this.actor.add_child(this._resetSection);
  }

  _buildRemote() {
    this._remoteSection = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-section codex-monitor-remote-section',
    });
    const heading = new St.BoxLayout({ style_class: 'codex-monitor-section-heading' });
    heading.add_child(new St.Label({
      text: this._('Remote access · Experimental'),
      style_class: 'codex-monitor-section-title',
      x_expand: true,
    }));
    this._remoteLabel = new St.Label({
      text: this._('Disabled'),
      style_class: 'codex-monitor-status',
    });
    heading.add_child(this._remoteLabel);
    this._remoteButtons = new St.BoxLayout({ style_class: 'codex-monitor-action-row' });
    this._pairingLabel = new St.Label({
      text: '',
      style_class: 'codex-monitor-pairing-code',
    });
    this._remoteSection.add_child(heading);
    this._remoteSection.add_child(this._pairingLabel);
    this._remoteSection.add_child(this._remoteButtons);
    this.actor.add_child(this._remoteSection);
  }

  _buildFooter() {
    const footer = new St.BoxLayout({ style_class: 'codex-monitor-footer' });
    this._updated = new St.Label({
      text: this._('No data yet'),
      style_class: 'codex-monitor-secondary',
      x_expand: true,
    });
    footer.add_child(this._updated);
    footer.add_child(_button(this._('Refresh'), this._callbacks.onRefresh));
    footer.add_child(_button(this._('Settings'), this._callbacks.onSettings));
    this.actor.add_child(footer);
  }

  setSettings(settings) {
    this._settings = settings;
    this._remoteSection.visible = Boolean(settings.enableRemote);
    for (const [mode, button] of Object.entries(this._modeButtons))
      this._setChecked(button, mode === settings.graphMode);
    for (const [hours, button] of Object.entries(this._rangeButtons))
      this._setChecked(button, Number(hours) === Number(settings.graphRangeHours));
    this._renderGraph();
  }

  _setChecked(button, checked) {
    if (checked)
      button.add_style_pseudo_class('checked');
    else
      button.remove_style_pseudo_class('checked');
  }

  update(snapshot, remoteStatus) {
    this._snapshot = snapshot;
    this._remoteStatus = remoteStatus || this._remoteStatus;
    const now = Math.floor(Date.now() / 1000);
    const plan = snapshot.planType || snapshot.account && snapshot.account.planType || this._('Unknown plan');
    this._status.set_text(`${plan} · ${this._('Live')} ●`);
    this._fiveHourCard.update(snapshot.windows.fiveHour, this._model, now);
    this._weeklyCard.update(snapshot.windows.weekly, this._model, now);
    this._updated.set_text(`${this._('Updated')} ${this._model.formatDuration(now - snapshot.capturedAt)} ${this._('ago')}`);
    this._renderGraph();
    this._renderResetBank();
    this._renderRemote();
  }

  showError(message) {
    this._status.set_text(this._('Stale · retrying'));
    this._updated.set_text(message || this._('Unable to refresh Codex'));
  }

  setRemoteStatus(status) {
    this._remoteStatus = status;
    this._renderRemote();
  }

  setPairing(pairing) {
    this._pairing = pairing;
    this._renderRemote();
  }

  showActionMessage(message) {
    this._updated.set_text(message);
  }

  _renderGraph() {
    if (!this._snapshot)
      return;
    const now = Math.floor(Date.now() / 1000);
    const cutoff = now - Number(this._settings.graphRangeHours || 168) * 3600;
    const mode = this._settings.graphMode || 'quota';
    const series = [];
    const markers = new Set();
    if (mode === 'quota' || mode === 'both') {
      for (const [windowName, label, colorIndex] of [
        ['fiveHour', '5h', 0],
        ['weekly', this._('Weekly'), 1],
      ]) {
        const points = this._model.quotaSeries(
          this._snapshot.history, windowName, cutoff, now
        ).map(point => {
          if (point.resetsAt != null)
            markers.add(point.resetsAt);
          return { timestamp: point.timestamp, value: point.usedPercent };
        });
        series.push({ label, points, colorIndex });
      }
    }
    if (mode === 'activity' || mode === 'both') {
      const points = this._model.activitySeries(this._snapshot.tokenUsage)
        .filter(point => point.timestamp >= cutoff);
      series.push({ label: this._('Activity'), points, colorIndex: 2 });
    }
    this._graph.updateQuotaGraph(this._graphActor, series, Array.from(markers));
  }

  _renderResetBank() {
    _clear(this._resetList);
    const bank = this._snapshot.resetCredits || { availableCount: 0, credits: [] };
    this._resetHeading.set_text(`${this._('Banked resets')} (${bank.availableCount || 0})`);
    const available = (bank.credits || []).filter(credit => credit.status === 'available');
    if (available.length === 0) {
      this._resetList.add_child(new St.Label({
        text: this._('No available reset credits'),
        style_class: 'codex-monitor-secondary',
      }));
      return;
    }
    const now = Math.floor(Date.now() / 1000);
    for (const credit of available) {
      const row = new St.BoxLayout({ style_class: 'codex-monitor-reset-row' });
      const expiry = credit.expiresAt
        ? `${this._('expires in')} ${this._model.formatDuration(credit.expiresAt - now)}`
        : this._('no expiry');
      const details = new St.BoxLayout({ vertical: true, x_expand: true });
      details.add_child(new St.Label({
        text: credit.title || this._('Codex limit reset'),
        style_class: 'codex-monitor-row-title',
      }));
      details.add_child(new St.Label({ text: expiry, style_class: 'codex-monitor-secondary' }));
      row.add_child(details);
      row.add_child(_button(this._('Apply…'), () => this._callbacks.onConsumeReset(credit)));
      this._resetList.add_child(row);
    }
  }

  _renderRemote() {
    if (!this._settings.enableRemote)
      return;
    const status = this._remoteStatus && this._remoteStatus.status || 'disabled';
    const labels = {
      disabled: this._('Disabled'),
      connecting: this._('Connecting…'),
      connected: this._('Connected'),
      errored: this._('Error'),
    };
    this._remoteLabel.set_text(labels[status] || this._('Unknown'));
    _clear(this._remoteButtons);
    if (status === 'connected') {
      this._remoteButtons.add_child(_button(this._('Stop'), this._callbacks.onRemoteStop));
      this._remoteButtons.add_child(_button(this._('Pair mobile'), this._callbacks.onRemotePair));
    } else {
      this._remoteButtons.add_child(_button(this._('Start'), this._callbacks.onRemoteStart));
    }
    const now = Math.floor(Date.now() / 1000);
    if (this._pairing && this._pairing.expiresAt > now) {
      const code = this._pairing.manualPairingCode || this._pairing.pairingCode;
      this._pairingLabel.set_text(
        `${this._('Pairing code')}: ${code} · ${this._('expires in')} ` +
        this._model.formatDuration(this._pairing.expiresAt - now)
      );
      this._pairingLabel.show();
    } else {
      this._pairingLabel.set_text('');
      this._pairingLabel.hide();
    }
  }
};
