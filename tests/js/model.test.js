const test = require('node:test');
const assert = require('node:assert/strict');

const model = require('../../files/codex-monitor@breixopd/model.js');

function snapshot() {
  return {
    capturedAt: 1_799_100_000,
    account: { type: 'chatgpt', email: 'developer@example.com', planType: 'prolite' },
    windows: {
      fiveHour: null,
      weekly: {
        usedPercent: 32,
        windowDurationMins: 10080,
        resetsAt: 1_799_200_000,
      },
    },
    resetCredits: {
      availableCount: 2,
      credits: [{ status: 'available', expiresAt: 1_799_110_000 }],
    },
    history: [],
  };
}

test('panel state uses explicit used percentages and conditional badges', () => {
  const state = model.panelState(snapshot(), {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
    resetExpiryWarningHours: 72,
    showResetBadge: true,
    showRemoteBadge: true,
  }, 1_799_100_100, { status: 'connected' });

  assert.equal(state.label, '5h —  W 32%');
  assert.equal(state.level, 'normal');
  assert.equal(state.resetBadge, '⚠2');
  assert.equal(state.resetExpiring, true);
  assert.match(state.resetExpiryText, /^Reset expires in /);
  assert.equal(state.remoteBadge, '●');
  assert.equal(state.staleBadge, '');
  assert.equal(state.stale, false);
  assert.match(state.indicatorText, /Banked reset expires in/);
  assert.match(state.indicatorText, /Remote Control connected/);
});

test('panel state keeps ordinary reset badge and hides disabled remote state', () => {
  const value = snapshot();
  value.resetCredits.credits[0].expiresAt = 1_800_000_000;

  const state = model.panelState(value, {
    resetExpiryWarningHours: 1,
    showResetBadge: true,
    showRemoteBadge: true,
  }, 1_799_100_100, { status: 'disabled' });

  assert.equal(state.resetBadge, '↻2');
  assert.equal(state.resetExpiring, false);
  assert.equal(state.resetExpiryText, '');
  assert.equal(state.remoteBadge, '');
});

test('panel state marks stale data and highest quota pressure', () => {
  const value = snapshot();
  value.windows.fiveHour = { usedPercent: 94, resetsAt: 1_799_200_000 };

  const state = model.panelState(value, {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
  }, 1_799_100_301, null);

  assert.equal(state.level, 'critical');
  assert.equal(state.stale, true);
  assert.equal(state.staleBadge, '!');
  assert.match(state.indicatorText, /Usage data stale/);
});

test('panel state exposes ordered indicators with explicit quota severity', () => {
  const value = snapshot();
  value.windows.fiveHour = { usedPercent: 74, resetsAt: 1_799_200_000 };
  value.resetCredits = { availableCount: 0, credits: [] };

  const warning = model.panelState(value, {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
  }, 1_799_100_100, { status: 'connecting' });

  assert.deepEqual(warning.indicators, [
    {
      kind: 'quota',
      severity: 'warning',
      symbol: '!',
      text: '5-hour quota warning: 74% used',
    },
    {
      kind: 'remote',
      severity: 'warning',
      symbol: '◐',
      text: 'Remote Control connecting',
    },
  ]);

  value.windows.weekly.usedPercent = 94;
  const critical = model.panelState(value, {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
  }, 1_799_100_100, { status: 'errored' });
  assert.deepEqual(critical.indicators.map(indicator => [
    indicator.kind, indicator.severity, indicator.text,
  ]), [
    ['quota', 'critical', 'Weekly quota critical: 94% used'],
    ['remote', 'critical', 'Remote Control error'],
  ]);
});

test('panel reset indicators distinguish info warning and final six hours', () => {
  const value = snapshot();
  const settings = {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 300,
    resetExpiryWarningHours: 72,
  };
  const now = 1_799_100_000;

  value.resetCredits.credits[0].expiresAt = now + 100 * 3600;
  assert.deepEqual(model.panelState(value, settings, now, null).indicators, [{
    kind: 'reset',
    severity: 'info',
    symbol: '↻2',
    text: '2 banked resets available',
  }]);

  value.resetCredits.credits[0].expiresAt = now + 48 * 3600;
  assert.deepEqual(model.panelState(value, settings, now, null).indicators, [{
    kind: 'reset',
    severity: 'warning',
    symbol: '⚠2',
    text: 'Banked reset expires in 2d',
  }]);

  value.resetCredits.credits[0].expiresAt = now + 4 * 3600;
  assert.deepEqual(model.panelState(value, settings, now, null).indicators, [{
    kind: 'reset',
    severity: 'critical',
    symbol: '⚠2',
    text: 'Banked reset expires in 4h',
  }]);
});

test('panel indicators explain remote success and stale quota data', () => {
  const value = snapshot();
  value.resetCredits = { availableCount: 0, credits: [] };

  const state = model.panelState(value, {
    warningThreshold: 70,
    criticalThreshold: 90,
    staleSeconds: 60,
  }, 1_799_100_100, { status: 'connected' });

  assert.deepEqual(state.indicators, [
    {
      kind: 'remote',
      severity: 'success',
      symbol: '●',
      text: 'Remote Control connected',
    },
    {
      kind: 'stale',
      severity: 'critical',
      symbol: '!',
      text: 'Usage data stale',
    },
  ]);
  assert.equal(state.indicatorText,
    'Remote Control connected · Usage data stale');
});

test('duration formatting remains compact and never goes negative', () => {
  assert.equal(model.formatDuration(3661), '1h 1m');
  assert.equal(model.formatDuration(59), '<1m');
  assert.equal(model.formatDuration(-10), 'now');
  assert.equal(model.formatDuration(172800), '2d');
});

test('transient Remote read failures retain only usable live states', () => {
  assert.equal(model.isUsableRemoteStatus({ status: 'connected' }), true);
  assert.equal(model.isUsableRemoteStatus({ status: 'connecting' }), true);
  assert.equal(model.isUsableRemoteStatus({ status: 'disabled' }), false);
  assert.equal(model.isUsableRemoteStatus({ status: 'errored' }), false);
  assert.equal(model.isUsableRemoteStatus(null), false);
});

test('quota series filters by selected range and preserves reset markers', () => {
  const history = [
    { capturedAt: 100, fiveHourUsedPercent: 10, fiveHourResetsAt: 500 },
    { capturedAt: 1000, fiveHourUsedPercent: 20, fiveHourResetsAt: 1500 },
  ];

  assert.deepEqual(model.quotaSeries(history, 'fiveHour', 400, 1200), [
    {
      timestamp: 1000,
      usedPercent: 20,
      resetsAt: 1500,
      resetTransition: false,
    },
  ]);
});

test('quota series marks reset transitions without inventing diagonal data', () => {
  const history = [
    { capturedAt: 100, weeklyUsedPercent: 80, weeklyResetsAt: 500 },
    { capturedAt: 200, weeklyUsedPercent: 5, weeklyResetsAt: 900 },
    { capturedAt: 300, weeklyUsedPercent: 10, weeklyResetsAt: 900 },
  ];

  const points = model.quotaSeries(history, 'weekly', 0, 400);

  assert.deepEqual(points.map(point => point.resetTransition), [false, true, false]);
  assert.deepEqual(points.map(point => point.usedPercent), [80, 5, 10]);
});

test('quota segments break range-specific gaps but retain reset transitions', () => {
  const points = [
    { timestamp: 0, usedPercent: 10, resetTransition: false },
    { timestamp: 7201, usedPercent: 20, resetTransition: true },
    { timestamp: 7202, usedPercent: 30, resetTransition: false },
  ];

  assert.deepEqual(model.quotaSegments(points, 24).map(segment => segment.length), [1, 2]);
  assert.deepEqual(model.quotaSegments([
    { timestamp: 0, usedPercent: 10 },
    { timestamp: 43201, usedPercent: 20 },
  ], 168).map(segment => segment.length), [1, 1]);
  assert.deepEqual(model.quotaSegments([
    { timestamp: 0, usedPercent: 10 },
    { timestamp: 129601, usedPercent: 20 },
  ], 720).map(segment => segment.length), [1, 1]);
  assert.deepEqual(model.quotaSegments([], 24), []);
});

test('quota series bounds long histories while preserving endpoints', () => {
  const history = Array.from({ length: 2401 }, (_unused, index) => ({
    capturedAt: index,
    weeklyUsedPercent: index % 101,
    weeklyResetsAt: 5000,
  }));

  const points = model.quotaSeries(history, 'weekly', 0, 2400);

  assert.ok(points.length <= 1200);
  assert.equal(points[0].timestamp, 0);
  assert.equal(points.at(-1).timestamp, 2400);
});

test('quota downsampling preserves extrema reset transitions and endpoints', () => {
  const points = Array.from({ length: 5000 }, (_unused, index) => ({
    timestamp: index,
    usedPercent: index % 100,
    resetsAt: index < 2500 ? 6000 : 12000,
    resetTransition: index === 2500,
  }));
  points[1200].usedPercent = 0;
  points[1300].usedPercent = 100;

  const sampled = model.downsampleQuota(points, 1200);

  assert.ok(sampled.length <= 1200);
  assert.equal(sampled[0], points[0]);
  assert.equal(sampled.at(-1), points.at(-1));
  assert.ok(sampled.includes(points[2500]));
  assert.ok(sampled.includes(points[1200]));
  assert.ok(sampled.includes(points[1300]));
});

test('tooltip summarizes limits, reset bank, remote state, and freshness', () => {
  const text = model.tooltipText(snapshot(), 1_799_100_100, { status: 'connected' });

  assert.match(text, /5-hour: unavailable/);
  assert.match(text, /Weekly: 32% used/);
  assert.match(text, /Banked resets: 2/);
  assert.match(text, /Remote: connected/);
  assert.match(text, /Updated: 1m ago/);
  assert.doesNotMatch(text, /developer@example.com/);
});

test('tooltip does not invent a countdown when a reset time is unavailable', () => {
  const value = snapshot();
  value.windows.weekly.resetsAt = null;

  const text = model.tooltipText(value, 1_799_100_100, null);

  assert.match(text, /Weekly: 32% used · reset time unavailable/);
});

test('activity series normalizes daily token buckets for shared graph scale', () => {
  const usage = {
    dailyUsageBuckets: [
      { startDate: '2026-07-12', tokens: 250 },
      { startDate: '2026-07-13', tokens: 1000 },
    ],
  };

  const points = model.activitySeries(usage);

  assert.deepEqual(points.map(point => [point.value, point.tokens]), [
    [25, 250],
    [100, 1000],
  ]);
});

test('token formatting is compact without losing exact graph values', () => {
  assert.equal(model.formatTokenCount(999), '999');
  assert.equal(model.formatTokenCount(1200), '1.2K');
  assert.equal(model.formatTokenCount(1_234_567), '1.2M');
  assert.equal(model.formatTokenCount(2_000_000_000), '2B');

  const summary = model.graphSummary({
    label: 'Activity',
    kind: 'activity',
    points: [
      { timestamp: 100, value: 25, tokens: 250 },
      { timestamp: 200, value: 100, tokens: 900 },
    ],
  });

  assert.equal(summary.current.tokens, 900);
  assert.equal(summary.minimum.tokens, 250);
  assert.equal(summary.maximum.tokens, 900);
});

test('graph axis exposes start midpoint and end labels for the visible range', () => {
  const axis = model.graphAxis(100, 300, 24);

  assert.deepEqual(axis.map(item => item.timestamp), [100, 200, 300]);
  assert.equal(axis.length, 3);
  assert.ok(axis.every(item => typeof item.label === 'string' && item.label.length > 0));
});

test('graph axes distinguish quota activity and combined scales', () => {
  const activity = [{
    kind: 'activity',
    points: [
      { timestamp: 100, tokens: 500 },
      { timestamp: 200, tokens: 12_500 },
    ],
  }];

  const activityAxes = model.graphAxes(activity, 100, 300, 24, 'activity');
  assert.equal(activityAxes.left.kind, 'tokens');
  assert.equal(activityAxes.left.maximum, 15_000);
  assert.equal(activityAxes.right, null);
  assert.match(activityAxes.left.ticks[0].label, /15K/);

  const combined = model.graphAxes(activity, 100, 300, 24, 'both');
  assert.equal(combined.left.kind, 'percent');
  assert.equal(combined.left.maximum, 100);
  assert.equal(combined.right.kind, 'tokens');
  assert.equal(combined.right.maximum, 15_000);
  assert.deepEqual(combined.x.map(item => item.timestamp), [100, 200, 300]);
});

test('nearest graph values select one point from every available series', () => {
  const values = model.nearestGraphValues([
    {
      label: '5h',
      points: [
        { timestamp: 100, value: 10 },
        { timestamp: 200, value: 20 },
      ],
    },
    {
      label: 'Weekly',
      points: [
        { timestamp: 150, value: 30 },
        { timestamp: 220, value: 40 },
      ],
    },
    { label: 'Empty', points: [] },
  ], 205);

  assert.deepEqual(values.map(item => [item.label, item.value]), [
    ['5h', 20],
    ['Weekly', 40],
  ]);

  assert.deepEqual(model.nearestGraphValues([
    { label: 'Weekly', points: [{ timestamp: 100, value: 20 }] },
  ], 300, 50), []);
});

test('graph summary reports empty and insufficient history states', () => {
  assert.equal(model.graphSummary({ label: '5h', points: [] }).state, 'empty');
  assert.equal(model.graphSummary({
    label: '5h',
    points: [{ timestamp: 100, value: 10 }],
  }).state, 'insufficient');
});

test('update state accepts only bounded consistent bridge fields', () => {
  assert.deepEqual(model.normalizeUpdateState({
    installedVersion: '0.144.3',
    latestVersion: '0.145.0',
    updateAvailable: true,
    checkedAt: 1_800_000_000,
    status: 'idle',
    message: null,
  }), {
    installedVersion: '0.144.3',
    latestVersion: '0.145.0',
    updateAvailable: true,
    checkedAt: 1_800_000_000,
    status: 'idle',
    message: null,
  });

  assert.deepEqual(model.normalizeUpdateState({
    installedVersion: '0.145.0',
    latestVersion: '0.144.3',
    updateAvailable: true,
    checkedAt: -1,
    status: 'unknown',
    message: 'x'.repeat(1000),
  }), {
    installedVersion: '0.145.0',
    latestVersion: '0.144.3',
    updateAvailable: false,
    checkedAt: null,
    status: 'idle',
    message: null,
  });
});

test('update state preserves known active and result states without raw fields', () => {
  for (const status of ['checking', 'updating', 'updated', 'failed']) {
    const state = model.normalizeUpdateState({
      installedVersion: '0.144.3',
      latestVersion: '0.145.0',
      updateAvailable: true,
      checkedAt: 1_800_000_000,
      status,
      message: status === 'failed' ? 'Update failed' : null,
      privateDiagnostics: 'do not expose',
    });
    assert.equal(state.status, status);
    assert.equal(state.privateDiagnostics, undefined);
  }
});
