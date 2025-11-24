import streamlit as st
import torch
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image
import requests
import numpy as np
from ultralytics import YOLO   # FIX: Official YOLO import

# -------------------------------------------------------
# Page Title
# -------------------------------------------------------
st.title("🧠 Computer Vision POC")
st.write("Upload an image and choose between **Image Classification** or **Object Detection**.")

# -------------------------------------------------------
# Load ResNet18 (Classification)
# -------------------------------------------------------
@st.cache_resource
def load_classification_model():
    model = models.resnet18(pretrained=True)
    model.eval()
    return model

clf_model = load_classification_model()

# -------------------------------------------------------
# Load YOLOv5 (Object Detection)
# -------------------------------------------------------
@st.cache_resource
def load_yolo_model():
    return YOLO("yolov5s.pt")     # FIX: Loads YOLOv5 model

yolo = load_yolo_model()

# -------------------------------------------------------
# Load ImageNet Labels
# -------------------------------------------------------
@st.cache_resource
def load_labels():
    url = "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
    return requests.get(url).text.split("\n")

labels = load_labels()

# -------------------------------------------------------
# Image Transform
# -------------------------------------------------------
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

# -------------------------------------------------------
# Select Mode
# -------------------------------------------------------
mode = st.radio(
    "Select Mode:",
    ["Image Classification", "Object Detection"],
    horizontal=True
)

# -------------------------------------------------------
# File Upload
# -------------------------------------------------------
uploaded_file = st.file_uploader("📤 Upload an image", type=["jpg", "jpeg", "png"])

if uploaded_file:

    # Convert RGBA → RGB
    img = Image.open(uploaded_file).convert("RGB")

    # Show uploaded image
    st.image(img, caption="Uploaded Image", use_container_width=True)

    img_array = np.array(img)

    # =====================================================
    # MODE 1: IMAGE CLASSIFICATION
    # =====================================================
    if mode == "Image Classification":

        img_t = transform(img).unsqueeze(0)

        with torch.no_grad():
            outputs = clf_model(img_t)

        _, predicted = torch.max(outputs, 1)
        predicted_label = labels[predicted]

        st.success(f"🎯 **Prediction:** {predicted_label}")

    # =====================================================
    # MODE 2: OBJECT DETECTION
    # =====================================================
    else:
        st.info("🔎 Running YOLOv5 object detection...")

        results = yolo(img_array)

        # Render image with bounding boxes
        detected_img = results[0].plot()

        st.image(detected_img, caption="Detected Objects", use_container_width=True)

        st.subheader("📌 Detected Objects:")
        for box in results[0].boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            label = results[0].names[cls]
            st.write(f"• **{label}** — {conf:.2f} confidence")
