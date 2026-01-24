import base64
import io
import logging
import os
from typing import Optional, Union

import httpx
from PIL import Image

# Configuration for external AI restoration service (e.g., CodeFormer, GFPGAN)
# Default points to a local service that would be running the heavy AI models
FACE_RESTORATION_URL = os.getenv(
    "SOCIAL_HUNT_FACE_AI_URL", "http://localhost:5000/restore"
)


async def restore_face(
    image_input: Union[str, bytes], strength: float = 0.5
) -> Optional[bytes]:
    """
    Sends an image to an external AI service for face restoration/demasking.
    This is intended to work with models like CodeFormer or GFPGAN which can
    reconstruct facial features from blurry or masked inputs.

    Args:
        image_input: Path to image file or raw bytes.
        strength: Fidelity weight (usually 0 to 1).

    Returns:
        Restored image bytes if successful, None otherwise.
    """
    try:
        if isinstance(image_input, str):
            with open(image_input, "rb") as f:
                image_bytes = f.read()
        else:
            image_bytes = image_input

        # Encode for JSON transport
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                FACE_RESTORATION_URL,
                json={
                    "image": encoded_image,
                    "fidelity": strength,
                    "task": "face_restoration",
                },
                timeout=60.0,  # AI inference can be slow
            )

            if response.status_code == 200:
                result = response.json()
                if "image" in result:
                    return base64.b64decode(result["image"])

            logging.error(f"AI Service error: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Failed to call face restoration service: {e}")

    return None


def preprocess_for_ai(image_bytes: bytes, max_size: int = 1024) -> bytes:
    """
    Standardizes image size and format before sending to AI processing.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (remove Alpha channel)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if too large to save bandwidth/VRAM
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()
    except Exception as e:
        logging.warning(f"Preprocessing failed: {e}")
        return image_bytes


def image_to_base64_uri(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Helper to convert bytes to a browser-ready Data URI."""
    base64_str = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_str}"
