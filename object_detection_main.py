# -*- coding: utf-8 -*-
"""Object-Detection-Main.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1opYpeO9HiZrUTEqUpDFKsYDYvdQZDASp
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install -q datasets transformers evaluate timm albumentations
!pip install accelerate -U
!pip install datasets

#Do imports required
from datasets import load_dataset
import json
import albumentations
import numpy as np
import torch
from transformers import Trainer

with open('/content/drive/MyDrive/MMAI5500/result.json') as f:
 cocodata = json.load(f)

# Store Huggingface formated data in a list
huggingdata = []
# Iterate through the images
for image in cocodata['images']:
  # Remove the image directory from the file name
  image['file_name'] = image['file_name'].split('/')[-1]
  image['image_id'] = image['id']
  # Extend the image dict with bounding boxes and class labels
  image['objects'] = {'id': [],'area': [],'bbox': [], 'category': []}
  # Iterate through the annotations (bounding boxes and labels)
  for annot in cocodata['annotations']:
  # Check if the annotation matches the image
    if annot['image_id'] == image['id']:
      # Add the annotation
      image['objects']['bbox'].append(annot['bbox'])
      image['objects']['category'].append(annot['category_id'])
      image['objects']['area'].append(annot['area'])
      image['objects']['id'].append(annot['id'])
  # Append the image dict with annotations to the list
  huggingdata.append(image)

#Specify the path here of where to save
with open("/content/drive/MyDrive/MMAI5500/Images/metadata.jsonl", 'w') as f:
 for item in huggingdata:
  f.write(json.dumps(item) + "\n")

from datasets import load_dataset
dataset = load_dataset('imagefolder', data_dir="/content/drive/MyDrive/MMAI5500/Images", split='train')

import numpy as np
import os
from PIL import Image, ImageDraw


id2label = {item['id']: item['name'] for item in cocodata['categories']}
label2id = {v: k for k, v in id2label.items()}

#We need to make a list of cateogries to convert convert to labels
categories = []
for i in cocodata['categories']:
  categories.append(i['name'])

"""
#Visualize the data
image = dataset[4]["image"]
annotations = dataset[4]["objects"]
draw = ImageDraw.Draw(image)



id2label = {index: x for index, x in enumerate(categories, start=0)}
label2id = {v: k for k, v in id2label.items()}

for i in range(len(annotations["id"])):
    box = annotations["bbox"][i - 1]
    class_idx = annotations["category"][i - 1]
    x, y, w, h = tuple(box)
    draw.rectangle((x, y, x + w, y + h), outline="red", width=1)
    draw.text((x, y), id2label[class_idx], fill="white")

"""

#Preprocess the data
from transformers import AutoImageProcessor
checkpoint = "facebook/detr-resnet-50"
image_processor = AutoImageProcessor.from_pretrained(checkpoint)

transform = albumentations.Compose(
    [
        albumentations.Resize(480, 480),
        albumentations.HorizontalFlip(p=1.0),
        albumentations.RandomBrightnessContrast(p=1.0),
    ],
    bbox_params=albumentations.BboxParams(format="coco", label_fields=["category"]),
)

def formatted_anns(image_id, category, area, bbox):
    annotations = []
    for i in range(0, len(category)):
        new_ann = {
            "image_id": image_id,
            "category_id": category[i],
            "isCrowd": 0,
            "area": area[i],
            "bbox": list(bbox[i]),
        }
        annotations.append(new_ann)

    return annotations

def transform_aug_ann(examples):
    image_ids = examples["image_id"]
    images, bboxes, area, categories = [], [], [], []
    for image, objects in zip(examples["image"], examples["objects"]):
        image = np.array(image.convert("RGB"))[:, :, ::-1]
        out = transform(image=image, bboxes=objects["bbox"], category=objects["category"])

        area.append(objects["area"])
        images.append(out["image"])
        bboxes.append(out["bboxes"])
        categories.append(out["category"])

    targets = [
        {"image_id": id_, "annotations": formatted_anns(id_, cat_, ar_, box_)}
        for id_, cat_, ar_, box_ in zip(image_ids, categories, area, bboxes)
    ]

    return image_processor(images=images, annotations=targets, return_tensors="pt")

dataset = dataset.with_transform(transform_aug_ann)

def collate_fn(batch):
    pixel_values = [item["pixel_values"] for item in batch]
    encoding = image_processor.pad_and_create_pixel_mask(pixel_values, return_tensors="pt")
    labels = [item["labels"] for item in batch]
    batch = {}
    batch["pixel_values"] = encoding["pixel_values"]
    batch["pixel_mask"] = encoding["pixel_mask"]
    batch["labels"] = labels
    return batch

#Training the model
from transformers import AutoModelForObjectDetection
model = AutoModelForObjectDetection.from_pretrained(
    checkpoint,
    id2label=id2label,
    label2id=label2id,
    ignore_mismatched_sizes=True,
)

from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="/content",
    per_device_train_batch_size=8,
    num_train_epochs=1000,
    fp16=True,
    save_steps=200,
    logging_steps=25,
    learning_rate=1e-5,
    weight_decay=1e-4,
    save_total_limit=2,
    remove_unused_columns=False,
    push_to_hub=False,
)

trainer = Trainer(
    model=model,
    args=training_args,
    data_collator=collate_fn,
    train_dataset=dataset,
    tokenizer=image_processor,
)

trainer.train()

#Save the model to a path
trainer.save_model('/content/drive/MyDrive/MMAI5500/candy_detector')

#Test the perofrmance on a sample image
url = "/content/drive/MyDrive/MMAI5500/Images/d4cdfc73-cd_24.jpg"
image = Image.open(url)

image_processor = AutoImageProcessor.from_pretrained("candy_detector")
model = AutoModelForObjectDetection.from_pretrained("candy_detector")

with torch.no_grad():
    inputs = image_processor(images=image, return_tensors="pt")
    outputs = model(**inputs)
    target_sizes = torch.tensor([image.size[::-1]])
    results = image_processor.post_process_object_detection(outputs, threshold=0.2, target_sizes=target_sizes)[0]

for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
    box = [round(i, 2) for i in box.tolist()]
    print(
        f"Detected {model.config.id2label[label.item()]} with confidence "
        f"{round(score.item(), 3)} at location {box}"
    )

#Print the image out with the labels from our model
draw = ImageDraw.Draw(image)

for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
    box = [round(i, 2) for i in box.tolist()]
    x, y, x2, y2 = tuple(box)
    draw.rectangle((x, y, x2, y2), outline="red", width=1)
    draw.text((x, y), model.config.id2label[label.item()], fill="white")

image

#Create a function to return the dictionary as specified in the assingment
def candy_counter(image_path, model_path):
  image = Image.open(image_path)
  final_dic = {'Moon': 0,'Insect': 0,'Black_star': 0,'Grey_star': 0,'Unicorn_whole': 0,'Unicorn_head': 0,'Owl': 0,'Cat': 0}
  image_processor = AutoImageProcessor.from_pretrained("candy_detector")
  model = AutoModelForObjectDetection.from_pretrained("candy_detector")

  with torch.no_grad():
      inputs = image_processor(images=image, return_tensors="pt")
      outputs = model(**inputs)
      target_sizes = torch.tensor([image.size[::-1]])
      results = image_processor.post_process_object_detection(outputs, threshold=0.2, target_sizes=target_sizes)[0]

  for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
      box = [round(i, 2) for i in box.tolist()]
      label_name = model.config.id2label[label.item()]
      if label_name not in final_dic:
        final_dic[label_name] = 1
      else:
        final_dic[label_name] = final_dic[label_name] + 1





  print(final_dic)
  return final_dic

#Here is an example of running the function with a test image and the model that we have saved
candy_counter(image_path='/content/drive/MyDrive/MMAI5500/Images/d4cdfc73-cd_24.jpg', model_path='/content/drive/MyDrive/MMAI5500/candy_detector')