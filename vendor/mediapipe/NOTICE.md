# MediaPipe person segmentation (vendored)

Used by the streamer's webcam preview to cut the person out of the camera picture.
These files are third-party and unmodified; they run only in the streamer's browser tab.

| File | Source | SHA-256 |
|---|---|---|
| `vision_bundle.mjs` | npm `@mediapipe/tasks-vision` 1.2.0 (Apache-2.0, Google) | `870da5cfc43bfcf2a8b0f14e8152dae8c7e701722e1191b0e592b94b81b4127a` |
| `wasm/vision_wasm_internal.js` | same package | `85c1a342be70427987f900969a5f26e17557351111364e6585e97fb03e93e108` |
| `wasm/vision_wasm_internal.wasm` | same package | `bcc13df22d3d69ec8cbe8e280989356d844ae00f4523eb82072d2484f44134dc` |
| `selfie_segmenter.tflite` | https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite (Google, Apache-2.0) | `191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b` |

Verify with `shasum -a 256 vendor/mediapipe/vision_bundle.mjs vendor/mediapipe/wasm/* vendor/mediapipe/selfie_segmenter.tflite`.
Only the SIMD WebAssembly build is included (every current Chrome and Edge supports it).
