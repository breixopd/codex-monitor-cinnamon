'use strict';

const Clutter = imports.gi.Clutter;
const St = imports.gi.St;

var createQrCode = function() {
  const area = new St.DrawingArea({
    style_class: 'codex-monitor-qr',
    x_align: Clutter.ActorAlign.CENTER,
    x_expand: false,
  });
  area._matrix = [];
  area.connect('repaint', _drawQrCode);
  return area;
};

var updateQrCode = function(area, matrix) {
  const valid = Array.isArray(matrix) && matrix.length > 0 && matrix.length <= 177 &&
    matrix.every(row => typeof row === 'string' && row.length === matrix.length &&
      /^[01]+$/.test(row));
  area._matrix = valid ? matrix.slice() : [];
  area.visible = valid;
  area.queue_repaint();
  return valid;
};

function _drawQrCode(area) {
  const context = area.get_context();
  const [width, height] = area.get_surface_size();
  context.setSourceRGB(1, 1, 1);
  context.rectangle(0, 0, width, height);
  context.fill();
  const matrix = area._matrix || [];
  if (matrix.length === 0) {
    context.$dispose();
    return;
  }
  const quietZone = 4;
  const modules = matrix.length + quietZone * 2;
  const scale = Math.max(1, Math.floor(Math.min(width, height) / modules));
  const drawnSize = modules * scale;
  const offsetX = Math.floor((width - drawnSize) / 2) + quietZone * scale;
  const offsetY = Math.floor((height - drawnSize) / 2) + quietZone * scale;
  context.setSourceRGB(0, 0, 0);
  for (let y = 0; y < matrix.length; y += 1) {
    for (let x = 0; x < matrix.length; x += 1) {
      if (matrix[y][x] === '1')
        context.rectangle(offsetX + x * scale, offsetY + y * scale, scale, scale);
    }
  }
  context.fill();
  context.$dispose();
}
