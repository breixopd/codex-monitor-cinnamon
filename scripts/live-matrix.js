(function () {
  var UUID = "codex-monitor@breixopd";
  var x = imports.ui.appletManager.getRunningInstancesForUuid(UUID)[0];
  if (!x)
    return JSON.stringify({ instance: false });
  var dashboard = x._dashboard;
  var model = dashboard._model;
  var saved = {
    snapshot: x._snapshot,
    remoteStatus: x._remoteStatus,
    sessions: x._sessions,
    updateState: x._updateState,
    pairing: x._pairing,
    remoteClients: dashboard._remoteClients,
    remoteClientsSupported: dashboard._remoteClientsSupported,
    remoteClientsAvailable: dashboard._remoteClientsAvailable,
    remoteClientsLoaded: dashboard._remoteClientsLoaded,
    remoteClientsLoading: dashboard._remoteClientsLoading,
    graphMode: x.graphMode,
    graphRangeHours: x.graphRangeHours,
    sessionFilter: dashboard._sessionFilter,
  };
  var results = { instance: true };
  var now = Math.floor(Date.now() / 1000);
  var settings = {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
    resetExpiryWarningHours: 72,
    showResetBadge: true,
    showRemoteBadge: true,
  };

  function snapshot(history, tokenBuckets) {
    return {
      capturedAt: now,
      planType: "test",
      windows: {
        fiveHour: { usedPercent: 48, resetsAt: now + 3600 },
        weekly: { usedPercent: 63, resetsAt: now + 86400 },
      },
      resetCredits: { availableCount: 0, credits: [] },
      history: history || [],
      tokenUsage: { dailyUsageBuckets: tokenBuckets || [] },
    };
  }

  function historyPoint(timestamp, fiveHour, weekly, reset) {
    return {
      capturedAt: timestamp,
      fiveHourUsedPercent: fiveHour,
      fiveHourResetsAt: reset,
      weeklyUsedPercent: weekly,
      weeklyResetsAt: reset + 86400,
    };
  }

  function indicatorState(value, remote) {
    return model.panelState(value, settings, now, remote).indicators;
  }

  try {
    var today = new Date(now * 1000).toISOString().slice(0, 10);
    var history = [
      historyPoint(now - 23 * 3600, 12, 42, now - 18 * 3600),
      historyPoint(now - 3 * 3600, 82, 61, now + 2 * 3600),
      historyPoint(now - 3600, 24, 63, now + 2 * 3600),
    ];
    x._snapshot = snapshot(history, [{ startDate: today, tokens: 12500 }]);
    var modes = ["quota", "activity", "both"];
    var ranges = [24, 168, 720];
    var graphCases = 0;
    var graphAxesValid = true;
    for (var modeIndex = 0; modeIndex < modes.length; modeIndex += 1) {
      for (var rangeIndex = 0; rangeIndex < ranges.length; rangeIndex += 1) {
        x.graphMode = modes[modeIndex];
        x.graphRangeHours = ranges[rangeIndex];
        x._render();
        var graph = dashboard._graphActor;
        var left = graph._leftAxis.get_children().map(function (label) {
          return label.get_text();
        });
        var rightVisible = graph._rightAxis.visible;
        var hasActivity = graph._area._series.some(function (series) {
          return series.kind === "activity";
        });
        var hasQuota = graph._area._series.some(function (series) {
          return series.kind === "quota" && Array.isArray(series.segments);
        });
        graphAxesValid = graphAxesValid && left.length === 5 &&
          (modes[modeIndex] === "activity" ? left[0].indexOf("%") < 0 :
            left[0].indexOf("%") >= 0) &&
          rightVisible === (modes[modeIndex] === "both") &&
          hasActivity === (modes[modeIndex] !== "quota") &&
          hasQuota === (modes[modeIndex] !== "activity");
        graphCases += 1;
      }
    }
    results.graphMatrix = graphCases === 9 && graphAxesValid;

    x.graphMode = "quota";
    x.graphRangeHours = 24;
    x._snapshot = snapshot([], []);
    x._render();
    results.emptyGraph = dashboard._graphActor._empty.visible;

    x._snapshot = snapshot([historyPoint(now - 60, 20, 30, now + 3600)], []);
    x._render();
    results.singleGraph = dashboard._graphActor._empty.get_text().indexOf("Collecting") >= 0;

    x._snapshot = snapshot([
      historyPoint(now - 10 * 3600, 10, 20, now + 3600),
      historyPoint(now - 3600, 40, 50, now + 7200),
    ], []);
    x._render();
    results.gapGraph = dashboard._graphActor._area._series[0].segments.length === 2;

    x.graphRangeHours = 168;
    x._snapshot = snapshot([
      historyPoint(now - 4 * 3600, 30, 55, now + 2 * 86400),
      historyPoint(now - 3 * 3600, 0, 0, now + 7 * 86400),
      historyPoint(now - 2 * 3600, 0, 0, now + 7 * 86400 + 3600),
      historyPoint(now - 60, 32, 57, now + 2 * 86400),
    ], []);
    x._render();
    results.foreignQuotaFiltered = dashboard._graphActor._area._series.every(
      function (series) { return series.points.length === 2; }
    ) && dashboard._graphActor._area._resetMarkers.length === 0;
    results.sparseQuotaFullRange =
      Math.abs(dashboard._graphActor._area._minimum - (now - 168 * 3600)) <= 2 &&
      Math.abs(dashboard._graphActor._area._maximum - now) <= 2 &&
      Math.abs(dashboard._graphActor._area._collectionStart - (now - 4 * 3600)) <= 2 &&
      dashboard._graphActor._hover.get_text().indexOf("History starts") >= 0 &&
      dashboard._graphActor._hover.get_text().indexOf("collected of 7d") >= 0;

    var dense = [];
    for (var denseIndex = 0; denseIndex < 1800; denseIndex += 1) {
      dense.push(historyPoint(
        now - 1800 + denseIndex,
        denseIndex % 101,
        (denseIndex * 3) % 101,
        denseIndex < 900 ? now + 3600 : now + 7200
      ));
    }
    x._snapshot = snapshot(dense, [{ startDate: today, tokens: 987654 }]);
    x._render();
    results.denseGraph = dashboard._graphActor._area._series.every(function (series) {
      return series.points.length <= 1200;
    });
    x.graphMode = "activity";
    x._render();
    results.peakGraph = dashboard._graphActor._leftAxis.get_children()[0]
      .get_text() === "1M";

    var unavailable = snapshot([], []);
    unavailable.windows = { fiveHour: null, weekly: null };
    results.quotaUnavailable = indicatorState(unavailable, null).length === 0;
    var normal = snapshot([], []);
    results.quotaNormal = indicatorState(normal, null).length === 0;
    var warning = snapshot([], []);
    warning.windows.weekly.usedPercent = 74;
    results.quotaWarning = indicatorState(warning, null).some(function (indicator) {
      return indicator.kind === "quota" && indicator.severity === "warning";
    });
    var critical = snapshot([], []);
    critical.windows.weekly.usedPercent = 94;
    results.quotaCritical = indicatorState(critical, null).some(function (indicator) {
      return indicator.kind === "quota" && indicator.severity === "critical";
    });
    var stale = snapshot([], []);
    stale.capturedAt = now - 301;
    results.staleCritical = indicatorState(stale, null).some(function (indicator) {
      return indicator.kind === "stale" && indicator.severity === "critical";
    });

    var reset = snapshot([], []);
    reset.resetCredits = {
      availableCount: 1,
      credits: [{ status: "available", expiresAt: now + 100 * 3600 }],
    };
    results.resetNormal = indicatorState(reset, null)[0].severity === "info";
    reset.resetCredits.credits[0].expiresAt = now + 48 * 3600;
    results.resetWarning = indicatorState(reset, null)[0].severity === "warning";
    reset.resetCredits.credits[0].expiresAt = now + 4 * 3600;
    results.resetCritical = indicatorState(reset, null)[0].severity === "critical";

    var indicatorSample = snapshot([], []);
    indicatorSample.windows.weekly.usedPercent = 94;
    indicatorSample.capturedAt = now - 301;
    indicatorSample.resetCredits = {
      availableCount: 1,
      credits: [{ status: "available", expiresAt: now + 100 * 3600 }],
    };
    dashboard.setIndicators(indicatorState(indicatorSample, { status: "connected" }));
    var indicatorRows = dashboard._indicatorList.get_children();
    var indicatorChips = [];
    indicatorRows.forEach(function (row) {
      indicatorChips = indicatorChips.concat(row.get_children());
    });
    results.indicatorRowsWrap = indicatorRows.length === 2 &&
      indicatorRows.every(function (row) { return row.get_children().length === 2; }) &&
      indicatorChips.every(function (chip) { return chip.clutter_text.get_line_wrap(); });
    results.indicatorTextComplete = indicatorChips.some(function (chip) {
      return chip.get_text() === "↻ 1 banked reset available";
    });

    results.remoteDisabled = indicatorState(normal, { status: "disabled" }).length === 0;
    results.remoteConnecting = indicatorState(normal, { status: "connecting" })[0]
      .severity === "warning";
    results.remoteRunning = indicatorState(normal, { status: "running" })[0]
      .text.indexOf("connection state unavailable") >= 0;
    results.remoteConnected = indicatorState(normal, { status: "connected" })[0]
      .severity === "success";
    results.remoteError = indicatorState(normal, { status: "errored" })[0]
      .severity === "critical";
    dashboard.setRemoteStatus({ status: "errored" });
    dashboard.showRemoteError("Codex Remote background service is stuck", true);
    results.remoteRepair = dashboard._remoteButtons.get_children().length === 2 &&
      dashboard._remoteButtons.get_children()[0].label === "Repair Remote…" &&
      dashboard._remoteButtons.get_children()[1].label === "Refresh";

    dashboard.setRemoteStatus({
      status: "connected",
      serverName: "Test workstation",
      environmentId: "environment-test",
    });
    dashboard._remoteClients = [];
    dashboard._remoteClientsSupported = true;
    dashboard._remoteClientsAvailable = true;
    dashboard._remoteClientsLoaded = false;
    dashboard.setRemoteClientsLoading(true);
    results.remoteDevicesLoading =
      dashboard._remoteClientsState.get_text() === "Checking" &&
      dashboard._remoteClientList.get_children()[0].get_text()
        .indexOf("Checking paired devices") >= 0;
    dashboard.setRemoteClients({ available: false });
    results.remoteDevicesUnavailable =
      dashboard._remoteClientsState.get_text() === "Unavailable" &&
      dashboard._remoteClientList.get_children()[0].get_text()
        .indexOf("not responding") >= 0;
    dashboard.setRemoteClients({ clients: [], supported: false });
    results.remoteDevicesUnsupported =
      dashboard._remoteClientsState.get_text() === "Unsupported" &&
      dashboard._remoteClientList.get_children()[0].get_text()
        .indexOf("does not expose device management") >= 0;
    dashboard.setRemoteClients({ clients: [] });
    results.remoteDevicesEmpty =
      dashboard._remoteClientsState.get_text() === "Live" &&
      dashboard._remoteClientList.get_children()[0].get_text() ===
        "No paired devices";
    dashboard.setRemoteClients({
      clients: [{
        clientId: "client-test",
        displayName: "Test phone",
        deviceType: "phone",
        platform: "android",
        lastSeenAt: now,
      }],
    });
    results.remoteDevicesListed =
      dashboard._remoteClientsState.get_text() === "Live" &&
      dashboard._remoteClientsHeading.get_text() === "Paired devices (1)" &&
      dashboard._remoteClientList.get_children().length === 1;

    var testSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 11 11" shape-rendering="crispEdges"><rect width="11" height="11" fill="#fff"/><path d="M4 4h1v1h-1z" fill="#000"/></svg>';
    dashboard.setPairing({
      qrSvg: testSvg,
      manualPairingCode: "TEST-ONLY",
      expiresAt: now + 600,
    });
    results.qrAvailable = dashboard._pairingQr.visible;
    results.qrScrollOverflow =
      dashboard.actor.get_preferred_height(dashboard.actor.width)[1] >
      x._dashboardScroll.height;
    dashboard.setPairing({
      qrSvg: "invalid",
      manualPairingCode: "TEST-ONLY",
      expiresAt: now + 600,
    });
    results.qrFallback = dashboard._pairingQrFallback.visible;
    dashboard.setPairing({ claimed: true });
    results.pairingClaimed = dashboard._pairingState.get_text().indexOf("complete") >= 0 &&
      dashboard._pairingManualLabel.get_text() === "";
    dashboard.setPairing({ manualPairingCode: "TEST-ONLY", expiresAt: now - 1 });
    results.pairingExpired = dashboard._pairing === null &&
      dashboard._pairingManualLabel.get_text() === "";

    dashboard.setUpdateState({
      installedVersion: "0.145.0", latestVersion: "0.145.0",
      updateAvailable: false, status: "idle", checkedAt: now,
    });
    results.updateCurrent = !dashboard._updateButton.visible;
    dashboard.setUpdateState({
      installedVersion: "0.144.3", latestVersion: "0.145.0",
      updateAvailable: true, status: "idle", checkedAt: now,
    });
    results.updateAvailable = dashboard._updateButton.visible;
    dashboard.setUpdateState({
      installedVersion: "0.144.3", latestVersion: "0.145.0",
      updateAvailable: true, status: "checking", checkedAt: now,
    });
    results.updateChecking = !dashboard._updateButton.visible;
    dashboard.setUpdateState({
      installedVersion: "0.144.3", latestVersion: "0.145.0",
      updateAvailable: true, status: "updating", checkedAt: now,
    });
    results.updateUpdating = dashboard._versionLabel.get_text().indexOf("Updating") >= 0;
    dashboard.setUpdateState({
      installedVersion: "0.145.0", latestVersion: "0.145.0",
      updateAvailable: false, status: "updated", checkedAt: now,
      message: "Updated to Codex 0.145.0. New Codex launches use this version.",
    });
    results.updateUpdated = !dashboard._updateButton.visible;
    dashboard.setUpdateState({
      installedVersion: "0.144.3", latestVersion: "0.145.0",
      updateAvailable: true, status: "failed", checkedAt: now,
      message: "Automatic update failed; Codex 0.144.3 is still installed. Use the official Codex installation instructions to update manually.",
    });
    results.updateFailed = dashboard._updateButton.visible &&
      dashboard._updateButton.label === "Retry" &&
      dashboard._versionLabel.get_text().indexOf("official Codex installation instructions") >= 0;

    dashboard.setSessions({ active: [], recent: [] });
    results.sessionsEmpty = dashboard._sessionList.get_children().length === 1 &&
      Object.keys(dashboard._sessionFilterButtons).length === 4;
    dashboard.setSessions({
      active: [{
        id: "019c0000-0000-7000-8000-000000000001",
        title: "Active", project: "Widgets", sourceLabel: "CLI",
        statusLabel: "Active", updatedAt: now,
        attention: ["waitingOnUserInput"],
      }],
      recent: [{
        id: "019c0000-0000-7000-8000-000000000002",
        title: "Finished", project: "Skynet", sourceLabel: "CLI",
        statusLabel: "Finished", updatedAt: now - 60,
        attention: [],
      }],
    });
    results.sessionsActiveRecent = dashboard._sessionList.get_children().length === 2;
    dashboard._sessionFilter = "attention";
    dashboard._renderSessions();
    results.sessionsAttentionFilter = dashboard._sessionList.get_children().length === 1 &&
      dashboard._sessionFilterButtons.attention.has_style_pseudo_class("checked");
    dashboard._sessionFilter = "all";
    dashboard._renderSessions();
    dashboard.showSessionsError();
    results.sessionsUnavailable = dashboard._sessionList.get_children()[0]
      .get_text().indexOf("unavailable") >= 0;

    x._updateDashboardLayout({ width: 1920, height: 1040 });
    results.responsiveWide = dashboard.actor.width === 640 &&
      !dashboard._compact && !dashboard._quotaRow.vertical &&
      dashboard._sessionFilters.get_children().length === 1 &&
      x._dashboardScroll.get_style().indexOf("752px") >= 0;

    x._updateDashboardLayout({ width: 560, height: 600 });
    var compactFilterRows = dashboard._sessionFilters.get_children();
    var compactIndicatorRows = dashboard._indicatorList.get_children();
    var compactRemoteRows = dashboard._remoteClientList.get_children();
    results.responsiveCompact = dashboard.actor.width === 508 &&
      dashboard._compact && dashboard._header.vertical &&
      dashboard._quotaRow.vertical && dashboard._graphHeading.vertical &&
      dashboard._sessionHeadingRow.vertical && dashboard._remoteHeading.vertical &&
      dashboard._remoteButtons.vertical && dashboard._footer.vertical &&
      compactFilterRows.length === 2 && compactFilterRows.every(function (row) {
        return row.get_children().length === 2;
      }) && compactIndicatorRows.length === 4 &&
      compactIndicatorRows.every(function (row) {
        return row.get_children().length === 1;
      }) && compactRemoteRows.length === 1 && compactRemoteRows[0].vertical &&
      x._dashboardScroll.get_style().indexOf("552px") >= 0;

    x._updateDashboardLayout({ width: 360, height: 400 });
    results.responsiveShort = dashboard.actor.width === 308 &&
      dashboard._compact &&
      x._dashboardScroll.get_style().indexOf("352px") >= 0;
  } catch (error) {
    results.matrixException = true;
  } finally {
    x._snapshot = saved.snapshot;
    x._remoteStatus = saved.remoteStatus;
    x._sessions = saved.sessions;
    x._updateState = saved.updateState;
    x._pairing = saved.pairing;
    x.graphMode = saved.graphMode;
    x.graphRangeHours = saved.graphRangeHours;
    dashboard._sessionFilter = saved.sessionFilter;
    dashboard._remoteClients = saved.remoteClients;
    dashboard._remoteClientsSupported = saved.remoteClientsSupported;
    dashboard._remoteClientsAvailable = saved.remoteClientsAvailable;
    dashboard._remoteClientsLoaded = saved.remoteClientsLoaded;
    dashboard._remoteClientsLoading = saved.remoteClientsLoading;
    dashboard.setSessions(saved.sessions || { active: [], recent: [] });
    dashboard.setRemoteStatus(saved.remoteStatus || { status: "disabled" });
    dashboard.setPairing(saved.pairing || null);
    dashboard.setUpdateState(saved.updateState || {});
    x._render();
    x._updateDashboardLayout();
  }
  return JSON.stringify(results);
})()
