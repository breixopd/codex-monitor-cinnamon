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
  const resetExpiring = availableCredits.some(credit =>
    Number(credit.expiresAt) - now <= expiryWarningSeconds
  );
  const remoteBadges = {
    connected: '●',
    connecting: '◐',
    errored: '!',
    disabled: '○',
  };

  return {
    label: `5h ${formatPercent(fiveHour)} · W ${formatPercent(weekly)}`,
    level,
    stale: now - Number(snapshot.capturedAt || 0) > Number(settings.staleSeconds || 300),
    resetBadge: settings.showResetBadge !== false && resetCredits.availableCount > 0
      ? `↻${resetCredits.availableCount}`
      : '',
    resetExpiring,
    remoteBadge: settings.showRemoteBadge !== false && remoteStatus
      ? remoteBadges[remoteStatus.status] || '!'
      : '',
  };
}

function quotaSeries(history, windowName, cutoff, now) {
  const prefix = windowName === 'weekly' ? 'weekly' : 'fiveHour';
  const usedKey = `${prefix}UsedPercent`;
  const resetKey = `${prefix}ResetsAt`;
  return (history || [])
    .filter(row => Number(row.capturedAt) >= cutoff && Number(row.capturedAt) <= now)
    .filter(row => row[usedKey] != null && row[resetKey] != null)
    .map(row => ({
      timestamp: Number(row.capturedAt),
      usedPercent: Number(row[usedKey]),
      resetsAt: Number(row[resetKey]),
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
    const resetIn = formatDuration(Number(window.resetsAt) - now);
    return `${name}: ${Math.round(Number(window.usedPercent))}% used · resets in ${resetIn}`;
  };
  const capturedAge = formatDuration(now - Number(snapshot.capturedAt || now));
  const resetCount = Number((snapshot.resetCredits || {}).availableCount || 0);
  const lines = [
    lineForWindow('5-hour', windows.fiveHour),
    lineForWindow('Weekly', windows.weekly),
    `Banked resets: ${resetCount}`,
  ];
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

const CodexModel = {
  formatDuration,
  formatPercent,
  panelState,
  quotaSeries,
  tooltipText,
  activitySeries,
};

if (typeof module !== 'undefined' && module.exports)
  module.exports = CodexModel;
