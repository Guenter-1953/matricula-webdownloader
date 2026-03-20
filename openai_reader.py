import os
import base64
from pathlib import Path
from openai import OpenAI


class OpenAIPageReader:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY nicht gesetzt")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def read_page(self, image_path: str) -> dict:
        base64_image = self.encode_image(image_path)

        prompt = """
Du bist ein Experte für historische Kirchenbücher.

Aufgabe:
- Lies die Seite vollständig
- Erkenne alle Einträge (Trauungen)
- Transkribiere sauber (auch Latein → Deutsch)
- Strukturiere die Daten

Gib ausschließlich JSON zurück im Format:

{
  "entries": [
    {
      "type": "marriage",
      "date": "",
      "groom": {
        "name": "",
        "details": ""
      },
      "bride": {
        "name": "",
        "details": ""
      },
      "raw_text": ""
    }
  ],
  "notes": ""
}

Wichtig:
- keine Erklärungen
- nur JSON
"""

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{base64_image}",
                        },
                    ],
                }
            ],
            max_output_tokens=2000,
        )

        text = response.output[0].content[0].text

        return {
            "engine": "openai",
            "model": self.model,
            "raw_response": text
        }
