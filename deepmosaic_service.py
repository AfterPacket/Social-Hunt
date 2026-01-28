# deepmosaic_service.py
import subprocess
import json
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
import uuid
import asyncio
from fastapi import HTTPException

class DeepMosaicService:
    def __init__(self, deepmosaic_path: str = None):
        # Path to the DeepMosaic module
        if deepmosaic_path is None:
            # Try to auto-detect the path
            possible_paths = [
                "DeepMosaics/deepmosaic.py",
                "../DeepMosaics/deepmosaic.py",
                "./DeepMosaics/deepmosaic.py"
            ]
            for path in possible_paths:
                if Path(path).exists():
                    deepmosaic_path = path
                    break
        
        if not deepmosaic_path or not Path(deepmosaic_path).exists():
            raise FileNotFoundError(f"DeepMosaic module not found at {deepmosaic_path}")
        
        self.deepmosaic_path = deepmosaic_path
        self.results_dir = Path("data/deepmosaic_results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    async def process_image(
        self,
        input_path: str,
        mode: str = "clean",
        mosaic_type: str = "squa_avg",
        quality: str = "medium",
        output_format: str = "png"
    ) -> Dict[str, Any]:
        """Process a single image with DeepMosaic"""
        try:
            # Generate unique output filename
            job_id = str(uuid.uuid4())
            output_path = self.results_dir / f"{job_id}.{output_format}"
            
            # Build command based on parameters
            cmd = [
                "python", self.deepmosaic_path,
                "--media_path", input_path,
                "--mode", mode,
                "--result_dir", str(self.results_dir),
                "--temp_dir", "/tmp/deepmosaic_temp",
                "--no_preview"
            ]
            
            # Add mode-specific parameters
            if mode == "add":
                cmd.extend(["--mosaic_mod", mosaic_type])
                # Adjust quality settings
                if quality == "high":
                    cmd.extend(["--mask_extend", "5"])  # More precise
                elif quality == "low":
                    cmd.extend(["--mask_extend", "20"])  # Faster
                else:  # medium
                    cmd.extend(["--mask_extend", "10"])
            
            elif mode == "clean":
                if quality == "high":
                    cmd.extend(["--traditional"])  # Use traditional for high quality
                elif quality == "low":
                    cmd.extend(["--tr_blur", "15", "--tr_down", "15"])  # Faster processing
                else:  # medium
                    cmd.extend(["--tr_blur", "10", "--tr_down", "10"])
            
            elif mode == "style":
                cmd.extend(["--model_path", "./pretrained_models/style/style_monet.pth"])
                if quality == "high":
                    cmd.extend(["--output_size", "1024"])
                elif quality == "low":
                    cmd.extend(["--output_size", "256"])
                else:  # medium
                    cmd.extend(["--output_size", "512"])
            
            # Run DeepMosaic
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"DeepMosaic failed: {stderr.decode()}")
            
            # Find the output file (DeepMosaic might name it differently)
            # Look for the most recent file in results directory
            output_files = list(self.results_dir.glob("*"))
            if output_files:
                latest_file = max(output_files, key=os.path.getmtime)
                output_path = latest_file
            
            return {
                "success": True,
                "job_id": job_id,
                "output_path": str(output_path),
                "stdout": stdout.decode(),
                "stderr": stderr.decode()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def process_video(
        self,
        input_path: str,
        mode: str = "clean",
        mosaic_type: str = "squa_avg",
        quality: str = "medium",
        start_time: str = "00:00:00",
        last_time: str = "00:00:00"
    ) -> Dict[str, Any]:
        """Process a video with DeepMosaic"""
        try:
            job_id = str(uuid.uuid4())
            output_dir = self.results_dir / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                "python", self.deepmosaic_path,
                "--media_path", input_path,
                "--mode", mode,
                "--result_dir", str(output_dir),
                "--temp_dir", "/tmp/deepmosaic_temp",
                "--start_time", start_time,
                "--last_time", last_time,
                "--no_preview"
            ]
            
            if mode == "add":
                cmd.extend(["--mosaic_mod", mosaic_type])
                if quality == "high":
                    cmd.extend(["--mask_extend", "5"])
                elif quality == "low":
                    cmd.extend(["--mask_extend", "20"])
                else:
                    cmd.extend(["--mask_extend", "10"])
            
            elif mode == "clean":
                if quality == "high":
                    cmd.extend(["--traditional"])
                elif quality == "low":
                    cmd.extend(["--tr_blur", "15", "--tr_down", "15"])
                else:
                    cmd.extend(["--tr_blur", "10", "--tr_down", "10"])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"DeepMosaic failed: {stderr.decode()}")
            
            # Find output video
            output_videos = list(output_dir.glob("*.mp4"))
            if not output_videos:
                output_videos = list(output_dir.glob("*.avi"))
            
            if output_videos:
                output_path = output_videos[0]
            else:
                raise Exception("No output video found")
            
            return {
                "success": True,
                "job_id": job_id,
                "output_path": str(output_path),
                "stdout": stdout.decode(),
                "stderr": stderr.decode()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }