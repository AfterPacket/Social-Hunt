from __future__ import annotations

import io
import logging
from typing import List, Optional, Tuple

try:
    import face_recognition
    _FACE_RECOGNITION_AVAILABLE = True
except BaseException:
    face_recognition = None  # type: ignore[assignment]
    _FACE_RECOGNITION_AVAILABLE = False
import httpx
try:
    import imagehash
    from PIL import Image
    from PIL import UnidentifiedImageError as PILUnidentifiedImageError
    _IMAGING_AVAILABLE = True
except BaseException:
    imagehash = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]
    PILUnidentifiedImageError = Exception  # type: ignore[assignment]
    _IMAGING_AVAILABLE = False

from ..addons_base import BaseAddon
from ..rate_limit import HostRateLimiter
from ..types import ProviderResult
from .net_safety import UnsafeURLError, safe_fetch_bytes


class FaceMatcherAddon(BaseAddon):
    """
    Downloads avatar URLs and compares them against a target face.
    """

    name = "face_matcher"

    def __init__(
        self,
        *,
        target_image_paths: List[str],
        max_bytes: int = 2_000_000,
        timeout: float = 10.0,
        hash_threshold: int = 10,
    ) -> None:
        self.max_bytes = int(max_bytes)
        self.timeout = float(timeout)
        self.target_image_paths = target_image_paths
        self.hash_threshold = int(hash_threshold)
        self.target_encodings, self.target_hashes = self._load_target_data()

    def _load_target_data(self) -> Tuple[List, List]:
        """Load both face encodings and image hashes from target images."""
        encodings = []
        hashes = []
        for image_path in self.target_image_paths:
            try:
                # Load for face recognition
                image = face_recognition.load_image_file(image_path)
                face_encodings_list = face_recognition.face_encodings(image)

                # Load for image hashing
                pil_image = Image.open(image_path)
                img_hash = imagehash.average_hash(pil_image)
                hashes.append(img_hash)

                if face_encodings_list:
                    encoding = face_encodings_list[0]
                    encodings.append(encoding)
                else:
                    logging.info(
                        f"No face detected in target image '{image_path}', "
                        f"will use image hash matching only"
                    )

            except (FileNotFoundError, PILUnidentifiedImageError) as e:
                logging.warning(f"Could not process target image '{image_path}': {e}")

        if not encodings and not hashes:
            logging.error("No usable target images loaded (no faces or hashes)")
        elif encodings and hashes:
            logging.info(
                f"Loaded {len(encodings)} face encodings and {len(hashes)} image hashes"
            )
        elif hashes:
            logging.info(f"Loaded {len(hashes)} image hashes (no faces detected)")

        return encodings, hashes

    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: HostRateLimiter | None = None,
    ) -> None:
        if not self.target_encodings and not self.target_hashes:
            # If we failed to load any target data, add an error to every result
            # so the user gets feedback in the UI.
            for r in results:
                prof = r.profile or {}
                prof["face_match_error"] = (
                    "Could not load any usable target images for comparison."
                )
                r.profile = prof
            return

        for r in results:
            prof = r.profile or {}
            avatar_url = prof.get("avatar_url")
            if not isinstance(avatar_url, str) or not avatar_url.strip():
                continue

            try:
                host = (httpx.URL(avatar_url).host or "").lower()
            except Exception:
                host = ""

            if host.endswith(".onion"):
                prof["face_match"] = {"match": False, "reason": "skipped_onion"}
                r.profile = prof
                continue

            try:
                if limiter:
                    await limiter.wait(avatar_url)

                content, _ = await safe_fetch_bytes(
                    client,
                    avatar_url,
                    timeout=self.timeout,
                    max_bytes=self.max_bytes,
                    accept_prefix="image",
                )

                # Try face matching first if we have target face encodings
                face_matched = False
                if self.target_encodings:
                    avatar_image = face_recognition.load_image_file(io.BytesIO(content))
                    avatar_encodings = face_recognition.face_encodings(avatar_image)

                    if avatar_encodings:
                        # For simplicity, use the first face found in the avatar
                        avatar_encoding = avatar_encodings[0]

                        # Compare with target faces
                        matches = face_recognition.compare_faces(
                            self.target_encodings, avatar_encoding
                        )

                        if any(matches):
                            prof["face_match"] = {
                                "match": True,
                                "method": "face_recognition",
                            }
                            face_matched = True

                # If no face match, try image hash matching
                if not face_matched and self.target_hashes:
                    pil_image = Image.open(io.BytesIO(content))
                    avatar_hash = imagehash.average_hash(pil_image)

                    # Compare with target image hashes
                    for target_hash in self.target_hashes:
                        hash_diff = avatar_hash - target_hash
                        if hash_diff <= self.hash_threshold:
                            prof["face_match"] = {
                                "match": True,
                                "method": "image_hash",
                                "hash_difference": hash_diff,
                            }
                            face_matched = True
                            break

                # Set result
                if not face_matched:
                    prof["face_match"] = {"match": False, "reason": "no_match"}

                r.profile = prof

            except (UnsafeURLError, httpx.HTTPError, OSError, IndexError) as e:
                prof["face_match"] = {"match": False, "reason": f"error: {e}"}
                r.profile = prof


# TODO: This addon is not yet integrated into the CLI or API.
# To use it, you need to manually add it to the list of addons in the engine.
# For now, we will not be adding it to the ADDONS list.
ADDONS = []
