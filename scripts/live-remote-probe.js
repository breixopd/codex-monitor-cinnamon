(function () {
  var UUID = "codex-monitor@breixopd";
  var x = imports.ui.appletManager.getRunningInstancesForUuid(UUID)[0];
  global._codexMonitorDeviceProbe = { done: false };

  function finish(value) {
    global._codexMonitorDeviceProbe = value;
  }

  function fail() {
    finish({ done: true, error: true });
  }

  if (!x) {
    fail();
    return JSON.stringify({ started: false });
  }

  x._request("remote_status", {}, function (statusError, status) {
    if (statusError || !status || status.status !== "connected" ||
        !status.environmentId) {
      fail();
      return;
    }
    x._request("remote_clients", {
      environmentId: status.environmentId,
    }, function (clientError, clients) {
      var list = clients && Array.isArray(clients.clients)
        ? clients.clients : [];
      var clientListSupported = Boolean(clients && clients.supported !== false);
      var clientListAvailable = Boolean(clients && clients.available !== false);
      finish({
        done: true,
        error: Boolean(clientError),
        clientListSupported: clientListSupported,
        clientListAvailable: clientListAvailable,
        clientCount: list.length,
        remoteDeviceBridge: Boolean(
          !clientError && clientListSupported && clientListAvailable
        ),
      });
    });
  });
  return JSON.stringify({ started: true });
})()
