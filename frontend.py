import gradio as gr
from transformers import pipeline
import numpy as np
from PIL import ImageDraw, Image
import json
import os

DATASET_PATH = "./dataset/"

transcriber = pipeline("automatic-speech-recognition", model="./whisper-base", device=0)


anno_example = {
    "messages": [
        {
            "content": "",
            "role": "user"
        },
        {
            "content": "",
            "role": "assistant"
        }
    ],
    "images": [],
    "bbox": []
}

user_input_examples=[
    "请用一段话介绍一下这个图片。",
    "bb"
]

user_input = gr.Textbox(label="User Input", interactive=True, value=user_input_examples[0])
anno_example["messages"][0]["content"] = "<image>{}".format(user_input_examples[0])

with gr.Blocks(theme=gr.themes.Soft()) as demo:

    gr.Markdown("<center><strong><font size='7'>Data Pipeline<font></strong></center>")

    anno = gr.State(anno_example)

    with gr.Row():
        gr.Examples(user_input_examples, user_input)

    with gr.Row():
        user_input.render()

        @user_input.change(inputs=[user_input, anno], outputs=anno)
        def update_user_input(user_input, anno):
            anno["messages"][0]["content"] = "<image>{}".format(user_input)
            return anno

    with gr.Row(equal_height=True):
        with gr.Column():

            points = gr.State([])
            colors = gr.State([])
            origin_image = gr.State(Image.open("example.jpg"))

            image = gr.Image(label="To Be Annotated", value="example.jpg", type="pil")
            
            @image.select(inputs=[image, points, colors], outputs=[image, points, colors])
            def get_point(image, points, colors, evt: gr.SelectData):

                x1, y1 = evt.index[0], evt.index[1]

                points.append([x1, y1])
                # append random color
                if len(points) % 2 == 1:
                    colors.append(tuple(np.random.randint(0, 255, size=(3,))))
                
                draw = ImageDraw.Draw(image)
                point_radius = 5
                point_color = colors[(len(points)-1)//2]

                draw.ellipse([(x1 - point_radius, y1 - point_radius), (x1 + point_radius, y1 + point_radius)], fill=point_color)

                if len(points) % 2 == 0:

                    x2, y2 = points[-2]
                    xmin, xmax, ymin, ymax = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)

                    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
                    draw_overlay = ImageDraw.Draw(overlay)

                    draw_overlay.rectangle([xmin, ymin, xmax, ymax], fill=point_color + (85,), outline=point_color+(255,), width=2)
                    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

                return image, points, colors

            @points.change(inputs=[points, anno], outputs=anno)
            def update_box(points, anno):
                if len(points) == 0:
                    anno["bbox"] = []

                elif len(points) % 2 == 0:
                    x1, y1 = points[-2]
                    x2, y2 = points[-1]
                    xmin, xmax, ymin, ymax = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
                    anno["bbox"].append([xmin, ymin, xmax, ymax])

                return anno


            image.input(lambda x: x, inputs=image, outputs=origin_image)

            
        
        with gr.Column():

            ATT_audio = gr.Audio(label="Audio Input", sources="microphone")

            @ATT_audio.stop_recording(inputs=[ATT_audio, anno], outputs=anno)
            def transcribe(audio, anno):

                sr, y = audio
                # Convert to mono if stereo
                if y.ndim > 1:
                    y = y.mean(axis=1)
                y = y.astype(np.float32)
                y /= np.max(np.abs(y))
                text = transcriber({"sampling_rate": sr, "raw": y})["text"]

                print("Audio Transcription: ", text)
                anno["messages"][1]["content"] = text

                return anno
            
            # visualize anno json
            annotation = gr.JSON(label="Annotation", value=json.dumps(anno_example, indent=4), height=500)
            @anno.change(inputs=anno, outputs=annotation)
            def update_annotation(anno):
                str = json.dumps(anno, indent=4)
                return gr.JSON(label="Annotation", value=str)


    with gr.Row():
        with gr.Column(scale=1):
            clear_btn = gr.Button("Clear Boxes")
            clear_btn.click(lambda ori: (ori, [], []), inputs=origin_image, outputs=[image, points, colors])

        with gr.Column(scale=1):
            spider_btn = gr.Button("Spider")

        with gr.Column(scale=2):
            save_btn = gr.Button("Save")

            @save_btn.click(inputs=[origin_image, anno])
            def save(origin_image, anno):
                id = len(os.listdir(DATASET_PATH + "images/"))

                image_path = f"{DATASET_PATH}images/{str(id)}.png"

                print(f"Saving to {image_path}")

                origin_image.save(DATASET_PATH + f"images/{str(id)}.png")

                with open(DATASET_PATH + "anno.json", "r") as f:
                    data = json.load(f)

                data.append(anno)

                with open(DATASET_PATH + "anno.json", "w") as f:
                    json.dump(data, f, indent=4)




demo.launch()