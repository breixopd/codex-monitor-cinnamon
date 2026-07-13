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
  assert.match(state.indicatorText, /Reset expires in/);
  assert.match(state.indicatorText, /Remote connected/);
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
  assert.match(state.indicatorText, /Data stale/);
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
    { timestamp: 1000, usedPercent: 20, resetsAt: 1500 },
  ]);
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
});

test('graph summary reports empty and insufficient history states', () => {
  assert.equal(model.graphSummary({ label: '5h', points: [] }).state, 'empty');
  assert.equal(model.graphSummary({
    label: '5h',
    points: [{ timestamp: 100, value: 10 }],
  }).state, 'insufficient');
});
