from comfy.cli_args import args
import folder_paths
import json
import numpy
import os
from PIL import Image, ExifTags, ImageDraw, ImageFont, ImageFilter
from PIL.PngImagePlugin import PngInfo
import math

class Apoloniscope:
    def __init__(self):
        pass

    FILE_TYPE_PNG = "PNG"
    FILE_TYPE_JPEG = "JPEG"
    FILE_TYPE_WEBP_LOSSLESS = "WEBP (lossless)"
    FILE_TYPE_WEBP_LOSSY = "WEBP (lossy)"
    FILE_TYPE_TIFF = "TIFF (lossless)"
    
    TILE_RESOLUTIONS = ["64x64", "128x128", "192x192", "256x256", "320x320", "384x384", "448x448", "512x512"]
    
    EDGE_EFFECTS = ["None", "Blur", "Fade", "Vignette", "Sharpen", "Emboss"]
    
    RETURN_TYPES = ()
    FUNCTION = "save_tiled_images"
    OUTPUT_NODE = True
    CATEGORY = "image"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", ),
                "filename_prefix": ("STRING", {"default": "ComfyUI"}),
                "file_type": ([s.FILE_TYPE_PNG, s.FILE_TYPE_JPEG, s.FILE_TYPE_WEBP_LOSSLESS, s.FILE_TYPE_WEBP_LOSSY, s.FILE_TYPE_TIFF], ),
                "remove_metadata": ("BOOLEAN", {"default": False}),
                "tile_resolution": (s.TILE_RESOLUTIONS, {"default": "256x256"}),
                "edge_feather": ("INT", {"default": 0, "min": 0, "max": 100, "step": 1}),
                "edge_effect": (s.EDGE_EFFECTS, {"default": "None"}),
            },
            "optional": {
                "tile_selection": ("STRING", {"default": "all"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    def create_tiles(self, image, tile_resolution):
        width, height = image.size
        
        # Parse tile resolution
        tile_width, tile_height = map(int, tile_resolution.split('x'))
        
        # Calculate number of tiles in each dimension
        num_tiles_x = math.ceil(width / tile_width)
        num_tiles_y = math.ceil(height / tile_height)
        
        tiles = []
        tile_positions = []
        tile_numbers = []
        
        # Create tiles
        tile_number = 1
        for y in range(num_tiles_y):
            for x in range(num_tiles_x):
                left = x * tile_width
                upper = y * tile_height
                right = min((x + 1) * tile_width, width)
                lower = min((y + 1) * tile_height, height)
                
                # Crop the tile from the original image (without any overlay numbers)
                tile = image.crop((left, upper, right, lower))
                
                tiles.append(tile)
                tile_positions.append((left, upper))
                tile_numbers.append(tile_number)
                tile_number += 1
        
        return tiles, tile_positions, tile_numbers, num_tiles_x, num_tiles_y

    def create_preview_image(self, original_image, tile_positions, tile_numbers, tile_resolution):
        """Creates a preview image with tile grid and numbers overlay"""
        preview_img = original_image.copy()
        preview_draw = ImageDraw.Draw(preview_img)
        
        # Try to get a font, or use default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()
            
        # Draw grid lines
        width, height = original_image.size
        tile_width, tile_height = map(int, tile_resolution.split('x'))
        
        # Draw horizontal lines
        for y in range(0, height, tile_height):
            preview_draw.line([(0, y), (width, y)], fill="white", width=1)
            
        # Draw vertical lines
        for x in range(0, width, tile_width):
            preview_draw.line([(x, 0), (x, height)], fill="white", width=1)
            
        # Draw tile numbers
        for position, number in zip(tile_positions, tile_numbers):
            x, y = position
            text = str(number)
            
            # Get text dimensions - handle different Pillow versions
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(text)
                textwidth, textheight = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                # Fallback for older Pillow versions or when getbbox isn't available
                textwidth, textheight = len(text) * 10, 20
            
            text_x = x + (tile_width - textwidth) // 2
            text_y = y + (tile_height - textheight) // 2
            
            # Draw with outline for better visibility
            preview_draw.text((text_x-1, text_y-1), text, font=font, fill="black")
            preview_draw.text((text_x+1, text_y-1), text, font=font, fill="black")
            preview_draw.text((text_x-1, text_y+1), text, font=font, fill="black")
            preview_draw.text((text_x+1, text_y+1), text, font=font, fill="black")
            preview_draw.text((text_x, text_y), text, font=font, fill="white")
            
        return preview_img

    def apply_edge_effect(self, tile, edge_feather, edge_effect):
        if edge_feather <= 0 and edge_effect == "None":
            return tile
        
        width, height = tile.size
        
        # Create a mask for feathering
        mask = Image.new('L', (width, height), 255)
        draw = ImageDraw.Draw(mask)
        
        # Draw a gradient for the feathering
        if edge_feather > 0:
            for i in range(edge_feather):
                # Draw rectangle with decreasing opacity from center to edges
                value = int(255 * (1 - i / edge_feather))
                draw.rectangle(
                    (i, i, width - i - 1, height - i - 1),
                    outline=value
                )
        
        # Apply the selected edge effect
        if edge_effect == "Blur":
            blurred = tile.filter(ImageFilter.GaussianBlur(radius=edge_feather/10))
            result = Image.composite(tile, blurred, mask)
        elif edge_effect == "Fade":
            black = Image.new('RGB', tile.size, (0, 0, 0))
            result = Image.composite(tile, black, mask)
        elif edge_effect == "Vignette":
            # Create a radial gradient mask
            center_x, center_y = width // 2, height // 2
            max_dist = math.sqrt(center_x**2 + center_y**2)
            vignette_mask = Image.new('L', (width, height))
            for y in range(height):
                for x in range(width):
                    dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                    # Normalize distance and apply fade
                    opacity = int(255 * (1 - min(1, dist / max_dist * edge_feather / 50)))
                    vignette_mask.putpixel((x, y), opacity)
            black = Image.new('RGB', tile.size, (0, 0, 0))
            result = Image.composite(tile, black, vignette_mask)
        elif edge_effect == "Sharpen":
            sharpened = tile.filter(ImageFilter.SHARPEN)
            result = Image.composite(sharpened, tile, mask.point(lambda x: 255 - x))
        elif edge_effect == "Emboss":
            embossed = tile.filter(ImageFilter.EMBOSS)
            result = Image.composite(embossed, tile, mask.point(lambda x: 255 - x))
        else:  # "None" or any other value
            result = tile
            
        return result

    def create_output_image(self, original_image, tiles, tile_positions, selected_tiles, edge_feather, edge_effect):
        width, height = original_image.size
        output = Image.new('RGB', (width, height), (0, 0, 0))  # Black background
        
        for i, (tile, position) in enumerate(zip(tiles, tile_positions)):
            tile_number = i + 1
            
            if tile_number in selected_tiles:
                # Apply edge effects to selected tiles
                processed_tile = self.apply_edge_effect(tile, edge_feather, edge_effect)
                output.paste(processed_tile, position)
        
        return output

    def parse_tile_selection(self, selection_str, total_tiles):
        if selection_str.lower() == "all":
            return list(range(1, total_tiles + 1))
        
        selected_tiles = []
        parts = selection_str.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Handle ranges like "1-5"
                start, end = map(int, part.split('-'))
                selected_tiles.extend(range(start, end + 1))
            else:
                # Handle single numbers
                try:
                    selected_tiles.append(int(part))
                except ValueError:
                    pass  # Ignore invalid entries
        
        # Ensure all tiles are within valid range
        return [t for t in selected_tiles if 1 <= t <= total_tiles]

    def save_tiled_images(self, images, filename_prefix="ComfyUI", file_type=FILE_TYPE_PNG, 
                         remove_metadata=False, tile_resolution="256x256", 
                         edge_feather=0, edge_effect="None", tile_selection="all",
                         prompt=None, extra_pnginfo=None):
        output_dir = folder_paths.get_output_directory()
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, output_dir, images[0].shape[1], images[0].shape[0])
        extension = {
            self.FILE_TYPE_PNG: "png",
            self.FILE_TYPE_JPEG: "jpg",
            self.FILE_TYPE_WEBP_LOSSLESS: "webp",
            self.FILE_TYPE_WEBP_LOSSY: "webp",
            self.FILE_TYPE_TIFF: "tiff",
        }.get(file_type, "png")

        results = []
        for image in images:
            # Convert the tensor to a PIL image
            array = 255. * image.cpu().numpy()
            img = Image.fromarray(numpy.clip(array, 0, 255).astype(numpy.uint8))
            
            # Create tiles from the image (without grid or numbers)
            tiles, tile_positions, tile_numbers, num_tiles_x, num_tiles_y = self.create_tiles(img, tile_resolution)
            
            # Create preview image with tile grid and numbers
            preview_img = self.create_preview_image(img, tile_positions, tile_numbers, tile_resolution)
            
            # Save the preview image
            preview_file = f"{filename}_{counter:05}_preview.{extension}"
            preview_img.save(os.path.join(full_output_folder, preview_file))
            results.append({
                "filename": preview_file,
                "subfolder": subfolder,
                "type": "output",
            })
            
            # Parse tile selection
            total_tiles = len(tiles)
            selected_tiles = self.parse_tile_selection(tile_selection, total_tiles)
            
            # Create and save the final output image
            output_img = self.create_output_image(img, tiles, tile_positions, selected_tiles, edge_feather, edge_effect)
            
            kwargs = dict()
            if extension == "png":
                kwargs["compress_level"] = 4
                if not remove_metadata and not args.disable_metadata:
                    metadata = PngInfo()
                    if prompt is not None:
                        metadata.add_text("prompt", json.dumps(prompt))
                    if extra_pnginfo is not None:
                        for x in extra_pnginfo:
                            metadata.add_text(x, json.dumps(extra_pnginfo[x]))
                    # Add tile information to metadata
                    tile_info = {
                        "tile_resolution": tile_resolution,
                        "selected_tiles": selected_tiles,
                        "total_tiles": total_tiles,
                        "edge_feather": edge_feather,
                        "edge_effect": edge_effect
                    }
                    metadata.add_text("apoloniscope_info", json.dumps(tile_info))
                    kwargs["pnginfo"] = metadata
            elif extension == "tiff":
                kwargs["compression"] = "tiff_lzw"  # LZW compression for lossless TIFF
                if not remove_metadata and not args.disable_metadata:
                    exif = output_img.getexif()
                    metadata = {}
                    if prompt is not None:
                        metadata["prompt"] = prompt
                    if extra_pnginfo is not None:
                        metadata.update(extra_pnginfo)
                    # Add tile information to metadata
                    tile_info = {
                        "tile_resolution": tile_resolution,
                        "selected_tiles": selected_tiles,
                        "total_tiles": total_tiles,
                        "edge_feather": edge_feather,
                        "edge_effect": edge_effect
                    }
                    metadata["apoloniscope_info"] = tile_info
                    exif[ExifTags.Base.UserComment] = json.dumps(metadata)
                    kwargs["exif"] = exif
            else:
                if file_type == self.FILE_TYPE_WEBP_LOSSLESS:
                    kwargs["lossless"] = True
                else:
                    kwargs["quality"] = 90
                if not remove_metadata and not args.disable_metadata:
                    metadata = {}
                    if prompt is not None:
                        metadata["prompt"] = prompt
                    if extra_pnginfo is not None:
                        metadata.update(extra_pnginfo)
                    # Add tile information to metadata
                    tile_info = {
                        "tile_resolution": tile_resolution,
                        "selected_tiles": selected_tiles,
                        "total_tiles": total_tiles,
                        "edge_feather": edge_feather,
                        "edge_effect": edge_effect
                    }
                    metadata["apoloniscope_info"] = tile_info
                    exif = output_img.getexif()
                    exif[ExifTags.Base.UserComment] = json.dumps(metadata)
                    kwargs["exif"] = exif.tobytes()

            output_file = f"{filename}_{counter:05}_tiles.{extension}"
            output_img.save(os.path.join(full_output_folder, output_file), **kwargs)
            results.append({
                "filename": output_file,
                "subfolder": subfolder,
                "type": "output",
            })
            
            # If individual tiles are selected, save them separately
            if selected_tiles and selected_tiles != list(range(1, total_tiles + 1)):
                for tile_num in selected_tiles:
                    if 1 <= tile_num <= total_tiles:
                        idx = tile_num - 1
                        tile = tiles[idx]
                        processed_tile = self.apply_edge_effect(tile, edge_feather, edge_effect)
                        
                        tile_file = f"{filename}_{counter:05}_tile{tile_num}.{extension}"
                        processed_tile.save(os.path.join(full_output_folder, tile_file), **kwargs)
                        results.append({
                            "filename": tile_file,
                            "subfolder": subfolder,
                            "type": "output",
                        })
            
            counter += 1

        return { "ui": { "images": results } }

NODE_CLASS_MAPPINGS = {
    "Apoloniscope": Apoloniscope
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Apoloniscope": "Apoloniscope"
}

WEB_DIRECTORY = "web"