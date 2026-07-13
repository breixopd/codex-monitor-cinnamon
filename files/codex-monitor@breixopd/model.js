'use strict';

function formatDuration(seconds) {
  const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  if (safeSeconds === 0)
    return 'now';
  if (safeSeconds < 60)
    return '<1m';
  const minutes = Math.floor(safeSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) {
    const remainingHours = hours % 24;
    return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
  }
  if (hours > 0) {
    const remainingMinutes = minutes % 60;
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }
  return `${minutes}m`;
}

function panelState(snapshot, settings, now, remoteStatus) {
  const windows = snapshot.windows || {};
  const fiveHour = windows.fiveHour;
  const weekly = windows.weekly;
  const values = [fiveHour, weekly]
    .filter(Boolean)
    .map(window => Number(window.usedPercent));
  const highest = values.length > 0 ? Math.max(...values) : 0;
  let level = 'normal';
  if (highest >= Number(settings.criticalThreshold || 90))
    level = 'critical';
  else if (highest >= Number(settings.warningThreshold || 70))
    level = 'warning';

  const resetCredits = snapshot.resetCredits || { availableCount: 0, credits: [] };
  const availableCredits = (resetCredits.credits || [])
    .filter(credit => credit.status === 'available' && credit.expiresAt != null);
  const expiryWarningSeconds = Number(settings.resetExpiryWarningHours || 72) * 3600;
  const expiryTimes = availableCredits
    .map(credit => Number(credit.expiresAt))
    .filter(expiresAt => Number.isFinite(expiresAt) && expiresAt >= now)
    .sort((left, right) => left - right);
  const nearestExpiry = expiryTimes.length > 0 ? expiryTimes[0] : null;
  const resetExpiring = nearestExpiry != null &&
    nearestExpiry - now <= expiryWarningSeconds;
  const remoteBadges = {
    connected: '●',
    connecting: '◐',
    errored: '!',
    disabled: '',
  };
  const stale = now - Number(snapshot.capturedAt || 0) >
    Number(settings.staleSeconds || 300);
  const resetCount = Number(resetCredits.availableCount) || 0;

  return {
    label: `5h ${formatPercent(fiveHour)}  W ${formatPercent(weekly)}`,
    level,
    stale,
    staleBadge: stale ? '!' : '',
    resetBadge: settings.showResetBadge !== false && resetCount > 0
      ? `${resetExpiring ? '⚠' : '↻'}${resetCount}`
      : '',
    resetExpiring,
    resetExpiryText: resetExpiring
      ? `Reset expires in ${formatDuration(nearestExpiry - now)}`
      : '',
    remoteBadge: settings.showRemoteBadge !== false && remoteStatus
      ? Object.prototype.hasOwnProperty.call(remoteBadges, remoteStatus.status)
        ? remoteBadges[remoteStatus.status]
        : '!'
      : '',
  };
}

function quotaSeries(history, windowName, cutoff, now) {
  const prefix = windowName === 'weekly' ? 'weekly' : 'fiveHour';
  const usedKey = `${prefix}UsedPercent`;
  const resetKey = `${prefix}ResetsAt`;
  return (history || [])
    .filter(row => Number(row.capturedAt) >= cutoff && Number(row.capturedAt) <= now)
    .filter(row => row[usedKey] != null)
    .map(row => ({
      timestamp: Number(row.capturedAt),
      usedPercent: Number(row[usedKey]),
      resetsAt: row[resetKey] != null ? Number(row[resetKey]) : null,
    }));
}

function formatPercent(window) {
  return window && window.usedPercent != null
    ? `${Math.round(Number(window.usedPercent))}%`
    : '—';
}

function tooltipText(snapshot, now, remoteStatus) {
  const windows = snapshot.windows || {};
  const lineForWindow = (name, window) => {
    if (!window)
      return `${name}: unavailable`;
    const reset = window.resetsAt != null
      ? `resets in ${formatDuration(Number(window.resetsAt) - now)}`
      : 'reset time unavailable';
    return `${name}: ${Math.round(Number(window.usedPercent))}% used · ${reset}`;
  };
  const capturedAge = formatDuration(now - Number(snapshot.capturedAt || now));
  const resetCount = Number((snapshot.resetCredits || {}).availableCount || 0);
  const expiringCredits = ((snapshot.resetCredits || {}).credits || [])
    .filter(credit => credit.status === 'available' && credit.expiresAt != null)
    .map(credit => Number(credit.expiresAt))
    .filter(expiresAt => Number.isFinite(expiresAt) && expiresAt >= now)
    .sort((left, right) => left - right);
  const lines = [
    lineForWindow('5-hour', windows.fiveHour),
    lineForWindow('Weekly', windows.weekly),
    `Banked resets: ${resetCount}`,
  ];
  if (expiringCredits.length > 0)
    lines.push(`Nearest banked reset expiry: ${formatDuration(expiringCredits[0] - now)}`);
  if (remoteStatus)
    lines.push(`Remote: ${remoteStatus.status || 'unknown'}`);
  lines.push(`Updated: ${capturedAge} ago`);
  return lines.join('\n');
}

function activitySeries(tokenUsage) {
  const buckets = tokenUsage && tokenUsage.dailyUsageBuckets
    ? tokenUsage.dailyUsageBuckets
    : [];
  const peak = buckets.reduce((maximum, bucket) =>
    Math.max(maximum, Number(bucket.tokens) || 0), 0);
  return buckets.map(bucket => {
    const tokens = Number(bucket.tokens) || 0;
    return {
      timestamp: Math.floor(Date.parse(`${bucket.startDate}T00:00:00Z`) / 1000),
      value: peak > 0 ? Math.round((tokens / peak) * 100) : 0,
      tokens,
    };
  });
}

function formatTokenCount(value) {
  const tokens = Math.max(0, Number(value) || 0);
  const compact = (amount, suffix) =>
    `${amount.toFixed(1).replace(/\.0$/, '')}${suffix}`;
  if (tokens >= 1e9)
    return compact(tokens / 1e9, 'B');
  if (tokens >= 1e6)
    return compact(tokens / 1e6, 'M');
  if (tokens >= 1e3)
    return compact(tokens / 1e3, 'K');
  return `${Math.round(tokens)}`;
}

function graphSummary(series) {
  const points = (series && series.points || [])
    .slice()
    .sort((left, right) => Number(left.timestamp) - Number(right.timestamp));
  if (points.length === 0) {
    return {
      label: series && series.label || '',
      kind: series && series.kind || 'quota',
      state: 'empty',
      current: null,
      minimum: null,
      maximum: null,
    };
  }
  const metric = point => point.tokens != null
    ? Number(point.tokens)
    : Number(point.value);
  return {
    label: series.label || '',
    kind: series.kind || 'quota',
    state: points.length === 1 ? 'insufficient' : 'ready',
    current: points[points.length - 1],
    minimum: points.reduce((best, point) => metric(point) < metric(best) ? point : best),
    maximum: points.reduce((best, point) => metric(point) > metric(best) ? point : best),
  };
}

function _pad(value) {
  return `${value}`.padStart(2, '0');
}

function _axisLabel(timestamp, rangeHours) {
  const date = new Date(Number(timestamp) * 1000);
  const time = `${_pad(date.getHours())}:${_pad(date.getMinutes())}`;
  if (Number(rangeHours) <= 24)
    return time;
  const day = `${date.getFullYear()}-${_pad(date.getMonth() + 1)}-${_pad(date.getDate())}`;
  return Number(rangeHours) <= 168 ? `${day} ${time}` : day;
}

function graphAxis(cutoff, now, rangeHours) {
  const start = Number(cutoff);
  const end = Math.max(start, Number(now));
  const middle = start + (end - start) / 2;
  return [start, middle, end].map(timestamp => ({
    timestamp,
    label: _axisLabel(timestamp, rangeHours),
  }));
}

function nearestGraphValues(series, timestamp) {
  const target = Number(timestamp);
  return (series || [])
    .filter(item => item.points && item.points.length > 0)
    .map(item => {
      const point = item.points.reduce((best, candidate) =>
        Math.abs(Number(candidate.timestamp) - target) <
          Math.abs(Number(best.timestamp) - target) ? candidate : best);
      return { label: item.label, kind: item.kind || 'quota', ...point };
    });
}

const CodexModel = {
  formatDuration,
  formatPercent,
  panelState,
  quotaSeries,
  tooltipText,
  activitySeries,
  formatTokenCount,
  graphSummary,
  graphAxis,
  nearestGraphValues,
};

if (typeof module !== 'undefined' && module.exports)
  module.exports = CodexModel;
