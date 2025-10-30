"""
S3 Image Service
Service để download và xử lý ảnh từ AWS S3
"""
import boto3
import base64
import logging
import os
from typing import Optional, Dict
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3ImageService:
    """
    Service để download ảnh từ S3 và convert sang base64
    """
    
    def __init__(self):
        """Initialize S3 client"""
        self.s3_client = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'recipe-images-bucket')
        self.max_image_size = int(os.getenv('MAX_IMAGE_SIZE_MB', '10')) * 1024 * 1024  # 10MB default
        
        logger.info(f"S3ImageService initialized with bucket: {self.bucket_name}")
    
    def download_image_as_base64(
        self, 
        s3_url: str,
        validate: bool = True
    ) -> Optional[Dict[str, str]]:

        try:
            # Parse S3 URL to get key
            key = self._parse_s3_key(s3_url)
            if not key:
                logger.error(f"Invalid S3 URL format: {s3_url}")
                return None
            
            logger.info(f"Downloading image from S3: {key}")
            
            # Download từ S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            # Get content type
            content_type = response.get('ContentType', 'application/octet-stream')
            
            # Read image bytes
            image_bytes = response['Body'].read()
            
            # Validate size
            if len(image_bytes) > self.max_image_size:
                logger.error(f"Image too large: {len(image_bytes)} bytes (max: {self.max_image_size})")
                return None
            
            # Detect mime type from file extension if not in metadata
            mime_type = self._get_mime_type(key, content_type)
            
            # Validate image content (optional)
            if validate and not self._validate_image(image_bytes):
                logger.error(f"Image validation failed for key: {key}")
                return None
            
            # Convert to base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            logger.info(f"Successfully downloaded image: {key} ({len(image_bytes)} bytes, {mime_type})")
            
            return {
                'data': image_b64,
                'mime_type': mime_type,
                'size': len(image_bytes),
                'key': key
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"Image not found in S3: {s3_url}")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to S3 object: {s3_url}")
            else:
                logger.error(f"S3 client error: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to download image from S3: {e}", exc_info=True)
            return None
    
    def get_image_metadata(self, s3_url: str) -> Dict[str, str]:
        try:
            key = self._parse_s3_key(s3_url)
            if not key:
                return {}
            
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            metadata = response.get('Metadata', {})
            metadata['ContentType'] = response.get('ContentType', '')
            metadata['ContentLength'] = response.get('ContentLength', 0)
            metadata['LastModified'] = str(response.get('LastModified', ''))
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get image metadata: {e}")
            return {}
    
    def check_image_exists(self, s3_url: str) -> bool:
        try:
            key = self._parse_s3_key(s3_url)
            if not key:
                return False
            
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
            
        except ClientError:
            return False
    
    def _parse_s3_key(self, s3_url: str) -> Optional[str]:
        if not s3_url:
            return None
        
        # Format 1: HTTPS URL
        if s3_url.startswith('http'):
            try:
                parts = s3_url.split('.amazonaws.com/')
                if len(parts) == 2:
                    return parts[1]
            except:
                pass
        
        # Format 2: S3 URI
        elif s3_url.startswith('s3://'):
            try:
                parts = s3_url.replace('s3://', '').split('/', 1)
                if len(parts) == 2:
                    return parts[1]
            except:
                pass

        else:
            return s3_url
        
        logger.error(f"Could not parse S3 key from URL: {s3_url}")
        return None
    
    def _get_mime_type(self, key: str, content_type: str) -> str:

        # Nếu content_type đã có và hợp lệ, dùng luôn
        if content_type and content_type != 'application/octet-stream':
            return content_type
        
        # Map extension -> MIME type
        extension_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.svg': 'image/svg+xml',
        }
        
        # Get extension từ key
        key_lower = key.lower()
        for ext, mime in extension_map.items():
            if key_lower.endswith(ext):
                return mime
        
        # Default
        return 'image/jpeg'
    
    def _validate_image(self, image_bytes: bytes) -> bool:

        try:
            # Check if PIL is available
            try:
                from PIL import Image
                import io
                
                # Try to open image
                img = Image.open(io.BytesIO(image_bytes))
                
                # Check dimensions
                max_dimension = 4096
                if img.width > max_dimension or img.height > max_dimension:
                    logger.warning(f"Image dimensions too large: {img.width}x{img.height}")
                    return False
                
                # Check format
                allowed_formats = ['JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF']
                if img.format not in allowed_formats:
                    logger.warning(f"Image format not supported: {img.format}")
                    return False
                
                return True
                
            except ImportError:
                logger.warning("PIL not available, skipping image validation")
                return True
            
        except Exception as e:
            logger.error(f"Image validation error: {e}")
            return False


# Singleton instance
_s3_image_service = None

def get_s3_image_service() -> S3ImageService:
    """Get singleton instance of S3ImageService"""
    global _s3_image_service
    if _s3_image_service is None:
        _s3_image_service = S3ImageService()
    return _s3_image_service
