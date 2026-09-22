"""
device_detector.py
YOLO-based bond pad detection and device center calculation.
Supports crosspoint (1 north + 1 right pad per device) and
crossbar (3 north + 3 right pads per cluster, use middle of each).
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


CONFIDENCE_THRESHOLD = 0.75
BOND_PAD_W_UM = 300.0   # physical pad width  (short side of north pad / long side of right pad)
BOND_PAD_H_UM = 385.0   # physical pad height (long side of north pad / short side of right pad)
BOND_PAD_SIZE_UM = BOND_PAD_W_UM  # kept for back-compat; ppm now uses per-axis estimates


@dataclass
class BondPad:
    cx: float          # pixel center x
    cy: float          # pixel center y
    w: float           # bounding box width in pixels
    h: float           # bounding box height in pixels
    stage_x: float = 0.0   # stage coordinate mm
    stage_y: float = 0.0


@dataclass
class Device:
    center_x_mm: float     # stage coordinate
    center_y_mm: float
    north_pads: List[BondPad] = field(default_factory=list)
    right_pads: List[BondPad] = field(default_factory=list)


def load_model(model_path: str):
    """Load YOLO model. Returns model or None on failure."""
    try:
        from ultralytics import YOLO
        return YOLO(model_path)
    except Exception as e:
        print(f"[detector] Failed to load model: {e}")
        return None


def detect_bond_pads(model, frame) -> List[BondPad]:
    """Run YOLO inference on a frame, return list of BondPad objects."""
    if model is None or frame is None:
        return []
    try:
        results = model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
        pads = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                w  = x2 - x1
                h  = y2 - y1
                pads.append(BondPad(cx=cx, cy=cy, w=w, h=h))
        return pads
    except Exception as e:
        print(f"[detector] Inference error: {e}")
        return []


def pixels_per_mm(pads: List[BondPad]) -> Optional[float]:
    """
    Estimate pixels/mm from detected pad bounding boxes.
    North pads are portrait (w=300µm, h=385µm); right pads are landscape (w=385µm, h=300µm).
    Estimate ppm separately per axis and return the average for a robust single value.
    """
    if not pads:
        return None
    # Per-pad ppm: use whichever dimension is the short axis (300µm) for each pad
    ppm_estimates = []
    for p in pads:
        if p.h >= p.w:
            # portrait (north): w = 300µm physical
            ppm_estimates.append(p.w / (BOND_PAD_W_UM / 1000.0))
            ppm_estimates.append(p.h / (BOND_PAD_H_UM / 1000.0))
        else:
            # landscape (right): h = 300µm physical
            ppm_estimates.append(p.h / (BOND_PAD_W_UM / 1000.0))
            ppm_estimates.append(p.w / (BOND_PAD_H_UM / 1000.0))
    median_ppm = float(np.median(ppm_estimates))
    return median_ppm if median_ppm > 1 else None


def assign_stage_coords(pads: List[BondPad],
                        stage_x: float, stage_y: float,
                        frame_w: int, frame_h: int,
                        px_per_mm: float = None,
                        calib_matrix=None) -> List[BondPad]:
    """
    Convert pixel coordinates to stage coordinates.
    stage_x, stage_y = stage position when this frame was captured (mm).
    Frame center = stage position.

    calib_matrix: optional 2×2 numpy array A such that
        [stage_dx, stage_dy] = A @ [pixel_dx_from_center, pixel_dy_from_center]
    Handles camera rotation relative to stage axes.  Falls back to scalar
    px_per_mm if calib_matrix is None.
    """
    for p in pads:
        dx_px = p.cx - frame_w / 2
        dy_px = p.cy - frame_h / 2
        if calib_matrix is not None:
            v = calib_matrix @ np.array([dx_px, dy_px])
            p.stage_x = stage_x + float(v[0])
            p.stage_y = stage_y + float(v[1])
        else:
            # Scalar fallback: camera-on-stage, both axes positive
            p.stage_x = stage_x + dx_px / px_per_mm
            p.stage_y = stage_y + dy_px / px_per_mm
    return pads


def _cluster_2d(pads: List[BondPad], key1, gap1: float,
                key2, gap2: float) -> List[List[BondPad]]:
    """Two-level clustering: first by key1, then sub-cluster each group by key2."""
    result = []
    for c1 in _cluster_1d(pads, key1, gap1):
        result.extend(_cluster_1d(c1, key2, gap2))
    return result


def _cluster_1d(pads: List[BondPad], key, gap_mm: float) -> List[List[BondPad]]:
    """Generic 1-D clustering by any numeric key (stage_x or stage_y)."""
    if not pads:
        return []
    sorted_pads = sorted(pads, key=key)
    clusters = [[sorted_pads[0]]]
    for p in sorted_pads[1:]:
        if key(p) - key(clusters[-1][-1]) < gap_mm:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


# ── Orientation & geometry constants ──────────────────────────────────────────
# Pad pitch = 600 µm centre-to-centre; threshold must exceed this to cluster
# pads within the same device, while remaining below the between-device gap.
_PAD_PITCH_GAP_MM = 0.7      # 700 µm > 600 µm pitch

# Max Y distance between north-cluster centroid and right-cluster centroid
# for the same device.
# Crosspoint: devices are 1845 µm apart in Y, same-device Y offset ≈ 0 → use 1.2 mm
_DEVICE_Y_BAND_CROSSPOINT_MM = 1.2

# Aspect ratio (h/w or w/h) above which a pad is classified as portrait/landscape.
# North pads: 300 µm × 385 µm → h/w = 1.28.  Right pads: 385 µm × 300 µm → w/h = 1.28.
_ASPECT_T = 1.1

# Crossbar 2D clustering constants
# North pads spread in X by 600 µm pitch; device rows are 3009 µm apart in Y.
# Y sub-gap must be between within-device noise (~0.1 mm) and row spacing (3.009 mm).
_NORTH_Y_SUBGAP_MM = 1.5
# Right pads spread in Y by 600 µm pitch; device columns are separated in X by > 1 mm.
# X sub-gap must be between within-device noise (~0.05 mm) and column spacing.
_RIGHT_X_SUBGAP_MM = 0.5
# 2D pairing tolerances: must be less than device row/column spacing.
_PAIR_X_BAND_MM    = 3.0
_PAIR_Y_BAND_MM    = 2.5


def _split_by_orientation(pads: List[BondPad]):
    """Split pads into north-candidates (portrait h>w) and right-candidates (landscape w>h).
    Ambiguous pads (near-square aspect ratio) are discarded as likely false positives."""
    north, right = [], []
    for p in pads:
        if p.h > p.w * _ASPECT_T:
            north.append(p)
        elif p.w > p.h * _ASPECT_T:
            right.append(p)
        # else: too square — discard (aspect ratio 0.79:1 expected, 1.1 threshold)
    return north, right


def find_devices_crosspoint(pads: List[BondPad],
                             frame_w: int, frame_h: int) -> List[Device]:
    """
    Crosspoint: 1 north pad (portrait) + 1 right pad (landscape) per device.
    Split pads by orientation, cluster each set independently, then pair
    each north cluster with the nearest right cluster at the same Y band.
    Device centre = (north.stage_x, right.stage_y).
    """
    if len(pads) < 2:
        return []

    north_cands, right_cands = _split_by_orientation(pads)
    north_clusters = _cluster_1d(north_cands, lambda p: p.stage_x, _PAD_PITCH_GAP_MM)
    right_clusters = _cluster_1d(right_cands, lambda p: p.stage_y, _PAD_PITCH_GAP_MM)

    devices = []
    used_right = set()
    for nc in north_clusters:
        north = sorted(nc, key=lambda p: p.stage_x)[len(nc) // 2]
        best_j, best_right, best_dist = None, None, float('inf')
        for j, rc in enumerate(right_clusters):
            if j in used_right:
                continue
            r = sorted(rc, key=lambda p: p.stage_y)[len(rc) // 2]
            dy = abs(r.stage_y - north.stage_y)
            if dy < _DEVICE_Y_BAND_CROSSPOINT_MM and dy < best_dist:
                best_dist, best_j, best_right = dy, j, r
        if best_j is not None:
            used_right.add(best_j)
            devices.append(Device(
                center_x_mm=north.stage_x,
                center_y_mm=best_right.stage_y,
                north_pads=[north],
                right_pads=[best_right],
            ))
    return devices


def find_devices_crossbar(pads: List[BondPad],
                           frame_w: int, frame_h: int) -> List[Device]:
    """
    Crossbar: 3 north pads (portrait) + 3 right pads (landscape) per device.
    Uses 2D clustering to handle multi-row, multi-column device grids:
    - North: cluster by stage_x (600µm pitch within device), then by stage_y
      (separates device rows spaced 3009µm apart).
    - Right: cluster by stage_y (600µm pitch within device), then by stage_x
      (separates device columns).
    Pairs north and right clusters by 2D proximity (nearest within both bands).
    Device centre = (north_mid.stage_x, right_mid.stage_y).
    """
    if len(pads) < 6:
        return []

    north_cands, right_cands = _split_by_orientation(pads)

    # 2D clustering: north pads share X within device (600µm pitch), rows split by Y gap
    all_nc = _cluster_2d(north_cands,
                          lambda p: p.stage_x, _PAD_PITCH_GAP_MM,
                          lambda p: p.stage_y, _NORTH_Y_SUBGAP_MM)
    # 2D clustering: right pads share Y within device (600µm pitch), columns split by X gap
    all_rc = _cluster_2d(right_cands,
                          lambda p: p.stage_y, _PAD_PITCH_GAP_MM,
                          lambda p: p.stage_x, _RIGHT_X_SUBGAP_MM)

    # Accept ≥3 pads as primary; also keep ≥2 clusters for fallback recovery
    # (dirty wafer may leave one pad undetected, reducing a 3-pad cluster to 2).
    north_clusters = [c for c in all_nc if len(c) >= 2]
    right_clusters = [c for c in all_rc if len(c) >= 2]
    n3_north = sum(1 for c in north_clusters if len(c) >= 3)
    n3_right = sum(1 for c in right_clusters if len(c) >= 3)
    print(f"[detector] crossbar: {len(north_cands)} north, {len(right_cands)} right pads | "
          f"{len(all_nc)} 2D-north clusters ({n3_north} ≥3, {len(north_clusters)-n3_north} =2), "
          f"{len(all_rc)} 2D-right clusters ({n3_right} ≥3, {len(right_clusters)-n3_right} =2)")

    def _trim3(cluster, key):
        """Return the central 3 pads of a cluster (or all if ≤3)."""
        c = sorted(cluster, key=key)
        if len(c) > 3:
            m = len(c) // 2
            c = c[m-1:m+2]
        return c

    def _centroid(cluster):
        return (float(np.mean([p.stage_x for p in cluster])),
                float(np.mean([p.stage_y for p in cluster])))

    # Pre-compute trimmed clusters and centroids once
    nc_data = []  # (original_cluster, trimmed, cx, cy, size)
    for nc in north_clusters:
        nc3 = _trim3(nc, lambda p: p.stage_x)
        cx, cy = _centroid(nc3)
        nc_data.append({"raw": nc, "t": nc3, "cx": cx, "cy": cy, "sz": len(nc)})

    rc_data = []  # same structure
    for rc in right_clusters:
        rc3 = _trim3(rc, lambda p: p.stage_y)
        cx, cy = _centroid(rc3)
        rc_data.append({"raw": rc, "t": rc3, "cx": cx, "cy": cy, "sz": len(rc)})

    INF = 1e9

    # Build all valid (distance, ni, rj) candidate pairs within the geometry bands.
    # Prefer ≥3+≥3 pairings: give a cost bonus to higher-quality clusters so
    # they are matched first, preventing a ≥2+≥2 pairing from stealing the
    # correct ≥3 partner of a ≥3 cluster.
    candidates = []
    for ni, nd in enumerate(nc_data):
        for rj, rd in enumerate(rc_data):
            dx = abs(rd["cx"] - nd["cx"])
            dy = abs(rd["cy"] - nd["cy"])
            if dx < _PAIR_X_BAND_MM and dy < _PAIR_Y_BAND_MM:
                dist = (dx**2 + dy**2) ** 0.5
                # Quality penalty: prefer ≥3+≥3 pairs (0 penalty) over ≥2 pairs (+1 mm bonus cost)
                quality_penalty = 0.0 if (nd["sz"] >= 3 and rd["sz"] >= 3) else 1.0
                candidates.append((dist + quality_penalty, ni, rj))

    # Sort all candidates by effective cost — greedy assignment on sorted list
    # gives near-optimal matching without needing scipy.
    candidates.sort()
    used_north = set()
    used_right = set()
    assignments = []   # list of (ni, rj)
    for _, ni, rj in candidates:
        if ni in used_north or rj in used_right:
            continue
        used_north.add(ni)
        used_right.add(rj)
        assignments.append((ni, rj))

    # Build Device objects from assignments
    devices = []
    n_33, n_32, n_23 = 0, 0, 0
    for ni, rj in assignments:
        nd = nc_data[ni]
        rd = rc_data[rj]
        north_mid = nd["t"][len(nd["t"]) // 2]
        right_mid = rd["t"][len(rd["t"]) // 2]
        devices.append(Device(
            center_x_mm=north_mid.stage_x,
            center_y_mm=right_mid.stage_y,
            north_pads=nd["t"],
            right_pads=rd["t"],
        ))
        if nd["sz"] >= 3 and rd["sz"] >= 3:
            n_33 += 1
        elif nd["sz"] >= 3:
            n_32 += 1
        else:
            n_23 += 1

    print(f"[detector] crossbar: {len(devices)} devices found "
          f"({n_33} full ≥3+≥3, {n_32} partial ≥3+≥2, {n_23} partial ≥2+≥3)")
    return devices


def find_devices(pads: List[BondPad], wafer_type: str,
                 frame_w: int, frame_h: int) -> List[Device]:
    """Entry point: detect devices from bond pads based on wafer type."""
    if wafer_type.lower() == "crosspoint":
        return find_devices_crosspoint(pads, frame_w, frame_h)
    else:
        return find_devices_crossbar(pads, frame_w, frame_h)