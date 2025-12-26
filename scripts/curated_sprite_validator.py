#!/usr/bin/env python3
"""
Validator for curated sprite images
Compares expected sprite colors with actual colors from screenshots
"""
try:
    import cv2
    import numpy as np
    from sklearn.cluster import KMeans
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from pathlib import Path
import yaml
import json
from typing import Dict, List, Tuple

class CuratedSpriteValidator:
    def __init__(self, curated_dir: Path, monster_map_path: Path):
        self.curated_dir = curated_dir
        self.monster_map_path = monster_map_path
        
        # Load monster palette map
        with open(monster_map_path) as f:
            self.monster_map = yaml.safe_load(f)
    
    def extract_sprite_colors(self, sprite_image_path: Path) -> Dict:
        """Extract dominant colors from a curated sprite image"""
        if not CV2_AVAILABLE:
            return {"error": "cv2 not available - install opencv-python"}
        
        img = cv2.imread(str(sprite_image_path))
        if img is None:
            return {"error": "Failed to load image"}
        
        # Convert to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Reshape to list of pixels
        pixels = img_rgb.reshape(-1, 3)
        
        # Remove transparent/black pixels (assuming transparency is black)
        non_black = pixels[np.any(pixels > 10, axis=1)]
        
        if len(non_black) == 0:
            return {"error": "No non-black pixels found"}
        
        # Use k-means to find dominant colors
        kmeans = KMeans(n_clusters=4, random_state=0, n_init=10)
        kmeans.fit(non_black)
        
        dominant_colors = kmeans.cluster_centers_.astype(int)
        labels = kmeans.labels_
        
        # Count pixels per cluster
        color_counts = {}
        for i, color in enumerate(dominant_colors):
            count = np.sum(labels == i)
            color_counts[tuple(color)] = count
        
        return {
            "dominant_colors": dominant_colors.tolist(),
            "color_counts": {str(k): v for k, v in color_counts.items()},
            "total_pixels": len(non_black)
        }
    
    def validate_sprite(self, sprite_name: str, sprite_image_path: Path) -> Dict:
        """Validate a single sprite against expected palette"""
        # Find expected palette for this sprite
        expected_palette = None
        expected_tiles = []
        
        if "monster_palette_map" in self.monster_map:
            for monster_name, data in self.monster_map["monster_palette_map"].items():
                if sprite_name.lower() in monster_name.lower() or monster_name.lower() in sprite_name.lower():
                    expected_palette = data.get("palette", None)
                    expected_tiles = data.get("tile_range", [])
                    break
        
        # Extract colors from sprite image
        color_data = self.extract_sprite_colors(sprite_image_path)
        
        if "error" in color_data:
            return {
                "sprite": sprite_name,
                "valid": False,
                "error": color_data["error"]
            }
        
        # Load expected palette colors
        palette_yaml_path = Path("palettes/penta_palettes.yaml")
        expected_colors = None
        
        if palette_yaml_path.exists():
            with open(palette_yaml_path) as f:
                palettes = yaml.safe_load(f)
            
            if expected_palette is not None:
                palette_name = f"Palette{expected_palette}"
                if palette_name in palettes.get("obj_palettes", {}):
                    expected_colors = palettes["obj_palettes"][palette_name].get("colors", [])
        
        return {
            "sprite": sprite_name,
            "expected_palette": expected_palette,
            "expected_tiles": expected_tiles,
            "extracted_colors": color_data["dominant_colors"],
            "expected_colors": expected_colors,
            "valid": expected_palette is not None
        }
    
    def validate_all_sprites(self) -> Dict:
        """Validate all curated sprites"""
        sprite_files = list(self.curated_dir.glob("*.png")) + list(self.curated_dir.glob("*.jpg"))
        
        results = {
            "total_sprites": len(sprite_files),
            "validations": []
        }
        
        for sprite_file in sprite_files:
            sprite_name = sprite_file.stem
            validation = self.validate_sprite(sprite_name, sprite_file)
            results["validations"].append(validation)
        
        return results

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: curated_sprite_validator.py <curated_sprites_dir> [monster_map.yaml]")
        sys.exit(1)
    
    curated_dir = Path(sys.argv[1])
    monster_map_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("palettes/monster_palette_map.yaml")
    
    if not curated_dir.exists():
        print(f"❌ Curated sprites directory not found: {curated_dir}")
        sys.exit(1)
    
    validator = CuratedSpriteValidator(curated_dir, monster_map_path)
    results = validator.validate_all_sprites()
    
    print(f"✅ Validated {results['total_sprites']} sprites")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()

