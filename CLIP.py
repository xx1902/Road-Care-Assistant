# from transformers import pipeline
from PIL import Image
from transformers import AutoProcessor, AutoModel
import torch

SigLIP = "./siglip2-so400m-patch14-384" 
device = "cuda:0" if torch.cuda.is_available() else "cpu"
# SigLIP = "./siglip2-base-patch16-224" 

def image_text_similarity(image, text):

    model = AutoModel.from_pretrained(SigLIP, device_map=device)
    processor = AutoProcessor.from_pretrained(SigLIP, device_map=device)

    inputs = processor(text=text, images=image, padding="max_length", max_length=64, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.sigmoid(outputs.logits_per_image)

    return probs.cpu().item()


def image_image_similarity(image1, image2):

    model = AutoModel.from_pretrained(SigLIP, device_map=device)
    processor = AutoProcessor.from_pretrained(SigLIP, device_map=device)

    inputs = processor(images=[image1, image2], return_tensors="pt").to(device)

    with torch.no_grad():
        image_embeddings = model.get_image_features(**inputs)
    
    return torch.cosine_similarity(image_embeddings[0].unsqueeze(0), image_embeddings[1].unsqueeze(0)).cpu().item()


if __name__ == "__main__":
    # image = Image.open("./demo/coco.jpg")
    # texts = ["a cat", "two cats", "three cats"]

    print(image_text_similarity(Image.open("./demo/1.jpg"), ["car accident"]))

    print(image_image_similarity(Image.open("./demo/1.jpg"), Image.open("./demo/1.jpg")))
