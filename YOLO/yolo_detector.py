import cv2
import numpy as np
from ultralytics import YOLO

class YOLODetector:
    def __init__(self, model_path="yolov8n.pt"):
        # 加载YOLO模型
        self.model = YOLO(model_path)

    def detect(self, image_path):
        # 加载输入图像
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError("无法加载图像")

        # 预处理图像
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (640, 640))
        image = image.astype(np.float32)
        image /= 255.0

        # 将图像转换为张量
        image = np.expand_dims(image, axis=0)

        # 进行目标检测
        results = self.model.predict(image, verbose=False)

        # 解析预测结果
        detections = []
        for result in results:
            boxes = result.boxes.xyxy.cpu().numpy()
            scores = result.boxes.conf.cpu().numpy()
            classes = result.boxes.cls.cpu().numpy().astype(int)

            for box, score, cls in zip(boxes, scores, classes):
                if score > 0.5:  # 过滤低置信度的预测
                    detections.append({
                        "class": self.model.names[cls],
                        "confidence": float(score),
                        "bbox_2d": [int(x) for x in box]
                    })

        return detections