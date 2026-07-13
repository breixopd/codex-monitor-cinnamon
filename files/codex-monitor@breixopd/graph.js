'use strict';

const Cairo = imports.cairo;
const Clutter = imports.gi.Clutter;
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

var createPanelBar = function(styleClass) {
  const area = new St.DrawingArea({
    style_class: `codex-monitor-panel-bar ${styleClass}`,
    x_expand: false,
    y_expand: false,
    y_align: Clutter.ActorAlign.CENTER,
  });
  area._value = 0;
  area._available = false;
  area.connect('repaint', _drawPanelBar);
  return area;
};

var updatePanelBar = function(area, window) {
  area._value = window ? Number(window.usedPercent) : 0;
  area._available = Boolean(window);
  area.queue_repaint();
};

function _drawPanelBar(area) {
  const context = area.get_context();
  const [width, height] = area.get_surface_size();
  const foreground = area.get_theme_node().get_foreground_color();
  const active = _themeColor(area, '-usage-bar-color', foreground);
  const muted = _themeColor(area, '-usage-track-color', foreground);
  const barHeight = Math.max(2, Math.min(4, height));
  const y = Math.max(0, Math.floor((height - barHeight) / 2));
  context.setSourceRGBA(..._rgba(muted, 0.25));
  context.rectangle(0, y, width, barHeight);
  context.fill();
  if (area._available) {
    context.setSourceRGBA(..._rgba(active, 0.95));
    context.rectangle(0, y, width * Math.min(100, Math.max(0, area._value)) / 100, barHeight);
    context.fill();
  }
  context.$dispose();
}

var createQuotaGraph = function(options = {}) {
  const view = new St.BoxLayout({
    vertical: true,
    style_class: 'codex-monitor-graph-view',
  });
  const plotRow = new St.BoxLayout({ style_class: 'codex-monitor-graph-plot-row' });
  view._yAxis = new St.BoxLayout({
    vertical: true,
    style_class: 'codex-monitor-graph-y-axis',
  });
  for (const label of ['100%', '75%', '50%', '25%', '0%']) {
    view._yAxis.add_child(new St.Label({
      text: label,
      style_class: 'codex-monitor-graph-axis-label',
      y_expand: true,
    }));
  }
  view._area = new St.DrawingArea({
    style_class: 'codex-monitor-graph',
    reactive: true,
    track_hover: true,
    x_expand: true,
  });
  view._area._series = [];
  view._area._resetMarkers = [];
  view._area._minimum = 0;
  view._area._maximum = 1;
  view._area._hoverTimestamp = null;
  view._area.connect('repaint', _drawQuotaGraph);
  view._area.connect('motion-event', (_actor, event) => {
    const [stageX, stageY] = event.get_coords();
    const transformed = view._area.transform_stage_point(stageX, stageY);
    if (!transformed[0] || !view._hoverFormatter)
      return Clutter.EVENT_PROPAGATE;
    const [width] = view._area.get_surface_size();
    const ratio = Math.max(0, Math.min(1, transformed[1] / Math.max(1, width)));
    const timestamp = view._area._minimum +
      ratio * (view._area._maximum - view._area._minimum);
    view._area._hoverTimestamp = timestamp;
    view._area.queue_repaint();
    view._hover.set_text(view._hoverFormatter(timestamp));
    return Clutter.EVENT_PROPAGATE;
  });
  view._area.connect('leave-event', () => {
    view._area._hoverTimestamp = null;
    view._area.queue_repaint();
    view._hover.set_text(view._defaultDetail || '');
    return Clutter.EVENT_PROPAGATE;
  });
  plotRow.add_child(view._yAxis);
  plotRow.add_child(view._area);
  view.add_child(plotRow);

  view._xAxis = new St.BoxLayout({ style_class: 'codex-monitor-graph-x-axis' });
  for (let index = 0; index < 3; index += 1) {
    view._xAxis.add_child(new St.Label({
      text: '—',
      style_class: 'codex-monitor-graph-axis-label',
      x_expand: true,
      x_align: index === 0
        ? Clutter.ActorAlign.START
        : index === 2 ? Clutter.ActorAlign.END : Clutter.ActorAlign.CENTER,
    }));
  }
  view.add_child(view._xAxis);
  view._legend = new St.BoxLayout({
    vertical: false,
    style_class: options.legendStyleClass || 'codex-monitor-graph-legend',
  });
  view.add_child(view._legend);
  view._empty = new St.Label({
    text: '',
    style_class: 'codex-monitor-graph-empty',
    x_align: Clutter.ActorAlign.CENTER,
  });
  view.add_child(view._empty);
  view._hover = new St.Label({
    text: '',
    style_class: 'codex-monitor-graph-detail',
  });
  view.add_child(view._hover);
  return view;
};

var updateQuotaGraph = function(view, payload) {
  const data = payload || {};
  const series = data.series || [];
  const axis = data.axis || [];
  view._area._series = series;
  view._area._resetMarkers = data.resetMarkers || [];
  view._area._minimum = axis.length > 0 ? Number(axis[0].timestamp) : 0;
  view._area._maximum = axis.length > 0
    ? Math.max(view._area._minimum + 1, Number(axis[axis.length - 1].timestamp))
    : 1;
  view._hoverFormatter = data.hoverFormatter || null;
  view._defaultDetail = data.defaultDetail || '';
  view._hover.set_text(view._defaultDetail);

  const xLabels = view._xAxis.get_children();
  xLabels.forEach((label, index) => label.set_text(axis[index] ? axis[index].label : '—'));
  for (const child of view._legend.get_children())
    child.destroy();
  for (const item of data.legend || []) {
    const label = new St.Label({
      text: item.text,
      style_class: `codex-monitor-graph-legend-item codex-monitor-graph-color-${item.colorIndex}`,
      x_expand: true,
    });
    view._legend.add_child(label);
  }
  if ((data.resetMarkers || []).length > 0) {
    view._legend.add_child(new St.Label({
      text: 'R = reset',
      style_class: 'codex-monitor-graph-legend-item codex-monitor-graph-reset-key',
    }));
  }

  const counts = series.map(item => item.points.length);
  const total = counts.reduce((sum, count) => sum + count, 0);
  view._empty.set_text(total === 0
    ? 'No history in this range'
    : counts.every(count => count <= 1) ? 'Collecting more history…' : '');
  view._empty.visible = Boolean(view._empty.get_text());
  view._area.queue_repaint();
};

function _drawQuotaGraph(area) {
  const context = area.get_context();
  const [width, height] = area.get_surface_size();
  const padding = 6;
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
  const minimum = Number(area._minimum);
  const maximum = Math.max(Number(area._maximum), minimum + 1);
  const xFor = timestamp => padding + ((timestamp - minimum) / (maximum - minimum)) * plotWidth;

  context.setDash([4, 4], 0);
  context.setSourceRGBA(..._rgba(foreground, 0.22));
  for (const marker of area._resetMarkers) {
    if (marker < minimum || marker > maximum)
      continue;
    const x = xFor(marker);
    context.moveTo(x, padding);
    context.lineTo(x, height - padding);
    context.stroke();
    context.setDash([], 0);
    context.setSourceRGBA(..._rgba(foreground, 0.65));
    context.setFontSize(9);
    context.moveTo(Math.min(width - 10, x + 2), padding + 9);
    context.showText('R');
    context.setDash([4, 4], 0);
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
    if (series.points.length === 1) {
      const point = series.points[0];
      const x = xFor(point.timestamp);
      const y = padding + plotHeight *
        (1 - Math.max(0, Math.min(100, Number(point.value))) / 100);
      context.arc(x, y, 2.5, 0, Math.PI * 2);
      context.fill();
    }
  });
  if (Number.isFinite(area._hoverTimestamp)) {
    const x = xFor(area._hoverTimestamp);
    context.setLineWidth(1);
    context.setSourceRGBA(..._rgba(foreground, 0.5));
    context.moveTo(x, padding);
    context.lineTo(x, height - padding);
    context.stroke();
  }
  context.$dispose();
}
