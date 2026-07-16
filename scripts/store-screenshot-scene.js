(function () {
  var UUID = 'codex-monitor@breixopd';
  var Main = imports.ui.main;
  var PopupMenu = imports.ui.popupMenu;
  var Clutter = imports.gi.Clutter;
  var St = imports.gi.St;
  var x = imports.ui.appletManager.getRunningInstancesForUuid(UUID)[0];
  if (!x)
    return JSON.stringify({ ready: false, reason: 'not-running' });
  if (global._codexMonitorDestroyScreenshotScene)
    global._codexMonitorDestroyScreenshotScene();

  var Dashboard = x._dashboard.constructor;
  var Model = x._dashboard._model;
  var Graph = x._dashboard._graph;
  var translate = x._;
  var noOp = function () {};
  var callbacks = {
    onRefresh: noOp,
    onGraphMode: noOp,
    onGraphRange: noOp,
    onConsumeReset: noOp,
    onOpenCodex: noOp,
    onOpenSession: noOp,
    onRemoteStart: noOp,
    onRemoteStop: noOp,
    onRemotePair: noOp,
    onRemoteRefresh: noOp,
    onRemoteRevoke: noOp,
    onUpdate: noOp,
  };
  var now = Math.floor(Date.now() / 1000);
  var history = [];
  for (var index = 0; index <= 24; index += 1) {
    var timestamp = now - (24 - index) * 3600;
    var afterReset = index >= 16;
    history.push({
      capturedAt: timestamp,
      fiveHourUsedPercent: afterReset ? 4 + (index - 16) * 2.5 : 9 + index * 2,
      fiveHourResetsAt: afterReset ? now + 2 * 3600 : now - 8 * 3600,
      weeklyUsedPercent: 31 + Math.round(index * 36 / 24),
      weeklyResetsAt: now + 5 * 86400,
    });
  }
  var settings = {
    warningThreshold: 65,
    criticalThreshold: 90,
    staleSeconds: 300,
    resetExpiryWarningHours: 72,
    showResetBadge: true,
    showRemoteBadge: true,
    graphMode: 'quota',
    graphRangeHours: 24,
  };
  var snapshot = {
    capturedAt: now,
    planType: 'Demo',
    windows: {
      fiveHour: { usedPercent: 24, resetsAt: now + 2 * 3600 },
      weekly: { usedPercent: 67, resetsAt: now + 5 * 86400 },
    },
    resetCredits: {
      availableCount: 1,
      credits: [{
        id: 'example-reset',
        status: 'available',
        title: 'Example reset',
        expiresAt: now + 5 * 86400,
      }],
    },
    history: history,
    tokenUsage: { dailyUsageBuckets: [] },
  };
  var remoteStatus = {
    status: 'connected',
    serverName: 'Example Remote',
    environmentId: 'demo-environment',
  };
  var sessions = {
    active: [{
      id: 'example-active',
      title: 'Example active session',
      project: 'Demo project',
      sourceLabel: 'CLI',
      status: 'active',
      statusLabel: 'Active',
      activeSince: now - 18 * 60,
      updatedAt: now - 120,
      attention: [],
    }],
    recent: [{
      id: 'example-finished',
      title: 'Example finished session',
      project: 'Demo project',
      sourceLabel: 'Codex app',
      status: 'notLoaded',
      statusLabel: 'Ready to resume',
      updatedAt: now - 900,
      attention: [],
    }],
  };
  var clients = {
    clients: [{
      clientId: 'example-phone',
      displayName: 'Example phone',
      deviceType: 'phone',
      platform: 'example-os',
      osVersion: '1',
      appVersion: '1.1.1',
      lastSeenAt: now - 60,
    }],
  };
  var panelState = Model.panelState(snapshot, settings, now, remoteStatus, translate);

  function createDashboard(compact, width, height) {
    var dashboard = new Dashboard({
      translate: translate,
      model: Model,
      graph: Graph,
      callbacks: callbacks,
    });
    dashboard.actor.set_width(compact ? 508 : 640);
    dashboard.setCompactLayout(compact);
    dashboard.setSettings(settings);
    dashboard.setSessions(sessions);
    dashboard.setRemoteClients(clients);
    dashboard.setUpdateState({
      installedVersion: '1.1.1',
      latestVersion: '1.1.1',
      updateAvailable: false,
      status: 'idle',
      checkedAt: now,
    });
    dashboard.update(snapshot, remoteStatus, panelState);
    var scroll = new St.ScrollView({
      style_class: 'codex-monitor-scroll',
      overlay_scrollbars: false,
      x_expand: true,
    });
    scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
    scroll.set_clip_to_allocation(true);
    scroll.add_actor(dashboard.actor);
    scroll.set_width(width);
    scroll.set_height(height);
    var menuItem = new PopupMenu.PopupBaseMenuItem({
      reactive: false,
      style_class: 'codex-monitor-menu-item',
    });
    menuItem.addActor(scroll);
    var frame = new St.BoxLayout({
      vertical: true,
      style: 'background-color: #242424; border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; padding: 0 12px;',
    });
    frame.add_child(menuItem.actor);
    return frame;
  }

  function createPanelRow(label, styleClass, window) {
    var row = new St.BoxLayout({
      style_class: 'codex-monitor-panel-usage-row',
      y_align: Clutter.ActorAlign.CENTER,
    });
    row.add_child(new St.Label({
      text: label,
      style_class: 'codex-monitor-panel-window-label',
      y_align: Clutter.ActorAlign.CENTER,
    }));
    var bar = Graph.createPanelBar(styleClass);
    Graph.updatePanelBar(bar, window);
    row.add_child(bar);
    return row;
  }

  function createPanel() {
    var panel = new St.BoxLayout({
      style_class: 'codex-monitor-panel codex-monitor-warning',
      y_align: Clutter.ActorAlign.CENTER,
    });
    var usage = new St.BoxLayout({
      vertical: true,
      style_class: 'codex-monitor-panel-usage',
      y_align: Clutter.ActorAlign.CENTER,
    });
    usage.add_child(createPanelRow(
      '5h', 'codex-monitor-five-hour-bar', snapshot.windows.fiveHour
    ));
    usage.add_child(createPanelRow(
      'W', 'codex-monitor-weekly-bar', snapshot.windows.weekly
    ));
    panel.add_child(usage);
    var indicators = new St.BoxLayout({
      style_class: 'codex-monitor-panel-indicators',
      y_align: Clutter.ActorAlign.CENTER,
    });
    panelState.indicators.forEach(function (indicator) {
      indicators.add_child(new St.Label({
        text: indicator.panelSymbol || indicator.symbol,
        style_class: 'codex-indicator codex-indicator-' + indicator.kind +
          ' codex-indicator-' + indicator.severity,
        y_align: Clutter.ActorAlign.CENTER,
      }));
    });
    panel.add_child(indicators);
    var frame = new St.Bin({
      child: panel,
      x_align: St.Align.MIDDLE,
      y_align: St.Align.MIDDLE,
      style: 'width: 548px; height: 58px; background-color: #181818; border: 1px solid rgba(255,255,255,0.06);',
    });
    return frame;
  }

  function createFooterPreview() {
    var dashboard = new Dashboard({
      translate: translate,
      model: Model,
      graph: Graph,
      callbacks: callbacks,
    });
    dashboard.actor.set_width(524);
    dashboard.setUpdateState({
      installedVersion: '1.1.1',
      latestVersion: '1.1.1',
      updateAvailable: false,
      status: 'idle',
      checkedAt: now - 12 * 60,
    });
    dashboard.update(snapshot, remoteStatus, panelState);
    var footer = dashboard._footer;
    dashboard.actor.remove_child(footer);
    dashboard.actor.destroy();
    var frame = new St.BoxLayout({
      vertical: true,
      style: 'width: 524px; background-color: #242424; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 12px;',
    });
    frame.add_child(footer);
    return frame;
  }

  function label(text) {
    return new St.Label({
      text: text,
      style: 'color: #a0a6ae; font-size: 13px; padding-bottom: 8px;',
    });
  }

  var left = new St.BoxLayout({ vertical: true });
  left.add_child(label('DASHBOARD'));
  left.add_child(createDashboard(false, 662, 796));
  var right = new St.BoxLayout({
    vertical: true,
    style: 'spacing: 16px;',
  });
  var compactGroup = new St.BoxLayout({ vertical: true });
  compactGroup.add_child(label('COMPACT'));
  compactGroup.add_child(createDashboard(true, 532, 596));
  right.add_child(compactGroup);
  var panelGroup = new St.BoxLayout({ vertical: true });
  panelGroup.add_child(label('PANEL'));
  panelGroup.add_child(createPanel());
  right.add_child(panelGroup);
  var footerGroup = new St.BoxLayout({ vertical: true });
  footerGroup.add_child(label('FOOTER'));
  footerGroup.add_child(createFooterPreview());
  right.add_child(footerGroup);
  var root = new St.BoxLayout({
    style: 'background-color: #14171a; padding: 20px; spacing: 18px;',
    reactive: true,
  });
  root.add_child(left);
  root.add_child(right);
  root.set_position(20, 20);
  root.set_size(1300, 880);
  Main.uiGroup.add_child(root);
  root.raise_top();
  global._codexMonitorScreenshotScene = { root: root };
  global._codexMonitorDestroyScreenshotScene = function () {
    var scene = global._codexMonitorScreenshotScene;
    if (scene && scene.root)
      scene.root.destroy();
    delete global._codexMonitorScreenshotScene;
    delete global._codexMonitorDestroyScreenshotScene;
    return true;
  };
  return JSON.stringify({ ready: true });
})()
