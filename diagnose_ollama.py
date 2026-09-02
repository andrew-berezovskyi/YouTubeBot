from pathlib import Path
import sys

from ollama import Client

from config import (
    OLLAMA_HOST,
    VISION_MODEL,
    FRAMES,
)


def main():
    client = Client(
        host=OLLAMA_HOST
    )

    print("MODEL:")
    info = client.show(VISION_MODEL)
    print(VISION_MODEL)
    print("model check: OK")
    print("")

    images = sorted(
        FRAMES.glob("*.jpg")
    )

    if not images:
        print(
            "У Frames немає JPG. "
            "Спочатку запусти python main.py "
            "або поклади JPG у Frames."
        )
        return

    image = images[0]

    print("IMAGE:")
    print(image)
    print("")

    response = client.chat(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Describe this image in one short "
                    "English sentence."
                ),
                "images": [str(image)],
            }
        ],
        stream=False,
    )

    print("RESPONSE:")
    print(response.message.content)
    print("")
    print("done:", response.done)
    print(
        "done_reason:",
        response.done_reason
    )


if __name__ == "__main__":
    main()
