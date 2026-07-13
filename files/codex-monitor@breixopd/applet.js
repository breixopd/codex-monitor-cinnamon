'use strict';

const Applet = imports.ui.applet;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Gettext = imports.gettext;
const Main = imports.ui.main;
const Mainloop = imports.mainloop;
const ModalDialog = imports.ui.modalDialog;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const St = imports.gi.St;
const Util = imports.misc.util;

const UUID = 'codex-monitor@breixopd';
const Modules = imports.applets[UUID];
const BridgeClient = Modules.bridgeClient.BridgeClient;
const Dashboard = Modules.ui.Dashboard;
const Graph = Modules.graph;
const Model = Modules.model;

class CodexMonitorApplet extends Applet.Applet {
  constructor(metadata, orientation, panelHeight, instanceId) {
    super(orientation, panelHeight, instanceId);
    this._metadata = metadata;
    this._orientation = orientation;
    this._snapshot = null;
    this._remoteStatus = null;
    this._refreshing = false;
    this._refreshTimer = 0;
    this._restartTimer = 0;
    this._restartAttempt = 0;
    this._bridge = null;

    Gettext.bindtextdomain(UUID, GLib.build_filenamev([metadata.path, 'locale']));
    this._ = text => Gettext.dgettext(UUID, text);
    this.setAllowedLayout(Applet.AllowedLayout.BOTH);
    this.actor.set_accessible_name(this._('Codex usage monitor'));

    this._bindSettings(instanceId);
    this._buildPanel();
    this._buildMenu();
    this._startBridge();
    this._installRefreshTimer();
  }

  _bindSettings(instanceId) {
    this.settings = new Settings.AppletSettings(this, UUID, instanceId);
    const restart = this._configurationChanged.bind(this);
    const render = this._render.bind(this);
    this.settings.bind('refresh-interval', 'refreshInterval', restart);
    this.settings.bind('history-days', 'historyDays', restart);
    this.settings.bind('codex-binary', 'codexBinary', restart);
    this.settings.bind('codex-home', 'codexHome', restart);
    this.settings.bind('warning-threshold', 'warningThreshold', render);
    this.settings.bind('critical-threshold', 'criticalThreshold', render);
    this.settings.bind('reset-expiry-warning-hours', 'resetExpiryWarningHours', render);
    this.settings.bind('show-reset-badge', 'showResetBadge', render);
    this.settings.bind('show-remote-badge', 'showRemoteBadge', render);
    this.settings.bind('enable-remote', 'enableRemote', restart);
    this.settings.bind('graph-mode', 'graphMode', render);
    this.settings.bind('graph-range-hours', 'graphRangeHours', render);
  }

  _buildPanel() {
    this._panelBox = new St.BoxLayout({
      style_class: 'codex-monitor-panel',
      reactive: false,
    });
    const iconPath = GLib.build_filenamev([this._metadata.path, 'icons', 'codex-monitor-symbolic.svg']);
    this._panelIcon = new St.Icon({
      gicon: Gio.icon_new_for_string(iconPath),
      icon_type: St.IconType.SYMBOLIC,
      style_class: 'system-status-icon codex-monitor-panel-icon',
    });
    this._panelMeter = Graph.createPanelMeter();
    this._panelLabel = new St.Label({
      text: '5h — · W —',
      style_class: 'codex-monitor-panel-label',
      y_align: St.Align.MIDDLE,
    });
    this._resetBadge = new St.Label({ text: '', style_class: 'codex-monitor-badge' });
    this._remoteBadge = new St.Label({ text: '', style_class: 'codex-monitor-remote-badge' });
    this._panelBox.add_child(this._panelIcon);
    this._panelBox.add_child(this._panelMeter);
    this._panelBox.add_child(this._panelLabel);
    this._panelBox.add_child(this._resetBadge);
    this._panelBox.add_child(this._remoteBadge);
    this.actor.add_child(this._panelBox);
    this.on_orientation_changed(this._orientation);
  }

  _buildMenu() {
    this.menu = new Applet.AppletPopupMenu(this, this._orientation);
    this._menuManager.addMenu(this.menu);
    this._dashboard = new Dashboard({
      translate: this._,
      model: Model,
      graph: Graph,
      callbacks: {
        onRefresh: this._refresh.bind(this),
        onSettings: this._openSettings.bind(this),
        onGraphMode: mode => {
          this.graphMode = mode;
          this._render();
        },
        onGraphRange: hours => {
          this.graphRangeHours = hours;
          this._render();
        },
        onConsumeReset: this._confirmConsumeReset.bind(this),
        onRemoteStart: this._confirmRemoteStart.bind(this),
        onRemoteStop: () => this._remoteAction('remote_stop'),
        onRemotePair: () => this._remoteAction('remote_pair'),
      },
    });
    this._menuItem = new PopupMenu.PopupBaseMenuItem({
      reactive: false,
      can_focus: false,
    });
    this._menuItem.addActor(this._dashboard.actor);
    this.menu.addMenuItem(this._menuItem);
    this._render();
  }

  _settingsView() {
    return {
      warningThreshold: this.warningThreshold,
      criticalThreshold: this.criticalThreshold,
      staleSeconds: 300,
      resetExpiryWarningHours: this.resetExpiryWarningHours,
      showResetBadge: this.showResetBadge,
      showRemoteBadge: this.showRemoteBadge,
      enableRemote: this.enableRemote,
      graphMode: this.graphMode,
      graphRangeHours: this.graphRangeHours,
    };
  }

  _startBridge() {
    if (this._bridge)
      this._bridge.stop();
    this._bridge = new BridgeClient({
      appletPath: this._metadata.path,
      codexBinary: this.codexBinary || 'codex',
      codexHome: this.codexHome || '',
      historyDays: this.historyDays || 30,
    });
    try {
      this._bridge.start();
      this._refresh();
    } catch (error) {
      this._handleRefreshError();
    }
  }

  _refresh() {
    if (this._refreshing || !this._bridge)
      return;
    this._refreshing = true;
    this._dashboard.showActionMessage(this._('Refreshing…'));
    this._bridge.request('snapshot', {}, (error, snapshot) => {
      this._refreshing = false;
      if (error) {
        this._handleRefreshError();
        return;
      }
      this._restartAttempt = 0;
      this._snapshot = snapshot;
      this._render();
      if (this.enableRemote)
        this._readRemoteStatus();
    });
  }

  _readRemoteStatus() {
    this._bridge.request('remote_status', {}, (error, status) => {
      this._remoteStatus = error ? { status: 'errored' } : status;
      this._render();
    });
  }

  _handleRefreshError() {
    this._dashboard.showError(this._('Unable to refresh Codex; showing last data'));
    this._render();
    this._restartAttempt += 1;
    if (this._restartTimer)
      return;
    const delay = Math.min(60, Math.pow(2, Math.min(5, this._restartAttempt)));
    this._restartTimer = Mainloop.timeout_add_seconds(delay, () => {
      this._restartTimer = 0;
      this._startBridge();
      return GLib.SOURCE_REMOVE;
    });
  }

  _render() {
    if (!this._dashboard)
      return;
    const settings = this._settingsView();
    this._dashboard.setSettings(settings);
    if (!this._snapshot) {
      this.set_applet_tooltip(this._('Codex Monitor · connecting'));
      return;
    }
    const now = Math.floor(Date.now() / 1000);
    const state = Model.panelState(this._snapshot, settings, now, this._remoteStatus);
    this._panelLabel.set_text(state.label);
    this._resetBadge.set_text(state.resetBadge);
    this._resetBadge.visible = Boolean(state.resetBadge);
    this._remoteBadge.set_text(state.remoteBadge);
    this._remoteBadge.visible = Boolean(state.remoteBadge) && this.enableRemote;
    Graph.updatePanelMeter(
      this._panelMeter,
      this._snapshot.windows.fiveHour,
      this._snapshot.windows.weekly
    );
    for (const style of ['normal', 'warning', 'critical', 'stale'])
      this._panelBox.remove_style_class_name(`codex-monitor-${style}`);
    this._panelBox.add_style_class_name(`codex-monitor-${state.level}`);
    if (state.stale)
      this._panelBox.add_style_class_name('codex-monitor-stale');
    this.set_applet_tooltip(Model.tooltipText(this._snapshot, now, this._remoteStatus));
    this._dashboard.update(this._snapshot, this._remoteStatus);
  }

  _confirmConsumeReset(credit) {
    const expiry = credit.expiresAt
      ? new Date(credit.expiresAt * 1000).toLocaleString()
      : this._('no expiry');
    const message = `${this._('Apply this banked reset?')}\n\n` +
      `${credit.title || this._('Codex limit reset')} · ${expiry}`;
    new ModalDialog.ConfirmDialog(message, () => {
      this._bridge.request('consume_reset', {
        creditId: credit.id,
        idempotencyKey: GLib.uuid_string_random(),
        confirmed: true,
      }, (error, result) => {
        this._dashboard.showActionMessage(error
          ? this._('Reset could not be applied')
          : `${this._('Reset result')}: ${result.outcome}`);
        this._refresh();
      });
    }).open();
  }

  _confirmRemoteStart() {
    const message = this._(
      'Start Codex Remote Control? This allows paired mobile clients to control this machine.'
    );
    new ModalDialog.ConfirmDialog(message, () => {
      this._remoteAction('remote_start', { confirmed: true });
    }).open();
  }

  _remoteAction(action, params = {}) {
    this._dashboard.showActionMessage(this._('Updating Remote Control…'));
    this._bridge.request(action, params, (error, result) => {
      if (error) {
        this._dashboard.showActionMessage(this._('Remote Control action failed'));
        this._remoteStatus = { status: 'errored' };
      } else if (action === 'remote_pair') {
        this._dashboard.setPairing(result);
        this._remoteStatus = { status: 'connected' };
      } else {
        this._remoteStatus = result;
      }
      this._render();
    });
  }

  _configurationChanged() {
    if (!this._dashboard)
      return;
    this._installRefreshTimer();
    this._startBridge();
    this._render();
  }

  _installRefreshTimer() {
    if (this._refreshTimer)
      Mainloop.source_remove(this._refreshTimer);
    this._refreshTimer = Mainloop.timeout_add_seconds(
      Math.max(30, Number(this.refreshInterval || 60)),
      () => {
        this._refresh();
        return GLib.SOURCE_CONTINUE;
      }
    );
  }

  _openSettings() {
    Util.spawn(['cinnamon-settings', 'applets', UUID]);
  }

  on_applet_clicked() {
    this.menu.toggle();
  }

  on_applet_middle_clicked() {
    this._refresh();
  }

  on_orientation_changed(orientation) {
    this._orientation = orientation;
    if (!this._panelLabel)
      return;
    const vertical = orientation === St.Side.LEFT || orientation === St.Side.RIGHT;
    this._panelLabel.visible = !vertical;
    this._resetBadge.visible = !vertical && Boolean(this._resetBadge.get_text());
    this._remoteBadge.visible = !vertical && this.enableRemote && Boolean(this._remoteBadge.get_text());
  }

  on_applet_removed_from_panel() {
    if (this._refreshTimer)
      Mainloop.source_remove(this._refreshTimer);
    if (this._restartTimer)
      Mainloop.source_remove(this._restartTimer);
    if (this._bridge)
      this._bridge.stop();
    if (this.menu)
      this.menu.destroy();
    if (this.settings)
      this.settings.finalize();
  }
}

function main(metadata, orientation, panelHeight, instanceId) {
  return new CodexMonitorApplet(metadata, orientation, panelHeight, instanceId);
}
