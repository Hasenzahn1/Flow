const assert = require('node:assert/strict');

let alpineInit;
let componentFactory;
global.window = { socket: null, isSecureContext: true };
global.document = {
  addEventListener(name, callback) { if (name === 'alpine:init') alpineInit = callback; },
  removeEventListener() {},
  body: { style: {} },
  hidden: false
};
Object.defineProperty(global, 'navigator', {
  configurable: true,
  value: { mediaDevices: { getUserMedia() {} } }
});
global.Alpine = { data(name, factory) { if (name === 'helpersPage') componentFactory = factory; } };

let openAttempts = 0;
let releases = 0;
let stoppedTracks = 0;
const makeStream = () => ({
  getTracks: () => [{ stop() { stoppedTracks += 1; } }]
});

class FakeReader {
  async decodeFromVideoDevice(deviceId, video) {
    openAttempts += 1;
    if (openAttempts === 1) {
      const error = new Error('Could not start video source');
      error.name = 'NotReadableError';
      throw error;
    }
    video.srcObject = makeStream();
    return { async stop() { video.srcObject?.getTracks().forEach(track => track.stop()); } };
  }
}

window.ZXingBrowser = global.ZXingBrowser = {
  BrowserQRCodeReader: FakeReader,
  BrowserCodeReader: {
    releaseAllStreams() { releases += 1; },
    cleanVideoSource(video) { video.srcObject = null; video.removeAttribute('src'); },
    async listVideoInputDevices() { return [{ deviceId: 'rear', label: 'Back camera' }]; }
  }
};

require('../static/js/helpers.js');
alpineInit();

const video = {
  srcObject: null,
  pause() {},
  load() {},
  removeAttribute() {},
  clientWidth: 640,
  clientHeight: 360,
  videoWidth: 640,
  videoHeight: 360
};
const component = componentFactory(1);
component.$refs = { cameraVideo: video };
component.$nextTick = async () => {};

(async () => {
  await component.startCamera();
  assert.equal(openAttempts, 2, 'NotReadableError triggers one clean retry');
  assert.equal(component.cameraRunning, true);
  assert.equal(component.modalError, '');

  await component.stopCamera();
  assert.equal(component.cameraRunning, false);
  assert.equal(video.srcObject, null);
  assert.ok(releases >= 2, 'ZXing tracked streams are released');
  assert.ok(stoppedTracks >= 1, 'media tracks are stopped');

  await component.startCamera();
  assert.equal(component.cameraRunning, true, 'camera can start again without a page reload');
  await component.stopCamera();
  console.log('camera lifecycle test: ok');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
