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

  x._request("remote_pair_start", {}, function (pairError, pairing) {
    if (pairError || !pairing) {
      fail();
      return;
    }
    x._request("remote_pair_status", {
      pairingCode: pairing.pairingCode || null,
      manualPairingCode: pairing.manualPairingCode || null,
    }, function (statusError, pairStatus) {
      if (statusError || !pairStatus) {
        fail();
        return;
      }
      var environmentId = pairing.environmentId ||
        x._remoteStatus && x._remoteStatus.environmentId;
      if (!environmentId) {
        fail();
        return;
      }
      x._request("remote_clients", {
        environmentId: environmentId,
      }, function (clientError, clients) {
        var list = clients && Array.isArray(clients.clients)
          ? clients.clients : [];
        var pairStatusSupported = pairStatus.supported !== false;
        var pairStatusAvailable = pairStatus.available !== false;
        var clientListSupported = Boolean(clients && clients.supported !== false);
        var clientListAvailable = Boolean(clients && clients.available !== false);
        finish({
          done: true,
          error: Boolean(clientError),
          pairStatusSupported: pairStatusSupported,
          pairStatusAvailable: pairStatusAvailable,
          clientListSupported: clientListSupported,
          clientListAvailable: clientListAvailable,
          clientCount: list.length,
          remoteDeviceBridge: Boolean(
            !clientError && pairStatusSupported && pairStatusAvailable &&
            clientListSupported && clientListAvailable
          ),
        });
      });
    });
  });
  return JSON.stringify({ started: true });
})()
