'use strict';

const Cairo = imports.cairo;
const St = imports.gi.St;

function _rgba(color, alpha) {
  return [color.red / 255, color.green / 255, color.blue / 255, alpha];
}

function _themeColor(area, property, fallback) {
  try {
    return area.get_theme_node().get_color(property);
  } catch (error) {
    return fallback || area.get_theme_node().get_foreground_color();
  }
}

var createPanelMeter = function() {
  const area = new St.DrawingArea({ style_class: 'codex-monitor-panel-meter' });
  area._values = [0, 0];
  area._available = [false, false];
  area.connect('repaint', _drawPanelMeter);
  return area;
};

var updatePanelMeter = function(area, fiveHour, weekly) {
  area._values = [fiveHour, weekly].map(window => window ? Number(window.usedPercent) : 0);
  area._available = [Boolean(fiveHour), Boolean(weekly)];
  area.queue_repaint();
};

function _drawPanelMeter(area) {
  const context = area.get_context();
  const [width, height] = area.get_surface_size();
  const foreground = _themeColor(area, '-meter-active-color');
  const muted = _themeColor(area, '-meter-track-color', foreground);
  const rowHeight = Math.max(2, Math.floor(height / 5));
  const gap = Math.max(2, Math.floor(height / 4));
  for (let index = 0; index < 2; index += 1) {
    const y = index * (rowHeight + gap) + rowHeight;
    context.setSourceRGBA(..._rgba(muted, 0.25));
    context.rectangle(0, y, width, rowHeight);
    context.fill();
    if (area._available[index]) {
      context.setSourceRGBA(..._rgba(foreground, 0.95));
      context.rectangle(0, y, width * Math.min(100, area._values[index]) / 100, rowHeight);
      context.fill();
    }
  }
  context.$dispose();
}

var createQuotaGraph = function() {
  const area = new St.DrawingArea({ style_class: 'codex-monitor-graph' });
  area._series = [];
  area._resetMarkers = [];
  area.connect('repaint', _drawQuotaGraph);
  return area;
};

var updateQuotaGraph = function(area, series, resetMarkers) {
  area._series = series || [];
  area._resetMarkers = resetMarkers || [];
  area.queue_repaint();
};

function _drawQuotaGraph(area) {
  const context = area.get_context();
  const [width, height] = area.get_surface_size();
  const padding = 10;
  const plotWidth = Math.max(1, width - padding * 2);
  const plotHeight = Math.max(1, height - padding * 2);
  const foreground = area.get_theme_node().get_foreground_color();
  const colors = [
    _themeColor(area, '-graph-five-hour-color', foreground),
    _themeColor(area, '-graph-weekly-color', foreground),
    _themeColor(area, '-graph-activity-color', foreground),
  ];

  context.setLineWidth(1);
  context.setSourceRGBA(..._rgba(foreground, 0.14));
  for (let index = 0; index <= 4; index += 1) {
    const y = padding + plotHeight * index / 4;
    context.moveTo(padding, y);
    context.lineTo(width - padding, y);
  }
  context.stroke();

  const timestamps = area._series.flatMap(series => series.points.map(point => point.timestamp));
  if (timestamps.length === 0) {
    context.$dispose();
    return;
  }
  const minimum = Math.min(...timestamps);
  const maximum = Math.max(...timestamps, minimum + 1);
  const xFor = timestamp => padding + ((timestamp - minimum) / (maximum - minimum)) * plotWidth;

  context.setDash([4, 4], 0);
  context.setSourceRGBA(..._rgba(foreground, 0.22));
  for (const marker of area._resetMarkers) {
    if (marker < minimum || marker > maximum)
      continue;
    const x = xFor(marker);
    context.moveTo(x, padding);
    context.lineTo(x, height - padding);
  }
  context.stroke();
  context.setDash([], 0);
  context.setLineCap(Cairo.LineCap.ROUND);
  context.setLineJoin(Cairo.LineJoin.ROUND);
  context.setLineWidth(2);

  area._series.forEach((series, seriesIndex) => {
    if (!series.points || series.points.length === 0)
      return;
    const colorIndex = Number.isInteger(series.colorIndex) ? series.colorIndex : seriesIndex;
    context.setSourceRGBA(..._rgba(colors[colorIndex % colors.length], 0.95));
    series.points.forEach((point, pointIndex) => {
      const x = xFor(point.timestamp);
      const value = Math.max(0, Math.min(100, Number(point.value)));
      const y = padding + plotHeight * (1 - value / 100);
      if (pointIndex === 0)
        context.moveTo(x, y);
      else
        context.lineTo(x, y);
    });
    context.stroke();
  });
  context.$dispose();
}
