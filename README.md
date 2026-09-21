<img width="426" height="240" alt="device_positioning" src="https://github.com/user-attachments/assets/564f1dfa-1d53-46ce-aa9d-41e2844bdc76" />



# Vision-Guided Automated Probe Alignment System for Wafer-Level Testing

A low-cost (~$200 USD), fully integrated system that automates micron-scale alignment between tungsten microprobes and semiconductor bond pads for wafer-level electrical testing — built as a Final Year Project in Robotics & Mechatronics Engineering at Monash University Malaysia, and awarded **Best FYP Report** by the department.

Commercial probe stations solve this alignment problem with proprietary vision systems and high-resolution servo stages costing $50,000–$500,000, putting them out of reach for teaching labs and small/medium enterprises. This project builds a functional equivalent from off-the-shelf components and 3D-printed parts, combining a custom motorised XY stage, a YOLOv11-based vision pipeline, magnetic encoder feedback, and an automated microprobe mechanism into a single reproducible, open-source workflow.

<div style="display: flex; gap: 2%;">
  <img src="images/overview.gif" alt="System overview" width="49%">
  <img src="images/wafer_minimap.gif" alt="Wafer minimap and device registry" width="49%">
</div>

<!-- TODO: replace the two images above with a system overview shot/gif and a clip of the wafer minimap filling in with detected devices -->

## What it does

1. Drives a custom motorised XY stage using 3D-printed anti-backlash gear couplings and NEMA17 steppers
2. Automatically scans the wafer, using YOLOv11 to detect all bond pads in real time — reliably, even on damaged or oxidised pads where classical template matching fails outright
3. Computes device (crossbar) centre coordinates from detected pads and stores them in a persistent registry with a live wafer minimap
4. Recentres the stage on any selected device using a three-stage correction chain — encoder drift correction, magnetic encoder step correction, and two-pass image-guided fine centering — pushing positioning error from ~300 µm down to **below 43 µm**
5. Drives a two-axis microprobe mechanism to make electrical contact with the aligned device

## Demo Videos

Three short videos, one for each major milestone of the system:

<div style="display: flex; gap: 2%;">
  <a href="https://youtu.be/YOUR_VIDEO_ID_1"><img src="images/video-thumbnails/01_yolo_detection.jpg" alt="Bond pad detection with YOLOv11" width="32%"></a>
  <a href="https://youtu.be/YOUR_VIDEO_ID_2"><img src="images/video-thumbnails/02_fine_centering.jpg" alt="Encoder + image-guided fine centering" width="32%"></a>
  <a href="https://youtu.be/YOUR_VIDEO_ID_3"><img src="images/video-thumbnails/03_probing.jpg" alt="Microprobe alignment and contact" width="32%"></a>
</div>

<!-- TODO: swap in real thumbnails + YouTube links:
1. YOLOv11 bond pad detection running live across a wafer scan
2. Three-stage fine centering bringing a device under the crosshair
3. Microprobe lateral positioning and Z-axis electrical contact -->

## Results at a glance

| Metric | Result |
|---|---|
| Bond pad detection | All 144/144 pads and all 24/24 device centres recovered, in all 30 repeated full-wafer scans |
| YOLOv11 model | mAP@0.5 = 0.872, mAP@0.5:0.95 = 0.820, precision = 0.995, recall = 0.860 (100 epochs, 150 labelled images) |
| Final positioning accuracy | <43 µm typical residual (≤87 µm worst case) — well within the 150 µm pad half-width |
| Probe contact | 100% lateral on-pad success (150/150 pads × 2 probes) and 100% electrical contact success across 50 devices |
| Full wafer scan time | <7 minutes per full-wafer scan |
| Total hardware cost | ~$200 USD vs. $50,000–$500,000 for commercial probe stations |

## System architecture

Four subsystems, coordinated over USB serial:

- **Motorised XY wafer stage** — driven by NEMA17 steppers through custom 3D-printed spring-loaded split-gear anti-backlash couplings. 25 mm travel per axis, 0.156 µm/step theoretical resolution at 16× microstepping.
- **Firmware (Raspberry Pi Pico 2W / RP2350A)** — PIO-based, dual-core motion control (Core 0: USB serial + X-axis, Core 1: Y-axis) for jitter-free, simultaneous XY motion via TMC2209 stepper drivers. Trapezoidal S-curve motion profiles, safe homing logic, and MT6835 21-bit magnetic encoder integration for closed-loop correction.
- **Vision & scan pipeline (host, PySide6 desktop app)** — a YOLOv11 model (replacing an earlier OpenCV template-matching approach that failed on damaged/oxidised pads) detects bond pads per frame; a phase-correlation calibration procedure maps pixel space to stage space; an automated unidirectional scan builds a full device registry.
- **Microprobe mechanism** — two independently-actuated probe carriages (one per crossbar bus line), each with a lateral axis and a Z-axis for pad contact, mounted symmetrically on the stage base.

<div style="display: flex; gap: 2%;">
  <img src="images/xy_stage_cad.jpg" alt="XY stage CAD model" width="49%">
  <img src="images/xy_stage_build.jpg" alt="Assembled XY stage" width="49%">
</div>

<!-- TODO: CAD render + assembled photo of the stage, side by side -->

## Key engineering problems and how they were solved

**Backlash was the core obstacle.** A 15-cycle backlash test revealed a sharp asymmetry: the Y axis had a small, highly repeatable systematic offset (σ = 4.8 µm), but the X axis — which has to carry both its own stage layer and the entire Y layer above it — showed erratic scatter of σ = 92.4 µm, with individual errors up to ±150 µm. This made step-count-only positioning unusable on X.

**Three-stage correction chain** was built to close that gap:
1. *Scan-registered* — per-frame MT6835 encoder drift correction anchors pad coordinates during the scan itself (raw error ≤300 µm)
2. *Encoder correction* — comparing the sub-revolution encoder angle against the expected step count and issuing a correction move (reduces error to 50–150 µm)
3. *Image-guided fine centering* — two passes of YOLO-guided centroid correction on live camera frames (brings residual below 43 µm)

<img src="images/backlash_chart.png" alt="Backlash error chart / correction stage chart" width="70%">

<!-- TODO: the per-cycle backlash chart or the stage-wise residual reduction chart -->

**Detection robustness.** Bond pads on the test wafer ranged from clean to heavily damaged/oxidised. Classical template matching failed outright on damaged pads; YOLOv11, trained across the full condition range, detected all pad conditions reliably and was the reason full pipeline recovery reached 100% across 30 repeated scans.

<div style="display: flex; gap: 2%;">
  <img src="images/pad_conditions.jpg" alt="Bond pad conditions: clean to damaged" width="49%">
  <img src="images/yolo_detection_result.jpg" alt="YOLOv11 detection result" width="49%">
</div>

<!-- TODO: pad condition range photo + a YOLO detection frame with bounding boxes -->

## Hardware

- NEMA17 stepper motors (17HS4401) with TMC2209 drivers (StealthChop2, MicroPlyer interpolation)
- Raspberry Pi Pico 2W (RP2350A) — PIO + dual-core motion control
- MT6835 21-bit absolute magnetic rotary encoders (both axes)
- Microscopic board camera with high-magnification zoom lens
- All structural/custom parts (motor mounts, gear housings, limit switch brackets, encoder mounts, base platform) designed in CAD and 3D-printed in PLA

<img src="images/microprobe_assembly.jpg" alt="Microprobe sub-assembly" width="60%">

<!-- TODO: microprobe carriage photo -->

## Author

**Ghui Chen Yang** — Robotics & Mechatronics Engineering, Monash University Malaysia
Supervised by Dr. Patrick Ho, Department of Electrical and Computer Systems Engineering

Project was Awarded Best FYP Report for Department of Robotics & Mechatronics Engineering


