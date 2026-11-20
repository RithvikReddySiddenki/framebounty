const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, "../app/camera.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {}, Error, Math };
vm.runInNewContext(compiled, sandbox);
const { cameraErrorMessage, recordingExtension, recordingMimeType, secondsLabel } = sandbox.exports;

test("camera recording chooses MP4 first and falls back to browser WebM", () => {
  assert.equal(recordingMimeType(type => type === "video/mp4"), "video/mp4");
  assert.equal(recordingMimeType(type => type === "video/webm;codecs=vp8"), "video/webm;codecs=vp8");
  assert.equal(recordingMimeType(() => false), undefined);
  assert.equal(recordingExtension("video/mp4;codecs=avc1"), "mp4");
  assert.equal(recordingExtension("video/webm;codecs=vp9"), "webm");
});

test("camera failures provide specific permission and device recovery", () => {
  for (const [name, message] of [
    ["NotAllowedError", /Allow camera access/],
    ["NotFoundError", /No usable camera/],
    ["NotReadableError", /camera is busy/],
    ["SecurityError", /HTTPS/],
  ]) {
    const error = new Error(name); error.name = name;
    assert.match(cameraErrorMessage(error), message);
  }
  assert.equal(secondsLabel(10_001), "11s");
});
