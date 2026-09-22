from ultralytics import YOLO
import cv2
import os

# Load model
model = YOLO(r"C:\Users\cy\Desktop\Monash_Engineering\FYP\firmware\src\yolo_model\runs\detect\train\weights\best.pt")

# Image folder
# image_folder = r"C:\Users\cy\Desktop\Monash_Engineering\FYP\MicromanipulatorWork\old-versions-work\wafer images\new test images" 
image_folder = r"C:\Users\cy\Desktop\Monash_Engineering\FYP\firmware\src\scan_debug\20260516_233945"

# Create a resizable window
cv2.namedWindow("Result", cv2.WINDOW_NORMAL)

for img_name in os.listdir(image_folder):
    img_path = os.path.join(image_folder, img_name)

    # Run inference
    results = model(img_path)

    # Get annotated image
    annotated = results[0].plot()

    # 🔑 Resize window to match image EXACTLY
    h, w = annotated.shape[:2]
    screen_width = 1280
    screen_height = 800

    scale = min(screen_width / w, screen_height / h)
    resized = cv2.resize(annotated, (int(w * scale), int(h * scale)))

    cv2.imshow("Result", resized)
    print(f"Showing: {img_name}")

    if cv2.waitKey(0) == 27:
        break

cv2.destroyAllWindows()