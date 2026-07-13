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
  const quotaWindows = [
    { name: '5-hour', window: fiveHour },
    { name: 'Weekly', window: weekly },
  ].filter(item => item.window && Number.isFinite(Number(item.window.usedPercent)));
  const highestWindow = quotaWindows.reduce((highestValue, item) =>
    highestValue == null || Number(item.window.usedPercent) >
      Number(highestValue.window.usedPercent) ? item : highestValue, null);
  const highest = highestWindow ? Number(highestWindow.window.usedPercent) : 0;
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
  const stale = now - Number(snapshot.capturedAt || 0) >
    Number(settings.staleSeconds || 300);
  const resetCount = Number(resetCredits.availableCount) || 0;
  const indicators = [];
  if (level !== 'normal' && highestWindow) {
    indicators.push({
      kind: 'quota',
      severity: level,
      symbol: '!',
      text: `${highestWindow.name} quota ${level}: ${Math.round(highest)}% used`,
    });
  }
  if (settings.showResetBadge !== false && resetCount > 0) {
    const secondsUntilExpiry = nearestExpiry == null ? null : nearestExpiry - now;
    indicators.push({
      kind: 'reset',
      severity: resetExpiring
        ? secondsUntilExpiry <= 6 * 3600 ? 'critical' : 'warning'
        : 'info',
      symbol: `${resetExpiring ? '⚠' : '↻'}${resetCount}`,
      text: resetExpiring
        ? `Banked reset expires in ${formatDuration(secondsUntilExpiry)}`
        : `${resetCount} banked reset${resetCount === 1 ? '' : 's'} available`,
    });
  }
  if (settings.showRemoteBadge !== false && remoteStatus &&
      remoteStatus.status !== 'disabled') {
    const remoteIndicators = {
      connecting: {
        severity: 'warning', symbol: '◐', text: 'Remote Control connecting',
      },
      running: {
        severity: 'warning', symbol: '◐',
        text: 'Remote Control running; connection state unavailable',
      },
      connected: {
        severity: 'success', symbol: '●', text: 'Remote Control connected',
      },
      errored: {
        severity: 'critical', symbol: '!', text: 'Remote Control error',
      },
    };
    const remoteIndicator = remoteIndicators[remoteStatus.status] ||
      { severity: 'critical', symbol: '!', text: 'Remote Control status unknown' };
    indicators.push({ kind: 'remote', ...remoteIndicator });
  }
  if (stale) {
    indicators.push({
      kind: 'stale',
      severity: 'critical',
      symbol: '!',
      text: 'Usage data stale',
    });
  }
  const resetIndicator = indicators.find(indicator => indicator.kind === 'reset');
  const remoteIndicator = indicators.find(indicator => indicator.kind === 'remote');

  return {
    label: `5h ${formatPercent(fiveHour)}  W ${formatPercent(weekly)}`,
    level,
    stale,
    staleBadge: stale ? '!' : '',
    indicators,
    indicatorText: indicators.map(indicator => indicator.text).join(' · '),
    resetBadge: resetIndicator ? resetIndicator.symbol : '',
    resetSeverity: resetIndicator ? resetIndicator.severity : null,
    resetExpiring,
    resetExpiryText: resetExpiring
      ? `Reset expires in ${formatDuration(nearestExpiry - now)}`
      : '',
    remoteBadge: remoteIndicator ? remoteIndicator.symbol : '',
    remoteSeverity: remoteIndicator ? remoteIndicator.severity : null,
  };
}

function quotaSeries(history, windowName, cutoff, now) {
  const prefix = windowName === 'weekly' ? 'weekly' : 'fiveHour';
  const usedKey = `${prefix}UsedPercent`;
  const resetKey = `${prefix}ResetsAt`;
  const windowSeconds = windowName === 'weekly' ? 7 * 24 * 3600 : 5 * 3600;
  const rawPoints = (history || [])
    .filter(row => Number(row.capturedAt) >= cutoff && Number(row.capturedAt) <= now)
    .filter(row => row[usedKey] != null)
    .slice()
    .sort((left, right) => Number(left.capturedAt) - Number(right.capturedAt))
    .map(row => ({
      timestamp: Number(row.capturedAt),
      usedPercent: Number(row[usedKey]),
      resetsAt: row[resetKey] != null ? Number(row[resetKey]) : null,
    }));
  const previousPositive = [];
  let previous = null;
  for (const point of rawPoints) {
    previousPositive.push(previous);
    if (point.usedPercent > 0)
      previous = point;
  }
  const nextPositive = Array(rawPoints.length).fill(null);
  let next = null;
  for (let index = rawPoints.length - 1; index >= 0; index -= 1) {
    nextPositive[index] = next;
    if (rawPoints[index].usedPercent > 0)
      next = rawPoints[index];
  }
  const sameCycle = (left, right) => left && right && left.resetsAt != null &&
    right.resetsAt != null && Math.abs(left.resetsAt - right.resetsAt) <= 300;
  const points = rawPoints
    .filter((point, index) => point.usedPercent !== 0 ||
      !sameCycle(previousPositive[index], nextPositive[index]) ||
      sameCycle(point, previousPositive[index]))
    .map((point, index, visiblePoints) => ({
      ...point,
      resetTransition: index > 0 && visiblePoints[index - 1].resetsAt != null &&
        point.resetsAt != null &&
        point.resetsAt - visiblePoints[index - 1].resetsAt >= windowSeconds / 2 &&
        point.usedPercent <= visiblePoints[index - 1].usedPercent,
    }));
  return downsampleQuota(points, 1200);
}

function _evenlySample(items, maximum) {
  if (items.length <= maximum)
    return items;
  if (maximum <= 1)
    return items.slice(0, maximum);
  return Array.from({ length: maximum }, (_unused, index) =>
    items[Math.round(index * (items.length - 1) / (maximum - 1))]);
}

function downsampleQuota(points, maximumPoints = 1200) {
  const values = Array.isArray(points) ? points : [];
  const limit = Math.max(2, Math.floor(Number(maximumPoints) || 1200));
  if (values.length <= limit)
    return values;

  const mandatory = new Set([0, values.length - 1]);
  values.forEach((point, index) => {
    if (point.resetTransition)
      mandatory.add(index);
  });
  if (mandatory.size >= limit) {
    const indices = _evenlySample(Array.from(mandatory).sort((a, b) => a - b), limit);
    indices[0] = 0;
    indices[indices.length - 1] = values.length - 1;
    return Array.from(new Set(indices)).sort((a, b) => a - b).map(index => values[index]);
  }

  const selected = new Set(mandatory);
  const capacity = limit - selected.size;
  const bucketCount = Math.max(1, Math.floor(capacity / 2));
  for (let bucket = 0; bucket < bucketCount && selected.size < limit; bucket += 1) {
    const start = Math.floor(bucket * values.length / bucketCount);
    const end = Math.max(start + 1, Math.floor((bucket + 1) * values.length / bucketCount));
    let minimumIndex = start;
    let maximumIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if (Number(values[index].usedPercent) < Number(values[minimumIndex].usedPercent))
        minimumIndex = index;
      if (Number(values[index].usedPercent) > Number(values[maximumIndex].usedPercent))
        maximumIndex = index;
    }
    selected.add(minimumIndex);
    if (selected.size < limit)
      selected.add(maximumIndex);
  }
  return Array.from(selected)
    .sort((left, right) => left - right)
    .slice(0, limit)
    .map(index => values[index]);
}

function quotaSegments(points, rangeHours) {
  const thresholds = Number(rangeHours) <= 24
    ? 2 * 3600
    : Number(rangeHours) <= 168 ? 12 * 3600 : 36 * 3600;
  const ordered = (points || [])
    .slice()
    .sort((left, right) => Number(left.timestamp) - Number(right.timestamp));
  const segments = [];
  for (const point of ordered) {
    const current = segments[segments.length - 1];
    const previous = current && current[current.length - 1];
    if (!current || Number(point.timestamp) - Number(previous.timestamp) > thresholds)
      segments.push([point]);
    else
      current.push(point);
  }
  return segments;
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

function graphDomain(series, cutoff, now) {
  const selectedStart = Number(cutoff);
  const selectedEnd = Math.max(selectedStart, Number(now));
  const selectedSeconds = selectedEnd - selectedStart;
  const timestamps = (series || [])
    .flatMap(item => item.points || [])
    .map(point => Number(point.timestamp))
    .filter(timestamp => Number.isFinite(timestamp) &&
      timestamp >= selectedStart && timestamp <= selectedEnd);
  if (timestamps.length === 0) {
    return {
      start: selectedStart,
      end: selectedEnd,
      selectedSeconds,
      collectedSeconds: 0,
      collectionStart: null,
    };
  }
  const first = Math.min(...timestamps);
  const collectedSeconds = Math.max(0, selectedEnd - first);
  return {
    start: selectedStart,
    end: selectedEnd,
    selectedSeconds,
    collectedSeconds,
    collectionStart: first,
  };
}

function _tokenMaximum(series) {
  const peak = (series || [])
    .filter(item => item.kind === 'activity')
    .flatMap(item => item.points || [])
    .reduce((maximum, point) => Math.max(maximum, Number(point.tokens) || 0), 0);
  if (peak <= 0)
    return 1;
  const roughStep = peak / 4;
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const normalized = roughStep / magnitude;
  const stepFactor = [1, 2, 2.5, 5, 10].find(value => value >= normalized) || 10;
  const step = stepFactor * magnitude;
  return Math.ceil(peak / step) * step;
}

function _axisTicks(maximum, formatter) {
  return Array.from({ length: 5 }, (_unused, index) => {
    const value = maximum * (4 - index) / 4;
    return { value, label: formatter(value) };
  });
}

function graphAxes(series, cutoff, now, rangeHours, mode) {
  const domain = graphDomain(series, cutoff, now);
  const visibleHours = Math.max(1, (domain.end - domain.start) / 3600);
  const percentAxis = {
    kind: 'percent',
    maximum: 100,
    ticks: _axisTicks(100, value => `${Math.round(value)}%`),
  };
  const tokenMaximum = _tokenMaximum(series);
  const tokenAxis = {
    kind: 'tokens',
    maximum: tokenMaximum,
    ticks: _axisTicks(tokenMaximum, formatTokenCount),
  };
  return {
    x: graphAxis(domain.start, domain.end, visibleHours),
    left: mode === 'activity' ? tokenAxis : percentAxis,
    right: mode === 'both' ? tokenAxis : null,
    domain,
  };
}

function nearestGraphValues(series, timestamp, maximumDistance = null) {
  const target = Number(timestamp);
  return (series || [])
    .filter(item => item.points && item.points.length > 0)
    .map(item => {
      const point = item.points.reduce((best, candidate) =>
        Math.abs(Number(candidate.timestamp) - target) <
          Math.abs(Number(best.timestamp) - target) ? candidate : best);
      return { label: item.label, kind: item.kind || 'quota', ...point };
    })
    .filter(point => maximumDistance == null ||
      Math.abs(Number(point.timestamp) - target) <= Number(maximumDistance));
}

function isUsableRemoteStatus(remoteStatus) {
  const status = remoteStatus && remoteStatus.status;
  return status === 'connecting' || status === 'connected' || status === 'running';
}

function _semanticVersion(value) {
  if (typeof value !== 'string' || value.length > 64)
    return null;
  const match = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value);
  if (!match)
    return null;
  return {
    display: value,
    core: match.slice(1, 4).map(Number),
    prerelease: match[4] || null,
  };
}

function _isNewerSemanticVersion(candidate, current) {
  if (!candidate || !current)
    return false;
  for (let index = 0; index < 3; index += 1) {
    if (candidate.core[index] !== current.core[index])
      return candidate.core[index] > current.core[index];
  }
  return candidate.prerelease == null && current.prerelease != null;
}

function normalizeUpdateState(value) {
  const raw = value && typeof value === 'object' ? value : {};
  const installed = _semanticVersion(raw.installedVersion);
  const latest = _semanticVersion(raw.latestVersion);
  const statuses = new Set(['idle', 'checking', 'updating', 'updated', 'failed']);
  const checkedAt = Number(raw.checkedAt);
  return {
    installedVersion: installed ? installed.display : null,
    latestVersion: latest ? latest.display : null,
    updateAvailable: raw.updateAvailable === true &&
      _isNewerSemanticVersion(latest, installed),
    checkedAt: Number.isFinite(checkedAt) && checkedAt >= 0
      ? Math.floor(checkedAt) : null,
    status: statuses.has(raw.status) ? raw.status : 'idle',
    message: typeof raw.message === 'string' && raw.message.length <= 256
      ? raw.message : null,
  };
}

const CodexModel = {
  formatDuration,
  formatPercent,
  panelState,
  quotaSeries,
  quotaSegments,
  downsampleQuota,
  tooltipText,
  activitySeries,
  formatTokenCount,
  graphSummary,
  graphAxis,
  graphDomain,
  graphAxes,
  nearestGraphValues,
  isUsableRemoteStatus,
  normalizeUpdateState,
};

if (typeof module !== 'undefined' && module.exports)
  module.exports = CodexModel;
