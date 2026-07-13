'use strict';

const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Mainloop = imports.mainloop;

var BridgeClient = class BridgeClient {
  constructor(options) {
    this._options = options;
    this._pending = new Map();
    this._sequence = 0;
    this._process = null;
    this._running = false;
    this._reader = null;
    this._writer = null;
  }

  start() {
    this.stop();
    const flags = Gio.SubprocessFlags.STDIN_PIPE |
      Gio.SubprocessFlags.STDOUT_PIPE |
      Gio.SubprocessFlags.STDERR_SILENCE;
    const launcher = Gio.SubprocessLauncher.new(flags);
    if (this._options.codexHome)
      launcher.setenv('CODEX_HOME', this._options.codexHome, true);
    const argv = [
      'python3',
      GLib.build_filenamev([this._options.appletPath, 'helper', 'bridge.py']),
      '--codex', this._options.codexBinary || 'codex',
      '--history-days', String(this._options.historyDays || 30),
    ];
    if (this._options.codexHome)
      argv.push('--codex-home', this._options.codexHome);

    this._process = launcher.spawnv(argv);
    this._running = true;
    this._reader = new Gio.DataInputStream({
      base_stream: this._process.get_stdout_pipe(),
    });
    this._writer = new Gio.DataOutputStream({
      base_stream: this._process.get_stdin_pipe(),
    });
    this._readNextLine();
  }

  request(action, params, callback) {
    if (!this._process || !this._running) {
      callback(new Error('Codex bridge is not running'));
      return;
    }
    this._sequence += 1;
    const id = `cinnamon-${Date.now()}-${this._sequence}`;
    const timeoutId = Mainloop.timeout_add_seconds(30, () => {
      const pending = this._pending.get(id);
      if (pending) {
        this._pending.delete(id);
        pending.callback(new Error('Codex bridge timed out'));
      }
      return GLib.SOURCE_REMOVE;
    });
    this._pending.set(id, { callback, timeoutId });

    try {
      this._writer.put_string(JSON.stringify({ id, action, params: params || {} }) + '\n', null);
    } catch (error) {
      Mainloop.source_remove(timeoutId);
      this._pending.delete(id);
      callback(new Error('Unable to write to Codex bridge'));
    }
  }

  stop() {
    for (const pending of this._pending.values()) {
      Mainloop.source_remove(pending.timeoutId);
      pending.callback(new Error('Codex bridge stopped'));
    }
    this._pending.clear();
    if (this._writer) {
      try {
        this._writer.close(null);
      } catch (error) {
        // The helper may already have closed its pipe.
      }
    }
    if (this._process && this._running) {
      try {
        this._process.force_exit();
      } catch (error) {
        // The helper may already have exited.
      }
    }
    this._running = false;
    this._process = null;
    this._reader = null;
    this._writer = null;
  }

  _readNextLine() {
    if (!this._reader)
      return;
    this._reader.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, result) => {
      let line = null;
      try {
        [line] = stream.read_line_finish_utf8(result);
      } catch (error) {
        this._failPending('Codex bridge read failed');
        return;
      }
      if (line === null) {
        this._running = false;
        this._failPending('Codex bridge exited');
        return;
      }
      this._handleLine(line);
      this._readNextLine();
    });
  }

  _handleLine(line) {
    let response;
    try {
      response = JSON.parse(line);
    } catch (error) {
      return;
    }
    const pending = this._pending.get(response.id);
    if (!pending)
      return;
    Mainloop.source_remove(pending.timeoutId);
    this._pending.delete(response.id);
    if (response.ok)
      pending.callback(null, response.data);
    else
      pending.callback(new Error(response.error && response.error.message || 'Codex request failed'));
  }

  _failPending(message) {
    this._running = false;
    for (const pending of this._pending.values()) {
      Mainloop.source_remove(pending.timeoutId);
      pending.callback(new Error(message));
    }
    this._pending.clear();
  }
};
